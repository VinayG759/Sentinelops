import { useQuery } from '@tanstack/react-query'
import { cn } from '@/lib/utils'
import { api } from '@/shared/api'
import { useTimeRange } from '@/shared/timeRange'

type IncidentStats = {
  minutes: number
  opened: number
  resolved: number
  closed_by_verified_fix: number
  median_seconds_to_root_cause: number | null
  median_seconds_to_resolve: number | null
  rollbacks: number
}

/**
 * Outcome numbers for incidents opened in the selected range. Computed by the backend from
 * the incident table and the event log. With nothing to measure, a tile says so ("—")
 * instead of showing a flattering zero.
 */
export function StatTiles() {
  const { minutes, refetchEvery, range } = useTimeRange()
  const stats = useQuery({
    queryKey: ['incident-stats', minutes],
    queryFn: () => api<IncidentStats>(`/api/incidents/stats?minutes=${minutes}`),
    refetchInterval: refetchEvery(30_000),
    placeholderData: (previous) => previous,
  })

  if (stats.isError) {
    return (
      <div className="panel px-4 py-6 text-[12px] text-muted-foreground">
        Could not load outcome numbers: {stats.error.message}
      </div>
    )
  }

  const s = stats.data
  const none = !s || s.opened === 0
  const tiles: { label: string; value: string; detail: string }[] = [
    {
      label: 'Incidents',
      value: s ? String(s.opened) : '–',
      detail: !s ? '' : s.opened ? `${s.resolved} resolved` : `none opened in the last ${range.label}`,
    },
    {
      label: 'Time to root cause',
      value: duration(s?.median_seconds_to_root_cause),
      detail: 'median · detection → evidence-backed diagnosis',
    },
    {
      label: 'Time to resolve',
      value: duration(s?.median_seconds_to_resolve),
      detail: 'median · detection → incident closed',
    },
    {
      label: 'Closed by a verified fix',
      value: none || !s.resolved ? '—' : `${s.closed_by_verified_fix} of ${s.resolved}`,
      detail: 'approved change, recovery confirmed by metrics',
    },
    {
      label: 'Fixes rolled back',
      value: s ? String(s.rollbacks) : '–',
      detail: 'recovery not confirmed → change undone',
    },
  ]

  return (
    <div
      className={cn(
        'grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 transition-opacity',
        stats.isPlaceholderData && 'opacity-60',
      )}
    >
      {tiles.map((tile) => (
        <div key={tile.label} className="panel px-4 py-3.5">
          <div className="text-[11.5px] text-muted-foreground">{tile.label}</div>
          <div className="mt-1.5 text-[22px] font-semibold leading-none tracking-tight">
            {stats.isLoading ? <span className="text-muted-foreground">…</span> : tile.value}
          </div>
          <div className="mt-2 text-[11px] leading-snug text-muted-foreground">{tile.detail}</div>
        </div>
      ))}
    </div>
  )
}

function duration(seconds: number | null | undefined): string {
  if (seconds == null) return '—'
  if (seconds < 90) return `${Math.round(seconds)}s`
  if (seconds < 3600) {
    const m = Math.floor(seconds / 60)
    const s = Math.round(seconds % 60)
    return s ? `${m}m ${s}s` : `${m}m`
  }
  const h = Math.floor(seconds / 3600)
  return `${h}h ${Math.round((seconds % 3600) / 60)}m`
}
