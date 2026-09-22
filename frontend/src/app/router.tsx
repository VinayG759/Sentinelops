import { createBrowserRouter, Navigate } from 'react-router-dom'
import { Layout } from '@/app/Layout'
import { RequireAuth } from '@/app/auth'
import { LoginPage } from '@/features/auth/LoginPage'
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
      { path: '/incidents', element: <PagePlaceholder title="Incidents" arrives="Phase 1" /> },
      { path: '/approvals', element: <PagePlaceholder title="Approvals" arrives="Phase 3" /> },
      { path: '/topology', element: <PagePlaceholder title="Topology" arrives="Phase 5" /> },
      { path: '/audit', element: <PagePlaceholder title="Audit" arrives="Phase 4" /> },
      { path: '/simulator', element: <PagePlaceholder title="Simulator" arrives="Phase 1" /> },
    ],
  },
])
