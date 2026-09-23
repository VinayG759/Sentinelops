/**
 * Colour follows the service, never its position in a list: order-service is violet on
 * every chart, whatever else is shown. Values live in index.css (--series-*).
 */
const SERVICE_COLORS: Record<string, string> = {
  'order-service': 'var(--series-1)',
  'payment-service': 'var(--series-2)',
}

export function serviceColor(name: string): string {
  return SERVICE_COLORS[name] ?? 'var(--muted-foreground)'
}
