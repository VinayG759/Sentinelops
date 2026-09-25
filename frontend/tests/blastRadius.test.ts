// Run with: npm test   (Node's built-in runner; Node 24 runs TypeScript directly)
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { dependentsOf, failureBlastRadius, targetNode } from '../src/features/topology/blastRadius.ts'

// The real registry: both services call postgres.
const registry = [
  { name: 'order-service', depends_on: ['postgres'] },
  { name: 'payment-service', depends_on: ['postgres'] },
  { name: 'postgres', depends_on: [] },
]

test('postgres going down puts both services at risk', () => {
  assert.deepEqual([...dependentsOf(registry, 'postgres')].sort(), ['order-service', 'payment-service'])
})

test('nothing depends on a leaf service', () => {
  assert.deepEqual([...dependentsOf(registry, 'order-service')], [])
})

test('the walk follows chains transitively', () => {
  const chain = [
    { name: 'web', depends_on: ['api'] },
    { name: 'api', depends_on: ['db'] },
    { name: 'db', depends_on: [] },
  ]
  assert.deepEqual([...dependentsOf(chain, 'db')].sort(), ['api', 'web'])
})

test('a dependency cycle terminates and never includes the start', () => {
  const cycle = [
    { name: 'a', depends_on: ['b'] },
    { name: 'b', depends_on: ['a'] },
  ]
  assert.deepEqual([...dependentsOf(cycle, 'a')], ['b'])
})

test('at-risk excludes services that are already broken themselves', () => {
  const atRisk = failureBlastRadius(registry, ['postgres', 'order-service'])
  assert.deepEqual([...atRisk], ['payment-service'])
})

test('unknown names are ignored', () => {
  assert.deepEqual([...failureBlastRadius(registry, ['nope'])], [])
})

test('a fix target maps to the node it changes', () => {
  const names = registry.map((s) => s.name)
  assert.equal(targetNode('service/postgres', names), 'postgres')
  assert.equal(targetNode('deployment/order-service', names), 'order-service')
  assert.equal(targetNode('postgres/max_connections', names), 'postgres')
  assert.equal(targetNode('configmap/unrelated', names), null)
})
