import { ChevronRight } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useState } from 'react'
import { useProposal } from '@/features/remediation/api'
import { ApprovalCard } from '@/features/remediation/ApprovalCard'
import { cn } from '@/lib/utils'
import { absoluteTime } from '@/shared/time'
import type { IncidentEvent } from '@/shared/types'
import { StatusDot, type Tone } from '@/shared/ui/primitives'

const labels: Record<string, string> = {
  'incident.opened': 'Incident detected',
  'incident.acknowledged': 'Acknowledged',
  'incident.resolved': 'Resolved',
  'incident.triggered': 'Reopened',
  'investigation.started': 'Investigation started',
  'investigation.step': 'Tool call',
  'investigation.completed': 'Root cause found',
  'investigation.failed': 'Investigation failed',
  'remediation.proposed': 'Fix proposed',
  'remediation.reused': 'Same fix already proposed for another incident',
  'incident.resolved_by_sibling': 'Resolved by a fix applied elsewhere',
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
  'autonomy.paused': 'Autonomy paused',
  'autonomy.resumed': 'Autonomy resumed',
  'handler.failed': 'Internal handler failed',
}

const tones: Record<string, Tone> = {
  'incident.opened': 'sev1',
  'incident.triggered': 'sev1',
  'incident.resolved': 'ok',
  'investigation.completed': 'ok',
  'investigation.failed': 'sev2',
  'remediation.proposed': 'signal',
  'remediation.reused': 'signal',
  'incident.resolved_by_sibling': 'ok',
  'remediation.approved': 'signal',
  'remediation.rejected': 'muted',
  'execution.succeeded': 'signal',
  'execution.failed': 'sev1',
  'execution.refused': 'sev2',
  'verification.passed': 'ok',
  'verification.failed': 'sev2',
  'rollback.succeeded': 'sev2',
  'rollback.failed': 'sev1',
  'handler.failed': 'sev2',
}

const clock = (iso: string) => new Date(iso).toLocaleTimeString([], { hour12: false })

export function Timeline({ events }: { events: IncidentEvent[] }) {
  const [highlighted, setHighlighted] = useState<number | null>(null)

  return (
    <ol className="relative">
      {/* the spine */}
      <span className="absolute left-[78px] top-2 bottom-2 w-px bg-hairline" aria-hidden />
      <AnimatePresence initial={false}>
        {events.map((event, index) => (
          <motion.li
            key={event.id}
            id={`event-${event.id}`}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: Math.min(index * 0.02, 0.3) }}
            className={cn(
              'relative rounded-lg transition-colors',
              highlighted === event.id && 'bg-signal/8 ring-1 ring-signal/30',
            )}
          >
            <Row event={event} onJump={setHighlighted} />
          </motion.li>
        ))}
      </AnimatePresence>
    </ol>
  )
}

function Row({ event, onJump }: { event: IncidentEvent; onJump: (id: number) => void }) {
  const [open, setOpen] = useState(false)
  const expandable = event.type === 'investigation.step'
  const payload = event.payload as Record<string, unknown>
  const tone = tones[event.type] ?? 'muted'

  return (
    <div className="flex gap-3 px-2 py-2">
      <span
        className="w-[60px] shrink-0 pt-0.5 text-right font-mono text-[10.5px] text-muted-foreground"
        title={absoluteTime(event.created_at)}
      >
        {clock(event.created_at)}
      </span>
      <span className="relative z-10 mt-1.5 flex size-2 shrink-0 items-center justify-center">
        <StatusDot tone={tone} live={event.type === 'investigation.started'} />
      </span>

      <div className="min-w-0 flex-1 pl-1">
        <div className="flex flex-wrap items-baseline gap-2">
          <button
            className={cn(
              'text-left text-[12.5px] font-medium',
              expandable && 'hover:text-signal',
              tone === 'ok' && 'text-ok',
              tone === 'sev1' && 'text-sev1',
            )}
            onClick={() => expandable && setOpen(!open)}
          >
            {expandable && (
              <ChevronRight
                className={cn('mr-0.5 inline size-3 transition-transform', open && 'rotate-90')}
              />
            )}
            {labels[event.type] ?? event.type}
          </button>
          <span className="font-mono text-[10px] text-muted-foreground">{event.actor}</span>
          <span className="font-mono text-[10px] text-muted-foreground opacity-50">#{event.id}</span>
        </div>

        <Summary event={event} payload={payload} onJump={onJump} />

        <AnimatePresence>
          {open && (
            <motion.pre
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="mt-2 max-h-72 overflow-auto rounded-lg border border-hairline bg-surface-sunken p-3 font-mono text-[10.5px] leading-relaxed text-muted-foreground"
            >
              {JSON.stringify({ args: payload.args, result: safeParse(payload.result) }, null, 2)}
            </motion.pre>
          )}
        </AnimatePresence>
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
        <span className="text-signal/80">{String(payload.tool)}</span>({argSummary(payload.args)})
        {payload.ok === false && <span className="text-sev2"> — failed</span>}
      </p>
    )
  }

  if (event.type === 'investigation.completed') {
    const evidence = (payload.evidence as number[]) ?? []
    const ruledOut = (payload.ruled_out as string[]) ?? []
    const usage = payload.usage as { input_tokens?: number; output_tokens?: number } | undefined
    return (
      <div className="mt-1.5 rounded-lg border border-ok/20 bg-ok/[0.06] p-3">
        <p className="text-[12.5px]">{String(payload.hypothesis)}</p>
        <div className="mt-2 flex flex-wrap items-center gap-2 font-mono text-[10.5px] text-muted-foreground">
          <span className="text-ok">{String(payload.confidence)} confidence</span>
          <span>·</span>
          <span>{String(payload.tool_calls)} tool calls</span>
          <span>·</span>
          <span>{String(payload.seconds)}s</span>
          {usage?.input_tokens ? (
            <>
              <span>·</span>
              <span>{usage.input_tokens + (usage.output_tokens ?? 0)} tokens</span>
            </>
          ) : null}
        </div>
        {payload.suggested_fix ? (
          <p className="mt-2 text-[12px]">
            <span className="text-muted-foreground">Suggested: </span>
            {String(payload.suggested_fix)}
          </p>
        ) : null}
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <span className="text-[10.5px] uppercase tracking-wider text-muted-foreground">Evidence</span>
          {evidence.map((id) => (
            <a
              key={id}
              href={`#event-${id}`}
              onClick={() => onJump(id)}
              className="rounded border border-hairline bg-surface px-1.5 py-0.5 font-mono text-[10px] hover:border-signal/40 hover:text-signal"
            >
              #{id}
            </a>
          ))}
        </div>
        {ruledOut.length > 0 && (
          <ul className="mt-2 space-y-0.5 text-[11.5px] text-muted-foreground">
            {ruledOut.map((reason) => (
              <li key={reason}>
                <span className="text-sev3">Ruled out</span> — {reason}
              </li>
            ))}
          </ul>
        )}
      </div>
    )
  }

  if (event.type === 'remediation.proposed' || event.type === 'remediation.reused') {
    return <ProposalPreview proposalId={String(payload.proposal_id)} />
  }

  if (
    event.type.startsWith('execution.') ||
    event.type.startsWith('verification.') ||
    event.type.startsWith('rollback.')
  ) {
    const detail = payload.reason ?? payload.error ?? payload.query ?? payload.action
    return detail ? (
      <p className="font-mono text-[10.5px] text-muted-foreground">{String(detail)}</p>
    ) : null
  }

  if (event.type === 'incident.opened') {
    return (
      <p className="font-mono text-[10.5px] text-muted-foreground">
        error ratio <span className="text-sev1">{formatRatio(payload.error_ratio)}</span> ·{' '}
        {String(payload.request_rate)} req/s · threshold {formatRatio(payload.threshold)}
      </p>
    )
  }

  if (event.type === 'investigation.failed' || event.type === 'handler.failed') {
    return <p className="text-[11.5px] text-sev2">{String(payload.reason ?? payload.error)}</p>
  }

  return null
}

function ProposalPreview({ proposalId }: { proposalId: string }) {
  const proposal = useProposal(proposalId)
  if (!proposal.data) return <div className="mt-2 h-28 animate-pulse rounded-lg bg-white/[0.03]" />
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
