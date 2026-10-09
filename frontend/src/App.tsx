import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import AdminPage from './pages/AdminPage'
import AnalyticsPage from './pages/AnalyticsPage'
import CitizenPage from './pages/CitizenPage'
import LoginPage from './pages/LoginPage'
import StaffPage from './pages/StaffPage'
import { AuthProvider } from './lib/auth'
import { I18nProvider } from './lib/i18n'
import { OfficeProvider } from './lib/office'

export default function App() {
  return (
    <I18nProvider>
      <AuthProvider>
        <OfficeProvider>
          <BrowserRouter>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route element={<Layout />}>
                <Route index element={<CitizenPage />} />
                <Route path="staff" element={<StaffPage />} />
                <Route path="admin" element={<AdminPage />} />
                <Route path="analytics" element={<AnalyticsPage />} />
              </Route>
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </BrowserRouter>
        </OfficeProvider>
      </AuthProvider>
    </I18nProvider>
  )
}