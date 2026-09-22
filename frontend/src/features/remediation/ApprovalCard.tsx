import { Check, Clock, GitPullRequest, RotateCcw, ShieldCheck, Target, X } from 'lucide-react'
import { motion } from 'motion/react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { ProposalDetail } from '@/shared/types'
import { StatusDot, Tag, type Tone } from '@/shared/ui/primitives'
import { useMe } from '@/shared/useMe'
import { useDecide } from './api'

const riskTone: Record<ProposalDetail['risk'], Tone> = { low: 'ok', medium: 'sev2', high: 'sev1' }

/**
 * Remediation reviewed the way engineers already review change: a proposed diff, the
 * reasoning, the blast radius, the check that will prove it, and the way back.
 * Keyboard: A approves, R rejects.
 */
export function ApprovalCard({
  proposal,
  showIncidentLink = false,
}: {
  proposal: ProposalDetail
  showIncidentLink?: boolean
}) {
  const decide = useDecide()
  const { can } = useMe()
  const [reason, setReason] = useState('')
  const pending = proposal.status === 'pending'
  const canDecide = can('approver') && pending
  const tone = riskTone[proposal.risk]

  const act = (decision: 'approve' | 'reject') => {
    decide.mutate(
      { id: proposal.id, decision, reason },
      {
        onSuccess: () =>
          decision === 'approve'
            ? toast.success('Approved — executing now', {
                description: 'Recovery is verified for 2 minutes; a failed fix is undone automatically.',
              })
            : toast('Rejected', { description: 'Nothing was changed.' }),
        onError: (error) => toast.error('Could not record decision', { description: error.message }),
      },
    )
  }

  useEffect(() => {
    if (!canDecide) return
    const onKey = (e: KeyboardEvent) => {
      const typing = ['INPUT', 'TEXTAREA'].includes((e.target as HTMLElement)?.tagName)
      if (typing || e.metaKey || e.ctrlKey) return
      if (e.key.toLowerCase() === 'a') act('approve')
      if (e.key.toLowerCase() === 'r') act('reject')
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn('panel overflow-hidden', pending && 'glow-signal')}
    >
      <header className="flex flex-wrap items-center gap-3 border-b border-hairline bg-surface-raised/60 px-4 py-3">
        <GitPullRequest className="size-4 text-signal" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="font-medium">{proposal.title}</span>
            <code className="font-mono text-[10.5px] text-muted-foreground">{proposal.action}</code>
          </div>
          <p className="mt-0.5 text-[11.5px] text-muted-foreground">{proposal.description}</p>
        </div>
        <div className="flex items-center gap-2">
          <Tag tone={tone}>{proposal.risk} risk</Tag>
          <Tag tone={pending ? 'signal' : proposal.status === 'executed' ? 'ok' : 'muted'}>
            {pending && <StatusDot tone="signal" live />}
            {proposal.status}
          </Tag>
        </div>
      </header>

      <div className="grid gap-px bg-hairline md:grid-cols-[1.25fr_1fr]">
        <div className="bg-surface p-4">
          <Label>Proposed change</Label>
          <p className="mt-1 text-[12.5px]">
            {proposal.preview.summary === 'preview unavailable' ? (
              <span className="text-sev2">
                Live preview unavailable — the cluster is unreachable right now. The change itself
                is unaffected: {proposal.action}({formatParams(proposal.params)}).
              </span>
            ) : (
              proposal.preview.summary
            )}
          </p>
          <div className="mt-2 overflow-hidden rounded-lg border border-hairline font-mono text-[11.5px] empty:hidden">
            {proposal.preview.changes?.map((change) => (
              <div key={change.field} className="divide-y divide-hairline">
                <div className="bg-surface-sunken px-3 py-1.5 text-[10.5px] text-muted-foreground">
                  {change.field}
                </div>
                <div className="bg-sev1/8 px-3 py-1.5 text-sev1">- {String(change.from)}</div>
                <div className="bg-ok/8 px-3 py-1.5 text-ok">+ {String(change.to)}</div>
              </div>
            ))}
          </div>

          <Label className="mt-4">Why</Label>
          <p className="mt-1 text-[12.5px]">{proposal.rationale}</p>
        </div>

        <div className="space-y-3 bg-surface p-4">
          <Detail icon={Target} label="Affects">
            <div className="flex flex-wrap gap-1">
              {proposal.affected_services.map((service) => (
                <Tag key={service}>{service}</Tag>
              ))}
            </div>
          </Detail>

          <Detail icon={ShieldCheck} label="Verified by">
            <code className="block break-all font-mono text-[10.5px] text-muted-foreground">
              {proposal.verify_query}
            </code>
            <p className="mt-0.5 text-[11px] text-muted-foreground">
              Checked for 2 minutes. A fix that doesn&apos;t work is undone automatically.
            </p>
          </Detail>

          <Detail icon={RotateCcw} label="Rollback">
            <p className="text-[11.5px] text-muted-foreground">{proposal.rollback_plan}</p>
          </Detail>

          <Detail icon={Clock} label="Policy">
            <ul className="space-y-0.5 text-[11.5px] text-muted-foreground">
              {proposal.policy_reasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </Detail>

          {showIncidentLink && (
            <Link
              to={`/incidents/${proposal.incident_id}`}
              className="inline-block font-mono text-[11px] text-signal hover:underline"
            >
              incident {proposal.incident_id.slice(0, 8)} →
            </Link>
          )}
        </div>
      </div>

      {canDecide ? (
        <footer className="flex flex-wrap items-center gap-2 border-t border-hairline bg-surface-raised/40 px-4 py-3">
          <input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Reason (optional)"
            className="h-9 min-w-40 flex-1 rounded-lg border border-hairline bg-surface-sunken px-3 text-[12.5px] outline-none placeholder:text-muted-foreground focus:border-signal/40"
          />
          <Button size="sm" variant="outline" disabled={decide.isPending} onClick={() => act('reject')}>
            <X className="size-3.5" /> Reject <Kbd>R</Kbd>
          </Button>
          <Button
            size="sm"
            disabled={decide.isPending}
            onClick={() => act('approve')}
            className="bg-signal text-primary-foreground hover:bg-signal/90"
          >
            <Check className="size-3.5" /> Approve <Kbd className="opacity-70">A</Kbd>
          </Button>
        </footer>
      ) : (
        pending && (
          <footer className="border-t border-hairline px-4 py-3 text-[12px] text-muted-foreground">
            Waiting for an approver — your role cannot approve changes.
          </footer>
        )
      )}
    </motion.div>
  )
}

function formatParams(params: Record<string, unknown>): string {
  return Object.entries(params)
    .map(([key, value]) => `${key}=${value}`)
    .join(', ')
}

function Label({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={cn('text-[10.5px] uppercase tracking-wider text-muted-foreground', className)}>
      {children}
    </div>
  )
}

function Detail({
  icon: Icon,
  label,
  children,
}: {
  icon: typeof Target
  label: string
  children: React.ReactNode
}) {
  return (
    <div className="flex gap-2.5">
      <Icon className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
      <div className="min-w-0 flex-1">
        <Label>{label}</Label>
        <div className="mt-1">{children}</div>
      </div>
    </div>
  )
}

function Kbd({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <kbd className={cn('ml-1 rounded border border-white/15 px-1 font-mono text-[9.5px]', className)}>
      {children}
    </kbd>
  )
}
