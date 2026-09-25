/**
 * Blast radius = everything that stops working when one thing breaks.
 *
 * The registry records "A depends on B" (A calls B). When B breaks, A is at risk, and so is
 * anything that depends on A. So the walk follows `depends_on` backwards, from the broken
 * service to its callers, and on to their callers. Pure functions: no React, no fetching.
 */

export type Node = { name: string; depends_on: readonly string[] }

/** Every service that directly or indirectly depends on `name` (never `name` itself). */
export function dependentsOf(services: readonly Node[], name: string): Set<string> {
  const found = new Set<string>()
  const queue = [name]
  while (queue.length) {
    const current = queue.shift()!
    for (const s of services) {
      if (s.depends_on.includes(current) && s.name !== name && !found.has(s.name)) {
        found.add(s.name)
        queue.push(s.name)
      }
    }
  }
  return found
}

/** Services put at risk by the broken ones, excluding those already broken themselves. */
export function failureBlastRadius(services: readonly Node[], broken: readonly string[]): Set<string> {
  const atRisk = new Set<string>()
  for (const name of broken) for (const d of dependentsOf(services, name)) atRisk.add(d)
  for (const name of broken) atRisk.delete(name)
  return atRisk
}

/**
 * The node a fix changes. Targets look like `service/postgres`, `deployment/order-service`
 * or `postgres/max_connections`: whichever part names a known service is the node.
 */
export function targetNode(target: string, names: readonly string[]): string | null {
  return target.split('/').find((part) => names.includes(part)) ?? null
}
