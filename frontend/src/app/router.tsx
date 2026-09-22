import { createBrowserRouter, Navigate } from 'react-router-dom'
import { Layout } from '@/app/Layout'
import { RequireAuth } from '@/app/auth'
import { LoginPage } from '@/features/auth/LoginPage'
import { IncidentDetailPage } from '@/features/incidents/IncidentDetailPage'
import { IncidentsPage } from '@/features/incidents/IncidentsPage'
import { ApprovalsPage } from '@/features/remediation/ApprovalsPage'
import { SimulatorPage } from '@/features/simulator/SimulatorPage'
import { PagePlaceholder } from '@/shared/PagePlaceholder'

// One route per feature. Adding a feature = add its page here and a nav item in Layout.
export const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  {
    element: (
      <RequireAuth>
        <Layout />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <Navigate to="/incidents" replace /> },
      { path: '/incidents', element: <IncidentsPage /> },
      { path: '/incidents/:id', element: <IncidentDetailPage /> },
      { path: '/approvals', element: <ApprovalsPage /> },
      { path: '/topology', element: <PagePlaceholder title="Topology" arrives="Phase 5" /> },
      { path: '/audit', element: <PagePlaceholder title="Audit" arrives="Phase 4" /> },
      { path: '/simulator', element: <SimulatorPage /> },
    ],
  },
])
