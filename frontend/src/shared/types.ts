// Friendly names for the generated backend types. Regenerate with `npm run gen:types`
// (backend must be running) whenever a backend response model changes.
import type { components } from './api-types'

type Schemas = components['schemas']

export type Incident = Schemas['Incident']
export type IncidentEvent = Schemas['Event']
export type Scenario = Schemas['ScenarioOut']
export type Proposal = Schemas['Proposal']
export type ProposalDetail = Schemas['ProposalDetail'] & {
  preview: { summary?: string; changes?: { field: string; from: unknown; to: unknown }[] }
}
export type Role = 'viewer' | 'responder' | 'approver' | 'admin'
