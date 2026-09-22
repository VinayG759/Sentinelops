import { ChevronRight } from 'lucide-react'
import { useState } from 'react'
import { useProposal } from '@/features/remediation/api'
import { ApprovalCard } from '@/features/remediation/ApprovalCard'
import { cn } from '@/lib/utils'
import { absoluteTime } from '@/shared/time'
import type { IncidentEvent } from '@/shared/types'

/** Short label + accent per event type. Unknown types fall back to the raw type. */
const labels: Record<string, string> = {
  'incident.opened': 'Incident opened',
  'incident.acknowledged': 'Acknowledged',
  'incident.resolved': 'Resolved',
  'incident.triggered': 'Reopened',
  'investigation.started': 'Investigation started',
  'investigation.step': 'Tool call',
  'investigation.completed': 'Root cause found',
  'investigation.failed': 'Investigation failed',
  'remediation.proposed': 'Fix proposed',
  'remediation.approved': 'Approved by human',
  'remediation.rejected': 'Rejected by human',
  'remediation.expired': 'Proposal expired',
  'remediation.rejected_by_policy': 'Proposal refused by policy',
  'execution.started': 'Executing',
  'execution.succeeded': 'Change applied',
  'execution.failed': 'Execution failed',
  'execution.refused': 'Execution refused',
  'verification.passed': 'Verified — service recovered',
  'verification.failed': 'Verification failed',
  'rollback.started': 'Rolling back',
  'rollback.succeeded': 'Rolled back',
  'rollback.failed': 'Rollback failed',
  'handler.failed': 'Internal handler failed',
}

const accents: Record<string, string> = {
  'incident.opened': 'bg-red-500',
  'incident.resolved': 'bg-emerald-500',
  'incident.triggered': 'bg-red-500',
  'investigation.completed': 'bg-emerald-500',
  'investigation.failed': 'bg-amber-500',
  'remediation.proposed': 'bg-blue-500',
  'remediation.approved': 'bg-blue-500',
  'remediation.rejected': 'bg-zinc-400',
  'execution.succeeded': 'bg-blue-500',
  'execution.failed': 'bg-amber-500',
  'execution.refused': 'bg-amber-500',
  'verification.passed': 'bg-emerald-500',
  'verification.failed': 'bg-amber-500',
  'rollback.succeeded': 'bg-amber-500',
  'rollback.failed': 'bg-red-500',
  'handler.failed': 'bg-amber-500',
}

const clock = (iso: string) => new Date(iso).toLocaleTimeString([], { hour12: false })

export function Timeline({ events }: { events: IncidentEvent[] }) {
  const [highlighted, setHighlighted] = useState<number | null>(null)

  return (
    <ol className="mt-4 space-y-px">
      {events.map((event) => (
        <li
          key={event.id}
          id={`event-${event.id}`}
          className={cn(
            'rounded-md transition-colors',
            highlighted === event.id && 'bg-amber-50 ring-1 ring-amber-300',
          )}
        >
          <Row event={event} onJump={setHighlighted} />
        </li>
      ))}
    </ol>
  )
}

function Row({ event, onJump }: { event: IncidentEvent; onJump: (id: number) => void }) {
  const [open, setOpen] = useState(false)
  const expandable = event.type === 'investigation.step'
  const payload = event.payload as Record<string, unknown>

  return (
    <div className="flex gap-3 px-2 py-1.5">
      <span className="w-16 shrink-0 pt-0.5 font-mono text-[11px] text-muted-foreground"
        title={absoluteTime(event.created_at)}>
        {clock(event.created_at)}
      </span>
      <span className={cn('mt-1.5 size-1.5 shrink-0 rounded-full', accents[event.type] ?? 'bg-zinc-300')} />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <button
            className={cn('text-left font-medium', expandable && 'hover:underline')}
            onClick={() => expandable && setOpen(!open)}
          >
            {expandable && (
              <ChevronRight className={cn('mr-1 inline size-3 transition-transform', open && 'rotate-90')} />
            )}
            {labels[event.type] ?? event.type}
          </button>
          <span className="font-mono text-[11px] text-muted-foreground">{event.actor}</span>
          <span className="font-mono text-[11px] text-muted-foreground">#{event.id}</span>
        </div>

        <Summary event={event} payload={payload} onJump={onJump} />

        {open && (
          <pre className="mt-2 max-h-72 overflow-auto rounded-md bg-muted p-3 font-mono text-[11px] leading-relaxed">
            {JSON.stringify({ args: payload.args, result: safeParse(payload.result) }, null, 2)}
          </pre>
        )}
      </div>
    </div>
  )
}

function Summary({
  event,
  payload,
  onJump,
}: {
  event: IncidentEvent
  payload: Record<string, unknown>
  onJump: (id: number) => void
}) {
  if (event.type === 'investigation.step') {
    return (
      <p className="font-mono text-[11px] text-muted-foreground">
        {String(payload.tool)}({argSummary(payload.args)}){payload.ok === false && ' — failed'}
      </p>
    )
  }

  if (event.type === 'investigation.completed') {
    const evidence = (payload.evidence as number[]) ?? []
    const ruledOut = (payload.ruled_out as string[]) ?? []
    return (
      <div className="mt-1 rounded-md border bg-emerald-50/40 p-3">
        <p className="font-medium">{String(payload.hypothesis)}</p>
        <p className="mt-1 text-muted-foreground">
          Confidence: {String(payload.confidence)} · {String(payload.tool_calls)} tool calls ·{' '}
          {String(payload.seconds)}s
        </p>
        {payload.suggested_fix ? (
          <p className="mt-2">
            <span className="text-muted-foreground">Suggested fix: </span>
            {String(payload.suggested_fix)}
          </p>
        ) : null}
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <span className="text-muted-foreground">Evidence:</span>
          {evidence.map((id) => (
            <a
              key={id}
              href={`#event-${id}`}
              onClick={() => onJump(id)}
              className="rounded bg-background px-1.5 py-0.5 font-mono text-[11px] ring-1 ring-border hover:bg-muted"
            >
              #{id}
            </a>
          ))}
        </div>
        {ruledOut.length > 0 && (
          <ul className="mt-2 list-inside list-disc text-muted-foreground">
            {ruledOut.map((reason) => (
              <li key={reason}>Ruled out — {reason}</li>
            ))}
          </ul>
        )}
      </div>
    )
  }

  if (event.type === 'remediation.proposed') {
    return <ProposalPreview proposalId={String(payload.proposal_id)} />
  }

  if (event.type.startsWith('execution.') || event.type.startsWith('verification.')
      || event.type.startsWith('rollback.')) {
    const detail = payload.reason ?? payload.error ?? payload.query ?? payload.action
    return detail ? (
      <p className="font-mono text-[11px] text-muted-foreground">{String(detail)}</p>
    ) : null
  }

  if (event.type === 'incident.opened') {
    return (
      <p className="font-mono text-[11px] text-muted-foreground">
        error ratio {formatRatio(payload.error_ratio)} · {String(payload.request_rate)} req/s ·
        threshold {formatRatio(payload.threshold)}
      </p>
    )
  }

  if (event.type === 'investigation.failed' || event.type === 'handler.failed') {
    return <p className="text-amber-700">{String(payload.reason ?? payload.error)}</p>
  }

  return null
}

/** The proposal card, inline on the timeline, with live status and approve/reject. */
function ProposalPreview({ proposalId }: { proposalId: string }) {
  const proposal = useProposal(proposalId)
  if (!proposal.data) return null
  return (
    <div className="mt-2">
      <ApprovalCard proposal={proposal.data} />
    </div>
  )
}

function argSummary(args: unknown): string {
  if (!args || typeof args !== 'object') return ''
  return Object.entries(args as Record<string, unknown>)
    .map(([key, value]) => `${key}=${value}`)
    .join(', ')
}

function formatRatio(value: unknown): string {
  const n = Number(value)
  return Number.isFinite(n) ? `${(n * 100).toFixed(0)}%` : String(value)
}

function safeParse(value: unknown): unknown {
  if (typeof value !== 'string') return value
  try {
    return JSON.parse(value)
  } catch {
    return value
  }
}
