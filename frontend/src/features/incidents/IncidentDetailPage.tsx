import { ArrowLeft } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { absoluteTime, relativeTime } from '@/shared/time'
import type { Incident } from '@/shared/types'
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

const severityStyle: Record<Incident['severity'], string> = {
  sev1: 'bg-red-50 text-red-700 ring-red-600/20',
  sev2: 'bg-amber-50 text-amber-800 ring-amber-600/20',
  sev3: 'bg-zinc-50 text-zinc-700 ring-zinc-500/20',
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

  if (incident.isError) return <p className="text-destructive">{incident.error.message}</p>
  if (!incident.data) return null
  const inc = incident.data
  const investigating = events.data?.some((e) => e.type === 'investigation.started')
    && !events.data?.some((e) => ['investigation.completed', 'investigation.failed'].includes(e.type))

  return (
    <div className="max-w-5xl">
      <Link to="/incidents" className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-3.5" /> Incidents
      </Link>

      <div className="mt-3 flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className={cn('rounded px-1.5 py-0.5 font-mono text-[11px] font-medium uppercase ring-1 ring-inset',
              severityStyle[inc.severity])}>
              {inc.severity}
            </span>
            <h1 className="text-lg font-semibold tracking-tight">{inc.title}</h1>
          </div>
          <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[11px] text-muted-foreground">
            <span>{inc.service}</span>
            <span>{inc.signal}</span>
            <span>status: {inc.status}</span>
            <span title={absoluteTime(inc.opened_at)}>opened {relativeTime(inc.opened_at)}</span>
            {inc.resolved_at && <span>resolved {relativeTime(inc.resolved_at)}</span>}
            <span>{inc.id}</span>
          </div>
        </div>

        {can('responder') && (
          <div className="flex shrink-0 gap-2">
            <Button size="sm" variant="outline" disabled={investigate.isPending || investigating}
              onClick={() => investigate.mutate()}>
              {investigating ? 'Investigating…' : 'Re-investigate'}
            </Button>
            {inc.status === 'triggered' && (
              <Button size="sm" variant="outline"
                onClick={() => transition.mutate({ id: inc.id, to: 'acknowledge' })}>
                Acknowledge
              </Button>
            )}
            {inc.status !== 'resolved' && (
              <Button size="sm" variant="ghost"
                onClick={() => transition.mutate({ id: inc.id, to: 'resolve' })}>
                Resolve
              </Button>
            )}
          </div>
        )}
      </div>

      <div className="mt-5 flex gap-1 border-b">
        {(['timeline', 'metrics'] as const).map((name) => (
          <button key={name} onClick={() => setTab(name)}
            className={cn('-mb-px border-b-2 px-3 py-2 capitalize text-muted-foreground hover:text-foreground',
              tab === name ? 'border-foreground font-medium text-foreground' : 'border-transparent')}>
            {name}
          </button>
        ))}
      </div>

      {tab === 'timeline' ? (
        events.data?.length ? (
          <Timeline events={events.data} />
        ) : (
          <p className="mt-6 text-muted-foreground">No events yet.</p>
        )
      ) : metrics.data ? (
        <MetricsCharts metrics={metrics.data} />
      ) : (
        <p className="mt-6 text-muted-foreground">Loading metrics…</p>
      )}
    </div>
  )
}
