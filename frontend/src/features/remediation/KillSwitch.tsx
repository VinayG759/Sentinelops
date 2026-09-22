import { Pause, Play } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useMe } from '@/shared/useMe'
import { useAutonomy } from './api'

/**
 * One switch that stops every automatic change. Visible to everyone (so the state is
 * never a surprise), toggleable by admins.
 */
export function KillSwitch() {
  const { paused, set } = useAutonomy()
  const { can } = useMe()

  return (
    <button
      disabled={!can('admin') || set.isPending}
      onClick={() => set.mutate(!paused)}
      title={
        paused
          ? 'Autonomy is paused: approved changes will be refused'
          : 'Autonomy is active: approved changes execute'
      }
      className={cn(
        'flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs',
        paused ? 'border-red-300 bg-red-50 text-red-700' : 'text-muted-foreground',
        can('admin') ? 'hover:bg-muted' : 'cursor-default',
      )}
    >
      {paused ? <Pause className="size-3" /> : <Play className="size-3" />}
      {paused ? 'Autonomy paused' : 'Autonomy active'}
    </button>
  )
}
