import { motion } from 'motion/react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { cn } from '@/lib/utils'

export type Tone = 'sev1' | 'sev2' | 'sev3' | 'ok' | 'signal' | 'muted'

const toneText: Record<Tone, string> = {
  sev1: 'text-sev1',
  sev2: 'text-sev2',
  sev3: 'text-sev3',
  ok: 'text-ok',
  signal: 'text-signal',
  muted: 'text-muted-foreground',
}

const toneBg: Record<Tone, string> = {
  sev1: 'bg-sev1',
  sev2: 'bg-sev2',
  sev3: 'bg-sev3',
  ok: 'bg-ok',
  signal: 'bg-signal',
  muted: 'bg-muted-foreground',
}

/** A status dot. `live` adds the radar pulse used for anything happening right now. */
export function StatusDot({ tone, live, className }: { tone: Tone; live?: boolean; className?: string }) {
  return (
    <span className={cn('relative inline-flex size-2 shrink-0', toneText[tone], className)}>
      <span className={cn('size-2 rounded-full', toneBg[tone], live && 'pulse-dot')} />
    </span>
  )
}

export function Tag({
  tone = 'muted',
  children,
  className,
}: {
  tone?: Tone
  children: ReactNode
  className?: string
}) {
  const ring: Record<Tone, string> = {
    sev1: 'bg-sev1/12 text-sev1 ring-sev1/25',
    sev2: 'bg-sev2/12 text-sev2 ring-sev2/25',
    sev3: 'bg-white/5 text-sev3 ring-white/10',
    ok: 'bg-ok/12 text-ok ring-ok/25',
    signal: 'bg-signal/12 text-signal ring-signal/25',
    muted: 'bg-white/5 text-muted-foreground ring-white/10',
  }
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 font-mono text-[10.5px] font-medium uppercase tracking-wide ring-1 ring-inset',
        ring[tone],
        className,
      )}
    >
      {children}
    </span>
  )
}

/** Count-up number, so live figures feel alive rather than jumping. */
export function Animated({ value, format }: { value: number; format?: (v: number) => string }) {
  const [shown, setShown] = useState(value)
  const from = useRef(value)

  useEffect(() => {
    const start = performance.now()
    const origin = from.current
    const delta = value - origin
    if (delta === 0) return
    let frame = 0
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / 420)
      const eased = 1 - (1 - t) ** 3
      setShown(origin + delta * eased)
      if (t < 1) frame = requestAnimationFrame(tick)
      else from.current = value
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [value])

  return <span className="tabular">{format ? format(shown) : Math.round(shown)}</span>
}

/** Minimal sparkline: shape over precision, no axes, no grid. */
export function Sparkline({
  points,
  tone = 'signal',
  height = 28,
  className,
}: {
  points: number[]
  tone?: Tone
  height?: number
  className?: string
}) {
  if (points.length < 2) {
    return <div className={cn('h-7 rounded bg-white/[0.03]', className)} style={{ height }} />
  }
  const max = Math.max(...points, 0.0001)
  const min = Math.min(...points)
  const span = max - min || 1
  const step = 100 / (points.length - 1)
  const coords = points.map((p, i) => `${i * step},${100 - ((p - min) / span) * 100}`)
  const stroke = `var(--${tone === 'muted' ? 'muted-foreground' : tone})`

  return (
    <svg
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
      className={cn('w-full', className)}
      style={{ height }}
    >
      <defs>
        <linearGradient id={`fill-${tone}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.28" />
          <stop offset="100%" stopColor={stroke} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={`0,100 ${coords.join(' ')} 100,100`} fill={`url(#fill-${tone})`} />
      <polyline
        points={coords.join(' ')}
        fill="none"
        stroke={stroke}
        strokeWidth="1.5"
        vectorEffect="non-scaling-stroke"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  )
}

export function Stat({
  label,
  value,
  sub,
  tone = 'muted',
}: {
  label: string
  value: ReactNode
  sub?: ReactNode
  tone?: Tone
}) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className={cn('mt-1 font-mono text-2xl leading-none', toneText[tone])}>{value}</div>
      {sub && <div className="mt-1 text-[11px] text-muted-foreground">{sub}</div>}
    </div>
  )
}

export type Phase = { key: string; label: string; state: 'done' | 'active' | 'pending' | 'failed' }

/** The incident's life as five steps — the whole story readable in one glance. */
export function PhaseStepper({ phases }: { phases: Phase[] }) {
  return (
    <ol className="flex flex-wrap items-center gap-1.5">
      {phases.map((phase, index) => {
        const tone: Tone =
          phase.state === 'failed'
            ? 'sev1'
            : phase.state === 'done'
              ? 'ok'
              : phase.state === 'active'
                ? 'signal'
                : 'muted'
        return (
          <li key={phase.key} className="flex items-center gap-1.5">
            <motion.span
              initial={{ opacity: 0.4, scale: 0.96 }}
              animate={{ opacity: 1, scale: 1 }}
              className={cn(
                'relative flex items-center gap-1.5 overflow-hidden rounded-md px-2 py-1 text-[11px] font-medium ring-1 ring-inset',
                phase.state === 'pending' && 'text-muted-foreground ring-white/8',
                phase.state === 'done' && 'text-ok ring-ok/25 bg-ok/8',
                phase.state === 'active' && 'scanning text-signal ring-signal/30 bg-signal/8',
                phase.state === 'failed' && 'text-sev1 ring-sev1/30 bg-sev1/8',
              )}
            >
              <StatusDot tone={tone} live={phase.state === 'active'} />
              {phase.label}
            </motion.span>
            {index < phases.length - 1 && (
              <span className="h-px w-3 bg-hairline" aria-hidden />
            )}
          </li>
        )
      })}
    </ol>
  )
}
