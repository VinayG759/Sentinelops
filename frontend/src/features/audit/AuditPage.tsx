import { useQueryClient } from '@tanstack/react-query'
import { ChevronRight, Download, ShieldAlert, ShieldCheck, ShieldQuestion } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { absoluteTime, relativeTime } from '@/shared/time'
import type { AuditEvent, ChainStatus } from '@/shared/types'
import { Loadable } from '@/shared/ui/Loadable'
import { StatusDot, Tag, type Tone } from '@/shared/ui/primitives'
import { PAGE, downloadExport, useAuditEvents, useChainStatus, useVerifyChain } from './api'

/** `incident.opened` -> `incident`. The facet rail groups by this. */
const category = (type: string) => type.split('.')[0]
/** `user:9f3c...` -> `user`, so the rail has a few actors rather than one per person. */
const actorKind = (actor: string) => (actor.startsWith('user:') ? 'user' : actor)

const categoryTone: Record<string, Tone> = {
  incident: 'sev1',
  investigation: 'signal',
  remediation: 'sev2',
  execution: 'sev2',
  verification: 'ok',
  rollback: 'sev1',
  handler: 'sev1',
  autonomy: 'muted',
}

/**
 * The audit trail: every event the system has ever recorded, and proof that none of them has
 * been altered. Each event's hash covers the previous event's hash plus its own contents, so
 * editing any row breaks every row after it — and the badge says so.
 */
export function AuditPage() {
  const status = useChainStatus()
  const [beforeId, setBeforeId] = useState<number | undefined>()
  const events = useAuditEvents(beforeId)
  const [categories, setCategories] = useState<Set<string> | null>(null)
  const [actors, setActors] = useState<Set<string> | null>(null)
  const [expanded, setExpanded] = useState<number | null>(null)

  const rows = useMemo(() => events.data ?? [], [events.data])
  const allCategories = useMemo(
    () => [...new Set(rows.map((e) => category(e.type)))].sort(),
    [rows],
  )
  const allActors = useMemo(() => [...new Set(rows.map((e) => actorKind(e.actor)))].sort(), [rows])
  const visible = rows.filter(
    (e) =>
      (categories === null || categories.has(category(e.type))) &&
      (actors === null || actors.has(actorKind(e.actor))),
  )
  const oldest = rows.at(-1)?.id

  const toggle = (
    value: string,
    all: string[],
    current: Set<string> | null,
    set: (next: Set<string> | null) => void,
  ) => {
    const next = new Set(current ?? all)
    if (next.has(value)) next.delete(value)
    else next.add(value)
    set(next.size === all.length ? null : next)
  }

  return (
    <div className="mx-auto max-w-[1400px]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">Audit</h1>
          <p className="text-[12px] text-muted-foreground">
            Every event, in the order it happened, sealed in a hash chain. Nothing here can be
            edited or deleted — and if it were, the check below would say so.
          </p>
        </div>
        <Button size="sm" variant="outline" onClick={() => void downloadExport()}>
          <Download className="size-3.5" />
          Export chain
        </Button>
      </div>

      <div className="mt-4">
        <ChainBadge query={status} />
      </div>

      <div className="mt-5 grid items-start gap-5 lg:grid-cols-[200px_1fr]">
        <aside className="space-y-5 lg:sticky lg:top-20">
          <Facet title="Category">
            {allCategories.map((name) => (
              <Check
                key={name}
                label={name}
                count={rows.filter((e) => category(e.type) === name).length}
                checked={categories === null || categories.has(name)}
                onChange={() => toggle(name, allCategories, categories, setCategories)}
              />
            ))}
          </Facet>
          <Facet title="Actor">
            {allActors.map((name) => (
              <Check
                key={name}
                label={name}
                count={rows.filter((e) => actorKind(e.actor) === name).length}
                checked={actors === null || actors.has(name)}
                onChange={() => toggle(name, allActors, actors, setActors)}
              />
            ))}
          </Facet>
          <button
            onClick={() => {
              setCategories(null)
              setActors(null)
            }}
            className="text-[11.5px] text-signal underline-offset-4 hover:underline"
          >
            Reset filters
          </button>
        </aside>

        <div className="min-w-0">
          <Loadable
            query={events}
            skeleton={<div className="panel h-96 animate-pulse" />}
            isEmpty={(data) => data.length === 0}
            empty={
              <div className="panel px-6 py-16 text-center">
                <p className="font-medium">No events recorded yet</p>
                <p className="mt-1 text-[12px] text-muted-foreground">
                  The chain fills as the system works. Break something in the{' '}
                  <Link to="/simulator" className="text-signal underline-offset-4 hover:underline">
                    Simulator
                  </Link>{' '}
                  to start it.
                </p>
              </div>
            }
          >
            {() => (
              <div className="panel overflow-x-auto">
                <table className="w-full min-w-[820px] text-left">
                  <thead>
                    <tr className="border-b border-hairline text-[10.5px] uppercase tracking-wider text-muted-foreground">
                      <th className="w-[62px] py-2.5 pl-4 font-normal">#</th>
                      <th className="font-normal">Event</th>
                      <th className="w-[110px] font-normal">Actor</th>
                      <th className="w-[108px] font-normal">Incident</th>
                      <th className="w-[96px] font-normal">When</th>
                      <th className="w-[140px] pr-4 font-normal">Hash</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-hairline">
                    {visible.map((event) => (
                      <EventRow
                        key={event.id}
                        event={event}
                        broken={status.data?.first_broken_id === event.id}
                        open={expanded === event.id}
                        onToggle={() => setExpanded(expanded === event.id ? null : event.id)}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Loadable>

          <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
            <p className="text-[11px] text-muted-foreground">
              {visible.length} of {rows.length} events on this page
              {status.data && ` · ${status.data.checked} in the chain`}
            </p>
            <div className="flex gap-2">
              {beforeId !== undefined && (
                <Button size="xs" variant="ghost" onClick={() => setBeforeId(undefined)}>
                  Back to newest
                </Button>
              )}
              {rows.length === PAGE && oldest !== undefined && (
                <Button size="xs" variant="outline" onClick={() => setBeforeId(oldest)}>
                  Older events
                </Button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

/** The headline: is the chain intact? Deliberately a button, not a poll. */
function ChainBadge({ query }: { query: ReturnType<typeof useChainStatus> }) {
  const verify = useVerifyChain()
  const queryClient = useQueryClient()
  const status: ChainStatus | undefined = query.data
  const checking = query.isPending || verify.isPending
  const broken = status !== undefined && !status.valid

  const tone: Tone = checking ? 'muted' : broken ? 'sev1' : status ? 'ok' : 'muted'
  const Icon = checking ? ShieldQuestion : broken ? ShieldAlert : ShieldCheck

  return (
    <div
      className={cn(
        'panel flex flex-wrap items-center justify-between gap-4 px-5 py-4 ring-1 ring-inset',
        checking && 'ring-white/8',
        !checking && broken && 'bg-sev1/[0.04] ring-sev1/30',
        !checking && !broken && status && 'bg-ok/[0.03] ring-ok/25',
      )}
    >
      <div className="flex items-center gap-3.5">
        <div
          className={cn(
            'flex size-10 shrink-0 items-center justify-center rounded-full ring-1',
            broken ? 'bg-sev1/10 ring-sev1/25' : 'bg-ok/10 ring-ok/25',
            checking && 'bg-white/5 ring-white/10',
          )}
        >
          <Icon
            className={cn(
              'size-5',
              checking ? 'text-muted-foreground' : broken ? 'text-sev1' : 'text-ok',
            )}
          />
        </div>
        <div>
          <p className="flex items-center gap-2 font-medium">
            <StatusDot tone={tone} live={checking} />
            {checking
              ? 'Verifying chain...'
              : broken
                ? `Chain broken at event #${status.first_broken_id}`
                : status
                  ? 'Chain verified'
                  : 'Chain not yet verified'}
          </p>
          <p className="mt-0.5 text-[11.5px] text-muted-foreground">
            {broken
              ? `Event #${status.first_broken_id} no longer matches its hash. Everything after it is untrustworthy.`
              : status
                ? `All ${status.checked} events recomputed and matched, in ${status.took_ms} ms.`
                : "Recompute every event's hash from its contents and the event before it."}
          </p>
          {status && (
            <p
              className="mt-1 font-mono text-[10.5px] text-muted-foreground"
              title={absoluteTime(status.verified_at)}
            >
              checked {relativeTime(status.verified_at)}
            </p>
          )}
        </div>
      </div>
      <Button
        size="sm"
        variant={broken ? 'destructive' : 'outline'}
        disabled={checking}
        onClick={() => {
          verify.mutate()
          void queryClient.invalidateQueries({ queryKey: ['audit', 'events'] })
        }}
      >
        {checking ? 'Verifying...' : 'Verify chain'}
      </Button>
    </div>
  )
}

function EventRow({
  event,
  broken,
  open,
  onToggle,
}: {
  event: AuditEvent
  broken: boolean
  open: boolean
  onToggle: () => void
}) {
  const tone = categoryTone[category(event.type)] ?? 'muted'

  return (
    <>
      <tr
        onClick={onToggle}
        className={cn(
          'cursor-pointer align-top transition-colors hover:bg-white/[0.02]',
          broken && 'bg-sev1/[0.07]',
        )}
      >
        <td className="py-2.5 pl-4 font-mono text-[11px] text-muted-foreground">
          <span className="flex items-center gap-1">
            <ChevronRight className={cn('size-3 transition-transform', open && 'rotate-90')} />
            {event.id}
          </span>
        </td>
        <td className="py-2.5 pr-4">
          <span className="flex items-center gap-2">
            <Tag tone={tone}>{category(event.type)}</Tag>
            <span className="font-mono text-[11.5px]">{event.type}</span>
            {broken && <Tag tone="sev1">tampered</Tag>}
          </span>
        </td>
        <td className="py-2.5 pr-4 font-mono text-[11px] text-muted-foreground">
          {actorKind(event.actor)}
        </td>
        <td className="py-2.5 pr-4 font-mono text-[11px]">
          {event.incident_id ? (
            <Link
              to={`/incidents/${event.incident_id}`}
              onClick={(e) => e.stopPropagation()}
              className="text-signal underline-offset-4 hover:underline"
            >
              {event.incident_id.slice(0, 8)}
            </Link>
          ) : (
            <span className="text-muted-foreground">—</span>
          )}
        </td>
        <td
          className="py-2.5 pr-4 font-mono text-[11px] text-muted-foreground"
          title={absoluteTime(event.created_at)}
        >
          {relativeTime(event.created_at)}
        </td>
        <td className="py-2.5 pr-4 font-mono text-[10.5px] text-muted-foreground">
          {event.hash.slice(0, 16)}...
        </td>
      </tr>
      {open && (
        <tr className={cn('bg-white/[0.015]', broken && 'bg-sev1/[0.05]')}>
          <td colSpan={6} className="px-4 py-3">
            <div className="grid gap-3 lg:grid-cols-[1fr_320px]">
              <div>
                <Label>Payload</Label>
                <pre className="mt-1 max-h-72 overflow-auto rounded-md bg-black/30 p-3 font-mono text-[11px] leading-relaxed">
                  {JSON.stringify(event.payload, null, 2)}
                </pre>
              </div>
              <div className="space-y-3">
                <div>
                  <Label>Actor</Label>
                  <p className="mt-1 break-all font-mono text-[11px]">{event.actor}</p>
                </div>
                <div>
                  <Label>Recorded</Label>
                  <p className="mt-1 font-mono text-[11px]">{absoluteTime(event.created_at)}</p>
                </div>
                <div>
                  <Label>Previous hash</Label>
                  <p className="mt-1 break-all font-mono text-[10.5px] text-muted-foreground">
                    {event.prev_hash}
                  </p>
                </div>
                <div>
                  <Label>This hash</Label>
                  <p className="mt-1 break-all font-mono text-[10.5px]">{event.hash}</p>
                </div>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

function Label({ children }: { children: React.ReactNode }) {
  return (
    <span className="text-[10.5px] uppercase tracking-wider text-muted-foreground">{children}</span>
  )
}

function Facet({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <fieldset>
      <legend className="mb-1.5 text-[10.5px] uppercase tracking-wider text-muted-foreground">
        {title}
      </legend>
      <div className="space-y-0.5">{children}</div>
    </fieldset>
  )
}

function Check({
  label,
  count,
  checked,
  onChange,
}: {
  label: string
  count: number
  checked: boolean
  onChange: () => void
}) {
  return (
    <label className="flex cursor-pointer items-center gap-2 rounded-md px-1.5 py-1 text-[12px] hover:bg-white/[0.03]">
      <input
        type="checkbox"
        checked={checked}
        onChange={onChange}
        className="size-3.5 accent-[var(--signal)]"
      />
      <span
        className={cn('flex-1 truncate font-mono text-[11.5px]', !checked && 'text-muted-foreground')}
      >
        {label}
      </span>
      <span className="font-mono text-[10.5px] text-muted-foreground">{count}</span>
    </label>
  )
}
