import { useSyncExternalStore } from 'react'

/**
 * One time range and one auto-refresh switch for the whole app, set from the top bar.
 * Kept in localStorage (not the URL) so it survives moving between pages and reloads.
 */

export const RANGES = [
  { key: '15m', label: '15m', minutes: 15 },
  { key: '1h', label: '1h', minutes: 60 },
  { key: '6h', label: '6h', minutes: 360 },
] as const

export type RangeKey = (typeof RANGES)[number]['key']

type State = { range: RangeKey; live: boolean }

const STORAGE_KEY = 'sentinelops.timeRange'
const DEFAULT: State = { range: '1h', live: true }
const listeners = new Set<() => void>()

function read(): State {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? 'null')
    if (parsed && RANGES.some((r) => r.key === parsed.range) && typeof parsed.live === 'boolean') {
      return parsed
    }
  } catch {
    // Storage blocked or corrupt: fall back to the default.
  }
  return DEFAULT
}

let state = read()

function write(next: State) {
  state = next
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
  } catch {
    // Not persisted, but still applied for this session.
  }
  listeners.forEach((notify) => notify())
}

function subscribe(notify: () => void) {
  listeners.add(notify)
  return () => listeners.delete(notify)
}

export function useTimeRange() {
  const current = useSyncExternalStore(subscribe, () => state)
  const range = RANGES.find((r) => r.key === current.range) ?? RANGES[1]
  return {
    range,
    minutes: range.minutes,
    live: current.live,
    setRange: (key: RangeKey) => write({ ...state, range: key }),
    setLive: (live: boolean) => write({ ...state, live }),
    /** For TanStack Query's refetchInterval: poll only while live. */
    refetchEvery: (ms: number) => (current.live ? ms : false) as number | false,
  }
}
