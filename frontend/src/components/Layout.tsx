import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { Activity, BarChart3, LogIn, LogOut, Settings, ShieldCheck, Ticket, Users } from 'lucide-react'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import { useOffice } from '../lib/office'

const CRUMBS: Record<string, string> = {
  '/': 'Overview',
  '/staff': 'Staff console',
  '/admin': 'Administration',
  '/analytics': 'Analytics',
  '/login': 'Sign in',
}

export default function Layout() {
  const { t, lang, setLang } = useI18n()
  const { office, offices, setOfficeId, loading } = useOffice()
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [online, setOnline] = useState(navigator.onLine)
  const [largeText, setLargeText] = useState(() => document.documentElement.classList.contains('ql-large-text'))
  const [contrast, setContrast] = useState(() => document.documentElement.classList.contains('ql-high-contrast'))
  const location = useLocation()

  useEffect(() => {
    const up = () => setOnline(true)
    const down = () => setOnline(false)
    window.addEventListener('online', up)
    window.addEventListener('offline', down)
    return () => {
      window.removeEventListener('online', up)
      window.removeEventListener('offline', down)
    }
  }, [])

  useEffect(() => {
    document.documentElement.classList.toggle('ql-large-text', largeText)
    document.documentElement.classList.toggle('ql-high-contrast', contrast)
  }, [largeText, contrast])

  const role = user?.role
  const canStaff = role === 'STAFF' || role === 'ADMIN'
  const canAdmin = role === 'ADMIN'

  return (
    <div className="ql-shell">
      <aside className="ql-sidebar">
        <a className="ql-brand" href="/">
          <span className="ql-mark">
            <Activity size={21} />
          </span>
          <span>
            <b>QueueLess</b>
            <small>GOVERNMENT SERVICES</small>
          </span>
        </a>
        <div className="ql-office">
          <ShieldCheck size={18} />
          <span style={{ minWidth: 0 }}>
            <small>SELECTED OFFICE</small>
            {offices.length > 1 ? (
              <select
                className="ql-office-select"
                value={office?.id ?? ''}
                onChange={(e) => setOfficeId(Number(e.target.value))}
                aria-label="Selected office"
              >
                {offices.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.name}
                  </option>
                ))}
              </select>
            ) : (
              <b>{office?.name ?? 'Central Government Office'}</b>
            )}
          </span>
        </div>

        <p className="ql-label">WORKSPACE</p>
        <NavLink to="/" end className={({ isActive }) => `ql-link${isActive ? ' active' : ''}`}>
          <Ticket size={17} /> {t('nav.citizen', 'Citizen services')}
        </NavLink>
        {canStaff && (
          <NavLink to="/staff" className={({ isActive }) => `ql-link${isActive ? ' active' : ''}`}>
            <Users size={17} /> {t('nav.staff', 'Staff console')}
          </NavLink>
        )}
        {canAdmin && (
          <NavLink to="/admin" className={({ isActive }) => `ql-link${isActive ? ' active' : ''}`}>
            <Settings size={17} /> {t('nav.admin', 'Administration')}
          </NavLink>
        )}
        {canStaff && (
          <NavLink to="/analytics" className={({ isActive }) => `ql-link${isActive ? ' active' : ''}`}>
            <BarChart3 size={17} /> {t('nav.analytics', 'Analytics')}
          </NavLink>
        )}

        <div className="ql-sidebar-bottom">
          <b>{t('fairness.title', 'Fair service for everyone')}</b>
          <p>{t('fairness.body', 'Estimates use the live queue, average service times and open counters.')}</p>
        </div>
      </aside>

      <main className="ql-main">
        <header className="ql-header">
          <div>
            <span className="ql-crumb">{CRUMBS[location.pathname] ?? 'QueueLess'}</span>
          </div>
          <div className="ql-header-actions">
            <span className={online ? 'ql-online' : 'ql-offline'}>
              <i />
              {online ? t('header.online', 'System online') : t('header.offline', 'Offline')}
            </span>
            <select className="ql-mini-select" value={lang} onChange={(e) => setLang(e.target.value as typeof lang)} aria-label="Language">
              <option value="en">EN</option>
              <option value="hi">हि</option>
              <option value="gu">ગુ</option>
            </select>
            <label className="ql-toggle" title="Larger text">
              <input type="checkbox" checked={largeText} onChange={(e) => setLargeText(e.target.checked)} /> A+
            </label>
            <label className="ql-toggle" title="High contrast">
              <input type="checkbox" checked={contrast} onChange={(e) => setContrast(e.target.checked)} /> ◐
            </label>
            {user ? (
              <span className="ql-session">
                <span className="ql-session-name">{user.full_name}</span>
                <span className="ql-pill">{user.role}</span>
                <button
                  className="ql-secondary ql-small"
                  onClick={() => {
                    logout()
                    navigate('/')
                  }}
                >
                  <LogOut size={15} /> {t('common.signOut', 'Sign out')}
                </button>
              </span>
            ) : (
              <a className="ql-secondary ql-small" href="/login">
                <LogIn size={15} /> {t('common.signIn', 'Sign in')}
              </a>
            )}
          </div>
        </header>
        <div className="ql-content">{loading ? <p className="ql-muted">Loading directory…</p> : <Outlet />}</div>
        <footer className="ql-footer">
          <span>QueueLess · Public service, with less waiting</span>
          <span>Predictions are estimates, not guarantees.</span>
        </footer>
      </main>
    </div>
  )
}