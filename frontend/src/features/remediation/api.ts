import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/shared/api'
import type { Proposal, ProposalDetail } from '@/shared/types'
import { useLiveTable } from '@/shared/useLiveTable'

export function useProposals(status?: Proposal['status']) {
  useLiveTable('proposals', ['proposals'])
  return useQuery({
    queryKey: ['proposals', status ?? 'all'],
    queryFn: () => api<Proposal[]>(`/api/proposals${status ? `?status=${status}` : ''}`),
  })
}

export function useProposal(id: string | undefined) {
  return useQuery({
    queryKey: ['proposal', id],
    queryFn: () => api<ProposalDetail>(`/api/proposals/${id}`),
    enabled: !!id,
  })
}

export function useDecide() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, decision, reason }: { id: string; decision: 'approve' | 'reject'; reason?: string }) =>
      api<Proposal>(`/api/proposals/${id}/${decision}`, {
        method: 'POST',
        body: JSON.stringify({ reason: reason ?? '' }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['proposals'] })
      queryClient.invalidateQueries({ queryKey: ['proposal'] })
    },
  })
}

export function useAutonomy() {
  const queryClient = useQueryClient()
  useLiveTable('settings', ['autonomy'])
  const query = useQuery({
    queryKey: ['autonomy'],
    queryFn: () => api<{ paused: boolean }>('/api/settings/autonomy'),
  })
  const set = useMutation({
    mutationFn: (paused: boolean) =>
      api<{ paused: boolean }>('/api/settings/autonomy', {
        method: 'POST',
        body: JSON.stringify({ paused }),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['autonomy'] }),
  })
  return { paused: query.data?.paused ?? false, set }
}
