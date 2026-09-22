import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { api } from '@/shared/api'
import type { Scenario } from '@/shared/types'
import { useMe } from '@/shared/useMe'

export function SimulatorPage() {
  const { can } = useMe()
  const queryClient = useQueryClient()
  const scenarios = useQuery({
    queryKey: ['scenarios'],
    queryFn: () => api<Scenario[]>('/api/simulator/scenarios'),
    refetchInterval: 5_000,
  })
  const run = useMutation({
    mutationFn: ({ name, op }: { name: string; op: 'inject' | 'reset' }) =>
      api<Scenario>(`/api/simulator/scenarios/${name}/${op}`, { method: 'POST' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['scenarios'] }),
  })

  return (
    <div className="max-w-3xl">
      <h1 className="text-lg font-semibold tracking-tight">Simulator</h1>
      <p className="mt-1 text-muted-foreground">
        Break the demo system for real. Nothing here is faked — SentinelOps has to detect it from
        live metrics.
      </p>

      {!can('admin') && (
        <p className="mt-4 rounded-md border bg-muted/40 px-3 py-2 text-muted-foreground">
          Only admins can inject or reset scenarios.
        </p>
      )}
      {run.isError && <p className="mt-4 text-destructive">{run.error.message}</p>}

      <div className="mt-6 divide-y rounded-lg border">
        {scenarios.data?.map((s) => (
          <div key={s.name} className="flex items-start gap-4 p-4">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="font-medium">{s.title}</span>
                <StateBadge state={s.state} />
              </div>
              <p className="mt-1 text-muted-foreground">{s.description}</p>
              <code className="mt-1 block font-mono text-[11px] text-muted-foreground">{s.name}</code>
            </div>
            {can('admin') && (
              <div className="flex shrink-0 gap-2">
                <Button
                  size="sm"
                  variant="destructive"
                  disabled={run.isPending || s.state === 'active'}
                  onClick={() => run.mutate({ name: s.name, op: 'inject' })}
                >
                  Break it
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={run.isPending || s.state === 'inactive'}
                  onClick={() => run.mutate({ name: s.name, op: 'reset' })}
                >
                  Reset
                </Button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function StateBadge({ state }: { state: Scenario['state'] }) {
  return (
    <span
      className={cn(
        'rounded px-1.5 py-0.5 text-[11px] font-medium',
        state === 'active' && 'bg-red-50 text-red-700',
        state === 'inactive' && 'bg-zinc-100 text-zinc-600',
        state === 'unknown' && 'bg-amber-50 text-amber-800',
      )}
    >
      {state === 'active' ? 'Broken' : state === 'inactive' ? 'Healthy' : 'Changing…'}
    </span>
  )
}
