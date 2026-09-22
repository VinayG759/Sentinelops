import {
  CheckSquare,
  FlaskConical,
  Network,
  ScrollText,
  Siren,
  type LucideIcon,
} from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '@/app/auth'
import { HealthIndicator } from '@/features/system/HealthIndicator'
import { cn } from '@/lib/utils'
import { api } from '@/shared/api'
import { supabase } from '@/shared/supabase'

const nav: { to: string; label: string; icon: LucideIcon }[] = [
  { to: '/incidents', label: 'Incidents', icon: Siren },
  { to: '/approvals', label: 'Approvals', icon: CheckSquare },
  { to: '/topology', label: 'Topology', icon: Network },
  { to: '/audit', label: 'Audit', icon: ScrollText },
  { to: '/simulator', label: 'Simulator', icon: FlaskConical },
]

export function Layout() {
  const { session } = useAuth()
  // Round-trips through the backend's token verification + role lookup.
  const me = useQuery({ queryKey: ['me'], queryFn: () => api<{ role: string }>('/api/me') })

  return (
    <div className="flex min-h-svh text-sm">
      <aside className="flex w-52 shrink-0 flex-col border-r bg-sidebar">
        <div className="flex h-12 items-center border-b px-4 font-semibold tracking-tight">
          SentinelOps
        </div>
        <nav className="flex-1 space-y-0.5 p-2">
          {nav.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-2 rounded-md px-2 py-1.5 text-muted-foreground hover:bg-sidebar-accent hover:text-foreground',
                  isActive && 'bg-sidebar-accent font-medium text-foreground',
                )
              }
            >
              <Icon className="size-4" />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t p-3">
          <div className="truncate text-xs text-muted-foreground">{session?.user.email}</div>
          <div className="mt-0.5 font-mono text-[11px] text-muted-foreground">
            {me.isError ? 'role: unverified' : `role: ${me.data?.role ?? '…'}`}
          </div>
          <button
            className="mt-1 text-xs text-muted-foreground hover:text-foreground"
            onClick={() => supabase.auth.signOut()}
          >
            Sign out
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-12 items-center justify-end border-b px-6">
          <HealthIndicator />
        </header>
        <main className="flex-1 p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
