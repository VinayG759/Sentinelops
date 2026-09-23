import {
  CheckSquare,
  FlaskConical,
  LayoutDashboard,
  LogOut,
  Network,
  ScrollText,
  Shield,
  Siren,
  type LucideIcon,
} from 'lucide-react'
import { motion } from 'motion/react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { Toaster } from 'sonner'
import { useAuth } from '@/app/auth'
import { CommandPalette } from '@/app/CommandPalette'
import { useProposals } from '@/features/remediation/api'
import { KillSwitch } from '@/features/remediation/KillSwitch'
import { HealthIndicator } from '@/features/system/HealthIndicator'
import { TimeRangePicker } from '@/features/system/TimeRangePicker'
import { cn } from '@/lib/utils'
import { supabase } from '@/shared/supabase'
import { Tag } from '@/shared/ui/primitives'
import { useMe } from '@/shared/useMe'

type NavItem = { to: string; label: string; icon: LucideIcon; badge?: number }

export function Layout() {
  const { session } = useAuth()
  const me = useMe()
  const pending = useProposals('pending')
  const location = useLocation()

  const nav: NavItem[] = [
    { to: '/overview', label: 'Overview', icon: LayoutDashboard },
    { to: '/incidents', label: 'Incidents', icon: Siren },
    { to: '/approvals', label: 'Approvals', icon: CheckSquare, badge: pending.data?.length },
    { to: '/topology', label: 'Topology', icon: Network },
    { to: '/audit', label: 'Audit', icon: ScrollText },
    { to: '/simulator', label: 'Simulator', icon: FlaskConical },
  ]

  const current = nav.find((item) => location.pathname.startsWith(item.to))

  return (
    <div className="flex min-h-svh">
      <CommandPalette />
      <Toaster theme="dark" position="bottom-right" toastOptions={{ className: 'font-sans' }} />

      <aside className="sticky top-0 flex h-svh w-[210px] shrink-0 flex-col border-r border-hairline bg-sidebar">
        <div className="flex h-14 items-center gap-2 px-4">
          <div className="flex size-7 items-center justify-center rounded-md bg-signal/12 ring-1 ring-signal/25">
            <Shield className="size-3.5 text-signal" />
          </div>
          <div>
            <div className="text-[13px] font-semibold leading-none tracking-tight">SentinelOps</div>
            <div className="mt-1 font-mono text-[9.5px] uppercase tracking-[0.14em] text-muted-foreground">
              autonomous sre
            </div>
          </div>
        </div>

        <nav className="mt-2 flex-1 space-y-0.5 px-2">
          {nav.map(({ to, label, icon: Icon, badge }) => (
            <NavLink key={to} to={to}>
              {({ isActive }) => (
                <span
                  className={cn(
                    'relative flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[12.5px] text-muted-foreground transition-colors',
                    isActive ? 'bg-white/[0.06] text-foreground' : 'hover:bg-white/[0.03] hover:text-foreground',
                  )}
                >
                  {isActive && (
                    <motion.span
                      layoutId="nav-active"
                      className="absolute inset-y-1.5 -left-2 w-0.5 rounded-full bg-signal"
                    />
                  )}
                  <Icon className={cn('size-4', isActive && 'text-signal')} />
                  {label}
                  {badge ? (
                    <span className="ml-auto rounded-full bg-signal/15 px-1.5 font-mono text-[10px] text-signal">
                      {badge}
                    </span>
                  ) : null}
                </span>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-hairline p-3">
          <div className="truncate text-[11.5px]">{session?.user.email}</div>
          <div className="mt-1 flex items-center justify-between">
            <Tag tone={me.data?.role === 'admin' ? 'signal' : 'muted'}>{me.data?.role ?? '…'}</Tag>
            <button
              onClick={() => supabase.auth.signOut()}
              className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground"
            >
              <LogOut className="size-3" /> Sign out
            </button>
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-14 items-center gap-4 border-b border-hairline bg-background/80 px-6 backdrop-blur-md">
          <div className="text-[13px] font-medium tracking-tight">{current?.label ?? 'SentinelOps'}</div>
          <kbd className="hidden rounded border border-hairline px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground sm:block">
            ⌘K
          </kbd>
          <div className="ml-auto flex items-center gap-4">
            <TimeRangePicker />
            <KillSwitch />
            <HealthIndicator />
          </div>
        </header>

        <main className="flex-1 p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
