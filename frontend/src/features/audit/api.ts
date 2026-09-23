import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { supabase } from '@/shared/supabase'
import { api } from '@/shared/api'
import type { AuditEvent, ChainStatus } from '@/shared/types'
import { useLiveTable } from '@/shared/useLiveTable'

export const PAGE = 200

/** The chain check. Not polled — it is a deliberate act, so the badge reflects a real moment. */
export function useChainStatus() {
  return useQuery({
    queryKey: ['audit', 'verify'],
    queryFn: () => api<ChainStatus>('/api/audit/verify'),
    refetchOnWindowFocus: false,
    staleTime: Infinity,
  })
}

export function useVerifyChain() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api<ChainStatus>('/api/audit/verify'),
    onSuccess: (status) => queryClient.setQueryData(['audit', 'verify'], status),
  })
}

/** Newest events first. `beforeId` pages backwards; undefined loads the head of the chain. */
export function useAuditEvents(beforeId?: number) {
  useLiveTable('events', ['audit', 'events'])
  return useQuery({
    queryKey: ['audit', 'events', beforeId ?? 'head'],
    queryFn: () =>
      api<AuditEvent[]>(`/api/audit/events?limit=${PAGE}${beforeId ? `&before_id=${beforeId}` : ''}`),
    placeholderData: (previous) => previous,
  })
}

/** The export endpoint streams a file, so it needs the token on a plain fetch. */
export async function downloadExport() {
  const { data } = await supabase.auth.getSession()
  const res = await fetch('/api/audit/export', {
    headers: { Authorization: `Bearer ${data.session?.access_token ?? ''}` },
  })
  if (!res.ok) throw new Error(`Export failed (${res.status})`)
  const url = URL.createObjectURL(await res.blob())
  const link = document.createElement('a')
  link.href = url
  link.download = 'sentinelops-audit.jsonl'
  link.click()
  URL.revokeObjectURL(url)
}
