import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Zap } from 'lucide-react'
import { motion } from 'motion/react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { api } from '@/shared/api'
import type { Scenario } from '@/shared/types'
import { ErrorNote } from '@/shared/ui/Loadable'
import { StatusDot, Tag, type Tone } from '@/shared/ui/primitives'
import { useMe } from '@/shared/useMe'

const stateTone: Record<Scenario['state'], Tone> = {
  active: 'sev1',
  inactive: 'ok',
  unknown: 'sev2',
}

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
    onSuccess: (_, { op }) => {
      queryClient.invalidateQueries({ queryKey: ['scenarios'] })
      op === 'inject'
        ? toast.error('Fault injected', { description: 'Detection runs every 15 seconds.' })
        : toast.success('System restored')
    },
    onError: (error) => toast.error('Action failed', { description: error.message }),
  })

  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex items-center gap-2">
        <Zap className="size-4 text-sev2" />
        <h1 className="text-lg font-semibold tracking-tight">Simulator</h1>
      </div>
      <p className="mt-1 text-[12px] text-muted-foreground">
        Real faults on the real cluster — nothing is mocked. SentinelOps has to notice from live
        metrics, like it would in production.
      </p>

      {!can('admin') && (
        <p className="panel mt-4 px-4 py-3 text-[12px] text-muted-foreground">
          Only admins can inject or reset faults.
        </p>
      )}

      <div className="mt-5 space-y-3">
        {scenarios.isError && <ErrorNote message={scenarios.error.message} />}
        {scenarios.data?.map((scenario, index) => (
          <motion.div
            key={scenario.name}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.05 }}
            className={cn('panel flex flex-wrap items-start gap-4 p-4', scenario.state === 'active' && 'glow-sev1')}
          >
            <div className="min-w-60 flex-1">
              <div className="flex items-center gap-2">
                <span className="font-medium">{scenario.title}</span>
                <Tag tone={stateTone[scenario.state]}>
                  <StatusDot tone={stateTone[scenario.state]} live={scenario.state !== 'inactive'} />
                  {scenario.state === 'active' ? 'broken' : scenario.state === 'inactive' ? 'healthy' : 'changing'}
                </Tag>
              </div>
              <p className="mt-1.5 text-[12px] text-muted-foreground">{scenario.description}</p>
              <code className="mt-1.5 block font-mono text-[10.5px] text-muted-foreground opacity-70">
                {scenario.name}
              </code>
            </div>

            {can('admin') && (
              <div className="flex shrink-0 gap-2">
                <Button
                  size="sm"
                  disabled={run.isPending || scenario.state === 'active'}
                  onClick={() => run.mutate({ name: scenario.name, op: 'inject' })}
                  className="bg-sev1/90 text-white hover:bg-sev1"
                >
                  Break it
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={run.isPending || scenario.state === 'inactive'}
                  onClick={() => run.mutate({ name: scenario.name, op: 'reset' })}
                >
                  Reset
                </Button>
              </div>
            )}
          </motion.div>
        ))}
        {scenarios.isPending && [0, 1].map((i) => <div key={i} className="panel h-28 animate-pulse" />)}
      </div>
    </div>
  )
}
