import { useQueryClient } from '@tanstack/react-query'
import { Clock, Pause, Radio, RotateCw } from 'lucide-react'
import { cn } from '@/lib/utils'
import { RANGES, useTimeRange } from '@/shared/timeRange'

/** Top-bar control: the time window every chart shows, and whether the data keeps polling. */
export function TimeRangePicker() {
  const { range, setRange, live, setLive } = useTimeRange()
  const queryClient = useQueryClient()

  return (
    <div className="flex items-center gap-1.5">
      <div className="flex items-center gap-0.5 rounded-lg border border-hairline p-0.5" role="group" aria-label="Time range">
        <Clock className="mx-1 size-3 text-muted-foreground" />
        {RANGES.map((r) => (
          <button
            key={r.key}
            onClick={() => setRange(r.key)}
            aria-pressed={range.key === r.key}
            className={cn(
              'rounded-md px-2 py-1 font-mono text-[11px] transition-colors',
              range.key === r.key
                ? 'bg-white/[0.08] text-foreground'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {r.label}
          </button>
        ))}
      </div>

      <button
        onClick={() => setLive(!live)}
        title={live ? 'Live: charts refresh by themselves. Click to pause.' : 'Paused: click to resume live updates.'}
        className={cn(
          'flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11.5px] transition-colors',
          live ? 'border-hairline text-muted-foreground hover:text-foreground' : 'border-sev2/30 bg-sev2/10 text-sev2',
        )}
      >
        {live ? <Radio className="size-3" /> : <Pause className="size-3" />}
        {live ? 'Live' : 'Paused'}
      </button>

      <button
        onClick={() => queryClient.invalidateQueries()}
        title="Refresh now"
        aria-label="Refresh now"
        className="rounded-lg border border-hairline p-1.5 text-muted-foreground transition-colors hover:text-foreground"
      >
        <RotateCw className="size-3" />
      </button>
    </div>
  )
}
