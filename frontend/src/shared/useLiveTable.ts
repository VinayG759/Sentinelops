import { useQueryClient, type QueryKey } from '@tanstack/react-query'
import { useEffect } from 'react'
import { supabase } from './supabase'

/**
 * Refetch `queryKey` whenever rows in `table` change (Supabase Realtime).
 * Realtime only says "something changed"; the backend API stays the source of truth.
 */
export function useLiveTable(table: string, queryKey: QueryKey) {
  const queryClient = useQueryClient()
  const key = JSON.stringify(queryKey)

  useEffect(() => {
    const channel = supabase
      .channel(`live:${table}:${key}`)
      .on('postgres_changes', { event: '*', schema: 'public', table }, () => {
        queryClient.invalidateQueries({ queryKey })
      })
      .subscribe()
    return () => {
      supabase.removeChannel(channel)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- key is the stable form of queryKey
  }, [table, key, queryClient])
}
