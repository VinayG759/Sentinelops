import { useQueries, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { AlertTriangle, ArrowUpRight, CheckCircle2, Database, HelpCircle, Wrench, XOctagon } from 'lucide-react'
import { Link } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { api } from '@/shared/api'
import { serviceColor } from '@/shared/serviceColors'
import { useTimeRange } from '@/shared/timeRange'
import type { Incident, ProposalDetail, ServiceHealth } from '@/shared/types'
import { Tag, type Tone } from '@/shared/ui/primitives'
import { useLiveTable } from '@/shared/useLiveTable'
import { useProposals } from '@/features/remediation/api'
import { ServicePanel } from '@/features/overview/ServicePanel'
import { failureBlastRadius, targetNode } from './blastRadius'

type Status = ServiceHealth['status']

// Status colours only ever mean state, and always come with an icon and a word.
const STATUS: Record<Status, { tone: Tone; label: string; Icon: typeof CheckCircle2 }> = {
  healthy: { tone: 'ok', label: 'Healthy', Icon: CheckCircle2 },
  degraded: { tone: 'sev2', label: 'Degraded', Icon: AlertTriangle },
  critical: { tone: 'sev1', label: 'Critical', Icon: XOctagon },
  unknown: { tone: 'muted', label: 'Unknown', Icon: HelpCircle },
}
const border: Record<Tone, string> = {
  ok: 'border-ok/40',
  sev1: 'border-sev1/60',
  sev2: 'border-sev2/60',
  sev3: 'border-hairline',
  signal: 'border-signal/60',
  muted: 'border-hairline',
}

const toneText: Record<Tone, string> = {
  ok: 'text-ok',
  sev1: 'text-sev1',
  sev2: 'text-sev2',
  sev3: 'text-sev3',
  signal: 'text-signal',
  muted: 'text-muted-foreground',
}

// Canvas in SVG units; the map scales to its container width.
const W = 800
const NODE_W = 230
const NODE_H = 112
const ROW_GAP = 110
const PAD = 24

const percent = (v: number) => `${(v * 100).toFixed(v > 0 && v < 0.1 ? 1 : 0)}%`
const millis = (v: number) => (v >= 1000 ? `${Number((v / 1000).toFixed(1))} s` : `${Math.round(v)} ms`)

/** Depth in the dependency graph: things nothing is below (the database) sit at the bottom. */
function levels(services: ServiceHealth[]): Map<string, number> {
  const names = new Set(services.map((s) => s.name))
  const memo = new Map<string, number>()
  const level = (name: string, seen: Set<string>): number => {
    if (memo.has(name)) return memo.get(name)!
    if (seen.has(name)) return 0 // cycle guard
    seen.add(name)
    const deps = services.find((s) => s.name === name)?.depends_on.filter((d) => names.has(d)) ?? []
    const value = deps.length ? 1 + Math.max(...deps.map((d) => level(d, seen))) : 0
    memo.set(name, value)
    return value
  }
  services.forEach((s) => level(s.name, new Set()))
  return memo
}

function layout(services: ServiceHealth[]) {
  const depth = levels(services)
  const top = Math.max(0, ...depth.values())
  const rows = new Map<number, ServiceHealth[]>()
  services.forEach((s) => rows.set(depth.get(s.name)!, [...(rows.get(depth.get(s.name)!) ?? []), s]))
  const pos = new Map<string, { x: number; y: number }>()
  rows.forEach((row, lvl) => {
    const sorted = [...row].sort((a, b) => a.name.localeCompare(b.name))
    sorted.forEach((s, i) => {
      const x = (W * (i + 1)) / (sorted.length + 1) - NODE_W / 2
      pos.set(s.name, { x, y: PAD + (top - lvl) * (NODE_H + ROW_GAP) })
    })
  })
  return { pos, height: PAD * 2 + (top + 1) * NODE_H + top * ROW_GAP }
}

export function TopologyPage() {
  const { minutes, refetchEvery } = useTimeRange()
  const services = useQuery({
    queryKey: ['topology', minutes],
    queryFn: () => api<ServiceHealth[]>(`/api/topology?minutes=${minutes}`),
    refetchInterval: refetchEvery(10_000),
    placeholderData: (previous) => previous,
  })
  useLiveTable('incidents', ['incidents'])
  const incidents = useQuery({
    queryKey: ['incidents', 'overview'],
    queryFn: () => api<Incident[]>('/api/incidents'),
  })
  const pending = useProposals('pending')
  // The list has no target / affected services; the approval card (detail) does.
  const fixes = useQueries({
    queries: (pending.data ?? []).map((p) => ({
      queryKey: ['proposal', p.id],
      queryFn: () => api<ProposalDetail>(`/api/proposals/${p.id}`),
    })),
  })
  const [selected, setSelected] = useState<string | null>(null)

  const all = services.data ?? []
  const names = all.map((s) => s.name)
  const open = (incidents.data ?? []).filter((i) => i.status !== 'resolved')
  const openFor = (name: string) => open.filter((i) => i.service === name).length
  const broken = all.filter((s) => s.status === 'degraded' || s.status === 'critical' || openFor(s.name) > 0)
  const brokenNames = broken.map((s) => s.name)
  const atRisk = failureBlastRadius(all, brokenNames)

  const proposals = fixes.flatMap((q) => (q.data ? [q.data] : []))
  const fixTargets = new Set(proposals.map((p) => (p.target ? targetNode(p.target, names) : null)).filter(Boolean) as string[])
  const fixAffected = new Set(proposals.flatMap((p) => p.affected_services))

  const { pos, height } = layout(all)

  return (
    <div className="mx-auto max-w-[1400px] space-y-5">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">Topology</h1>
        <p className="text-[12px] text-muted-foreground">
          What is broken, and what does it take down with it? Every node is a service in the registry;
          an arrow means “calls / depends on”. Status is live from Prometheus and Kubernetes.
        </p>
      </div>

      <div className="panel overflow-hidden p-2">
        {services.isError ? (
          <p className="p-6 text-[12.5px] text-muted-foreground">
            Live health is unavailable (Prometheus or Kubernetes unreachable).
          </p>
        ) : services.isLoading ? (
          <div className="h-[380px] animate-pulse" />
        ) : (
          <svg viewBox={`0 0 ${W} ${height}`} className="mx-auto block w-full max-w-[900px]" role="group" aria-label="Service dependency map">
            <defs>
              {(['muted', 'sev1'] as const).map((t) => (
                <marker key={t} id={`arrow-${t}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                  <path d="M0,0 L10,5 L0,10 z" className={t === 'sev1' ? 'fill-sev1' : 'fill-muted-foreground'} />
                </marker>
              ))}
            </defs>
            {all.flatMap((s) =>
              s.depends_on
                .filter((d) => pos.has(d))
                .map((d) => {
                  const a = pos.get(s.name)!
                  const b = pos.get(d)!
                  const x1 = a.x + NODE_W / 2
                  const y1 = a.y + NODE_H
                  const x2 = b.x + NODE_W / 2
                  const y2 = b.y - 4
                  const failing = brokenNames.includes(d)
                  return (
                    <path
                      key={`${s.name}->${d}`}
                      d={`M${x1},${y1} C${x1},${(y1 + y2) / 2} ${x2},${(y1 + y2) / 2} ${x2},${y2}`}
                      fill="none"
                      strokeWidth={failing ? 2 : 1.5}
                      strokeDasharray={failing ? '6 5' : undefined}
                      className={failing ? 'stroke-sev1' : 'stroke-muted-foreground/60'}
                      markerEnd={`url(#arrow-${failing ? 'sev1' : 'muted'})`}
                    >
                      <title>{`${s.name} depends on ${d}`}</title>
                    </path>
                  )
                }),
            )}
            {all.map((s) => {
              const p = pos.get(s.name)!
              return (
                <foreignObject key={s.name} x={p.x} y={p.y} width={NODE_W} height={NODE_H} className="overflow-visible">
                  <ServiceNode
                    service={s}
                    openIncidents={openFor(s.name)}
                    atRisk={atRisk.has(s.name)}
                    fixTarget={fixTargets.has(s.name)}
                    fixAffected={fixAffected.has(s.name)}
                    onOpen={() => setSelected(s.name)}
                  />
                </foreignObject>
              )
            })}
          </svg>
        )}
      </div>

      <Explanation
        broken={broken}
        openFor={openFor}
        services={all}
        proposals={proposals}
        loading={services.isLoading}
      />

      <ServicePanel name={selected} incidents={incidents.data ?? []} onClose={() => setSelected(null)} />
    </div>
  )
}

function ServiceNode({
  service: s,
  openIncidents,
  atRisk,
  fixTarget,
  fixAffected,
  onOpen,
}: {
  service: ServiceHealth
  openIncidents: number
  atRisk: boolean
  fixTarget: boolean
  fixAffected: boolean
  onOpen: () => void
}) {
  const st = STATUS[s.status] ?? STATUS.unknown
  const tone: Tone = st.tone === 'ok' && atRisk ? 'sev2' : st.tone
  const isDb = s.kind === 'database'
  return (
    <button
      type="button"
      onClick={onOpen}
      aria-label={`${s.name}: ${st.label}${atRisk ? ', at risk' : ''}. Open details`}
      className={cn(
        'flex h-full w-full flex-col justify-between rounded-xl border-2 bg-card px-3 py-2.5 text-left transition-colors hover:bg-white/[0.03]',
        border[tone],
        fixTarget && 'outline-2 outline-offset-4 outline-dashed outline-signal',
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="flex min-w-0 items-center gap-1.5 font-mono text-[12.5px] font-medium">
          {isDb ? (
            <Database className="size-3.5 shrink-0 text-muted-foreground" />
          ) : (
            <span className="size-2 shrink-0 rounded-full" style={{ background: serviceColor(s.name) }} />
          )}
          <span className="truncate">{s.name}</span>
        </span>
        <span className={cn('flex shrink-0 items-center gap-1 text-[11px] font-medium', toneText[st.tone])}>
          <st.Icon className="size-3.5" />
          {st.label}
        </span>
      </div>
      <div className="font-mono text-[10.5px] leading-snug text-muted-foreground">
        {s.error_ratio != null && (
          <div className="truncate">
            {[
              `err ${percent(s.error_ratio)}`,
              s.requests_per_second != null && `${s.requests_per_second.toFixed(1)} req/s`,
              s.p95_latency_ms != null && `p95 ${millis(s.p95_latency_ms)}`,
            ]
              .filter(Boolean)
              .join(' · ')}
          </div>
        )}
        <div>
          pods {s.pods_ready ?? '?'}/{s.pods_desired ?? '?'}
        </div>
      </div>
      <div className="flex min-h-[18px] flex-wrap gap-1">
        {openIncidents > 0 && <Tag tone="sev1">{openIncidents} open incident{openIncidents > 1 ? 's' : ''}</Tag>}
        {atRisk && (
          <Tag tone="sev2">
            <AlertTriangle className="size-3" /> at risk
          </Tag>
        )}
        {fixTarget && (
          <Tag tone="signal">
            <Wrench className="size-3" /> fix changes this
          </Tag>
        )}
        {fixAffected && !fixTarget && <Tag tone="signal">fix affects</Tag>}
      </div>
    </button>
  )
}

function Explanation({
  broken,
  openFor,
  services,
  proposals,
  loading,
}: {
  broken: ServiceHealth[]
  openFor: (name: string) => number
  services: ServiceHealth[]
  proposals: ProposalDetail[]
  loading: boolean
}) {
  if (loading) return null
  const lines = broken.map((s) => {
    const deps = failureBlastRadius(services, [s.name])
    const incidents = openFor(s.name)
    return (
      <li key={s.name} className="flex gap-2">
        <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-sev2" />
        <span>
          <b className="font-mono font-medium">{s.name}</b> is {STATUS[s.status]?.label.toLowerCase() ?? s.status}
          {incidents > 0 && ` (${incidents} open incident${incidents > 1 ? 's' : ''})`}.{' '}
          {deps.size ? (
            <>At risk because they depend on it: <b className="font-mono font-medium">{[...deps].join(', ')}</b>.</>
          ) : (
            'Nothing else depends on it.'
          )}
        </span>
      </li>
    )
  })
  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <div className="panel p-4">
        <h2 className="text-[13px] font-semibold">Blast radius of the failure</h2>
        <ul className="mt-2 space-y-1.5 text-[12.5px]">
          {lines.length ? lines : <li className="text-muted-foreground">Nothing is broken: every service is healthy.</li>}
        </ul>
      </div>
      <div className="panel p-4">
        <h2 className="text-[13px] font-semibold">Blast radius of the proposed fix</h2>
        <ul className="mt-2 space-y-1.5 text-[12.5px]">
          {proposals.length ? (
            proposals.map((p) => (
              <li key={p.id} className="flex gap-2">
                <Wrench className="mt-0.5 size-3.5 shrink-0 text-signal" />
                <span>
                  <b className="font-medium">{p.title}</b> changes <b className="font-mono font-medium">{p.target}</b>{' '}
                  and affects <b className="font-mono font-medium">{p.affected_services.join(', ')}</b>. Awaiting{' '}
                  {p.approvals_required > 1 ? `${p.approvals_required} approvals` : 'approval'}.{' '}
                  <Link to="/approvals" className="text-signal hover:underline">
                    review <ArrowUpRight className="inline size-3" />
                  </Link>
                </span>
              </li>
            ))
          ) : (
            <li className="text-muted-foreground">No fix is waiting for approval.</li>
          )}
        </ul>
      </div>
    </div>
  )
}
