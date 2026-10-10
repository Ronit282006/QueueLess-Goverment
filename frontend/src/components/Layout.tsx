import { useEffect, useMemo, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import {
  Accessibility, Activity, BarChart3, Building2, ChevronDown, Home, LogIn, LogOut,
  Menu, Moon, Settings, ShieldCheck, SlidersHorizontal, Sun, Ticket,
  UserCog, Users, Languages, X,
} from 'lucide-react'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n, LANGUAGES } from '../lib/i18n'
import { useOffice } from '../lib/office'
import { useTheme } from '../lib/theme'
import { useToast, Popover } from './ui'
import type { Theme } from '../lib/theme'
import type { Lang } from '../lib/i18n'

const CRUMBS: Record<string, string> = {
  '/': 'Overview',
  '/staff': 'Staff console',
  '/admin': 'Administration',
  '/admin/offices': 'Office management',
  '/admin/staff': 'Staff management',
  '/admin/assignments': 'Counter assignments',
  '/analytics': 'Analytics',
  '/login': 'Sign in',
}

export default function Layout() {
  const { t, lang, setLang } = useI18n()
  const { office, offices, setOfficeId, loading } = useOffice()
  const { user, logout } = useAuth()
  const { theme, setTheme, largeText, setLargeText, highContrast, setHighContrast } = useTheme()
  const toast = useToast()
  const navigate = useNavigate()
  const location = useLocation()
  const [online, setOnline] = useState(navigator.onLine)
  const [menuOpen, setMenuOpen] = useState(false)
  const [staffOffices, setStaffOffices] = useState<number[] | null>(null)
  const role = user?.role ?? null

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

  // Staff only see offices they hold an active assignment in.
  useEffect(() => {
    let active = true
    setStaffOffices(role === 'STAFF' ? null : null)
    if (role === 'STAFF') {
      api
        .staffScope()
        .then((scope) => active && setStaffOffices(scope.offices))
        .catch(() => active && setStaffOffices([]))
    } else {
      setStaffOffices(null)
    }
    return () => {
      active = false
    }
  }, [role])

  const visibleOffices = staffOffices ? offices.filter((o) => staffOffices.includes(o.id)) : offices

  useEffect(() => {
    if (!staffOffices || !office) return
    if (!staffOffices.includes(office.id)) setOfficeId(staffOffices[0])
  }, [staffOffices, office, setOfficeId])

  useEffect(() => {
    setMenuOpen(false)
  }, [location.pathname])

  const canCitizen = role === null || role === 'CITIZEN'
  const canStaff = role === 'STAFF'
  const canAdmin = role === 'ADMIN'

  const nav = useMemo(() => {
    const items: { to: string; label: string; icon: React.ReactNode; end?: boolean }[] = []
    if (canCitizen) items.push({ to: '/', label: t('nav.citizen', 'Citizen services'), icon: <Ticket size={18} />, end: true })
    if (canStaff) items.push({ to: '/staff', label: t('nav.staff', 'Staff console'), icon: <Users size={18} /> })
    if (canAdmin) {
      items.push(
        { to: '/admin', label: t('nav.admin', 'Administration'), icon: <Settings size={18} /> },
        { to: '/admin/offices', label: t('nav.offices', 'Offices'), icon: <Building2 size={18} /> },
        { to: '/admin/staff', label: t('nav.staffManage', 'Staff management'), icon: <UserCog size={18} /> },
        { to: '/admin/assignments', label: t('nav.assignments', 'Counter assignments'), icon: <SlidersHorizontal size={18} /> },
        { to: '/analytics', label: t('nav.analytics', 'Analytics'), icon: <BarChart3 size={18} /> },
      )
    }
    return items
  }, [canCitizen, canStaff, canAdmin, t])

  const roleTone = role === 'CITIZEN' ? 'brand' : role === 'STAFF' ? 'info' : 'warn'

  const brand = (
    <a href="/" className="flex items-center gap-3 px-2 py-2">
      <span className="grid place-items-center w-10 h-10 rounded-lg bg-brand text-white shadow-brand">
        <Activity size={20} aria-hidden />
      </span>
      <span className="leading-tight">
        <b className="block text-base font-extrabold text-ink">{t('appName', 'QueueLess')}</b>
        <small className="block text-[10px] tracking-[0.22em] text-ink-3 font-bold">GOVERNMENT SERVICES</small>
      </span>
    </a>
  )

  const officeSelect = (
    <div className="rounded-lg bg-surface2 border border-line p-2.5 flex items-start gap-2">
      <ShieldCheck size={17} className="shrink-0 mt-0.5 text-brand" aria-hidden />
      <div className="min-w-0 flex-1">
        <small className="block text-[10px] uppercase tracking-[0.14em] text-ink-3 font-bold">
          {t('layout.selectedOffice', 'Selected office')}
        </small>
        {visibleOffices.length > 1 ? (
          <label className="relative block mt-0.5">
            <select
              className="w-full appearance-none bg-transparent text-ink text-sm font-semibold focus:outline-none cursor-pointer pr-4"
              value={office?.id ?? ''}
              onChange={(e) => {
                setOfficeId(Number(e.target.value))
                toast.success(t('layout.officeChanged', 'Office updated'))
              }}
              aria-label={t('layout.selectedOffice', 'Selected office')}
            >
              {visibleOffices.map((o) => (
                <option key={o.id} value={o.id} className="text-ink bg-surface">
                  {o.name}
                </option>
              ))}
            </select>
            <ChevronDown size={14} className="absolute right-0 top-1/2 -translate-y-1/2 text-ink-3 pointer-events-none" />
          </label>
        ) : (
          <p className="text-ink text-sm font-semibold mt-0.5 leading-snug">{office?.name ?? 'Central Government Office'}</p>
        )}
      </div>
    </div>
  )

  const navList = (
    <>
      <p className="px-2 pt-1 text-[10px] font-bold uppercase tracking-[0.22em] text-ink-3">{t('layout.workspace', 'Workspace')}</p>
      <nav aria-label={t('layout.mainNav', 'Main navigation')} className="mt-2 flex flex-col gap-1">
        {nav.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-semibold transition-colors ${
                isActive ? 'bg-brand text-white shadow-sm' : 'text-ink-2 hover:bg-surface2 hover:text-ink'
              }`
            }
          >
            {item.icon}
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>
    </>
  )

  const fairness = (
    <div className="rounded-lg bg-surface2 border border-line p-3.5">
      <b className="block text-sm text-ink">{t('fairness.title', 'Fair service for everyone')}</b>
      <p className="mt-1 text-[12px] leading-relaxed text-ink-2 m-0">
        {t('fairness.body', 'Estimates use the live queue, average service times and open counters.')}
      </p>
    </div>
  )

  const sidebarBody = (
    <div className="flex flex-col gap-4">
      {brand}
      {canStaff && officeSelect}
      {navList}
      <div className="mt-auto pt-4">{fairness}</div>
    </div>
  )

  const session = user ? (
    <span className="flex items-center gap-2">
      <span className="hidden sm:block text-sm font-semibold text-ink max-w-[160px] truncate" title={user.full_name}>
        {user.full_name}
      </span>
      <span
        className={`rounded-full px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-wider ${
          roleTone === 'brand' ? 'bg-brand-soft text-brand' : roleTone === 'info' ? 'bg-info-soft text-info' : 'bg-warn-soft text-warn'
        }`}
      >
        {user.role}
      </span>
      <button
        className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-2 text-sm font-semibold text-ink-2 hover:bg-surface2 min-h-[40px]"
        onClick={() => {
          logout()
          navigate('/')
        }}
      >
        <LogOut size={16} aria-hidden />
        <span className="hidden sm:inline">{t('common.signOut', 'Sign out')}</span>
      </button>
    </span>
  ) : (
    <NavLink
      to={location.pathname === '/login' ? '/' : '/login'}
      className="inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-semibold text-brand hover:bg-brand-soft min-h-[40px] transition-colors"
    >
      <LogIn size={16} aria-hidden />
      {t('common.signIn', 'Sign in')}
    </NavLink>
  )

  const a11y = (
    <Popover
      align="right"
      label={t('a11y.label', 'Accessibility and preferences')}
      trigger={({ open, toggle }) => (
        <button
          onClick={toggle}
          aria-expanded={open}
          aria-haspopup="menu"
          className={`grid place-items-center w-10 h-10 rounded-md ${open ? 'bg-surface2 text-brand' : 'text-ink-2 hover:bg-surface2 hover:text-ink'}`}
          title={t('a11y.label', 'Accessibility and preferences')}
        >
          <Accessibility size={19} />
          <span className="sr-only">{t('a11y.label', 'Accessibility and preferences')}</span>
        </button>
      )}
    >
      <div className="flex flex-col gap-4 p-4">
        <section>
          <h3 className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.14em] text-ink-3 mb-2.5">
            <Languages size={14} aria-hidden /> {t('a11y.language', 'Language')}
          </h3>
          <div className="grid grid-cols-3 gap-1.5" role="group" aria-label={t('a11y.language', 'Language')}>
            {LANGUAGES.map((l) => (
              <button
                key={l.code}
                onClick={() => setLang(l.code as Lang)}
                aria-pressed={lang === l.code}
                className={`rounded-md px-2 py-2 text-sm font-semibold border ${
                  lang === l.code ? 'bg-brand text-white border-brand' : 'border-line text-ink-2 hover:bg-surface2'
                }`}
              >
                {l.label}
              </button>
            ))}
          </div>
        </section>

        <section>
          <h3 className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.14em] text-ink-3 mb-2.5">
            <Moon size={14} aria-hidden /> {t('a11y.theme', 'Appearance')}
          </h3>
          <div className="grid grid-cols-3 gap-1.5" role="group" aria-label={t('a11y.theme', 'Appearance')}>
            {(
              [
                { id: 'light', label: t('a11y.themeLight', 'Light'), Icon: Sun },
                { id: 'dark', label: t('a11y.themeDark', 'Dark'), Icon: Moon },
                { id: 'system', label: t('a11y.themeSystem', 'Auto'), Icon: Activity },
              ] as const
            ).map(({ id, label, Icon }) => (
              <button
                key={id}
                onClick={() => setTheme(id)}
                aria-pressed={theme === id}
                className={`inline-flex items-center justify-center gap-1.5 rounded-md px-2 py-2 text-sm font-semibold border ${
                  theme === id ? 'bg-brand text-white border-brand' : 'border-line text-ink-2 hover:bg-surface2'
                }`}
              >
                <Icon size={15} aria-hidden />
                {label}
              </button>
            ))}
          </div>
        </section>

        <section className="flex flex-col gap-2.5">
          <ToggleRow
            id="ql-large"
            label={t('a11y.largeText', 'Larger text')}
            hint={t('a11y.largeTextHint', 'Raises the base font size')}
            checked={largeText}
            onChange={setLargeText}
          />
          <ToggleRow
            id="ql-contrast"
            label={t('a11y.highContrast', 'High contrast')}
            hint={t('a11y.highContrastHint', 'Stronger colours and borders')}
            checked={highContrast}
            onChange={setHighContrast}
          />
        </section>
      </div>
    </Popover>
  )

  const crumb =
    CRUMBS[location.pathname] ??
    Object.entries(CRUMBS)
      .filter(([path]) => path !== '/' && location.pathname.startsWith(`${path}/`))
      .sort((a, b) => b[0].length - a[0].length)[0]?.[1] ??
    (location.pathname.startsWith('/admin') ? CRUMBS['/admin'] : t('appName', 'QueueLess'))

  const handleLogoutMobile = () => {
    logout()
    navigate('/')
    toast.info(t('common.signedOut', 'Signed out'))
  }

  return (
    <div className="min-h-screen flex flex-col lg:flex-row">
      <a href="#ql-main" className="skip-link">
        {t('layout.skipContent', 'Skip to content')}
      </a>

      {/* Desktop sidebar */}
      <aside className="hidden lg:flex lg:w-[268px] lg:shrink-0 lg:sticky lg:top-0 lg:h-screen overflow-y-auto bg-surface border-r border-line px-3 py-5" aria-label="Primary">
        {sidebarBody}
      </aside>

      {/* Mobile drawer */}
      {menuOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/45 backdrop-blur-[2px]" onClick={() => setMenuOpen(false)} aria-hidden />
          <div className="absolute top-0 bottom-0 left-0 w-[86%] max-w-sm bg-surface border-r border-line px-3 py-4 flex flex-col animate-drawer overflow-y-auto">
            <button
              onClick={() => setMenuOpen(false)}
              aria-label={t('layout.closeMenu', 'Close menu')}
              className="absolute top-3 right-3 grid place-items-center w-10 h-10 rounded-md text-ink-2 hover:bg-surface2"
            >
              <X size={20} />
            </button>
            {sidebarBody}
          </div>
        </div>
      )}

      <div className="flex-1 flex flex-col min-w-0">
        <header className="app-header sticky top-0 z-30 bg-surface/85 backdrop-blur border-b border-line">
          <div className="mx-auto max-w-[1280px] px-4 sm:px-6 flex items-center justify-between gap-3 h-14">
            <div className="flex items-center gap-1 min-w-0">
              <button
                onClick={() => setMenuOpen(true)}
                aria-label={t('layout.openMenu', 'Open menu')}
                className="lg:hidden grid place-items-center w-10 h-10 rounded-md text-ink-2 hover:bg-surface2"
              >
                <Menu size={20} />
              </button>
              <p className="text-sm font-semibold text-ink-2 truncate">
                <span className="text-ink-3">/{crumb.toLowerCase()}</span>{' '}
                <span className="text-ink">{crumb}</span>
              </p>
            </div>

            <div className="flex items-center gap-1.5 sm:gap-2">
              <span className={`inline-flex items-center gap-2 px-2.5 py-1.5 rounded-full text-xs font-semibold ${online ? 'bg-ok-soft text-ok' : 'bg-warn-soft text-warn'}`}>
                <span aria-hidden className={`live-dot${online ? '' : ' off'}`} />
                {online ? t('header.online', 'System online') : t('header.offline', 'Offline')}
              </span>

              {a11y}

              {session}

              {/* mobile explicit sign-out target when logged in */}
              {user && (
                <button
                  onClick={handleLogoutMobile}
                  aria-label={t('common.signOut', 'Sign out')}
                  className="lg:hidden grid place-items-center w-10 h-10 rounded-md text-ink-2 hover:bg-surface2"
                >
                  <LogOut size={19} />
                </button>
              )}
            </div>
          </div>
        </header>

        <main id="ql-main" className="flex-1 animate-fade-in">
          <div className="mx-auto max-w-[1280px] w-full px-4 sm:px-6 py-6 pb-24 lg:pb-8">
            {loading ? (
              <div className="animate-pulse text-sm text-ink-2">Loading directory…</div>
            ) : (
              <Outlet />
            )}
          </div>
        </main>

        <footer className="border-t border-line py-5">
          <div className="mx-auto max-w-[1280px] px-4 sm:px-6 flex flex-wrap items-center justify-between gap-2 text-[13px]">
            <span className="font-medium text-ink-2">
              {t('appName', 'QueueLess')} · {t('footer.tagline', 'Public service, with less waiting')}
            </span>
            <span className="text-ink-3">{t('footer.disclaimer', 'Predictions are estimates, not guarantees.')}</span>
          </div>
        </footer>
      </div>

      {/* Mobile bottom navigation: primary actions for citizen & staff */}
      {(canCitizen || canStaff) && (
        <nav aria-label={t('layout.bottomNav', 'Primary actions')} className="bottom-nav lg:hidden">
          {canCitizen && (
            <NavLink to="/" end>
              <Home size={20} aria-hidden /> {t('bottomNav.home', 'Home')}
            </NavLink>
          )}
          {canStaff && (
            <NavLink to="/staff">
              <Users size={20} aria-hidden /> {t('nav.staff', 'Staff console')}
            </NavLink>
          )}
          <NavLink to={user ? '#signout' : '/login'} end onClick={user ? (e) => { e.preventDefault(); handleLogoutMobile() } : undefined}>
            {user ? <LogOut size={20} aria-hidden /> : <LogIn size={20} aria-hidden />}
            {user ? t('common.signOut', 'Sign out') : t('common.signIn', 'Sign in')}
          </NavLink>
        </nav>
      )}
    </div>
  )
}

function ToggleRow({ id, label, hint, checked, onChange }: { id: string; label: string; hint: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label htmlFor={id} className="flex items-center justify-between gap-3 cursor-pointer rounded-md px-2 -mx-2 py-1.5 hover:bg-surface2">
      <span>
        <span className="block text-sm font-semibold text-ink">{label}</span>
        <span className="block text-[12px] text-ink-3">{hint}</span>
      </span>
      <button
        id={id}
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`relative w-11 h-6 rounded-full transition-colors shrink-0 ${checked ? 'bg-brand' : 'bg-line'}`}
      >
        <span
          aria-hidden
          className={`absolute top-0.5 w-5 h-5 rounded-full bg-white shadow-card transition-all ${checked ? 'left-[22px]' : 'left-0.5'}`}
        />
      </button>
    </label>
  )
}