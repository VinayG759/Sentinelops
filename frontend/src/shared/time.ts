const units: [Intl.RelativeTimeFormatUnit, number][] = [
  ['day', 86_400],
  ['hour', 3_600],
  ['minute', 60],
  ['second', 1],
]
const rtf = new Intl.RelativeTimeFormat('en', { numeric: 'auto', style: 'narrow' })

/** "3 min ago". Pair with `absoluteTime` in a title attribute for the exact moment. */
export function relativeTime(iso: string, now = Date.now()): string {
  const seconds = Math.round((new Date(iso).getTime() - now) / 1000)
  for (const [unit, size] of units) {
    if (Math.abs(seconds) >= size || unit === 'second') {
      return rtf.format(Math.round(seconds / size), unit)
    }
  }
  return ''
}

export function absoluteTime(iso: string): string {
  return new Date(iso).toLocaleString()
}
