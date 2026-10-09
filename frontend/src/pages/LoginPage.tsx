import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { LogIn, UserPlus } from 'lucide-react'
import { ErrorBox } from '../components/Bits'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'

export default function LoginPage() {
  const [searchParams] = useSearchParams()
  const { login, register, resendRegistrationOtp, verifyRegistrationOtp } = useAuth()
  const { t } = useI18n()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [tags, setTags] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [otpPending, setOtpPending] = useState(false)
  const [otp, setOtp] = useState('')
  const [success, setSuccess] = useState('')
  const returnTo = searchParams.get('return_to')
  const destination = returnTo?.startsWith('/') && !returnTo.startsWith('//') ? returnTo : null
  const cleanEmail = (value: string) => value.trim().toLowerCase()

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    const address = cleanEmail(email)
    setEmail(address)
    setBusy(true)
    setError('')
    try {
      if (mode === 'login') {
        const result = await login(address, password)
        window.location.assign(destination ?? (result.role === 'ADMIN' ? '/admin' : result.role === 'STAFF' ? '/staff' : '/'))
      } else if (!otpPending) {
        await register(address, fullName, password, tags.split(',').map((x) => x.trim()).filter(Boolean))
        setOtpPending(true)
        setSuccess('Enter the six-digit code sent to your email. It expires in five minutes.')
        setBusy(false)
      } else {
        const result = await verifyRegistrationOtp(address, otp)
        setSuccess(result.message)
        window.setTimeout(() => window.location.assign(destination ?? '/'), 1500)
      }
    } catch (err) {
      setError((err as Error).message)
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
      setSuccess(`${result.message} It expires in five minutes.`)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="ql-auth">
      <section className="ql-card ql-auth-card">
        <span className="ql-kicker">QUEUELESS ACCOUNT</span>
        <h2>{mode === 'login' ? t('login.title', 'Welcome back') : t('login.register', 'Create your account')}</h2>
        <p className="ql-muted">
          {mode === 'login'
            ? 'Sign in to manage queues, counters and analytics.'
            : 'Register as a citizen. Priority tags (for example “Senior Citizen”) enable inclusive fast-tracking.'}
        </p>
        {error && <ErrorBox message={error} onDismiss={() => setError('')} />}
        {success && <p className="ql-notice">{success}</p>}
        <form className="ql-form" onSubmit={submit}>
          {mode === 'register' && !otpPending && (
            <label>
              Full name
              <input value={fullName} onChange={(e) => setFullName(e.target.value)} required minLength={2} />
            </label>
          )}
          {mode === 'register' && otpPending ? (
            <>
              <label>
                Email
                <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
              </label>
              <label>
                Email verification code
                <input value={otp} onChange={(e) => setOtp(e.target.value.replace(/\D/g, '').slice(0, 6))} required inputMode="numeric" pattern="[0-9]{6}" autoComplete="one-time-code" />
              </label>
            </>
          ) : (
          <label>
            Email
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
          </label>
          )}
          {!(mode === 'register' && otpPending) && <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            />
          </label>}
          {mode === 'register' && !otpPending && (
            <label>
              Priority tags (optional, comma separated)
              <input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="Senior Citizen, Differently Abled" />
            </label>
          )}
          <button className="ql-primary ql-wide" disabled={busy}>
            {busy ? 'Please wait…' : mode === 'login' ? <><LogIn size={16} /> Sign in</> : otpPending ? 'Verify email and create account' : <><UserPlus size={16} /> Send verification code</>}
          </button>
        </form>
        {mode === 'register' && otpPending && (
          <>
            <button className="ql-linkish" type="button" onClick={() => void resend()} disabled={busy}>Resend verification code</button>
            <button className="ql-linkish" type="button" onClick={() => { setOtpPending(false); setOtp(''); setSuccess(''); setError('') }} disabled={busy}>Change email or registration details</button>
          </>
        )}
        <button className="ql-linkish" type="button" onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setOtpPending(false); setOtp(''); setSuccess(''); setError('') }}>
          {mode === 'login' ? 'New here? Create an account' : 'Already registered? Sign in'}
        </button>
      </section>
    </div>
  )
}
