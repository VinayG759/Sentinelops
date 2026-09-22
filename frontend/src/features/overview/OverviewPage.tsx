import { useQuery } from '@tanstack/react-query'
import { motion } from 'motion/react'
import { ArrowUpRight, Database, Server } from 'lucide-react'
import { Link } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { api } from '@/shared/api'
import { relativeTime } from '@/shared/time'
import type { Incident, IncidentEvent } from '@/shared/types'
import { Animated, Sparkline, StatusDot, Tag, type Tone } from '@/shared/ui/primitives'
import { useLiveTable } from '@/shared/useLiveTable'
import { useProposals } from '@/features/remediation/api'

type ServiceHealth = {
  name: string
  kind: string
  status: 'healthy' | 'degraded' | 'critical' | 'unknown'
  depends_on: string[]
  error_ratio: number | null
  requests_per_second: number | null
  p95_latency_ms: number | null
  pods_ready: number | null
  pods_desired: number | null
  spark: number[]
}

const statusTone: Record<ServiceHealth['status'], Tone> = {
  healthy: 'ok',
  degraded: 'sev2',
  critical: 'sev1',
  unknown: 'muted',
}

export function OverviewPage() {
  const services = useQuery({
    queryKey: ['topology'],
    queryFn: () => api<ServiceHealth[]>('/api/topology'),
    refetchInterval: 10_000,
  })
  useLiveTable('incidents', ['incidents'])
  const incidents = useQuery({
    queryKey: ['incidents', 'overview'],
    queryFn: () => api<Incident[]>('/api/incidents'),
  })
  const pending = useProposals('pending')

  const open = (incidents.data ?? []).filter((i) => i.status !== 'resolved')
  const worstService = (services.data ?? []).reduce<ServiceHealth['status']>(
    (acc, s) =>
      s.status === 'critical' || acc === 'critical'
        ? 'critical'
        : s.status === 'degraded' || acc === 'degraded'
          ? 'degraded'
          : acc,
    'healthy',
  )
  // An open incident still counts as "not nominal" even once metrics have recovered:
  // the incident is only closed by verification or a human.
  const worst: ServiceHealth['status'] =
    worstService !== 'healthy' ? worstService : open.length ? 'degraded' : 'healthy'
  const allGood = worst === 'healthy'

  return (
    <div className="space-y-5">
      <SystemBanner status={worst} openCount={open.length} awaiting={pending.data?.length ?? 0} />

      <section>
        <SectionTitle>Services</SectionTitle>
        <div className="mt-2 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {(services.data ?? []).map((service, i) => (
            <ServiceCard key={service.name} service={service} index={i} />
          ))}
          {services.isLoading &&
            [0, 1, 2].map((i) => <div key={i} className="panel h-[132px] animate-pulse" />)}
        </div>
      </section>

      <div className="grid items-start gap-5 lg:grid-cols-[1.15fr_1fr]">
        <section>
          <SectionTitle>
            Active incidents
            <Link to="/incidents" className="text-signal hover:underline">
              all incidents <ArrowUpRight className="inline size-3" />
            </Link>
          </SectionTitle>
          <div className="panel mt-2 divide-y divide-hairline">
            {open.length === 0 ? (
              <Empty
                title={allGood ? 'All systems nominal' : 'No open incidents'}
                body="The detector checks every service every 15 seconds."
              />
            ) : (
              open.map((incident) => <IncidentRow key={incident.id} incident={incident} />)
            )}
          </div>
        </section>

        <section>
          <SectionTitle>Agent activity</SectionTitle>
          <ActivityFeed />
        </section>
      </div>
    </div>
  )
}

function SystemBanner({
  status,
  openCount,
  awaiting,
}: {
  status: ServiceHealth['status']
  openCount: number
  awaiting: number
}) {
  const tone = statusTone[status]
  const headline =
    status === 'critical'
      ? 'Critical — services are failing'
      : status === 'degraded'
        ? openCount
          ? `${openCount} incident${openCount > 1 ? 's' : ''} open`
          : 'Degraded — elevated error rate'
        : 'All systems nominal'

  return (
    <motion.div
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn(
        'panel flex flex-wrap items-center justify-between gap-6 px-5 py-4',
        status === 'critical' && 'glow-sev1',
        status === 'degraded' && 'glow-sev2',
      )}
    >
      <div className="flex items-center gap-3">
        <StatusDot tone={tone} live={status !== 'healthy'} className="size-2.5" />
        <div>
          <div className="text-[15px] font-medium tracking-tight">{headline}</div>
          <div className="text-[11px] text-muted-foreground">
            SentinelOps is watching · detection every 15s · investigation is automatic
          </div>
        </div>
      </div>
      <div className="flex items-center gap-8">
        <HeaderStat label="Open" value={openCount} tone={openCount ? 'sev1' : 'muted'} />
        <HeaderStat label="Awaiting approval" value={awaiting} tone={awaiting ? 'signal' : 'muted'} />
      </div>
    </motion.div>
  )
}

function HeaderStat({ label, value, tone }: { label: string; value: number; tone: Tone }) {
  const color = tone === 'sev1' ? 'text-sev1' : tone === 'signal' ? 'text-signal' : 'text-foreground'
  return (
    <div className="text-right">
      <div className={cn('font-mono text-xl leading-none', color)}>
        <Animated value={value} />
      </div>
      <div className="mt-1 text-[10.5px] uppercase tracking-wider text-muted-foreground">{label}</div>
    </div>
  )
}

function ServiceCard({ service, index }: { service: ServiceHealth; index: number }) {
  const tone = statusTone[service.status]
  const Icon = service.kind === 'database' ? Database : Server
  const ratio = service.error_ratio ?? 0

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.04 }}
      className={cn(
        'panel overflow-hidden p-4',
        service.status === 'critical' && 'glow-sev1',
        service.status === 'degraded' && 'glow-sev2',
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <Icon className="size-3.5 text-muted-foreground" />
          <span className="font-mono text-[13px]">{service.name}</span>
        </div>
        <Tag tone={tone}>
          <StatusDot tone={tone} live={service.status !== 'healthy'} />
          {service.status}
        </Tag>
      </div>

      <div className="mt-3 flex items-end justify-between gap-4">
        <div>
          <div className={cn('font-mono text-2xl leading-none', tone === 'ok' ? '' : `text-${tone}`)}>
            <Animated value={ratio * 100} format={(v) => `${v.toFixed(1)}%`} />
          </div>
          <div className="mt-1 text-[10.5px] uppercase tracking-wider text-muted-foreground">
            error rate
          </div>
        </div>
        <div className="w-28">
          <Sparkline points={service.spark.length ? service.spark : [0, 0]} tone={tone} />
        </div>
      </div>

      <div className="mt-3 flex gap-4 border-t border-hairline pt-2.5 font-mono text-[11px] text-muted-foreground">
        {service.requests_per_second != null && (
          <span>{service.requests_per_second.toFixed(1)} req/s</span>
        )}
        {service.p95_latency_ms != null && <span>p95 {Math.round(service.p95_latency_ms)}ms</span>}
        {service.pods_desired != null && (
          <span className="ml-auto">
            {service.pods_ready}/{service.pods_desired} pods
          </span>
        )}
      </div>
    </motion.div>
  )
}

function IncidentRow({ incident }: { incident: Incident }) {
  const tone: Tone = incident.severity === 'sev1' ? 'sev1' : incident.severity === 'sev2' ? 'sev2' : 'sev3'
  return (
    <Link to={`/incidents/${incident.id}`} className="flex items-center gap-3 px-4 py-3 hover:bg-white/[0.02]">
      <StatusDot tone={tone} live={incident.status === 'triggered'} />
      <div className="min-w-0 flex-1">
        <div className="truncate font-medium">{incident.title}</div>
        <div className="font-mono text-[11px] text-muted-foreground">
          {incident.service} · opened {relativeTime(incident.opened_at)}
        </div>
      </div>
      <Tag tone={tone}>{incident.severity}</Tag>
      <Tag tone={incident.status === 'triggered' ? 'sev2' : 'muted'}>{incident.status}</Tag>
    </Link>
  )
}

function ActivityFeed() {
  useLiveTable('events', ['recent-events'])
  const events = useQuery({
    queryKey: ['recent-events'],
    queryFn: () => api<IncidentEvent[]>('/api/events?limit=25'),
    refetchInterval: 15_000,
  })

  const labels: Record<string, string> = {
    'incident.opened': 'Incident detected',
    'investigation.started': 'Investigation started',
    'investigation.step': 'Agent used a tool',
    'investigation.completed': 'Root cause found',
    'remediation.proposed': 'Fix proposed',
    'remediation.approved': 'Human approved',
    'remediation.rejected': 'Human rejected',
    'execution.started': 'Executing change',
    'execution.succeeded': 'Change applied',
    'execution.refused': 'Execution refused',
    'verification.passed': 'Recovery verified',
    'verification.failed': 'Verification failed',
    'rollback.succeeded': 'Change rolled back',
    'remediation.expired': 'Proposal expired',
    'incident.resolved': 'Incident resolved',
    'incident.acknowledged': 'Acknowledged',
    'simulator.inject': 'Fault injected',
    'simulator.reset': 'Fault cleared',
    'autonomy.paused': 'Autonomy paused',
    'autonomy.resumed': 'Autonomy resumed',
  }

  const toneOf = (type: string): Tone =>
    type.includes('failed') || type === 'incident.opened'
      ? 'sev1'
      : type.includes('refused') || type.includes('rollback')
        ? 'sev2'
        : type.includes('passed') || type.includes('resolved') || type.includes('completed')
          ? 'ok'
          : 'signal'

  return (
    <div className="panel mt-2 max-h-[420px] overflow-y-auto">
      {events.data?.length ? (
        <ol className="divide-y divide-hairline">
          {events.data.map((event) => (
            <motion.li
              key={event.id}
              initial={{ opacity: 0, x: -6 }}
              animate={{ opacity: 1, x: 0 }}
              className="flex items-center gap-3 px-4 py-2.5"
            >
              <StatusDot tone={toneOf(event.type)} />
              <span className="flex-1 truncate">{labels[event.type] ?? event.type}</span>
              <span className="truncate font-mono text-[10.5px] text-muted-foreground">
                {event.actor.startsWith('user:') ? 'human' : event.actor}
              </span>
              <span className="w-20 shrink-0 whitespace-nowrap text-right font-mono text-[10.5px] text-muted-foreground">
                {relativeTime(event.created_at)}
              </span>
            </motion.li>
          ))}
        </ol>
      ) : (
        <Empty title="Nothing yet" body="Agent and human actions appear here as they happen." />
      )}
    </div>
  )
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="flex items-center justify-between text-[11px] uppercase tracking-wider text-muted-foreground">
      {children}
    </h2>
  )
}

function Empty({ title, body }: { title: string; body: string }) {
  return (
    <div className="px-4 py-10 text-center">
      <p className="font-medium">{title}</p>
      <p className="mt-1 text-[12px] text-muted-foreground">{body}</p>
    </div>
  )
}
