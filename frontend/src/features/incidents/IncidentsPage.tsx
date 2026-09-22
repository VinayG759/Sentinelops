import { motion } from 'motion/react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { absoluteTime, relativeTime } from '@/shared/time'
import type { Incident } from '@/shared/types'
import { StatusDot, Tag, type Tone } from '@/shared/ui/primitives'
import { useMe } from '@/shared/useMe'
import { useIncidentCounts, useIncidents, useTransition, type IncidentStatus } from './api'

const tabs: { status: IncidentStatus; label: string }[] = [
  { status: 'triggered', label: 'Triggered' },
  { status: 'acknowledged', label: 'Acknowledged' },
  { status: 'resolved', label: 'Resolved' },
]

const severityTone: Record<Incident['severity'], Tone> = { sev1: 'sev1', sev2: 'sev2', sev3: 'sev3' }

export function IncidentsPage() {
  const [status, setStatus] = useState<IncidentStatus>('triggered')
  const incidents = useIncidents(status)
  const counts = useIncidentCounts()

  return (
    <div className="mx-auto max-w-6xl">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">Incidents</h1>
          <p className="text-[12px] text-muted-foreground">
            Detected from live metrics — every 15 seconds, every service.
          </p>
        </div>
        <div className="flex gap-1 rounded-lg border border-hairline p-0.5">
          {tabs.map((tab) => (
            <button
              key={tab.status}
              onClick={() => setStatus(tab.status)}
              className={cn(
                'flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[12px] transition-colors',
                status === tab.status
                  ? 'bg-white/[0.07] font-medium text-foreground'
                  : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {tab.label}
              <span className="font-mono text-[10.5px] text-muted-foreground">
                {counts.data?.[tab.status] ?? '–'}
              </span>
            </button>
          ))}
        </div>
      </div>

      {incidents.isError ? (
        <p className="mt-6 text-sev1">Could not load incidents: {incidents.error.message}</p>
      ) : incidents.isLoading ? (
        <div className="panel mt-4 h-40 animate-pulse" />
      ) : incidents.data?.length === 0 ? (
        <EmptyState status={status} />
      ) : (
        <div className="panel mt-4 divide-y divide-hairline">
          {incidents.data?.map((incident, index) => (
            <IncidentRow key={incident.id} incident={incident} index={index} />
          ))}
        </div>
      )}
    </div>
  )
}

function IncidentRow({ incident, index }: { incident: Incident; index: number }) {
  const { can } = useMe()
  const transition = useTransition()
  const tone = severityTone[incident.severity]

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: Math.min(index * 0.03, 0.2) }}
      className="group flex items-center gap-4 px-4 py-3 transition-colors hover:bg-white/[0.02]"
    >
      <StatusDot tone={tone} live={incident.status === 'triggered'} />

      <div className="min-w-0 flex-1">
        <Link to={`/incidents/${incident.id}`} className="font-medium hover:text-signal">
          {incident.title}
        </Link>
        <div className="mt-0.5 flex gap-3 font-mono text-[11px] text-muted-foreground">
          <span>{incident.service}</span>
          <span>{incident.signal}</span>
          <span className="opacity-60">{incident.id.slice(0, 8)}</span>
        </div>
      </div>

      <Tag tone={tone}>{incident.severity}</Tag>
      <span
        className="w-20 text-right font-mono text-[11px] text-muted-foreground"
        title={absoluteTime(incident.opened_at)}
      >
        {relativeTime(incident.opened_at)}
      </span>

      <div className="flex w-[186px] justify-end gap-2">
        {can('responder') && incident.status !== 'resolved' && (
          <div className="flex gap-2 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
            {incident.status === 'triggered' && (
              <Button
                size="sm"
                variant="outline"
                disabled={transition.isPending}
                onClick={() => transition.mutate({ id: incident.id, to: 'acknowledge' })}
              >
                Acknowledge
              </Button>
            )}
            <Button
              size="sm"
              variant="ghost"
              disabled={transition.isPending}
              onClick={() => transition.mutate({ id: incident.id, to: 'resolve' })}
            >
              Resolve
            </Button>
          </div>
        )}
      </div>
    </motion.div>
  )
}

function EmptyState({ status }: { status: IncidentStatus }) {
  return (
    <div className="panel mt-4 px-6 py-16 text-center">
      <div className="mx-auto flex size-10 items-center justify-center rounded-full bg-ok/10 ring-1 ring-ok/25">
        <StatusDot tone="ok" className="size-2.5" />
      </div>
      <p className="mt-3 font-medium">
        {status === 'triggered' ? 'All clear — no open incidents' : `No ${status} incidents`}
      </p>
      {status === 'triggered' && (
        <p className="mt-1 text-[12px] text-muted-foreground">
          To see the agent work, break something in the{' '}
          <Link to="/simulator" className="text-signal underline-offset-4 hover:underline">
            Simulator
          </Link>{' '}
          — or press ⌘K.
        </p>
      )}
    </div>
  )
}
