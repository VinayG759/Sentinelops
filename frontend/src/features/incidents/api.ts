import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/shared/api'
import type { Incident } from '@/shared/types'
import { useLiveTable } from '@/shared/useLiveTable'

export type IncidentStatus = Incident['status']

export function useIncidents(status: IncidentStatus) {
  const queryKey = ['incidents', status]
  useLiveTable('incidents', ['incidents'])
  return useQuery({
    queryKey,
    queryFn: () => api<Incident[]>(`/api/incidents?status=${status}`),
  })
}

export function useIncidentCounts() {
  return useQuery({
    queryKey: ['incidents', 'all'],
    queryFn: () => api<Incident[]>('/api/incidents'),
    select: (rows) => ({
      triggered: rows.filter((r) => r.status === 'triggered').length,
      acknowledged: rows.filter((r) => r.status === 'acknowledged').length,
      resolved: rows.filter((r) => r.status === 'resolved').length,
    }),
  })
}

export function useTransition() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, to }: { id: string; to: 'acknowledge' | 'resolve' }) =>
      api<Incident>(`/api/incidents/${id}/${to}`, { method: 'POST' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['incidents'] }),
  })
}
