import { useQuery } from '@tanstack/react-query'
import { RotateCw, X } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { cn } from '@/lib/utils'
import { api } from '@/shared/api'
import { serviceColor } from '@/shared/serviceColors'
import { relativeTime } from '@/shared/time'
import { useTimeRange } from '@/shared/timeRange'
import type { Incident } from '@/shared/types'
import { StatusDot, Tag, type Tone } from '@/shared/ui/primitives'

type Point = [number, number]
type Health = {
  name: string
  kind: string
  status: 'healthy' | 'degraded' | 'critical' | 'unknown'
  error_ratio: number | null
  requests_per_second: number | null
  p95_latency_ms: number | null
  pods_ready: number | null
  pods_desired: number | null
}
type Detail = {
  health: Health
  start: number
  end: number
  series: Record<string, Point[]>
  pool_max_per_pod: number | null
}
type Logs = { pod: string; lines: string[] }

const statusTone: Record<Health['status'], Tone> = {
  healthy: 'ok',
  degraded: 'sev2',
  critical: 'sev1',
  unknown: 'muted',
}
const percent = (v: number) => `${(v * 100).toFixed(v > 0 && v < 0.1 ? 1 : 0)}%`
const millis = (v: number) => (v >= 1000 ? `${Number((v / 1000).toFixed(1))} s` : `${Math.round(v)} ms`)
const perSecond = (v: number) => v.toFixed(1)
const count = (v: number) => String(Math.round(v))

type Tab = 'metrics' | 'logs' | 'incidents'

/**
 * Slide-over for one service: current health as chips, then its metrics, recent logs and
 * incidents. Everything is live data from Prometheus, Kubernetes and the incident table.
 */
export function ServicePanel({
  name,
  incidents,
  onClose,
}: {
  name: string | null
  incidents: Incident[]
  onClose: () => void
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <AnimatePresence>
      {name && (
        <>
          <motion.div
            key="backdrop"
            className="fixed inset-0 z-40 bg-black/40"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />
          <motion.aside
            key="panel"
            role="dialog"
            aria-label={`${name} details`}
            className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[600px] flex-col border-l border-hairline bg-background shadow-2xl"
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', damping: 32, stiffness: 320 }}
          >
            <PanelBody name={name} incidents={incidents.filter((i) => i.service === name)} onClose={onClose} />
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  )
}

function PanelBody({ name, incidents, onClose }: { name: string; incidents: Incident[]; onClose: () => void }) {
  const { minutes, range, refetchEvery } = useTimeRange()
  const [tab, setTab] = useState<Tab>('metrics')
  const detail = useQuery({
    queryKey: ['service-detail', name, minutes],
    queryFn: () => api<Detail>(`/api/topology/${name}?minutes=${minutes}`),
    refetchInterval: refetchEvery(15_000),
    placeholderData: (previous) => previous,
  })
  const h = detail.data?.health
  const open = incidents.filter((i) => i.status !== 'resolved')

  return (
    <>
      <header className="flex items-start justify-between gap-4 border-b border-hairline px-5 py-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="h-0.5 w-3.5 rounded-full" style={{ background: serviceColor(name) }} />
            <h2 className="font-mono text-[15px] font-medium">{name}</h2>
            {h && (
              <Tag tone={statusTone[h.status]}>
                <StatusDot tone={statusTone[h.status]} live={h.status !== 'healthy'} />
                {h.status}
              </Tag>
            )}
          </div>
          <p className="mt-0.5 text-[11.5px] text-muted-foreground">
            {h?.kind ?? 'service'} · last {range.label} · press Esc to close
          </p>
        </div>
        <button
          onClick={onClose}
          aria-label="Close"
          className="rounded-md p-1.5 text-muted-foreground hover:bg-white/[0.05] hover:text-foreground"
        >
          <X className="size-4" />
        </button>
      </header>

      <div className="flex flex-wrap gap-2 border-b border-hairline px-5 py-3">
        <Chip label="Error rate" value={h?.error_ratio != null ? percent(h.error_ratio) : '—'} tone={h ? statusTone[h.status] : 'muted'} />
        <Chip label="Requests" value={h?.requests_per_second != null ? `${perSecond(h.requests_per_second)}/s` : '—'} />
        <Chip label="p95" value={h?.p95_latency_ms != null ? millis(h.p95_latency_ms) : '—'} />
        <Chip
          label="Pods"
          value={h?.pods_desired != null ? `${h.pods_ready}/${h.pods_desired}` : '—'}
          tone={h && h.pods_desired != null && (h.pods_ready ?? 0) < h.pods_desired ? 'sev2' : 'muted'}
        />
        <Chip label="Open incidents" value={String(open.length)} tone={open.length ? 'sev1' : 'muted'} />
      </div>

      <nav className="flex gap-1 px-5 pt-3">
        {(['metrics', 'logs', 'incidents'] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              'rounded-md px-3 py-1.5 text-[12px] capitalize transition-colors',
              tab === t ? 'bg-white/[0.07] font-medium' : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {t}
            {t === 'incidents' && <span className="ml-1.5 font-mono text-[10.5px] text-muted-foreground">{incidents.length}</span>}
          </button>
        ))}
      </nav>

      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
        {tab === 'metrics' &&
          (detail.isError ? (
            <Problem text={`Could not load metrics: ${detail.error.message}`} />
          ) : detail.isLoading ? (
            <div className="h-64 animate-pulse rounded-lg bg-white/[0.02]" />
          ) : (
            <Metrics name={name} detail={detail.data!} dim={detail.isPlaceholderData} />
          ))}
        {tab === 'logs' && <LogsTab name={name} />}
        {tab === 'incidents' && <IncidentsTab incidents={incidents} />}
      </div>
    </>
  )
}

function Chip({ label, value, tone = 'muted' }: { label: string; value: string; tone?: Tone }) {
  const color = tone === 'sev1' ? 'text-sev1' : tone === 'sev2' ? 'text-sev2' : tone === 'ok' ? 'text-ok' : 'text-foreground'
  return (
    <div className="rounded-lg border border-hairline px-2.5 py-1.5">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className={cn('text-[13px] font-semibold', color)}>{value}</div>
    </div>
  )
}

function Metrics({ name, detail, dim }: { name: string; detail: Detail; dim: boolean }) {
  const s = detail.series
  if (!Object.keys(s).length) {
    return (
      <Problem text="No application metrics for this component. Postgres is judged by its pods and by what the services report about their connections to it." />
    )
  }
  const pool = detail.pool_max_per_pod
  return (
    <div className={cn('space-y-3 transition-opacity', dim && 'opacity-60')}>
      <MiniChart title="Error rate" series={[{ key: 'value', points: s.error_ratio, color: serviceColor(name) }]} format={percent} domainMax={1} detail={detail} />
      <MiniChart title="Requests per second" series={[{ key: 'value', points: s.requests_per_second, color: serviceColor(name) }]} format={perSecond} detail={detail} />
      <MiniChart title="Latency (p95)" series={[{ key: 'value', points: s.p95_latency_ms, color: serviceColor(name) }]} format={millis} detail={detail} />
      <MiniChart
        title="Database connection pool"
        subtitle={`Summed across pods${pool != null ? ` · limit ${pool} per pod` : ''}. Queued queries above zero mean the pool is exhausted.`}
        series={[
          { key: 'open', label: 'open connections', points: s.pool_open, color: 'var(--muted-foreground)' },
          { key: 'waiting', label: 'queued queries', points: s.pool_waiting, color: 'var(--sev2)' },
        ]}
        format={count}
        detail={detail}
      />
    </div>
  )
}

type SeriesSpec = { key: string; label?: string; points: Point[] | undefined; color: string }

function MiniChart({
  title,
  subtitle,
  series,
  format,
  domainMax,
  detail,
}: {
  title: string
  subtitle?: string
  series: SeriesSpec[]
  format: (v: number) => string
  domainMax?: number
  detail: Detail
}) {
  const rows = useMemo(() => {
    const byTs = new Map<number, Record<string, number>>()
    for (const spec of series)
      for (const [ts, v] of spec.points ?? []) {
        const row = byTs.get(ts) ?? { ts }
        row[spec.key] = v
        byTs.set(ts, row)
      }
    return [...byTs.values()].sort((a, b) => a.ts - b.ts)
  }, [series])
  const legend = series.length > 1

  return (
    <div className="panel p-3.5">
      <div className="flex items-baseline justify-between gap-3">
        <div className="text-[12.5px] font-medium">{title}</div>
        {legend && (
          <div className="flex gap-3 text-[10.5px] text-muted-foreground">
            {series.map((spec) => (
              <span key={spec.key} className="flex items-center gap-1">
                <span className="h-0.5 w-3 rounded-full" style={{ background: spec.color }} />
                {spec.label}
              </span>
            ))}
          </div>
        )}
      </div>
      {subtitle && <p className="text-[10.5px] text-muted-foreground">{subtitle}</p>}
      {rows.length === 0 ? (
        <p className="py-6 text-center text-[11.5px] text-muted-foreground">No data in this window</p>
      ) : (
        <ResponsiveContainer width="100%" height={110}>
          <LineChart data={rows} margin={{ top: 8, right: 6, bottom: 0, left: 0 }} syncId="service-panel">
            <XAxis
              dataKey="ts"
              type="number"
              domain={[detail.start, detail.end]}
              tickFormatter={clock}
              tick={{ fill: 'var(--muted-foreground)', fontSize: 10 }}
              tickLine={false}
              axisLine={{ stroke: 'currentColor', strokeOpacity: 0.1 }}
              minTickGap={56}
            />
            <YAxis
              width={46}
              tickFormatter={format}
              tick={{ fill: 'var(--muted-foreground)', fontSize: 10 }}
              tickLine={false}
              axisLine={false}
              tickCount={3}
              domain={[0, domainMax ?? 'auto']}
              allowDecimals={false}
            />
            <Tooltip
              isAnimationActive={false}
              cursor={{ stroke: 'currentColor', strokeOpacity: 0.25 }}
              content={({ active, payload, label }) =>
                active && payload?.length ? (
                  <div className="rounded-lg border border-hairline bg-popover px-2.5 py-1.5 text-[11.5px] shadow-lg">
                    <div className="font-mono text-[10px] text-muted-foreground">{clock(Number(label))}</div>
                    {payload.map((entry) => {
                      const spec = series.find((x) => x.key === entry.dataKey)
                      return (
                        <div key={String(entry.dataKey)} className="flex items-center gap-1.5">
                          <span className="h-0.5 w-3 rounded-full" style={{ background: spec?.color }} />
                          <span className="font-medium">{format(Number(entry.value))}</span>
                          {spec?.label && <span className="text-muted-foreground">{spec.label}</span>}
                        </div>
                      )
                    })}
                  </div>
                ) : null
              }
            />
            {series.map((spec) => (
              <Line
                key={spec.key}
                dataKey={spec.key}
                type="monotone"
                stroke={spec.color}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, strokeWidth: 2, stroke: 'var(--background)' }}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}

function LogsTab({ name }: { name: string }) {
  const logs = useQuery({
    queryKey: ['service-logs', name],
    queryFn: () => api<Logs>(`/api/topology/${name}/logs?lines=80`),
  })
  if (logs.isError) return <Problem text={`Could not load logs: ${logs.error.message}`} />
  if (logs.isLoading) return <div className="h-64 animate-pulse rounded-lg bg-white/[0.02]" />
  const data = logs.data!
  return (
    <div>
      <div className="mb-2 flex items-center justify-between text-[11px] text-muted-foreground">
        <span>
          Last {data.lines.length} lines from pod <span className="font-mono text-foreground/80">{data.pod}</span>
        </span>
        <button
          onClick={() => logs.refetch()}
          className="flex items-center gap-1 rounded-md px-2 py-1 hover:bg-white/[0.05] hover:text-foreground"
        >
          <RotateCw className={cn('size-3', logs.isFetching && 'animate-spin')} /> Refresh
        </button>
      </div>
      {data.lines.length === 0 ? (
        <Problem text="The pod has written no log lines yet." />
      ) : (
        <pre className="max-h-[60vh] overflow-auto rounded-lg border border-hairline bg-surface-sunken p-3 font-mono text-[11px] leading-relaxed">
          {data.lines.map((raw, i) => {
            const { time, text } = splitTimestamp(raw)
            return (
              <div key={i} className="flex gap-3">
                <span className="shrink-0 text-muted-foreground" title={time?.toLocaleString()}>
                  {time ? time.toLocaleTimeString([], { hour12: false }) : ''}
                </span>
                <span
                  className={cn(
                    'whitespace-pre-wrap break-all',
                    /error|fail|timeout|refused|exception/i.test(text) ? 'text-sev1' : 'text-foreground/80',
                  )}
                >
                  {text}
                </span>
              </div>
            )
          })}
        </pre>
      )}
    </div>
  )
}

function IncidentsTab({ incidents }: { incidents: Incident[] }) {
  if (incidents.length === 0) return <Problem text="No incidents recorded for this service." />
  return (
    <ul className="divide-y divide-hairline rounded-lg border border-hairline">
      {incidents.map((i) => (
        <li key={i.id}>
          <Link to={`/incidents/${i.id}`} className="flex items-center gap-3 px-3 py-2.5 hover:bg-white/[0.02]">
            <StatusDot tone={i.status === 'resolved' ? 'muted' : 'sev1'} live={i.status === 'triggered'} />
            <span className="min-w-0 flex-1 truncate text-[12.5px]">{i.title}</span>
            <Tag tone={i.status === 'resolved' ? 'muted' : 'sev1'}>{i.status}</Tag>
            <span className="w-16 text-right font-mono text-[10.5px] text-muted-foreground">{relativeTime(i.opened_at)}</span>
          </Link>
        </li>
      ))}
    </ul>
  )
}

function Problem({ text }: { text: string }) {
  return <p className="rounded-lg border border-hairline px-4 py-6 text-center text-[12px] text-muted-foreground">{text}</p>
}

/** Kubernetes prefixes each line with an RFC 3339 timestamp when asked for timestamps. */
function splitTimestamp(line: string): { time: Date | null; text: string } {
  const space = line.indexOf(' ')
  const time = space > 0 ? new Date(line.slice(0, space)) : null
  return time && !Number.isNaN(time.getTime())
    ? { time, text: line.slice(space + 1) }
    : { time: null, text: line }
}

function clock(ts: number) {
  return new Date(ts * 1000).toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit' })
}
