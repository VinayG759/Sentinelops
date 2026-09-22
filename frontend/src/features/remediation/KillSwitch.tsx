import { Pause, Play } from 'lucide-react'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { StatusDot } from '@/shared/ui/primitives'
import { useMe } from '@/shared/useMe'
import { useAutonomy } from './api'

/**
 * One switch that stops every automatic change. Everyone sees its state; admins flip it.
 */
export function KillSwitch() {
  const { paused, set } = useAutonomy()
  const { can } = useMe()

  const toggle = () =>
    set.mutate(!paused, {
      onSuccess: () =>
        paused
          ? toast.success('Autonomy resumed', { description: 'Approved changes will execute.' })
          : toast.warning('Autonomy paused', { description: 'Approved changes will be refused.' }),
    })

  return (
    <button
      disabled={!can('admin') || set.isPending}
      onClick={toggle}
      title={
        paused
          ? 'Autonomy is paused: approved changes are refused'
          : 'Autonomy is active: approved changes execute'
      }
      className={cn(
        'flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11.5px] transition-colors',
        paused
          ? 'border-sev1/30 bg-sev1/10 text-sev1'
          : 'border-hairline text-muted-foreground hover:text-foreground',
        can('admin') ? 'cursor-pointer' : 'cursor-default',
      )}
    >
      {paused ? <Pause className="size-3" /> : <Play className="size-3" />}
      {paused ? 'Autonomy paused' : 'Autonomy active'}
      {paused && <StatusDot tone="sev1" live className="ml-0.5" />}
    </button>
  )
}
