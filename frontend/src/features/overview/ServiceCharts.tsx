import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { cn } from '@/lib/utils'
import { api } from '@/shared/api'
import { serviceColor } from '@/shared/serviceColors'
import { useTimeRange } from '@/shared/timeRange'
import type { Incident } from '@/shared/types'

type Point = [number, number]
type Signal = 'error_ratio' | 'requests_per_second' | 'p95_latency_ms'
type ServiceMetrics = {
  start: number
  end: number
  step: number
  services: Record<string, Record<Signal, Point[]>>
}

/** Must match the detector's rule (backend/app/features/incidents/rules.py). */
const ALERT_THRESHOLD = 0.05

const percent = (v: number) => `${(v * 100).toFixed(v > 0 && v < 0.1 ? 1 : 0)}%`
const millis = (v: number) =>
  v >= 1000 ? `${Number((v / 1000).toFixed(1))} s` : `${Math.round(v)} ms`

const charts: {
  signal: Signal
  title: string
  subtitle: string
  format: (v: number) => string
  threshold?: number
}[] = [
  {
    signal: 'error_ratio',
    title: 'Error rate',
    subtitle: 'Share of requests failing',
    format: percent,
    threshold: ALERT_THRESHOLD,
  },
  {
    signal: 'p95_latency_ms',
    title: 'Latency (p95)',
    subtitle: '95% of requests finish faster than this',
    format: millis,
  },
]

/**
 * Every service on one time axis, one chart per signal (never two scales on one chart).
 * Red hairlines mark when incidents opened; the crosshair is shared across both charts.
 */
export function ServiceCharts({ incidents }: { incidents: Incident[] }) {
  const { minutes, refetchEvery } = useTimeRange()
  const metrics = useQuery({
    queryKey: ['service-metrics', minutes],
    queryFn: () => api<ServiceMetrics>(`/api/topology/metrics?minutes=${minutes}`),
    refetchInterval: refetchEvery(15_000),
    placeholderData: (previous) => previous,
  })

  const names = Object.keys(metrics.data?.services ?? {}).sort()
  const markers = useMemo(() => {
    if (!metrics.data) return []
    const { start, end } = metrics.data
    return incidents
      .map((i) => ({ id: i.id, ts: new Date(i.opened_at).getTime() / 1000 }))
      .filter((m) => m.ts >= start && m.ts <= end)
  }, [incidents, metrics.data])

  if (metrics.isError) {
    return (
      <div className="panel px-4 py-10 text-center text-[12px] text-muted-foreground">
        Could not load metrics: {metrics.error.message}. Is Prometheus running?
      </div>
    )
  }

  return (
    <div className={cn('space-y-3 transition-opacity', metrics.isPlaceholderData && 'opacity-60')}>
      <Legend names={names} showIncidents={markers.length > 0} />
      <div className="grid gap-3 lg:grid-cols-2">
        {charts.map((chart) => (
          <ChartPanel
            key={chart.signal}
            {...chart}
            data={metrics.data}
            names={names}
            markers={markers}
            loading={metrics.isLoading}
          />
        ))}
      </div>
    </div>
  )
}

function Legend({ names, showIncidents }: { names: string[]; showIncidents: boolean }) {
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-[11.5px] text-muted-foreground">
      {names.map((name) => (
        <span key={name} className="flex items-center gap-1.5">
          <span className="h-0.5 w-3.5 rounded-full" style={{ background: serviceColor(name) }} />
          <span className="font-mono text-foreground/85">{name}</span>
        </span>
      ))}
      {showIncidents && (
        <span className="flex items-center gap-1.5">
          <span className="h-3 w-px bg-sev1/70" />
          incident opened
        </span>
      )}
      <span className="flex items-center gap-1.5">
        <span className="w-3.5 border-t border-dashed border-muted-foreground/70" />
        {percent(ALERT_THRESHOLD)} alert threshold (error rate)
      </span>
    </div>
  )
}

function ChartPanel({
  signal,
  title,
  subtitle,
  format,
  threshold,
  data,
  names,
  markers,
  loading,
}: (typeof charts)[number] & {
  data: ServiceMetrics | undefined
  names: string[]
  markers: { id: string; ts: number }[]
  loading: boolean
}) {
  // Merge each service's series into rows keyed by timestamp: { ts, 'order-service': v, ... }.
  const rows = useMemo(() => {
    if (!data) return []
    const byTs = new Map<number, Record<string, number>>()
    for (const name of names) {
      for (const [ts, value] of data.services[name]?.[signal] ?? []) {
        const row = byTs.get(ts) ?? { ts }
        row[name] = value
        byTs.set(ts, row)
      }
    }
    return [...byTs.values()].sort((a, b) => a.ts - b.ts)
  }, [data, names, signal])

  // Clean, evenly spaced ticks: 0 up to a round top that always leaves the threshold visible.
  const ticks = useMemo(() => {
    let max = 0
    for (const row of rows) for (const name of names) max = Math.max(max, row[name] ?? 0)
    const floor = threshold != null ? threshold * 1.4 : signal === 'p95_latency_ms' ? 20 : 1
    // A share of requests can't exceed 100%: past half, use quarter steps up to exactly 100%.
    if (signal === 'error_ratio' && max * 1.1 > 0.5) return [0, 0.25, 0.5, 0.75, 1]
    return niceTicks(Math.max(max * 1.1, floor))
  }, [rows, names, threshold, signal])

  return (
    <div className="panel p-4">
      <div className="mb-3">
        <div className="text-[13px] font-medium">{title}</div>
        <div className="text-[11px] text-muted-foreground">{subtitle}</div>
      </div>
      {loading ? (
        <div className="h-[180px] animate-pulse rounded-md bg-white/[0.02]" />
      ) : rows.length === 0 ? (
        <div className="flex h-[180px] items-center justify-center text-[12px] text-muted-foreground">
          No data in this window — services may not be receiving traffic.
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={rows} margin={{ top: 6, right: 8, bottom: 0, left: 0 }} syncId="overview">
            <CartesianGrid stroke="currentColor" strokeOpacity={0.07} vertical={false} />
            <XAxis
              dataKey="ts"
              type="number"
              scale="time"
              domain={data ? [data.start, data.end] : ['dataMin', 'dataMax']}
              tickFormatter={clock}
              tick={{ fill: 'var(--muted-foreground)', fontSize: 10.5 }}
              tickLine={false}
              axisLine={{ stroke: 'currentColor', strokeOpacity: 0.1 }}
              minTickGap={48}
            />
            <YAxis
              width={52}
              tickFormatter={format}
              tick={{ fill: 'var(--muted-foreground)', fontSize: 10.5 }}
              tickLine={false}
              axisLine={false}
              domain={[0, ticks.at(-1) ?? 1]}
              ticks={ticks}
              interval={0}
            />
            {markers.map((m) => (
              <ReferenceLine key={m.id} x={m.ts} stroke="var(--sev1)" strokeOpacity={0.55} />
            ))}
            {threshold != null && (
              <ReferenceLine
                y={threshold}
                stroke="var(--muted-foreground)"
                strokeOpacity={0.5}
                strokeDasharray="3 4"
              />
            )}
            <Tooltip
              content={(props) => <ChartTooltip {...props} format={format} />}
              cursor={{ stroke: 'currentColor', strokeOpacity: 0.25 }}
              isAnimationActive={false}
            />
            {names.map((name) => (
              <Line
                key={name}
                dataKey={name}
                name={name}
                type="monotone"
                stroke={serviceColor(name)}
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
                dot={false}
                activeDot={{ r: 4, strokeWidth: 2, stroke: 'var(--surface)' }}
                isAnimationActive={false}
                connectNulls={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}

/** Value first, service second, keyed by a short line in the service colour. */
function ChartTooltip({
  active,
  payload,
  label,
  format,
}: {
  active?: boolean
  payload?: readonly { dataKey?: unknown; value?: unknown }[]
  label?: unknown
  format: (v: number) => string
}) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-hairline bg-popover px-3 py-2 shadow-lg">
      <div className="mb-1 font-mono text-[10.5px] text-muted-foreground">{clock(Number(label))}</div>
      {payload.map((entry) => (
        <div key={String(entry.dataKey)} className="flex items-center gap-2 text-[12px]">
          <span className="h-0.5 w-3 rounded-full" style={{ background: serviceColor(String(entry.dataKey)) }} />
          <span className="font-medium">{format(Number(entry.value))}</span>
          <span className="font-mono text-[11px] text-muted-foreground">{String(entry.dataKey)}</span>
        </div>
      ))}
    </div>
  )
}

/** 0 and four equal steps up to a round top (1, 2, 2.5 or 5 × a power of ten per step). */
function niceTicks(top: number): number[] {
  const raw = top / 4
  const magnitude = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= raw) ?? raw
  return [0, 1, 2, 3, 4].map((i) => Number((i * step).toPrecision(6)))
}

function clock(ts: number) {
  return new Date(ts * 1000).toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit' })
}
