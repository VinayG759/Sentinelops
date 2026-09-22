import { AlertTriangle } from 'lucide-react'
import type { UseQueryResult } from '@tanstack/react-query'
import type { ReactNode } from 'react'

/**
 * One place that decides what a screen shows while data is loading or missing.
 * Silent blank panels were hiding real outages, so failure is always visible.
 */
export function Loadable<T>({
  query,
  skeleton,
  empty,
  isEmpty,
  children,
}: {
  query: UseQueryResult<T>
  skeleton?: ReactNode
  empty?: ReactNode
  isEmpty?: (data: T) => boolean
  children: (data: T) => ReactNode
}) {
  if (query.isPending) return <>{skeleton ?? <div className="panel h-28 animate-pulse" />}</>
  if (query.isError) return <ErrorNote message={query.error.message} />
  if (query.data === undefined) return <ErrorNote message="No data returned." />
  if (empty && isEmpty?.(query.data)) return <>{empty}</>
  return <>{children(query.data)}</>
}

export function ErrorNote({ message }: { message: string }) {
  return (
    <div className="panel flex items-start gap-2.5 border-sev2/25 px-4 py-3">
      <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-sev2" />
      <div>
        <p className="text-[12.5px] text-sev2">Could not load this</p>
        <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">{message}</p>
      </div>
    </div>
  )
}
