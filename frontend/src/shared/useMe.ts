import { useQuery } from '@tanstack/react-query'
import { api } from './api'
import type { Role } from './types'

const rank: Record<Role, number> = { viewer: 0, responder: 1, approver: 2, admin: 3 }

/** The signed-in user as the backend sees them (token verified, role from the database). */
export function useMe() {
  const query = useQuery({
    queryKey: ['me'],
    queryFn: () => api<{ id: string; email: string | null; role: Role }>('/api/me'),
    staleTime: 60_000,
  })
  const can = (minimum: Role) => !!query.data && rank[query.data.role] >= rank[minimum]
  return { ...query, can }
}
