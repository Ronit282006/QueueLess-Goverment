import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Check, KeyRound, MailCheck, Search, ShieldCheck, SlidersHorizontal, UserCog, UserPlus } from 'lucide-react'
import {
  Badge,
  Button,
  Card,
  EmptyState,
  FormField,
  OtpInput,
  Page,
  Skeleton,
  Stepper,
  useToast,
} from '../components/ui'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import type { StaffMember } from '../lib/types'

const STEPS: { key: string; fallback: string }[] = [
  { key: 'sm.detailsStep', fallback: 'Details' },
  { key: 'sm.verifyStep', fallback: 'Verify code' },
  { key: 'sm.doneStep', fallback: 'Done' },
]

export default function StaffManagementPage() {
  const { user } = useAuth()
  const { t } = useI18n()
  const toast = useToast()

  const [members, setMembers] = useState<StaffMember[]>([])
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')

  const [step, setStep] = useState(0)
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [otp, setOtp] = useState('')
  const [verified, setVerified] = useState(false)
  const [created, setCreated] = useState<{ email: string; message: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [resendIn, setResendIn] = useState(0)
  const [fieldErrors, setFieldErrors] = useState<{ fullName?: string; email?: string; password?: string; confirm?: string }>({})

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setMembers(await api.adminStaff())
    } catch (err) {
      toast.error(t('sm.loadFailed', 'Could not load the staff directory'), (err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [t, toast])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    if (resendIn <= 0) return
    const id = window.setInterval(() => setResendIn((v) => v - 1), 1000)
    return () => window.clearInterval(id)
  }, [resendIn > 0])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return members
    return members.filter((m) => m.full_name.toLowerCase().includes(q) || m.email.toLowerCase().includes(q))
  }, [members, query])

  if (!user || user.role !== 'ADMIN') {
    return (
      <Page title={t('sm.title', 'Staff management')}>
        <p className="text-sm text-ink-2">{t('sm.notAdmin', 'Only administrators can create and manage staff accounts.')}</p>
      </Page>
    )
  }

  const validateDetails = () => {
    const errs: typeof fieldErrors = {}
    if (!fullName.trim()) errs.fullName = t('err.required', 'This field is required.')
    if (!email.trim() || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) errs.email = t('err.invalidEmail', 'Enter a valid email address.')
    if (password.length < 8) errs.password = t('err.passwordTooShort', 'Password must be at least 8 characters.')
    if (password !== confirmPassword) errs.confirm = t('sm.passwordMismatch', 'The two passwords do not match.')
    setFieldErrors(errs)
    return Object.keys(errs).length === 0
  }

  const sendOtp = async () => {
    if (!validateDetails()) return
    setBusy(true)
    try {
      const result = await api.adminStaffOtp(fullName.trim(), email.trim().toLowerCase(), password, confirmPassword)
      setResendIn(60)
      setVerified(false)
      setOtp('')
      setStep(1)
      toast.success(t('sm.codeSent', 'Verification code sent'), result.message)
    } catch (err) {
      toast.error(t('admin.actionFailed', 'That did not work'), (err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const verifyOtp = async () => {
    if (otp.length !== 6) {
      toast.error(t('err.otpLen', 'Enter the complete 6-digit code.'))
      return
    }
    setBusy(true)
    try {
      const result = await api.adminStaffOtpVerify(email.trim().toLowerCase(), otp)
      setVerified(true)
      toast.success(t('sm.verified', 'Email verified'), result.message)
    } catch (err) {
      toast.error(t('sm.otpInvalid', "That code didn't match. Try again."), (err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const resend = async () => {
    setBusy(true)
    try {
      const result = await api.adminStaffOtp(fullName.trim(), email.trim().toLowerCase(), password, confirmPassword)
      setResendIn(60)
      toast.success(t('sm.codeSent', 'Verification code sent'), result.message)
    } catch (err) {
      toast.error(t('admin.actionFailed', 'That did not work'), (err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const createStaff = async () => {
    setBusy(true)
    try {
      const result = await api.adminCreateStaff(email.trim().toLowerCase())
      setCreated({ email: result.email, message: result.message })
      setStep(2)
      toast.success(t('sm.created', 'Account created'), result.message)
      await load()
    } catch (err) {
      toast.error(t('admin.actionFailed', 'That did not work'), (err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const resetWizard = () => {
    setStep(0)
    setFullName('')
    setEmail('')
    setPassword('')
    setConfirmPassword('')
    setOtp('')
    setVerified(false)
    setCreated(null)
    setResendIn(0)
    setFieldErrors({})
  }

  return (
    <Page kicker={t('sm.kicker', 'People · Staff accounts')} title={t('sm.title', 'Staff management')}>
      <p className="text-sm text-ink-2 mt-0 mb-5 max-w-3xl">
        {t('sm.subtitle', 'Create verified staff accounts and hand them counters from the assignments page.')}
      </p>

      <div className="grid xl:grid-cols-[minmax(0,420px)_1fr] gap-5">
        {/* Wizard */}
        <Card kicker={t('sm.createTitle', 'Add a staff member')} title={t('sm.createTitle', 'Add a staff member')}>
          <div className="mb-4">
            <Stepper
              steps={STEPS.map((s) => ({ label: t(s.key, s.fallback) }))}
              current={step}
              label={t('sm.stepper', 'Staff creation steps')}
              onStep={(i) => {
                if (i < step && i !== 2) setStep(i)
              }}
            />
          </div>

          {step === 0 && (
            <form
              className="flex flex-col gap-4"
              onSubmit={(e) => {
                e.preventDefault()
                void sendOtp()
              }}
              noValidate
            >
              <FormField
                id="staff-full-name"
                label={t('sm.fullName', 'Full name')}
                value={fullName}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFullName(e.target.value)}
                autoComplete="name"
                placeholder="Ramesh Patel"
                error={fieldErrors.fullName}
                required
              />
              <FormField
                id="staff-email"
                label={t('sm.email', 'Work email')}
                type="email"
                value={email}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setEmail(e.target.value)}
                autoComplete="email"
                placeholder="ramesh@office.gov.in"
                error={fieldErrors.email}
                required
              />
              <FormField
                id="staff-password"
                label={t('login.passwordLabel', 'Password')}
                type="password"
                value={password}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setPassword(e.target.value)}
                autoComplete="new-password"
                error={fieldErrors.password}
                hint={t('sm.passwordHint', 'At least 8 characters.')}
                required
              />
              <FormField
                id="staff-confirm"
                label={t('sm.confirmPassword', 'Confirm password')}
                type="password"
                value={confirmPassword}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setConfirmPassword(e.target.value)}
                autoComplete="new-password"
                error={fieldErrors.confirm}
                required
              />
              <p className="text-[12px] text-ink-3 m-0">
                {t('sm.detailsNote', 'A six-digit code is emailed to the address above. The account is only created after the code is verified — never before.')}
              </p>
              <Button type="submit" loading={busy} icon={<MailCheck size={16} />}>
                {t('sm.sendCode', 'Send verification code')}
              </Button>
            </form>
          )}

          {step === 1 && (
            <div className="flex flex-col gap-4">
              <div className="rounded-md border border-line bg-surface2 p-3.5">
                <p className="m-0 text-sm font-semibold text-ink flex items-center gap-2">
                  <KeyRound size={16} className="text-brand" aria-hidden /> {t('sm.verifyTitle', 'Verify the one-time code')}
                </p>
                <p className="m-0 mt-1 text-[13px] text-ink-2">
                  {t('sm.verifySubtitle', 'A 6-digit code was emailed to {email}. Enter it here to create the account.').replace('{email}', email)}
                </p>
              </div>

              <OtpInput
                length={6}
                value={otp}
                onChange={setOtp}
                disabled={busy || verified}
                name="staff-otp"
              />

              <p aria-live="polite" className="text-xs text-ink-3 text-center m-0">
                {resendIn > 0
                  ? t('login.otpResendIn', 'Resend code in {sec}s').replace('{sec}', String(resendIn))
                  : t('login.attemptsHint', 'After several wrong attempts the code expires — you can resend.')}
              </p>

              {!verified ? (
                <div className="flex flex-col gap-2">
                  <Button onClick={() => void verifyOtp()} loading={busy} disabled={otp.length !== 6} icon={<ShieldCheck size={16} />}>
                    {t('login.otpSubmit', 'Verify code')}
                  </Button>
                  <Button variant="ghost" onClick={() => void resend()} disabled={busy || resendIn > 0}>
                    {resendIn > 0 ? t('login.otpResendIn', 'Resend code in {sec}s').replace('{sec}', String(resendIn)) : t('login.otpResend', 'Resend code')}
                  </Button>
                </div>
              ) : (
                <div className="flex flex-col gap-3">
                  <p role="status" className="m-0 rounded-md border border-ok bg-ok-soft px-4 py-3 text-sm font-medium text-ok flex items-center gap-2">
                    <Check size={16} aria-hidden /> {t('sm.verifiedEmail', 'Email verified:')} <b className="truncate">{email}</b>
                  </p>
                  <Button onClick={() => void createStaff()} loading={busy} icon={<UserCog size={16} />}>
                    {t('sm.createAccount', 'Create staff account')}
                  </Button>
                </div>
              )}

              <Button variant="ghost" type="button" onClick={() => setStep(0)} disabled={busy}>
                {t('sm.changeDetails', 'Change details and resend')}
              </Button>
            </div>
          )}

          {step === 2 && created && (
            <div className="flex flex-col gap-4 items-center text-center">
              <span className="grid place-items-center w-14 h-14 rounded-full bg-ok-soft text-ok">
                <Check size={28} aria-hidden />
              </span>
              <div>
                <p className="m-0 text-lg font-bold text-ink">{t('sm.doneTitle', 'Staff account created')}</p>
                <p className="m-0 mt-1 text-sm text-ink-2">{created.message}</p>
              </div>
              <p className="m-0 rounded-md border border-line bg-surface2 px-4 py-3 text-sm text-ink break-all w-full">
                <b className="block text-[11px] uppercase tracking-wider text-ink-3 mb-1">{t('sm.accountEmail', 'Account email')}</b>
                {created.email}
              </p>
              <div className="flex flex-wrap gap-2 justify-center">
                <Button variant="secondary" onClick={resetWizard} icon={<UserPlus size={16} />}>
                  {t('sm.createAnother', 'Add another')}
                </Button>
                <Link
                  to={`/admin/assignments?staff=${members.find((m) => m.email === created.email)?.id ?? ''}`}
                  className="inline-flex items-center justify-center gap-2 rounded-md border border-line bg-surface px-4 py-2.5 text-sm font-semibold text-ink hover:bg-surface2 hover:border-slate-300 shadow-sm transition-all active:scale-[0.985] min-h-[42px]"
                >
                  <SlidersHorizontal size={16} aria-hidden /> {t('sm.assignNow', 'Assign counters')}
                </Link>
              </div>
            </div>
          )}
        </Card>

        {/* Directory */}
        <Card kicker={t('sm.directory', 'Staff directory')} title={t('sm.membersCount', 'Staff members ({n})').replace('{n}', String(members.length))}>
          <label className="relative block mb-4">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-3 pointer-events-none" aria-hidden />
            <span className="sr-only">{t('sm.search', 'Search')}</span>
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t('sm.searchPlaceholder', 'Search by name or email')}
              className="w-full rounded-md border border-line bg-surface pl-9 pr-3.5 py-2.5 text-[15px] text-ink placeholder:text-ink-3 min-h-[44px] focus:outline-none focus:ring-2 focus:border-brand focus:ring-brand/25"
            />
          </label>

          {loading && !members.length ? (
            <Skeleton lines={4} />
          ) : members.length === 0 ? (
            <EmptyState
              icon={<UserCog size={22} />}
              title={t('sm.noStaff', 'No staff accounts yet')}
              hint={t('sm.noStaffHint', 'Create the first staff account on the left.')}
            />
          ) : filtered.length === 0 ? (
            <EmptyState icon={<Search size={22} />} title={t('sm.noResults', 'No staff match your search.')} hint={t('sm.noResultsHint', 'Try a different name or email.')} />
          ) : (
            <ul className="m-0 p-0 list-none flex flex-col gap-2">
              {filtered.map((member) => (
                <li key={member.id} className="rounded-md border border-line p-3.5 flex flex-wrap items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="m-0 text-[15px] font-semibold text-ink truncate">{member.full_name}</p>
                    <p className="m-0 mt-0.5 text-[13px] text-ink-2 truncate">{member.email}</p>
                    <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                      <Badge tone={member.is_active ? 'ok' : 'alert'}>
                        {member.is_active ? <Check size={12} aria-hidden /> : null}
                        {member.is_active ? t('sm.active', 'Active') : t('sm.suspended', 'Suspended')}
                      </Badge>
                      <Badge tone={member.counters.length ? 'info' : 'neutral'}>
                        {member.counters.length
                          ? t('sm.counters', '{n} counter(s)').replace('{n}', String(member.counters.length))
                          : t('sm.unassigned', 'Not assigned')}
                      </Badge>
                    </div>
                  </div>
                  <Link
                    to={`/admin/assignments?staff=${member.id}&office=${member.offices[0] ?? ''}`}
                    className="inline-flex items-center justify-center gap-2 rounded-md border border-line bg-surface px-3 py-1.5 text-xs font-semibold text-brand hover:bg-brand-soft hover:border-brand/35 shadow-sm transition-all active:scale-[0.985] min-h-[34px]"
                  >
                    <SlidersHorizontal size={14} aria-hidden /> {t('sm.assignCounters', 'Assign counters')}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </Page>
  )
}
