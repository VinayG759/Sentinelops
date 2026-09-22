import { useProposal, useProposals } from './api'
import { ApprovalCard } from './ApprovalCard'

export function ApprovalsPage() {
  const pending = useProposals('pending')
  const recent = useProposals()

  const decided = (recent.data ?? []).filter((p) => p.status !== 'pending').slice(0, 5)

  return (
    <div className="max-w-3xl">
      <h1 className="text-lg font-semibold tracking-tight">Approvals</h1>
      <p className="mt-1 text-muted-foreground">
        Every change SentinelOps wants to make waits here. Nothing runs until a human approves it.
      </p>

      {pending.data?.length === 0 ? (
        <div className="mt-6 rounded-lg border border-dashed p-10 text-center">
          <p className="font-medium">Nothing waiting for approval</p>
          <p className="mt-1 text-muted-foreground">
            Proposals appear here after the agent finishes investigating an incident.
          </p>
        </div>
      ) : (
        <div className="mt-6 space-y-4">
          {pending.data?.map((p) => <LoadedCard key={p.id} id={p.id} />)}
        </div>
      )}

      {decided.length > 0 && (
        <>
          <h2 className="mt-10 text-sm font-medium text-muted-foreground">Recently decided</h2>
          <table className="mt-2 w-full">
            <tbody>
              {decided.map((p) => (
                <tr key={p.id} className="border-b last:border-0">
                  <td className="py-2 pr-3 font-mono text-xs">{p.action}</td>
                  <td className="py-2 pr-3 text-muted-foreground">{p.status}</td>
                  <td className="py-2 font-mono text-[11px] text-muted-foreground">
                    {p.id.slice(0, 8)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  )
}

/** The list gives ids; the card needs the full detail (live preview from the cluster). */
function LoadedCard({ id }: { id: string }) {
  const proposal = useProposal(id)
  if (!proposal.data) return null
  return <ApprovalCard proposal={proposal.data} showIncidentLink />
}
