import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { ProposalDetail } from '@/shared/types'
import { useMe } from '@/shared/useMe'
import { useDecide } from './api'

const riskStyle: Record<ProposalDetail['risk'], string> = {
  low: 'bg-zinc-100 text-zinc-700',
  medium: 'bg-amber-50 text-amber-800 ring-1 ring-amber-600/20',
  high: 'bg-red-50 text-red-700 ring-1 ring-red-600/20',
}

/**
 * The remediation shown the way engineers already review changes: what changes, why,
 * who it affects, how we will know it worked, and how to undo it — then Approve / Reject.
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

  useEffect(() => {
    if (!canDecide) return
    const onKey = (e: KeyboardEvent) => {
      const typing = (e.target as HTMLElement)?.tagName === 'INPUT'
      if (typing || e.metaKey || e.ctrlKey) return
      if (e.key.toLowerCase() === 'a') decide.mutate({ id: proposal.id, decision: 'approve', reason })
      if (e.key.toLowerCase() === 'r') decide.mutate({ id: proposal.id, decision: 'reject', reason })
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [canDecide, decide, proposal.id, reason])

  return (
    <div className="rounded-lg border">
      <div className="flex items-center justify-between gap-3 border-b bg-muted/30 px-4 py-2.5">
        <div className="flex items-center gap-2">
          <span className="font-medium">{proposal.title}</span>
          <code className="font-mono text-[11px] text-muted-foreground">{proposal.action}</code>
        </div>
        <div className="flex items-center gap-2 text-[11px]">
          <span className={cn('rounded px-1.5 py-0.5 font-medium uppercase', riskStyle[proposal.risk])}>
            {proposal.risk} risk
          </span>
          <span className="text-muted-foreground">
            {proposal.approvals_required} approval{proposal.approvals_required > 1 ? 's' : ''} required
          </span>
          <StatusPill status={proposal.status} />
        </div>
      </div>

      <div className="space-y-3 px-4 py-3">
        <Field label="Change">
          <p>{proposal.preview.summary}</p>
          <div className="mt-1.5 space-y-0.5 font-mono text-[11px]">
            {proposal.preview.changes?.map((change) => (
              <div key={change.field} className="flex flex-wrap gap-2">
                <span className="text-muted-foreground">{change.field}</span>
                <span className="text-red-700">- {String(change.from)}</span>
                <span className="text-emerald-700">+ {String(change.to)}</span>
              </div>
            ))}
          </div>
        </Field>

        <Field label="Why">{proposal.rationale}</Field>
        <Field label="Affects">
          <span className="font-mono text-[11px]">{proposal.affected_services.join(', ')}</span>
        </Field>
        <Field label="Verify">
          <code className="font-mono text-[11px] break-all">{proposal.verify_query}</code>
          <p className="mt-0.5 text-muted-foreground">
            Checked for 2 minutes after execution. If it fails, the change is undone automatically.
          </p>
        </Field>
        <Field label="Rollback">{proposal.rollback_plan}</Field>
        <Field label="Policy">
          <ul className="list-inside list-disc text-muted-foreground">
            {proposal.policy_reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </Field>
        {showIncidentLink && (
          <Field label="Incident">
            <Link to={`/incidents/${proposal.incident_id}`} className="underline underline-offset-4">
              {proposal.incident_id.slice(0, 8)}
            </Link>
          </Field>
        )}
      </div>

      {canDecide && (
        <div className="flex items-center gap-2 border-t px-4 py-2.5">
          <input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Reason (optional)"
            className="h-8 flex-1 rounded-md border bg-background px-2.5 text-sm"
          />
          <Button
            size="sm"
            variant="outline"
            disabled={decide.isPending}
            onClick={() => decide.mutate({ id: proposal.id, decision: 'reject', reason })}
          >
            Reject <kbd className="ml-1.5 font-mono text-[10px] text-muted-foreground">R</kbd>
          </Button>
          <Button
            size="sm"
            disabled={decide.isPending}
            onClick={() => decide.mutate({ id: proposal.id, decision: 'approve', reason })}
          >
            Approve <kbd className="ml-1.5 font-mono text-[10px] opacity-70">A</kbd>
          </Button>
        </div>
      )}
      {!can('approver') && pending && (
        <p className="border-t px-4 py-2.5 text-muted-foreground">
          Waiting for an approver. Your role cannot approve changes.
        </p>
      )}
      {decide.isError && (
        <p className="border-t px-4 py-2.5 text-destructive">{decide.error.message}</p>
      )}
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[88px_1fr] gap-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="min-w-0">{children}</div>
    </div>
  )
}

function StatusPill({ status }: { status: ProposalDetail['status'] }) {
  const style =
    status === 'pending'
      ? 'bg-amber-50 text-amber-800'
      : status === 'approved' || status === 'executed'
        ? 'bg-emerald-50 text-emerald-700'
        : 'bg-zinc-100 text-zinc-600'
  return <span className={cn('rounded px-1.5 py-0.5 font-medium', style)}>{status}</span>
}
