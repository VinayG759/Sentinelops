import { createBrowserRouter, Navigate } from 'react-router-dom'
import { Layout } from '@/app/Layout'
import { RequireAuth } from '@/app/auth'
import { LoginPage } from '@/features/auth/LoginPage'
import { IncidentDetailPage } from '@/features/incidents/IncidentDetailPage'
import { IncidentsPage } from '@/features/incidents/IncidentsPage'
import { OverviewPage } from '@/features/overview/OverviewPage'
import { ApprovalsPage } from '@/features/remediation/ApprovalsPage'
import { SimulatorPage } from '@/features/simulator/SimulatorPage'
import { AuditPage } from '@/features/audit/AuditPage'
import { TopologyPage } from '@/features/topology/TopologyPage'

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
      { index: true, element: <Navigate to="/overview" replace /> },
      { path: '/overview', element: <OverviewPage /> },
      { path: '/incidents', element: <IncidentsPage /> },
      { path: '/incidents/:id', element: <IncidentDetailPage /> },
      { path: '/approvals', element: <ApprovalsPage /> },
      { path: '/topology', element: <TopologyPage /> },
      { path: '/audit', element: <AuditPage /> },
      { path: '/simulator', element: <SimulatorPage /> },
    ],
  },
])
