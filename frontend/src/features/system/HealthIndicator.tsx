import { useQuery } from '@tanstack/react-query'
import { api } from '@/shared/api'
import { StatusDot, type Tone } from '@/shared/ui/primitives'

type Check = { status: 'ok' | 'error' | 'skipped'; detail: string; ms: number }
type Health = { status: 'ok' | 'degraded'; checks: Record<string, Check> }

const tone: Record<Check['status'], Tone> = { ok: 'ok', error: 'sev1', skipped: 'muted' }

/** One dot per dependency — a red dot says which layer is down, before you ask. */
export function HealthIndicator() {
  const { data, isError } = useQuery({
    queryKey: ['health'],
    queryFn: () => api<Health>('/api/health'),
    refetchInterval: 10_000,
  })

  if (isError) return <span className="text-[11px] text-sev1">Backend unreachable</span>
  if (!data) {
    return (
      <div className="flex items-center gap-3">
        {['database', 'prometheus', 'kubernetes', 'freshservice'].map((name) => (
          <span key={name} className="flex items-center gap-1.5 font-mono text-[10.5px] text-muted-foreground opacity-40">
            <StatusDot tone="muted" />
            <span className="hidden lg:inline">{name}</span>
          </span>
        ))}
      </div>
    )
  }

  return (
    <div className="flex items-center gap-3">
      {Object.entries(data.checks).map(([name, check]) => (
        <span
          key={name}
          className="flex items-center gap-1.5 font-mono text-[10.5px] text-muted-foreground"
          title={`${name}: ${check.detail} (${check.ms} ms)`}
        >
          <StatusDot tone={tone[check.status]} live={check.status === 'error'} />
          <span className="hidden lg:inline">{name}</span>
        </span>
      ))}
    </div>
  )
}
