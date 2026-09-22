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

const charts: { key: Series; label: string; format: (v: number) => string }[] = [
  { key: 'error_ratio', label: 'Error ratio', format: (v) => `${(v * 100).toFixed(0)}%` },
  { key: 'requests_per_second', label: 'Requests / second', format: (v) => v.toFixed(1) },
  { key: 'p95_latency_ms', label: 'p95 latency (ms)', format: (v) => v.toFixed(0) },
]

const clock = (ts: number) =>
  new Date(ts * 1000).toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit' })

/** Three charts on one shared time axis, with the incident's start marked on each. */
export function MetricsCharts({ metrics }: { metrics: IncidentMetrics }) {
  const openedAt = new Date(metrics.opened_at).getTime() / 1000
  const resolvedAt = metrics.resolved_at ? new Date(metrics.resolved_at).getTime() / 1000 : null
  const domain = timeDomain(metrics)

  return (
    <div className="mt-4 space-y-4">
      {charts.map(({ key, label, format }) => {
        const data = metrics.series[key].map(([ts, value]) => ({ ts, value }))
        return (
          <div key={key} className="rounded-lg border p-3">
            <div className="mb-2 text-xs font-medium text-muted-foreground">{label}</div>
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
                    contentStyle={{ fontSize: 12, borderRadius: 6 }}
                  />
                  <ReferenceLine x={openedAt} stroke="#dc2626" strokeDasharray="3 3"
                    label={{ value: 'opened', fontSize: 10, fill: '#dc2626', position: 'insideTopLeft' }} />
                  {resolvedAt && (
                    <ReferenceLine x={resolvedAt} stroke="#059669" strokeDasharray="3 3"
                      label={{ value: 'resolved', fontSize: 10, fill: '#059669', position: 'insideTopRight' }} />
                  )}
                  <Line type="monotone" dataKey="value" stroke="currentColor" strokeWidth={1.5}
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
