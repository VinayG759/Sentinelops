import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { api } from '@/shared/api'
import { serviceColor } from '@/shared/serviceColors'
import { absoluteTime, relativeTime } from '@/shared/time'
import { useTimeRange } from '@/shared/timeRange'
import type { Incident } from '@/shared/types'
import { StatusDot, Tag, type Tone } from '@/shared/ui/primitives'
import { useLiveTable } from '@/shared/useLiveTable'
import { useMe } from '@/shared/useMe'
import { useTransition } from './api'

type Status = Incident['status']
type Severity = Incident['severity']

const STATUSES: { value: Status; label: string }[] = [
  { value: 'triggered', label: 'Triggered' },
  { value: 'acknowledged', label: 'Acknowledged' },
  { value: 'resolved', label: 'Resolved' },
]
const SEVERITIES: { value: Severity; label: string }[] = [
  { value: 'sev1', label: 'SEV1 · critical' },
  { value: 'sev2', label: 'SEV2 · major' },
  { value: 'sev3', label: 'SEV3 · minor' },
]
const severityTone: Record<Severity, Tone> = { sev1: 'sev1', sev2: 'sev2', sev3: 'sev3' }
const statusTone: Record<Status, Tone> = { triggered: 'sev1', acknowledged: 'sev2', resolved: 'muted' }

type Filters = { status: Set<Status>; severity: Set<Severity>; service: Set<string> | null }
const initialFilters = (): Filters => ({
  status: new Set(['triggered', 'acknowledged']),
  severity: new Set(['sev1', 'sev2', 'sev3']),
  service: null, // null = every service
})

/**
 * Incidents as a filterable table, like an observability "Problems" view: a facet rail on the
 * left, and one row per incident with the agent's root cause and how long it lasted.
 * Open incidents are always listed; resolved ones follow the global time range.
 */
export function IncidentsPage() {
  const { minutes, range } = useTimeRange()
  useLiveTable('incidents', ['incidents'])
  const incidents = useQuery({
    queryKey: ['incidents', 'table'],
    queryFn: () => api<Incident[]>('/api/incidents'),
  })
  const [filters, setFilters] = useState(initialFilters)
  const now = useNow(10_000)

  // Scope first (open always, resolved within range), then facet counts, then filters.
  const scoped = useMemo(
    () =>
      (incidents.data ?? []).filter(
        (i) => i.status !== 'resolved' || now - new Date(i.opened_at).getTime() <= minutes * 60_000,
      ),
    [incidents.data, minutes, now],
  )
  const services = useMemo(() => [...new Set(scoped.map((i) => i.service))].sort(), [scoped])
  const visible = scoped.filter(
    (i) =>
      filters.status.has(i.status) &&
      filters.severity.has(i.severity) &&
      (filters.service === null || filters.service.has(i.service)),
  )
  const longest = Math.max(1, ...visible.map((i) => durationMs(i, now)))

  const count = (pick: (i: Incident) => boolean) => scoped.filter(pick).length
  const toggle = <K extends 'status' | 'severity'>(key: K, value: Filters[K] extends Set<infer V> ? V : never) =>
    setFilters((f) => {
      const next = new Set(f[key] as Set<typeof value>)
      if (next.has(value)) next.delete(value)
      else next.add(value)
      return { ...f, [key]: next }
    })
  const toggleService = (name: string) =>
    setFilters((f) => {
      const next = new Set(f.service ?? services)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return { ...f, service: next.size === services.length ? null : next }
    })

  return (
    <div className="mx-auto max-w-[1400px]">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">Incidents</h1>
        <p className="text-[12px] text-muted-foreground">
          Detected from live metrics every 15 seconds. Open incidents are always listed; resolved
          ones from the last {range.label}.
        </p>
      </div>

      <div className="mt-4 grid items-start gap-5 lg:grid-cols-[200px_1fr]">
        <aside className="space-y-5 lg:sticky lg:top-20">
          <Facet title="Status">
            {STATUSES.map((s) => (
              <Check
                key={s.value}
                label={s.label}
                count={count((i) => i.status === s.value)}
                checked={filters.status.has(s.value)}
                onChange={() => toggle('status', s.value)}
              />
            ))}
          </Facet>
          <Facet title="Severity">
            {SEVERITIES.map((s) => (
              <Check
                key={s.value}
                label={s.label}
                count={count((i) => i.severity === s.value)}
                checked={filters.severity.has(s.value)}
                onChange={() => toggle('severity', s.value)}
              />
            ))}
          </Facet>
          <Facet title="Service">
            {services.length === 0 && <p className="text-[11.5px] text-muted-foreground">No services yet</p>}
            {services.map((name) => (
              <Check
                key={name}
                label={name}
                mono
                swatch={serviceColor(name)}
                count={count((i) => i.service === name)}
                checked={filters.service === null || filters.service.has(name)}
                onChange={() => toggleService(name)}
              />
            ))}
          </Facet>
          <button
            onClick={() => setFilters(initialFilters())}
            className="text-[11.5px] text-signal underline-offset-4 hover:underline"
          >
            Reset filters
          </button>
        </aside>

        <div className="min-w-0">
          {incidents.isError ? (
            <p className="text-sev1">Could not load incidents: {incidents.error.message}</p>
          ) : incidents.isLoading ? (
            <div className="panel h-48 animate-pulse" />
          ) : visible.length === 0 ? (
            <EmptyState filtered={scoped.length > 0} onlyOpen={filters.status.has('triggered')} />
          ) : (
            <div className="panel overflow-x-auto">
              <table className="w-full min-w-[900px] text-left">
                <thead>
                  <tr className="border-b border-hairline text-[10.5px] uppercase tracking-wider text-muted-foreground">
                    <th className="w-[92px] py-2.5 pl-4 font-normal">Severity</th>
                    <th className="font-normal">Incident</th>
                    <th className="w-[150px] font-normal">Service</th>
                    <th className="font-normal">Root cause</th>
                    <th className="w-[112px] font-normal">Status</th>
                    <th className="w-[84px] font-normal">Started</th>
                    <th className="w-[150px] pr-4 font-normal">Duration</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-hairline">
                  {visible.map((incident) => (
                    <IncidentRow key={incident.id} incident={incident} now={now} longest={longest} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {visible.length > 0 && (
            <p className="mt-2 text-[11px] text-muted-foreground">
              {visible.length} of {scoped.length} incidents · bars compare durations within this list
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

function IncidentRow({ incident, now, longest }: { incident: Incident; now: number; longest: number }) {
  const { can } = useMe()
  const transition = useTransition()
  const open = incident.status !== 'resolved'
  const ms = durationMs(incident, now)

  return (
    <tr className="group align-top transition-colors hover:bg-white/[0.02]">
      <td className="py-3 pl-4">
        <Tag tone={severityTone[incident.severity]}>
          <StatusDot tone={severityTone[incident.severity]} live={incident.status === 'triggered'} />
          {incident.severity}
        </Tag>
      </td>
      <td className="py-3 pr-4">
        <Link to={`/incidents/${incident.id}`} className="font-medium hover:text-signal">
          {incident.title}
        </Link>
        <div className="mt-0.5 flex items-center gap-2 font-mono text-[10.5px] text-muted-foreground">
          <span>{incident.signal}</span>
          <span className="opacity-60">{incident.id.slice(0, 8)}</span>
          {can('responder') && open && (
            <span className="ml-1 flex gap-1 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
              {incident.status === 'triggered' && (
                <Button
                  size="xs"
                  variant="outline"
                  disabled={transition.isPending}
                  onClick={() => transition.mutate({ id: incident.id, to: 'acknowledge' })}
                >
                  Acknowledge
                </Button>
              )}
              <Button
                size="xs"
                variant="ghost"
                disabled={transition.isPending}
                onClick={() => transition.mutate({ id: incident.id, to: 'resolve' })}
              >
                Resolve
              </Button>
            </span>
          )}
        </div>
      </td>
      <td className="py-3 pr-4">
        <span className="flex items-center gap-1.5 font-mono text-[11.5px]">
          <span className="h-0.5 w-3 shrink-0 rounded-full" style={{ background: serviceColor(incident.service) }} />
          {incident.service}
        </span>
      </td>
      <td className="max-w-[380px] py-3 pr-4 text-[12px]">
        <RootCause incident={incident} />
      </td>
      <td className="py-3">
        <Tag tone={statusTone[incident.status]}>{incident.status}</Tag>
      </td>
      <td className="py-3 font-mono text-[11px] text-muted-foreground" title={absoluteTime(incident.opened_at)}>
        {relativeTime(incident.opened_at, now)}
      </td>
      <td className="py-3 pr-4">
        <div className="font-mono text-[11.5px]">
          {formatDuration(ms)}
          {open && <span className="ml-1 text-muted-foreground">· ongoing</span>}
        </div>
        <div className="mt-1.5 h-1 w-full rounded-full bg-white/[0.05]">
          <div
            className={cn('h-1 rounded-full', open ? 'bg-foreground/60' : 'bg-foreground/30')}
            style={{ width: `${Math.max(3, (ms / longest) * 100)}%` }}
          />
        </div>
      </td>
    </tr>
  )
}

function RootCause({ incident }: { incident: Incident }) {
  if (incident.root_cause) {
    return (
      <div title={incident.root_cause}>
        <p className="line-clamp-2 text-foreground/85">{firstSentence(incident.root_cause)}</p>
        {incident.root_cause_confidence && (
          <span className="font-mono text-[10.5px] text-muted-foreground">
            {incident.root_cause_confidence} confidence
          </span>
        )}
      </div>
    )
  }
  if (incident.investigation_failed_reason) {
    return (
      <div>
        <Tag tone="sev2">no diagnosis</Tag>
        <p className="mt-1 text-[11.5px] text-muted-foreground">
          Investigation stopped: {incident.investigation_failed_reason}
        </p>
      </div>
    )
  }
  return (
    <span className="text-muted-foreground">
      {incident.status === 'resolved' ? '—' : 'Investigating…'}
    </span>
  )
}

function Facet({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <fieldset>
      <legend className="mb-1.5 text-[10.5px] uppercase tracking-wider text-muted-foreground">{title}</legend>
      <div className="space-y-0.5">{children}</div>
    </fieldset>
  )
}

function Check({
  label,
  count,
  checked,
  onChange,
  mono,
  swatch,
}: {
  label: string
  count: number
  checked: boolean
  onChange: () => void
  mono?: boolean
  swatch?: string
}) {
  return (
    <label className="flex cursor-pointer items-center gap-2 rounded-md px-1.5 py-1 text-[12px] hover:bg-white/[0.03]">
      <input type="checkbox" checked={checked} onChange={onChange} className="size-3.5 accent-[var(--signal)]" />
      {swatch && <span className="h-0.5 w-3 shrink-0 rounded-full" style={{ background: swatch }} />}
      <span className={cn('flex-1 truncate', mono && 'font-mono text-[11.5px]', !checked && 'text-muted-foreground')}>
        {label}
      </span>
      <span className="font-mono text-[10.5px] text-muted-foreground">{count}</span>
    </label>
  )
}

function EmptyState({ filtered, onlyOpen }: { filtered: boolean; onlyOpen: boolean }) {
  return (
    <div className="panel px-6 py-16 text-center">
      <div className="mx-auto flex size-10 items-center justify-center rounded-full bg-ok/10 ring-1 ring-ok/25">
        <StatusDot tone="ok" className="size-2.5" />
      </div>
      <p className="mt-3 font-medium">
        {filtered ? 'No incidents match these filters' : onlyOpen ? 'All clear — no open incidents' : 'No incidents'}
      </p>
      {!filtered && (
        <p className="mt-1 text-[12px] text-muted-foreground">
          To see the agent work, break something in the{' '}
          <Link to="/simulator" className="text-signal underline-offset-4 hover:underline">
            Simulator
          </Link>{' '}
          — or press ⌘K.
        </p>
      )}
    </div>
  )
}

/** Re-render on an interval so "ongoing" durations and relative times keep moving. */
function useNow(everyMs: number) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), everyMs)
    return () => clearInterval(id)
  }, [everyMs])
  return now
}

function durationMs(incident: Incident, now: number) {
  const end = incident.resolved_at ? new Date(incident.resolved_at).getTime() : now
  return Math.max(0, end - new Date(incident.opened_at).getTime())
}

function formatDuration(ms: number) {
  const s = Math.round(ms / 1000)
  if (s < 90) return `${s}s`
  const m = Math.floor(s / 60)
  if (m < 90) return `${m}m ${s % 60}s`
  return `${Math.floor(m / 60)}h ${m % 60}m`
}

function firstSentence(text: string) {
  const match = text.match(/^.*?[.!?](\s|$)/)
  return match ? match[0].trim() : text
}
