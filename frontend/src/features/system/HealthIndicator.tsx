import { useQuery } from '@tanstack/react-query'
import { cn } from '@/lib/utils'
import { api } from '@/shared/api'

type Check = { status: 'ok' | 'error' | 'skipped'; detail: string; ms: number }
type Health = { status: 'ok' | 'degraded'; checks: Record<string, Check> }

const dot: Record<Check['status'], string> = {
  ok: 'bg-emerald-500',
  error: 'bg-red-500',
  skipped: 'bg-zinc-300',
}

/** One dot per dependency. Hover for the detail — tells you *which* layer is down. */
export function HealthIndicator() {
  const { data, isError } = useQuery({
    queryKey: ['health'],
    queryFn: () => api<Health>('/api/health'),
    refetchInterval: 10_000,
  })

  if (isError) {
    return <span className="text-xs text-red-600">Backend unreachable</span>
  }

  return (
    <div className="flex items-center gap-3">
      {Object.entries(data?.checks ?? {}).map(([name, check]) => (
        <span
          key={name}
          className="flex items-center gap-1.5 text-xs text-muted-foreground"
          title={`${name}: ${check.detail} (${check.ms} ms)`}
        >
          <span className={cn('size-1.5 rounded-full', dot[check.status])} />
          {name}
        </span>
      ))}
    </div>
  )
}
