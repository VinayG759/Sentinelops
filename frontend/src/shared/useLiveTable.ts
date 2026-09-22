import { useQueryClient, type QueryKey } from '@tanstack/react-query'
import { useEffect, useId } from 'react'
import { supabase } from './supabase'

/**
 * Refetch `queryKey` whenever rows in `table` change (Supabase Realtime).
 * Realtime only says "something changed"; the backend API stays the source of truth.
 *
 * The channel name includes a per-subscriber id: supabase.channel() returns the *same*
 * channel for a repeated name, and attaching another listener to an already-subscribed
 * channel throws. Two components watching the same table must each get their own.
 */
export function useLiveTable(table: string, queryKey: QueryKey) {
  const queryClient = useQueryClient()
  const subscriberId = useId()
  const key = JSON.stringify(queryKey)

  useEffect(() => {
    const channel = supabase
      .channel(`live:${table}:${subscriberId}`)
      .on('postgres_changes', { event: '*', schema: 'public', table }, () => {
        queryClient.invalidateQueries({ queryKey: JSON.parse(key) as QueryKey })
      })
      .subscribe()
    return () => {
      supabase.removeChannel(channel)
    }
  }, [table, key, subscriberId, queryClient])
}
