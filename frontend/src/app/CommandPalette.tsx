import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command'
import { useAutonomy } from '@/features/remediation/api'
import { api } from '@/shared/api'
import { useMe } from '@/shared/useMe'

/** ⌘K: jump anywhere, or run the two actions worth reaching in a hurry. */
export function CommandPalette() {
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { paused, set } = useAutonomy()
  const { can } = useMe()

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === 'k' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault()
        setOpen((v) => !v)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const go = (path: string) => () => {
    navigate(path)
    setOpen(false)
  }

  const breakIt = (name: string) => async () => {
    setOpen(false)
    try {
      await api(`/api/simulator/scenarios/${name}/inject`, { method: 'POST' })
      toast.error(`Injected ${name.replace('_', ' ')}`, {
        description: 'Detection runs every 15 seconds.',
      })
      queryClient.invalidateQueries({ queryKey: ['scenarios'] })
    } catch (error) {
      toast.error('Could not inject', { description: (error as Error).message })
    }
  }

  return (
    // CommandDialog only provides the dialog shell — the <Command> wrapper is what
    // gives the input and list their shared store. Without it, cmdk throws on open.
    <CommandDialog open={open} onOpenChange={setOpen}>
      <Command>
        <CommandInput placeholder="Jump to a page, or run an action…" />
        <CommandList>
          <CommandEmpty>Nothing matches.</CommandEmpty>
          <CommandGroup heading="Go to">
            <CommandItem onSelect={go('/overview')}>Overview</CommandItem>
            <CommandItem onSelect={go('/incidents')}>Incidents</CommandItem>
            <CommandItem onSelect={go('/approvals')}>Approvals</CommandItem>
            <CommandItem onSelect={go('/topology')}>Topology</CommandItem>
            <CommandItem onSelect={go('/audit')}>Audit</CommandItem>
            <CommandItem onSelect={go('/simulator')}>Simulator</CommandItem>
          </CommandGroup>
          {can('admin') && (
            <CommandGroup heading="Actions">
              <CommandItem
                onSelect={() => {
                  set.mutate(!paused)
                  setOpen(false)
                  toast(paused ? 'Autonomy resumed' : 'Autonomy paused')
                }}
              >
                {paused ? 'Resume autonomy' : 'Pause autonomy (kill switch)'}
              </CommandItem>
              <CommandItem onSelect={breakIt('port_mismatch')}>
                Break it — database port mismatch
              </CommandItem>
              <CommandItem onSelect={breakIt('pool_exhaustion')}>
                Break it — connection limit too low
              </CommandItem>
            </CommandGroup>
          )}
        </CommandList>
      </Command>
    </CommandDialog>
  )
}
