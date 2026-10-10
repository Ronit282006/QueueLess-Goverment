import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Activity, Clock3, MailCheck, UserPlus, ShieldCheck } from 'lucide-react'
import TagPicker from '../components/TagPicker'
import { Button, FormField, OtpInput, ErrorState } from '../components/ui'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export default function LoginPage() {
  const [searchParams] = useSearchParams()
  const { login, register, resendRegistrationOtp, verifyRegistrationOtp } = useAuth()
  const { t } = useI18n()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [tags, setTags] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [fieldErrors, setFieldErrors] = useState<{ email?: string; password?: string; fullName?: string }>({})
  const [otpPending, setOtpPending] = useState(false)
  const [otp, setOtp] = useState('')
  const [success, setSuccess] = useState('')
  const [remaining, setRemaining] = useState(0)
  const returnTo = searchParams.get('return_to')
  const destination = returnTo?.startsWith('/') && !returnTo.startsWith('//') ? returnTo : null
  const cleanEmail = (value: string) => value.trim().toLowerCase()

  useEffect(() => {
    if (remaining <= 0) return
    const id = window.setInterval(() => setRemaining((r) => r - 1), 1000)
    return () => window.clearInterval(id)
  }, [remaining > 0])

  const startOtp = (address: string) => {
    setOtpPending(true)
    setOtp('')
    setSuccess('')
    setRemaining(60)
  }

  const validate = (address: string) => {
    const errs: { email?: string; password?: string; fullName?: string } = {}
    if (!address) errs.email = t('err.required', 'This field is required.')
    else if (!EMAIL_RE.test(address)) errs.email = t('err.invalidEmail', 'Enter a valid email address.')
    if (mode === 'register' && !otpPending && (password.length > 0 && password.length < 8))
      errs.password = t('err.passwordTooShort', 'Password must be at least 8 characters.')
    if (mode === 'register' && !otpPending && !fullName.trim()) errs.fullName = t('err.required', 'This field is required.')
    setFieldErrors(errs)
    return Object.keys(errs).length === 0
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    const address = cleanEmail(email)
    setEmail(address)
    setError('')
    setSuccess('')
    if (!validate(address)) return
    setBusy(true)
    try {
      if (mode === 'login') {
        const result = await login(address, password)
        window.location.assign(destination ?? (result.role === 'ADMIN' ? '/admin' : result.role === 'STAFF' ? '/staff' : '/'))
      } else if (!otpPending) {
        await register(address, fullName.trim(), password, tags)
        startOtp(address)
      } else {
        const result = await verifyRegistrationOtp(address, otp)
        setSuccess(result.message)
        window.setTimeout(() => window.location.assign(destination ?? '/'), 1500)
      }
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const resend = async () => {
    const address = cleanEmail(email)
    setEmail(address)
    setBusy(true)
    setError('')
    try {
      const result = await resendRegistrationOtp(address)
      setSuccess(result.message)
      setRemaining(60)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const switchMode = () => {
    setMode(mode === 'login' ? 'register' : 'login')
    setOtpPending(false)
    setOtp('')
    setSuccess('')
    setError('')
    setFieldErrors({})
  }

  const title = mode === 'login' ? t('login.title', 'Welcome back') : t('login.register', 'Create your account')

  return (
    <div className="min-h-screen grid lg:grid-cols-2 bg-surface">
      {/* Brand / value panel */}
      <aside className="relative hidden lg:flex lg:flex-col justify-between overflow-hidden bg-surface2 border-r border-line text-ink p-10">
        <a href="/" className="relative flex items-center gap-3">
          <span className="grid place-items-center w-11 h-11 rounded-xl bg-brand text-white shadow-brand">
            <Activity size={22} />
          </span>
          <span className="leading-tight">
            <b className="block text-lg font-extrabold text-ink">{t('appName', 'QueueLess')}</b>
            <small className="block text-[10px] tracking-[0.22em] text-ink-3 font-bold">GOVERNMENT SERVICES</small>
          </span>
        </a>

        <div className="relative">
          <h1 className="text-[2rem] leading-tight font-extrabold max-w-md text-ink">
            {t('citizen.title', 'Take your place in line — from anywhere')}
          </h1>
          <p className="mt-3 text-ink-2 max-w-md leading-relaxed">
            {t('citizen.subtitle', 'Get a virtual token, follow your live position and arrive only when it’s almost your turn.')}
          </p>
          <ul className="mt-8 space-y-4">
            <li className="flex items-center gap-3">
              <span className="grid place-items-center w-9 h-9 rounded-lg bg-brand-soft text-brand"><Clock3 size={18} /></span>
              <span className="text-sm font-medium text-ink-2">{t('fairness.body', 'Estimates use the live queue, average service times and open counters.')}</span>
            </li>
            <li className="flex items-center gap-3">
              <span className="grid place-items-center w-9 h-9 rounded-lg bg-brand-soft text-brand"><ShieldCheck size={18} /></span>
              <span className="text-sm font-medium text-ink-2">{t('fairness.title', 'Fair service for everyone')}</span>
            </li>
            <li className="flex items-center gap-3">
              <span className="grid place-items-center w-9 h-9 rounded-lg bg-brand-soft text-brand"><MailCheck size={18} /></span>
              <span className="text-sm font-medium text-ink-2">{t('login.tokenByEmail', 'Token updates by email')}</span>
            </li>
          </ul>
        </div>

        <p className="relative text-xs text-ink-3">{t('footer.disclaimer', 'Predictions are estimates, not guarantees.')}</p>
      </aside>

      {/* Form panel */}
      <main className="flex items-center justify-center px-4 sm:px-8 py-10">
        <div className="w-full max-w-md animate-fade-slide">
          <a href="/" className="lg:hidden flex items-center gap-2.5 mb-8" aria-label={t('appName', 'QueueLess')}>
            <span className="grid place-items-center w-10 h-10 rounded-lg bg-brand text-white"><Activity size={20} /></span>
            <span className="leading-tight">
              <b className="block text-base font-extrabold text-ink">{t('appName', 'QueueLess')}</b>
              <small className="block text-[9px] tracking-[0.2em] text-ink-3 font-bold">GOVERNMENT SERVICES</small>
            </span>
          </a>

          <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-brand">QUEUELESS ACCOUNT</p>
          <h1 className="mt-1 text-[1.7rem] font-extrabold text-ink">{title}</h1>
          <p className="mt-1.5 text-sm text-ink-2">
            {mode === 'login'
              ? t('login.subtitle', 'Sign in to your QueueLess account to continue.')
              : t('login.newHere', 'New to QueueLess?')}
          </p>

          {error && (
            <div className="mt-5">
              <ErrorState message={error} />
            </div>
          )}
          {success && (
            <p role="status" className="mt-5 rounded-md border border-ok bg-ok-soft px-4 py-3 text-sm font-medium text-ok">
              {success}
            </p>
          )}

          <form className="mt-6 flex flex-col gap-4" onSubmit={submit} noValidate>
            {mode === 'register' && !otpPending && (
              <FormField
                id="fullName"
                label={t('sm.fullName', 'Full name')}
                type="text"
                autoComplete="name"
                placeholder="Anita Sharma"
                value={fullName}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFullName(e.target.value)}
                error={fieldErrors.fullName}
              />
            )}
            <FormField
              id="email"
              label={t('login.emailLabel', 'Email address')}
              type="email"
              autoComplete="email"
              placeholder={t('login.emailPlaceholder', 'you@example.com')}
              value={email}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setEmail(e.target.value)}
              error={fieldErrors.email}
            />

            {otpPending ? (
              <div className="flex flex-col gap-4">
                <div className="rounded-md border border-line bg-surface2 px-4 py-3">
                  <p className="text-sm font-semibold text-ink mb-1">{t('login.otpTitle', 'Verify your email')}</p>
                  <p className="text-[13px] text-ink-2 leading-snug">
                    {t('login.otpSubtitle', 'We sent a 6-digit code to {email}. Enter it below to finish signing in.').replace('{email}', email)}
                  </p>
                </div>
                <OtpInput
                  length={6}
                  value={otp}
                  onChange={(v) => {
                    setOtp(v)
                    setError('')
                  }}
                  disabled={busy}
                  name="reg-otp"
                />
                <p aria-live="polite" className="text-xs text-ink-3 text-center">
                  {remaining > 0
                    ? t('login.otpResendIn', 'Resend code in {sec}s').replace('{sec}', String(remaining))
                    : t('login.attemptsHint', 'After several wrong attempts the code expires — you can resend.')}
                </p>
              </div>
            ) : (
              <FormField
                id="password"
                label={t('login.passwordLabel', 'Password')}
                type="password"
                placeholder={t('login.passwordPlaceholder', 'Enter your password')}
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                value={password}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setPassword(e.target.value)}
                error={fieldErrors.password}
              />
            )}

            {mode === 'register' && !otpPending && (
              <TagPicker
                id="tags"
                label={t('login.tagsLabel', 'Category / special assistance')}
                selected={tags}
                onChange={setTags}
                showNormal
                hint={t('login.tagsHint', 'Choose what best describes you so the office can fast-track inclusive categories.')}
              />
            )}

            <Button type="submit" size="lg" loading={busy} disabled={email.length === 0 || (mode === 'login' ? password.length === 0 : !otpPending && fullName.length === 0)}>
              {mode === 'login' ? t('login.submit', 'Continue') : otpPending ? t('login.otpSubmit', 'Verify code') : t('login.submit', 'Continue')}
            </Button>
          </form>

          <div className="mt-5 flex flex-col items-start gap-1">
            {otpPending && (
              <>
                <Button variant="ghost" loading={busy} disabled={remaining > 0} onClick={() => void resend()}>
                  {remaining > 0
                    ? t('login.otpResendIn', 'Resend code in {sec}s').replace('{sec}', String(remaining))
                    : t('login.otpResend', 'Resend code')}
                </Button>
                <Button
                  variant="ghost"
                  onClick={() => {
                    setOtpPending(false)
                    setOtp('')
                    setSuccess('')
                    setError('')
                  }}
                >
                  {t('login.changeDetails', 'Edit email or registration details')}
                </Button>
              </>
            )}
            <button
              type="button"
              onClick={switchMode}
              className="inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-semibold text-brand hover:bg-brand-soft transition-all min-h-[40px]"
            >
              <UserPlus size={16} aria-hidden />
              {mode === 'login' ? t('login.register', 'Create your account') : t('common.signIn', 'Sign in')}
            </button>
          </div>
        </div>
      </main>
    </div>
  )
}
