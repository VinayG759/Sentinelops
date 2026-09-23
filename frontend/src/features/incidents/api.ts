import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/shared/api'
import type { Incident, IncidentEvent } from '@/shared/types'
import { useLiveTable } from '@/shared/useLiveTable'

/** Metrics endpoint returns raw series; typed here rather than generated (no response model). */
export type IncidentMetrics = {
  service: string
  opened_at: string
  resolved_at: string | null
  series: {
    error_ratio: [number, number][]
    requests_per_second: [number, number][]
    p95_latency_ms: [number, number][]
  }
}

export function useIncident(id: string) {
  useLiveTable('incidents', ['incidents'])
  return useQuery({ queryKey: ['incident', id], queryFn: () => api<Incident>(`/api/incidents/${id}`) })
}

export function useIncidentEvents(id: string) {
  useLiveTable('events', ['incident-events', id])
  return useQuery({
    queryKey: ['incident-events', id],
    queryFn: () => api<IncidentEvent[]>(`/api/incidents/${id}/events`),
  })
}

export function useIncidentMetrics(id: string, minutes = 30) {
  return useQuery({
    queryKey: ['incident-metrics', id, minutes],
    queryFn: () => api<IncidentMetrics>(`/api/incidents/${id}/metrics?minutes=${minutes}`),
    refetchInterval: 15_000,
  })
}

export function useInvestigate(id: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api<{ status: string }>(`/api/incidents/${id}/investigate`, { method: 'POST' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['incident-events', id] }),
  })
}

export function useTransition() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, to }: { id: string; to: 'acknowledge' | 'resolve' }) =>
      api<Incident>(`/api/incidents/${id}/${to}`, { method: 'POST' }),
    onSuccess: (incident) => {
      queryClient.invalidateQueries({ queryKey: ['incidents'] })
      queryClient.invalidateQueries({ queryKey: ['incident', incident.id] })
    },
  })
}
