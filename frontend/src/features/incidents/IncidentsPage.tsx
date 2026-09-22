import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { absoluteTime, relativeTime } from '@/shared/time'
import type { Incident } from '@/shared/types'
import { useMe } from '@/shared/useMe'
import { useIncidentCounts, useIncidents, useTransition, type IncidentStatus } from './api'

const tabs: { status: IncidentStatus; label: string }[] = [
  { status: 'triggered', label: 'Triggered' },
  { status: 'acknowledged', label: 'Acknowledged' },
  { status: 'resolved', label: 'Resolved' },
]

const severityStyle: Record<Incident['severity'], string> = {
  sev1: 'bg-red-50 text-red-700 ring-red-600/20',
  sev2: 'bg-amber-50 text-amber-800 ring-amber-600/20',
  sev3: 'bg-zinc-50 text-zinc-700 ring-zinc-500/20',
}

export function IncidentsPage() {
  const [status, setStatus] = useState<IncidentStatus>('triggered')
  const incidents = useIncidents(status)
  const counts = useIncidentCounts()

  return (
    <div>
      <h1 className="text-lg font-semibold tracking-tight">Incidents</h1>

      <div className="mt-4 flex gap-1 border-b">
        {tabs.map((tab) => (
          <button
            key={tab.status}
            onClick={() => setStatus(tab.status)}
            className={cn(
              '-mb-px border-b-2 px-3 py-2 text-muted-foreground hover:text-foreground',
              status === tab.status ? 'border-foreground font-medium text-foreground' : 'border-transparent',
            )}
          >
            {tab.label}
            <span className="ml-1.5 font-mono text-xs text-muted-foreground">
              {counts.data?.[tab.status] ?? '–'}
            </span>
          </button>
        ))}
      </div>

      {incidents.isError ? (
        <p className="mt-6 text-destructive">Could not load incidents: {incidents.error.message}</p>
      ) : incidents.data?.length === 0 ? (
        <EmptyState status={status} />
      ) : (
        <IncidentTable rows={incidents.data ?? []} />
      )}
    </div>
  )
}

function IncidentTable({ rows }: { rows: Incident[] }) {
  const { can } = useMe()
  const transition = useTransition()

  return (
    <table className="mt-2 w-full">
      <thead>
        <tr className="border-b text-left text-xs text-muted-foreground">
          <th className="py-2 pr-3 font-medium">Severity</th>
          <th className="py-2 pr-3 font-medium">Incident</th>
          <th className="py-2 pr-3 font-medium">Service</th>
          <th className="py-2 pr-3 font-medium">Opened</th>
          <th className="py-2 font-medium" />
        </tr>
      </thead>
      <tbody>
        {rows.map((incident) => (
          <tr key={incident.id} className="border-b last:border-0 hover:bg-muted/40">
            <td className="py-2.5 pr-3">
              <span
                className={cn(
                  'rounded px-1.5 py-0.5 font-mono text-[11px] font-medium uppercase ring-1 ring-inset',
                  severityStyle[incident.severity],
                )}
              >
                {incident.severity}
              </span>
            </td>
            <td className="py-2.5 pr-3">
              <Link to={`/incidents/${incident.id}`} className="font-medium hover:underline">
                {incident.title}
              </Link>
              <div className="font-mono text-[11px] text-muted-foreground">
                {incident.id.slice(0, 8)} · {incident.signal}
              </div>
            </td>
            <td className="py-2.5 pr-3 font-mono text-xs">{incident.service}</td>
            <td className="py-2.5 pr-3 text-muted-foreground" title={absoluteTime(incident.opened_at)}>
              {relativeTime(incident.opened_at)}
            </td>
            <td className="py-2.5 text-right">
              {can('responder') && incident.status !== 'resolved' && (
                <div className="flex justify-end gap-2">
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
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function EmptyState({ status }: { status: IncidentStatus }) {
  return (
    <div className="mt-6 rounded-lg border border-dashed p-10 text-center">
      <p className="font-medium">
        {status === 'triggered' ? 'All clear — no open incidents' : `No ${status} incidents`}
      </p>
      {status === 'triggered' && (
        <p className="mt-1 text-muted-foreground">
          The detector checks every service every 15 seconds. To see one appear, break something
          in the{' '}
          <Link to="/simulator" className="text-foreground underline underline-offset-4">
            Simulator
          </Link>
          .
        </p>
      )}
    </div>
  )
}
