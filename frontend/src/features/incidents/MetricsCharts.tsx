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
import type { IncidentMetrics } from './api'

type Series = keyof IncidentMetrics['series']

const charts: { key: Series; label: string; color: string; format: (v: number) => string }[] = [
  {
    key: 'error_ratio',
    label: 'Error ratio',
    color: 'var(--sev1)',
    format: (v) => `${(v * 100).toFixed(0)}%`,
  },
  {
    key: 'requests_per_second',
    label: 'Requests / second',
    color: 'var(--signal)',
    format: (v) => v.toFixed(1),
  },
  {
    key: 'p95_latency_ms',
    label: 'p95 latency (ms)',
    color: 'var(--sev2)',
    format: (v) => v.toFixed(0),
  },
]

const clock = (ts: number) =>
  new Date(ts * 1000).toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit' })

/** Three charts on one shared time axis, with the incident's start marked on each. */
export function MetricsCharts({ metrics }: { metrics: IncidentMetrics }) {
  const openedAt = new Date(metrics.opened_at).getTime() / 1000
  const resolvedAt = metrics.resolved_at ? new Date(metrics.resolved_at).getTime() / 1000 : null
  const domain = timeDomain(metrics)

  return (
    <div className="space-y-3">
      {charts.map(({ key, label, color, format }) => {
        const data = metrics.series[key].map(([ts, value]) => ({ ts, value }))
        const latest = data.at(-1)?.value
        return (
          <div key={key} className="panel p-4">
            <div className="mb-2 flex items-baseline justify-between">
              <div className="text-[10.5px] uppercase tracking-wider text-muted-foreground">
                {label}
              </div>
              {latest != null && (
                <div className="font-mono text-[13px]" style={{ color }}>
                  {format(latest)}
                </div>
              )}
            </div>
            {data.length === 0 ? (
              <p className="py-8 text-center text-muted-foreground">No data in this window</p>
            ) : (
              <ResponsiveContainer width="100%" height={140}>
                <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }} syncId="incident">
                  <CartesianGrid stroke="currentColor" strokeOpacity={0.08} vertical={false} />
                  <XAxis
                    dataKey="ts"
                    type="number"
                    domain={domain}
                    scale="time"
                    tickFormatter={clock}
                    tick={{ fontSize: 11 }}
                    stroke="currentColor"
                    strokeOpacity={0.2}
                  />
                  <YAxis
                    width={48}
                    tickFormatter={format}
                    tick={{ fontSize: 11 }}
                    stroke="currentColor"
                    strokeOpacity={0.2}
                  />
                  <Tooltip
                    labelFormatter={(ts) => clock(Number(ts))}
                    formatter={(value) => [format(Number(value)), label]}
                    contentStyle={{
                      fontSize: 11,
                      borderRadius: 8,
                      background: 'var(--popover)',
                      border: '1px solid var(--border)',
                      color: 'var(--foreground)',
                    }}
                    cursor={{ stroke: 'var(--muted-foreground)', strokeDasharray: '3 3' }}
                  />
                  <ReferenceLine x={openedAt} stroke="var(--sev1)" strokeDasharray="3 3"
                    label={{ value: 'opened', fontSize: 9, fill: 'var(--sev1)', position: 'insideTopLeft' }} />
                  {resolvedAt && (
                    <ReferenceLine x={resolvedAt} stroke="var(--ok)" strokeDasharray="3 3"
                      label={{ value: 'resolved', fontSize: 9, fill: 'var(--ok)', position: 'insideTopRight' }} />
                  )}
                  <Line type="monotone" dataKey="value" stroke={color} strokeWidth={1.75}
                    dot={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>
        )
      })}
    </div>
  )
}

/** Shared x-axis range across all three charts, so moments line up. */
function timeDomain(metrics: IncidentMetrics): [number, number] {
  const all = Object.values(metrics.series).flatMap((s) => s.map(([ts]) => ts))
  return all.length ? [Math.min(...all), Math.max(...all)] : [0, 1]
}
