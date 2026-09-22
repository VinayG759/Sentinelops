import { ArrowLeft, RefreshCw } from 'lucide-react'
import { motion } from 'motion/react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { absoluteTime, relativeTime } from '@/shared/time'
import type { Incident, IncidentEvent } from '@/shared/types'
import { PhaseStepper, StatusDot, Tag, type Phase, type Tone } from '@/shared/ui/primitives'
import { useMe } from '@/shared/useMe'
import {
  useIncident,
  useIncidentEvents,
  useIncidentMetrics,
  useInvestigate,
  useTransition,
} from './api'
import { MetricsCharts } from './MetricsCharts'
import { Timeline } from './Timeline'

const severityTone: Record<Incident['severity'], Tone> = { sev1: 'sev1', sev2: 'sev2', sev3: 'sev3' }

/** Derive the five-step story from the events themselves — no extra state to keep in sync. */
function phasesFrom(events: IncidentEvent[], incident: Incident): Phase[] {
  const has = (type: string) => events.some((e) => e.type === type)
  const investigating = has('investigation.started')
  const diagnosed = has('investigation.completed')
  const investigationFailed = has('investigation.failed')
  const proposed = has('remediation.proposed')
  const approved = has('remediation.approved')
  const rejected = has('remediation.rejected')
  const executed = has('execution.succeeded')
  const verified = has('verification.passed')
  const rolledBack = has('rollback.succeeded')

  const step = (done: boolean, active: boolean, failed = false): Phase['state'] =>
    failed ? 'failed' : done ? 'done' : active ? 'active' : 'pending'

  return [
    { key: 'detected', label: 'Detected', state: 'done' },
    {
      key: 'investigated',
      label: 'Investigated',
      state: step(diagnosed, investigating && !diagnosed, investigationFailed && !diagnosed),
    },
    { key: 'proposed', label: 'Fix proposed', state: step(proposed, diagnosed && !proposed) },
    {
      key: 'approved',
      label: rejected && !approved ? 'Rejected' : approved ? 'Approved' : 'Awaiting approval',
      state: rejected && !approved ? 'failed' : step(approved, proposed && !approved),
    },
    {
      key: 'verified',
      label: rolledBack ? 'Rolled back' : 'Verified',
      state: rolledBack
        ? 'failed'
        : step(verified || incident.status === 'resolved', executed && !verified),
    },
  ]
}

export function IncidentDetailPage() {
  const { id = '' } = useParams()
  const [tab, setTab] = useState<'timeline' | 'metrics'>('timeline')
  const incident = useIncident(id)
  const events = useIncidentEvents(id)
  const metrics = useIncidentMetrics(id)
  const investigate = useInvestigate(id)
  const transition = useTransition()
  const { can } = useMe()

  if (incident.isError) return <p className="text-sev1">{incident.error.message}</p>
  if (!incident.data) return <div className="panel h-40 animate-pulse" />

  const inc = incident.data
  const list = events.data ?? []
  const investigating =
    list.some((e) => e.type === 'investigation.started') &&
    !list.some((e) => ['investigation.completed', 'investigation.failed'].includes(e.type))
  const tone = severityTone[inc.severity]

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <Link
        to="/incidents"
        className="inline-flex items-center gap-1 text-[12px] text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-3.5" /> Incidents
      </Link>

      <motion.section
        initial={{ opacity: 0, y: -4 }}
        animate={{ opacity: 1, y: 0 }}
        className={cn(
          'panel px-5 py-4',
          inc.status !== 'resolved' && inc.severity === 'sev1' && 'glow-sev1',
          inc.status !== 'resolved' && inc.severity === 'sev2' && 'glow-sev2',
          inc.status === 'resolved' && 'glow-ok',
        )}
      >
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <StatusDot tone={inc.status === 'resolved' ? 'ok' : tone} live={inc.status === 'triggered'} />
              <Tag tone={tone}>{inc.severity}</Tag>
              <Tag tone={inc.status === 'resolved' ? 'ok' : 'muted'}>{inc.status}</Tag>
            </div>
            <h1 className="mt-2 text-lg font-semibold tracking-tight">{inc.title}</h1>
            <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[11px] text-muted-foreground">
              <span>{inc.service}</span>
              <span>{inc.signal}</span>
              <span title={absoluteTime(inc.opened_at)}>opened {relativeTime(inc.opened_at)}</span>
              {inc.resolved_at && <span className="text-ok">resolved {relativeTime(inc.resolved_at)}</span>}
              <span className="opacity-60">{inc.id.slice(0, 8)}</span>
            </div>
          </div>

          {can('responder') && (
            <div className="flex shrink-0 gap-2">
              <Button
                size="sm"
                variant="outline"
                disabled={investigate.isPending || investigating}
                onClick={() => investigate.mutate()}
              >
                <RefreshCw className={cn('size-3.5', investigating && 'animate-spin')} />
                {investigating ? 'Investigating' : 'Re-investigate'}
              </Button>
              {inc.status === 'triggered' && (
                <Button size="sm" variant="outline" onClick={() => transition.mutate({ id: inc.id, to: 'acknowledge' })}>
                  Acknowledge
                </Button>
              )}
              {inc.status !== 'resolved' && (
                <Button size="sm" variant="ghost" onClick={() => transition.mutate({ id: inc.id, to: 'resolve' })}>
                  Resolve
                </Button>
              )}
            </div>
          )}
        </div>

        <div className="mt-4 border-t border-hairline pt-3">
          <PhaseStepper phases={phasesFrom(list, inc)} />
        </div>
      </motion.section>

      <div className="flex gap-1">
        {(['timeline', 'metrics'] as const).map((name) => (
          <button
            key={name}
            onClick={() => setTab(name)}
            className={cn(
              'rounded-lg px-3 py-1.5 text-[12px] capitalize transition-colors',
              tab === name
                ? 'bg-white/[0.06] font-medium text-foreground'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {name}
          </button>
        ))}
      </div>

      {tab === 'timeline' ? (
        list.length ? (
          <div className="panel p-3">
            <Timeline events={list} />
          </div>
        ) : (
          <div className="panel p-10 text-center text-muted-foreground">No events yet.</div>
        )
      ) : metrics.data ? (
        <MetricsCharts metrics={metrics.data} />
      ) : (
        <div className="panel h-64 animate-pulse" />
      )}
    </div>
  )
}
