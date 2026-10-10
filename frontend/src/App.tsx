import type { ReactNode } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import AdminPage from './pages/AdminPage'
import AnalyticsPage from './pages/AnalyticsPage'
import CitizenPage from './pages/CitizenPage'
import CounterAssignmentsPage from './pages/CounterAssignmentsPage'
import LoginPage from './pages/LoginPage'
import OfficeDetailPage from './pages/OfficeDetailPage'
import OfficeManagementPage from './pages/OfficeManagementPage'
import StaffManagementPage from './pages/StaffManagementPage'
import StaffPage from './pages/StaffPage'
import { AuthProvider, useAuth } from './lib/auth'
import { I18nProvider } from './lib/i18n'
import { LocationProvider } from './lib/location'
import { OfficeProvider } from './lib/office'
import { ThemeProvider } from './lib/theme'
import { ToastProvider } from './components/ui'
import type { Role } from './lib/types'

function homeFor(role: string): string {
  if (role === 'ADMIN') return '/admin'
  if (role === 'STAFF') return '/staff'
  return '/'
}

/** Route-level guard: staff and admin never land on the citizen flow. */
function RoleHome() {
  const { user, ready } = useAuth()
  if (!ready) return <div className="animate-pulse text-sm text-ink-2">Loading session…</div>
  if (!user || user.role === 'CITIZEN') return <CitizenPage />
  return <Navigate to={homeFor(user.role)} replace />
}

/** Access control for a specific page: wrong role → own dashboard, no session → login. */
function RequireRole({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const { user, ready } = useAuth()
  if (!ready) return <div className="animate-pulse text-sm text-ink-2">Loading session…</div>
  if (!user) return <Navigate to="/login" replace />
  if (!roles.includes(user.role as Role)) return <Navigate to={homeFor(user.role)} replace />
  return <>{children}</>
}

export default function App() {
  return (
    <ThemeProvider>
      <I18nProvider>
        <AuthProvider>
          <OfficeProvider>
            <LocationProvider>
            <ToastProvider>
              <BrowserRouter>
                <Routes>
                  <Route path="/login" element={<LoginPage />} />
                  <Route element={<Layout />}>
                    <Route index element={<RoleHome />} />
                    <Route path="staff" element={<RequireRole roles={['STAFF']}><StaffPage /></RequireRole>} />
                    <Route path="admin" element={<RequireRole roles={['ADMIN']}><AdminPage /></RequireRole>} />
                    <Route path="admin/offices" element={<RequireRole roles={['ADMIN']}><OfficeManagementPage /></RequireRole>} />
                    <Route path="admin/offices/:officeId" element={<RequireRole roles={['ADMIN']}><OfficeDetailPage /></RequireRole>} />
                    <Route path="admin/staff" element={<RequireRole roles={['ADMIN']}><StaffManagementPage /></RequireRole>} />
                    <Route path="admin/assignments" element={<RequireRole roles={['ADMIN']}><CounterAssignmentsPage /></RequireRole>} />
                    <Route path="analytics" element={<RequireRole roles={['ADMIN']}><AnalyticsPage /></RequireRole>} />
                  </Route>
                  <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
              </BrowserRouter>
            </ToastProvider>
            </LocationProvider>
          </OfficeProvider>
        </AuthProvider>
      </I18nProvider>
    </ThemeProvider>
  )
}