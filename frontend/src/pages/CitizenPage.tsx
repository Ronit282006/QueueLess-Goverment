import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Bell, CheckCircle2, Clock3, FileText, MapPin, QrCode, Search,
  ShieldCheck, Ticket, Users, AlertTriangle, Star, BadgeCheck,
} from 'lucide-react'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { useOffice } from '../lib/office'
import { useAuth } from '../lib/auth'
import { useQueue, useToken } from '../lib/hooks'
import {
  Badge, statusTone, Button, Card, NStat, EmptyState, SkeletonCard, Modal, ProgressRing,
  Meter, useToast,
} from '../components/ui'
import type { Token } from '../lib/types'

const SAVED_TOKENS_KEY = 'ql_citizen_tokens_by_owner'
const NO_REFERENCES: string[] = []

type StageLevel = 'safe' | 'approaching' | 'come_now' | 'your_turn'

function stageForToken(token: Token): { level: StageLevel; message: string } {
  const status = token.status?.toUpperCase()
  const stage = token.stage?.toUpperCase()
  if (status === 'SERVING' || stage === 'YOUR_TURN' || stage === 'SERVING') return { level: 'your_turn', message: 'citizen.goToCounter' }
  if (status === 'CALLED' || stage === 'CALLED_NOW' || (status === 'ARRIVED' && stage !== 'WAITING')) return { level: 'come_now', message: 'citizen.hurry' }
  if (stage === 'APPROACHING' || status === 'APPROACHING') return { level: 'approaching', message: 'citizen.headOver' }
  return { level: 'safe', message: 'citizen.stayHome' }
}

export default function CitizenPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const { t } = useI18n()
  const { user } = useAuth()
  const { services, office, loading } = useOffice()
  const toast = useToast()
  const [serviceId, setServiceId] = useState<number | null>(null)
  const [query, setQuery] = useState('')
  const [modal, setModal] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [incidentBusy, setIncidentBusy] = useState(false)
  const [incidentActionError, setIncidentActionError] = useState('')
  const emailTicketReference = searchParams.get('ticket')
  const incidentActionToken = searchParams.get('incident_action')
  const ownerKey = user ? `user:${user.id}` : 'guest'
  const [referencesByOwner, setReferencesByOwner] = useState<Record<string, string[]>>(() => {
    try {
      return JSON.parse(localStorage.getItem(SAVED_TOKENS_KEY) || '{}') as Record<string, string[]>
    } catch {
      return {}
    }
  })
  const savedReferences = referencesByOwner[ownerKey] ?? NO_REFERENCES
  const [selectedToken, setSelectedToken] = useState<{ ownerKey: string; reference: string } | null>(null)
  const [loadedTokenList, setLoadedTokenList] = useState<{ ownerKey: string; tokens: Token[] }>({ ownerKey: '', tokens: [] })
  const savedTokens = loadedTokenList.ownerKey === ownerKey ? loadedTokenList.tokens : []
  const reference = selectedToken?.ownerKey === ownerKey ? selectedToken.reference : null
  const selectToken = (value: string | null) => setSelectedToken(value ? { ownerKey, reference: value } : null)

  useEffect(() => {
    if (emailTicketReference) selectToken(emailTicketReference)
  }, [emailTicketReference, ownerKey])

  useEffect(() => {
    if (serviceId === null && services.length) setServiceId(services[0].id)
  }, [services, serviceId])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return services
    return services.filter((s) =>
      `${s.name} ${s.departmentName ?? ''} ${s.description ?? ''}`.toLowerCase().includes(q),
    )
  }, [services, query])
  const selected = useMemo(() => services.find((s) => s.id === serviceId) ?? null, [services, serviceId])
  const { queue } = useQueue(serviceId, office?.id)
  const { token } = useToken(reference)

  useEffect(() => {
    localStorage.setItem(SAVED_TOKENS_KEY, JSON.stringify(referencesByOwner))
    let active = true
    void Promise.all(savedReferences.map((saved) => api.token(saved).catch(() => null))).then((rows) => {
      if (!active) return
      const tokens = rows.filter((row): row is Token => row !== null)
      setLoadedTokenList({ ownerKey, tokens })
      const validReferences = tokens.map((row) => row.reference)
      if (validReferences.length !== savedReferences.length) {
        setReferencesByOwner((current) => ({ ...current, [ownerKey]: validReferences }))
      }
    })
    return () => {
      active = false
    }
  }, [ownerKey, referencesByOwner, savedReferences])

  const createToken = async () => {
    if (!serviceId) return
    setBusy(true)
    setError('')
    try {
      const created = await api.createToken(serviceId, office?.id, selected?.documents ?? [])
      selectToken(created.reference)
      setReferencesByOwner((current) => ({
        ...current,
        [ownerKey]: [created.reference, ...(current[ownerKey] ?? []).filter((saved) => saved !== created.reference)],
      }))
      setModal(false)
      toast.success(t('status.WAITING', 'Waiting'), `${created.label} · ${created.service_name}`)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const respondToIncident = async (action: 'TRANSFER' | 'CANCEL') => {
    if (!reference || !incidentActionToken) return
    setIncidentBusy(true)
    setIncidentActionError('')
    try {
      const result = await api.incidentResponse(reference, action, incidentActionToken)
      setIncidentActionError(action === 'TRANSFER' ? `Your ticket is rescheduled for ${result.scheduled_for}.` : 'Your ticket was cancelled.')
      const updatedReference = action === 'TRANSFER' ? result.token.reference : reference
      selectToken(updatedReference)
      if (action === 'TRANSFER') {
        setReferencesByOwner((current) => ({
          ...current,
          [ownerKey]: [updatedReference, ...(current[ownerKey] ?? []).filter((saved) => saved !== updatedReference)],
        }))
      }
      setSearchParams((current) => {
        const next = new URLSearchParams(current)
        next.delete('incident_action')
        next.set('ticket', updatedReference)
        return next
      })
    } catch (err) {
      setIncidentActionError((err as Error).message)
    } finally {
      setIncidentBusy(false)
    }
  }

  const checkIn = async () => {
    if (!reference) return
    try {
      const updated = await api.checkIn(reference)
      selectToken(updated.reference)
      setLoadedTokenList((current) =>
        current.ownerKey === ownerKey
          ? { ...current, tokens: current.tokens.map((saved) => (saved.reference === updated.reference ? updated : saved)) }
          : current,
      )
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const cancelToken = async () => {
    if (!reference) return
    try {
      const updated = await api.transition(reference, 'CANCELLED')
      setLoadedTokenList((current) =>
        current.ownerKey === ownerKey
          ? { ...current, tokens: current.tokens.map((saved) => (saved.reference === updated.reference ? updated : saved)) }
          : current,
      )
      selectToken(updated.reference)
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const horizon = queue?.prediction

  if (loading) {
    return (
      <div className="grid sm:grid-cols-2 gap-4">
        <SkeletonCard rows={4} />
        <SkeletonCard rows={4} />
      </div>
    )
  }

  return (
    <>
      {/* Hero */}
      <section className="relative overflow-hidden rounded-lg bg-surface border border-line shadow-card text-ink p-6 sm:p-10 mb-6">
        <div aria-hidden className="absolute -right-10 -top-10 w-64 h-64 rounded-full bg-brand/10 blur-3xl pointer-events-none" />
        <div className="relative max-w-2xl">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-soft text-brand px-3 py-1 text-[11px] font-bold uppercase tracking-[0.14em]">
            <ShieldCheck size={14} aria-hidden /> {t('citizen.stageQueued', "You're in the queue")} · {office?.name ?? ''}
          </span>
          <h1 className="mt-4 text-[1.6rem] sm:text-[2.1rem] leading-tight font-extrabold text-ink">
            {t('citizen.title', 'Take your place in line — from anywhere')}
          </h1>
          <p className="mt-2 text-ink-2 text-[15px] leading-relaxed max-w-xl">
            {t('citizen.subtitle', 'Get a virtual token, follow your live position and arrive only when it’s almost your turn.')}
          </p>
          <div className="mt-6 flex flex-wrap items-center gap-3">
            <button
              onClick={() => {
                if (selected) setModal(true)
                else window.location.hash = 'services'
              }}
              className="inline-flex items-center gap-2 rounded-md bg-brand text-white font-semibold px-5 py-3 text-sm border border-brand/90 shadow-sm hover:bg-brand-strong transition-all active:scale-[0.985] min-h-[46px]"
            >
              <Ticket size={18} aria-hidden /> {t('citizen.takeToken', 'Get a virtual token')}
            </button>
            <a
              href="#how"
              className="inline-flex items-center gap-2 rounded-md border border-line bg-surface text-ink font-semibold px-5 py-3 text-sm hover:bg-surface2 hover:border-slate-300 shadow-sm transition-all active:scale-[0.985] min-h-[46px]"
            >
              {t('citizen.howItWorks', 'How it works')}
            </a>
          </div>
        </div>
      </section>

      {/* Stats */}
      <section aria-label={t('staff.overview', 'Live overview')} className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
        <NStat label={t('citizen.peopleWaiting', 'People waiting')} valueNumber={queue?.waiting ?? 0} hint={selected ? selected.name : undefined} delay={0} />
        <NStat label={t('citizen.estimatedWait', 'Estimated wait')} valueNumber={horizon ? horizon.minutes_low : 0} unit="min" hint={horizon ? `~${horizon.minutes_low}–${horizon.minutes_high} min` : undefined} delay={45} />
        <NStat label={t('citizen.activeCounters', 'Open counters')} valueNumber={queue?.active_counters ?? 0} hint="Serving this service" delay={90} />
        <NStat label={t('citizen.avgService', 'Avg service')} valueNumber={Math.round(queue?.average_service_min ?? 0)} unit="min" hint="Real service times" delay={135} />
      </section>

      {/* How it works */}
      <section id="how" className="mb-6">
        <h2 className="text-lg font-bold mb-3">{t('citizen.howItWorks', 'How it works')}</h2>
        <div className="grid sm:grid-cols-3 gap-3">
          {[
            { icon: Search, title: t('citizen.step1.title', 'Pick a service'), body: t('citizen.step1.body', 'Choose the service you need and see the live wait.') },
            { icon: QrCode, title: t('citizen.step2.title', 'Take a virtual token'), body: t('citizen.step2.body', 'Confirm your token and get a QR code you can show at the office.') },
            { icon: Bell, title: t('citizen.step3.title', 'Arrive on time'), body: t('citizen.step3.body', 'Follow your live position. Get the alert and head over just in time.') },
          ].map((step, i) => (
            <article key={i} className="bg-surface border border-line rounded-md shadow-card p-4 flex gap-3 animate-fade-slide" style={{ animationDelay: `${i * 70}ms` }}>
              <span className="grid place-items-center w-10 h-10 rounded-lg bg-brand-soft text-brand shrink-0"><step.icon size={20} aria-hidden /></span>
              <div>
                <b className="block text-sm text-ink">{i + 1}. {step.title}</b>
                <p className="mt-0.5 text-[13px] text-ink-2 leading-snug">{step.body}</p>
              </div>
            </article>
          ))}
        </div>
      </section>

      {error && (
        <div role="alert" className="mb-4 flex items-start gap-3 rounded-md border border-alert/40 bg-alert-soft px-4 py-3 text-sm font-medium text-alert">
          <AlertTriangle size={18} className="shrink-0 mt-0.5" aria-hidden />
          <span className="flex-1">{error}</span>
          <button onClick={() => setError('')} aria-label={t('common.close', 'Close')} className="text-alert">✕</button>
        </div>
      )}

      {/* Services + detail + live queue */}
      <div id="services" className="mb-6">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
          <div>
            <h2 className="text-lg font-bold">{t('citizen.chooseService', 'Choose a service')}</h2>
            <p className="text-[13px] text-ink-2">{t('citizen.documentsHint', 'Check what to bring before you travel.')}</p>
          </div>
          <label className="relative block w-full sm:w-72">
            <span className="sr-only">{t('citizen.searchServices', 'Search services and documents')}</span>
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-3" aria-hidden />
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t('citizen.searchPlaceholder', 'Search by name, e.g. driving licence')}
              className="w-full rounded-md border border-line bg-surface pl-9 pr-3 py-2.5 text-sm min-h-[44px] placeholder:text-ink-3 focus:outline-none focus:ring-2 focus:border-brand focus:ring-brand/25"
            />
          </label>
        </div>

        {filtered.length === 0 ? (
          <EmptyState icon={<Search size={22} />} title={t('sm.noResults', 'No staff match your search.')} hint={t('empty.hint', 'There are no records here yet.')} />
        ) : (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {filtered.map((service, i) => {
              const active = service.id === serviceId
              return (
                <button
                  key={service.id}
                  onClick={() => setServiceId(service.id)}
                  aria-pressed={active}
                  className={`text-left rounded-md bg-surface border p-4 transition-all animate-fade-slide ${
                    active ? 'border-brand ring-2 ring-brand/20 shadow-card' : 'border-line hover:border-brand/50 shadow-card'
                  }`}
                  style={{ animationDelay: `${Math.min(i, 8) * 40}ms` }}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <b className="block text-[15px] text-ink">{service.name}</b>
                      <span className="block text-[11px] uppercase tracking-[0.08em] text-brand font-bold mt-0.5">{service.departmentName}</span>
                    </div>
                    <Badge tone="neutral">{service.code}</Badge>
                  </div>
                  <p className="mt-2 text-[13px] text-ink-2 leading-snug line-clamp-2">{service.description ?? t('citizen.step1.body', 'Choose the service you need and see the live wait.')}</p>
                  <div className="mt-3 flex items-center gap-3 text-[12px] text-ink-3">
                    <span className="inline-flex items-center gap-1"><Clock3 size={13} aria-hidden /> {service.average_service_min} min</span>
                    <span className="inline-flex items-center gap-1"><FileText size={13} aria-hidden /> {service.documents?.length ?? 0} docs</span>
                  </div>
                </button>
              )
            })}
          </div>
        )}
      </div>

      <div className="grid lg:grid-cols-2 gap-4 mb-6 items-start">
        {/* Selected service detail */}
        <Card kicker="SERVICE" title={selected?.name ?? t('citizen.chooseService', 'Choose a service')} action={<Badge tone="ok">{horizon?.method ?? 'live estimate'}</Badge>}>
          <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
            <span className="inline-flex items-center gap-1.5 text-sm text-ink-2">
              <MapPin size={15} aria-hidden /> {selected?.officeName ?? office?.name}
            </span>
          </div>

          {horizon && (
            <div className="rounded-md bg-surface2 border border-line p-4 mb-4">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <span className="block text-[11px] font-bold uppercase tracking-[0.1em] text-ink-3">{t('citizen.yourWait', 'Expected wait')}</span>
                  <b className="block mt-1 text-xl text-ink tabular-nums">
                    {horizon.minutes_low}–{horizon.minutes_high} <em className="text-sm not-italic font-semibold text-ink-2">min</em>
                  </b>
                  <small className="block mt-0.5 text-[12px] text-ink-3">
                    {Math.round(horizon.confidence * 100)}% confidence · {horizon.history_samples} samples
                  </small>
                </div>
                <div className="text-right">
                  <b className="block text-3xl text-brand tabular-nums">{horizon.people_ahead}</b>
                  <span className="block text-[11px] text-ink-3 font-semibold uppercase tracking-[0.08em]">{t('citizen.peopleBefore', 'people ahead')}</span>
                </div>
              </div>
            </div>
          )}

          {selected?.documents?.length ? (
            <div className="mb-4">
              <b className="flex items-center gap-1.5 text-sm text-ink mb-2"><FileText size={15} aria-hidden /> {t('citizen.documents', 'Documents you may need')}</b>
              <ul className="grid sm:grid-cols-2 gap-1.5">
                {selected.documents.map((d) => (
                  <li key={d} className="flex items-center gap-2 rounded-md bg-surface2 border border-line px-3 py-2 text-[13px] text-ink">
                    <CheckCircle2 size={15} className="text-ok shrink-0" aria-hidden /> {d}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          <Button size="lg" className="w-full" onClick={() => setModal(true)} disabled={!selected} icon={<Ticket size={18} />}>
            {t('citizen.takeToken', 'Get a virtual token')}
          </Button>
          <p className="mt-2 flex items-center gap-1.5 text-[12px] text-ink-3">
            <ShieldCheck size={13} aria-hidden /> QR code carries an opaque reference only — no personal data.
          </p>
        </Card>

        {/* Live queue */}
        <Card
          kicker={t('citizen.liveQueue', 'Current queue')}
          title={selected?.name ?? 'Queue'}
          action={
            <span className="inline-flex items-center gap-1.5 text-[12px] font-semibold text-ok">
              <span aria-hidden className="live-dot" /> {t('header.online', 'System online')}
            </span>
          }
        >
          {!queue ? (
            <SkeletonCard rows={4} />
          ) : queue.tokens.length === 0 ? (
            <EmptyState icon={<Users size={22} />} title={t('citizen.queueEmpty', 'No one is waiting for this service right now.')} hint={t('staff.noTokens', 'No one is waiting right now.')} />
          ) : (
            <ul className="divide-y divide-line">
              {queue.tokens.map((row) => (
                <li key={row.id} className="flex items-center gap-3 py-2.5">
                  <span className="grid place-items-center w-9 h-9 rounded-lg bg-brand-soft text-brand font-bold text-sm shrink-0">{row.label}</span>
                  <span className="flex-1 min-w-0">
                    <b className="block text-sm text-ink truncate">{row.stage.replace(/_/g, ' ')}</b>
                    <span className="text-[12px] text-ink-3">{t('citizen.eta', 'Estimated wait')} · {row.eta_min} min</span>
                  </span>
                  <Badge tone={statusTone(row.status)}>{t(`status.${row.status}`, row.status)}</Badge>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      {/* My token */}
      <section aria-label={t('citizen.myToken', 'My token')}>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-bold">{t('citizen.myToken', 'My token')}</h2>
          {token && (
            <button onClick={selectToken.bind(null, null)} className="inline-flex items-center gap-1.5 text-sm font-semibold text-ink-2 hover:text-ink rounded-md px-2 py-2 min-h-[40px]">
              ✕ {t('common.close', 'Close')}
            </button>
          )}
        </div>

        {token ? (
          <MyTokenPanel
            token={token}
            onClose={() => selectToken(null)}
            onCheckIn={() => void checkIn()}
            onCancel={() => void cancelToken()}
            incidentBusy={incidentBusy}
            incidentActionToken={incidentActionToken}
            incidentActionError={incidentActionError}
            onRespond={respondToIncident}
          />
        ) : savedTokens.length > 0 ? (
          <Card kicker="SAVED" title={t('citizen.myToken', 'My token')} action={<Badge tone="brand">{savedTokens.length} {t('ca.selected', '{n} selected').replace('{n}', 'saved')}</Badge>}>
            <ul className="divide-y divide-line">
              {savedTokens.map((saved) => (
                <li key={saved.reference}>
                  <button onClick={() => selectToken(saved.reference)} className="w-full flex items-center gap-3 py-3 text-left">
                    <span className="grid place-items-center w-9 h-9 rounded-lg bg-brand-soft text-brand font-bold text-sm shrink-0">{saved.label}</span>
                    <span className="flex-1 min-w-0">
                      <b className="block text-sm text-ink">{saved.service_name}</b>
                      <span className="text-[12px] text-ink-3">{saved.office_name}</span>
                    </span>
                    <Badge tone={statusTone(saved.status)}>{t(`status.${saved.status}`, saved.status)}</Badge>
                  </button>
                </li>
              ))}
            </ul>
          </Card>
        ) : (
          <EmptyState
            icon={<Ticket size={22} />}
            title={t('citizen.tokenEmpty', 'No active token yet')}
            hint={t('citizen.tokenHint', 'Take a virtual token above and track it here in real time.')}
          />
        )}
      </section>

      {/* Confirm modal */}
      <Modal
        open={modal && !!selected}
        onClose={() => setModal(false)}
        title={t('citizen.confirmToken', 'Confirm your token')}
        description={selected ? `${selected.name} · ${selected.officeName ?? office?.name}` : undefined}
        footer={
          <>
            <Button variant="secondary" onClick={() => setModal(false)} disabled={busy}>{t('common.cancel', 'Cancel')}</Button>
            <Button onClick={createToken} loading={busy} loadingLabel="Reserving…">{t('citizen.confirmToken', 'Confirm your token')}</Button>
          </>
        }
      >
        {selected && (
          <div className="flex flex-col gap-4">
            <div className="rounded-md border border-line bg-surface2 px-4 py-3">
              <div className="flex items-center justify-between gap-3">
                <span className="text-[11px] font-bold uppercase tracking-[0.1em] text-ink-3">{t('citizen.estimatedWait', 'Estimated wait')}</span>
                <b className="text-lg text-ink tabular-nums">
                  {horizon ? `${horizon.minutes_low}–${horizon.minutes_high} min` : '—'}
                </b>
              </div>
            </div>
            {selected.documents?.length ? (
              <div>
                <b className="block text-sm text-ink mb-2">{t('citizen.documents', 'Documents you may need')}</b>
                <ul className="space-y-1.5">
                  {selected.documents.map((d) => (
                    <li key={d} className="flex items-center gap-2 text-[13px] text-ink">
                      <CheckCircle2 size={15} className="text-ok shrink-0" aria-hidden /> {d}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        )}
      </Modal>
    </>
  )
}

function MyTokenPanel({
  token, onClose, onCheckIn, onCancel, incidentBusy, incidentActionToken, incidentActionError, onRespond,
}: {
  token: Token
  onClose: () => void
  onCheckIn: () => void
  onCancel: () => void
  incidentBusy: boolean
  incidentActionToken: string | null
  incidentActionError: string
  onRespond: (action: 'TRANSFER' | 'CANCEL') => void
}) {
  const { t } = useI18n()
  const { user } = useAuth()
  const stage = stageForToken(token)
  const progressPct = token.people_ahead === 0 ? 85 : Math.max(15, 100 - token.people_ahead * 12)

  return (
    <article className="rounded-lg bg-surface border border-line shadow-card overflow-hidden">
      <div className="grid md:grid-cols-[auto_1fr] gap-5 p-5">
        {/* QR */}
        <div className="flex flex-col items-center gap-2">
          {token.qr_data_url ? (
            <img src={token.qr_data_url} alt={`QR code for ${token.label}`} className="w-36 h-36 rounded-md bg-surface" width={144} height={144} />
          ) : (
            <div className="grid place-items-center w-36 h-36 rounded-md bg-surface2 border border-line text-ink-3">
              <QrCode size={40} />
            </div>
          )}
          <p className="text-[12px] text-ink-3 flex items-center gap-1"><QrCode size={13} aria-hidden /> Show at the office to check in.</p>
        </div>

        {/* Details */}
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2.5">
            <b className="text-2xl text-brand tabular-nums">{token.label}</b>
            <span className="text-sm text-ink-2">{token.service_name} · {token.office_name}</span>
            <Badge tone={statusTone(token.status)}>{t(`status.${token.status}`, token.status)}</Badge>
          </div>

          {/* Stage banner */}
          <div
            className={`mt-3 rounded-md border px-4 py-3 flex items-center gap-3 ${
              stage.level === 'your_turn' ? 'border-ok bg-ok-soft' : stage.level === 'come_now' ? 'border-warn bg-warn-soft' : stage.level === 'approaching' ? 'border-info bg-info-soft' : 'border-line bg-surface2'
            }`}
            role="status"
            aria-live="polite"
          >
            <span
              className={`grid place-items-center w-10 h-10 rounded-lg shrink-0 ${
                stage.level === 'your_turn' ? 'bg-ok text-white' : stage.level === 'come_now' ? 'bg-warn text-white' : stage.level === 'approaching' ? 'bg-info text-white' : 'bg-brand text-white'
              }`}
            >
              {stage.level === 'your_turn' ? <BadgeCheck size={20} aria-hidden /> : <Bell size={20} aria-hidden />}
            </span>
            <div>
              <b className="block text-sm text-ink">
                {stage.level === 'your_turn'
                  ? t('citizen.goToCounter', 'Go to counter {counter} and show this token').replace('{counter}', token.counter_name ?? token.label)
                  : t(stage.message)}
              </b>
              <small className="block text-[12px] text-ink-2 mt-0.5">{token.stage_message ?? ''}</small>
            </div>
          </div>

          {token.scheduled_for && (
            <p className="mt-2 text-[13px] text-info">Rescheduled for {token.scheduled_for}. Your earlier ticket history is preserved.</p>
          )}

          {token.incident_response_status === 'PENDING' && (
            <div className="mt-3 rounded-md border border-warn/50 bg-warn-soft px-4 py-3">
              <b className="flex items-center gap-1.5 text-sm text-warn"><AlertTriangle size={15} aria-hidden /> Office incident: action required</b>
              <p className="text-[13px] text-warn/90 mt-1">Choose whether to transfer this ticket to the next available working day or cancel it.</p>
              {token.incident_response_due && <small className="block text-[12px] text-ink-2">Respond by {new Date(token.incident_response_due).toLocaleString()}.</small>}
              {incidentActionError && <p className="text-[13px] font-semibold text-alert mt-1.5">{incidentActionError}</p>}
              {incidentActionToken ? (
                user ? (
                  <div className="mt-2 flex flex-wrap gap-2">
                    <Button size="sm" loading={incidentBusy} onClick={() => onRespond('TRANSFER')}>Transfer to next working day</Button>
                    <Button size="sm" variant="dangerGhost" loading={incidentBusy} onClick={() => onRespond('CANCEL')}>Cancel ticket</Button>
                  </div>
                ) : (
                  <a className="mt-2 inline-block" href={`/login?return_to=${encodeURIComponent(`${window.location.pathname}${window.location.search}`)}`}>
                    {t('common.signIn', 'Sign in')} to respond
                  </a>
                )
              ) : (
                <small className="block mt-1 text-[12px] text-ink-2">Open the secure action link from your incident email to respond.</small>
              )}
            </div>
          )}

          <div className="mt-4 grid grid-cols-[auto_1fr] gap-5 items-center">
            <ProgressRing value={progressPct} size={78} stroke={8} label={String(token.position ?? '—')} sub={t('citizen.position', 'Position in queue')} tone={stage.level === 'your_turn' ? 'ok' : stage.level === 'come_now' ? 'warn' : 'brand'} />
            <div className="space-y-3 min-w-0">
              <div>
                <div className="flex items-center justify-between text-[12px] font-semibold mb-1">
                  <span className="text-ink-3">
                    {t('citizen.stayHome', 'You can stay at home for now')} → {t('citizen.goToCounter', 'Go to counter {counter} and show this token').split(' ')[0]}
                  </span>
                  <span className="text-ink tabular-nums">{token.eta_min} min</span>
                </div>
                <Meter pct={progressPct} tone={stage.level === 'your_turn' ? 'ok' : stage.level === 'come_now' ? 'warn' : 'brand'} label={t('citizen.eta', 'Estimated wait')} />
              </div>
              {token.expected_service_at && (
                <p className="text-[12px] text-ink-3">
                  Expected service ≈ {new Date(token.expected_service_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  {token.counter_name ? ` · ${token.counter_name}` : ''}
                </p>
              )}
            </div>
          </div>

          {/* Actions */}
          {(token.status === 'WAITING' || token.status === 'APPROACHING') && (
            <div className="mt-4 flex flex-wrap gap-2">
              <Button onClick={onCheckIn} icon={<Bell size={16} />}>{t('citizen.checkIn', "I've arrived")}</Button>
            </div>
          )}
          {token.status === 'ARRIVED' && <p className="mt-3 text-[13px] text-ok">Arrival confirmed. Please wait for your token to be called.</p>}
          {(token.status === 'WAITING' || token.status === 'APPROACHING' || token.status === 'ARRIVED') && (
            <div className="mt-3">
              <Button variant="dangerGhost" onClick={onCancel}>{t('citizen.cancelToken', 'Cancel token')}</Button>
            </div>
          )}
          {token.status === 'COMPLETED' && <FeedbackForm reference={token.reference} onDone={onClose} />}
        </div>
      </div>
    </article>
  )
}

function FeedbackForm({ reference, onDone }: { reference: string; onDone: () => void }) {
  const { t } = useI18n()
  const [rating, setRating] = useState(5)
  const [accurate, setAccurate] = useState<boolean | null>(null)
  const [comment, setComment] = useState('')
  const [done, setDone] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const submit = async () => {
    setBusy(true)
    setError('')
    try {
      await api.feedback(reference, rating, accurate, comment)
      setDone(true)
      setTimeout(onDone, 1400)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  if (done) {
    return (
      <p className="mt-3 rounded-md border border-ok bg-ok-soft px-3 py-2 text-sm font-medium text-ok flex items-center gap-2">
        <CheckCircle2 size={16} aria-hidden /> {t('citizen.allGood', 'All good, thanks')}
      </p>
    )
  }

  return (
    <div className="mt-4 rounded-md border border-line bg-surface2 p-4">
      <b className="block text-sm text-ink">{t('citizen.feedback', 'How was your service?')}</b>
      {error && <p className="text-[13px] text-alert mt-1">{error}</p>}
      <div className="mt-2 flex items-center gap-1">
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            type="button"
            onClick={() => setRating(n)}
            aria-label={`${n} ${n === 1 ? 'star' : 'stars'}`}
            className={`grid place-items-center w-11 h-11 rounded-md transition-colors ${rating >= n ? 'text-warn' : 'text-ink-3 hover:text-warn/60'}`}
          >
            <Star size={22} fill={rating >= n ? 'currentColor' : 'none'} />
          </button>
        ))}
      </div>
      <div className="mt-3 flex items-center gap-2 text-[13px]">
        <span className="text-ink-2">{t('citizen.feedbackHint', 'Your feedback helps the office improve.')}</span>
        <span className="flex gap-1.5 ml-auto">
          <button
            type="button"
            onClick={() => setAccurate(true)}
            className={`rounded-md px-3 py-1.5 text-sm font-semibold border ${accurate === true ? 'border-ok bg-ok text-white' : 'border-line bg-surface text-ink-2'}`}
          >
            Yes
          </button>
          <button
            type="button"
            onClick={() => setAccurate(false)}
            className={`rounded-md px-3 py-1.5 text-sm font-semibold border ${accurate === false ? 'border-alert bg-alert text-white' : 'border-line bg-surface text-ink-2'}`}
          >
            No
          </button>
        </span>
      </div>
      <textarea
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        placeholder={t('common.optional', 'optional')}
        maxLength={1000}
        rows={2}
        className="mt-3 w-full rounded-md border border-line bg-surface px-3 py-2.5 text-sm min-h-[72px] focus:outline-none focus:ring-2 focus:border-brand focus:ring-brand/25"
      />
      <Button className="mt-2 w-full" onClick={submit} loading={busy} loadingLabel="Sending…">{t('citizen.submitFeedback', 'Submit feedback')}</Button>
    </div>
  )
}