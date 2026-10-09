import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Bell, CheckCircle2, Clock3, MapPin, QrCode, ShieldCheck, Ticket, Users } from 'lucide-react'
import { Badge, Card, CloseButton, Empty, ErrorBox, Spinner, Stat } from '../components/Bits'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { useOffice } from '../lib/office'
import { useAuth } from '../lib/auth'
import { useQueue, useToken } from '../lib/hooks'
import type { Token } from '../lib/types'

const SAVED_TOKENS_KEY = 'ql_citizen_tokens_by_owner'
const NO_REFERENCES: string[] = []

export default function CitizenPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const { t } = useI18n()
  const { user } = useAuth()
  const { services, office } = useOffice()
  const [serviceId, setServiceId] = useState<number | null>(null)
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
    return () => { active = false }
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

  const horizon = queue?.prediction

  return (
    <>
      <div className="ql-welcome">
        <div>
          <span className="ql-kicker">REMOTE CITIZEN SERVICES</span>
          <h1>{t('citizen.title', 'Take your place in line — from anywhere')}</h1>
          <p>{t('citizen.subtitle', 'Get a virtual token, follow your live position and arrive only when it’s almost your turn.')}</p>
        </div>
        <button className="ql-primary" onClick={() => setModal(true)} disabled={!selected}>
          <Ticket size={17} /> {t('citizen.takeToken', 'Get a virtual token')}
        </button>
      </div>

      {error && <ErrorBox message={error} onDismiss={() => setError('')} />}

      {savedTokens.length > 0 && (
        <Card kicker="YOUR TOKENS" title="Virtual tokens" action={<Badge tone="brand">{savedTokens.length} saved</Badge>}>
          <div className="ql-token-list">
            {savedTokens.map((saved) => (
              <button className="ql-queue-row ql-saved-token" key={saved.reference} onClick={() => selectToken(saved.reference)}>
                <span className="ql-number">{saved.label}</span>
                <span>{saved.service_name}</span>
                <Badge tone={saved.status === 'COMPLETED' ? 'ok' : 'brand'}>{saved.status}</Badge>
              </button>
            ))}
          </div>
          <small>Select a token to reopen its QR code and actions.</small>
        </Card>
      )}

      <div className="ql-stats">
        <Stat label={t('citizen.peopleWaiting', 'People waiting')} value={queue?.waiting ?? '—'} hint="In this service queue now" />
        <Stat
          label={t('citizen.estimatedWait', 'Estimated wait')}
          value={horizon ? horizon.minutes_low : '—'}
          unit="min"
          hint={horizon ? `Likely within ${horizon.minutes_low}–${horizon.minutes_high} min` : undefined}
        />
        <Stat label={t('citizen.activeCounters', 'Open counters')} value={queue?.active_counters ?? '—'} hint="Serving this service" />
        <Stat label={t('citizen.avgService', 'Avg service')} value={queue?.average_service_min ?? '—'} unit="min" hint="Measured from real service times" />
      </div>

      <div className="ql-columns">
        <Card
          kicker="SERVICE"
          title={selected?.name ?? 'Choose a service'}
          action={<Badge tone="ok">{horizon?.method ?? 'live estimate'}</Badge>}
        >
          <div className="ql-service-select">
            <label htmlFor="service">{t('citizen.chooseService', 'Choose a service')}</label>
            <select id="service" value={serviceId ?? ''} onChange={(e) => setServiceId(Number(e.target.value))}>
              {services.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} · {s.departmentName}
                </option>
              ))}
            </select>
            <small>
              <MapPin size={13} /> {selected?.officeName ?? office?.name}
            </small>
          </div>

          {horizon && (
            <>
              <div className="ql-wait">
                <div>
                  <span>{t('citizen.yourWait', 'EXPECTED WAIT')}</span>
                  <b>
                    {horizon.minutes_low}–{horizon.minutes_high} <em>min</em>
                  </b>
                  <small>{Math.round(horizon.confidence * 100)}% confidence · {horizon.history_samples} historical samples</small>
                </div>
                <div className="ql-people">
                  <b>{horizon.people_ahead}</b>
                  <span>ahead of you</span>
                </div>
              </div>

            </>
          )}

          {selected?.documents?.length ? (
            <div className="ql-docs">
              <b>Documents to bring</b>
              {selected.documents.map((d) => (
                <div key={d}>
                  <CheckCircle2 size={16} /> {d}
                </div>
              ))}
            </div>
          ) : null}

          <button className="ql-primary ql-wide" onClick={() => setModal(true)} disabled={!selected}>
            {t('citizen.takeToken', 'Get a virtual token')}
          </button>
          <p className="ql-note">
            <ShieldCheck size={14} /> Your QR code contains an opaque reference only — no personal data.
          </p>
        </Card>

        <Card
          kicker="LIVE QUEUE"
          title={selected?.name ?? 'Queue'}
          action={
            <span className="ql-refresh">
              <i /> live
            </span>
          }
        >
          {!queue ? (
            <Spinner />
          ) : queue.tokens.length === 0 ? (
            <Empty icon={<Users size={22} />} title="No one is waiting" hint="Be the first to take a token." />
          ) : (
            <div className="ql-token-list">
              {queue.tokens.map((row) => (
                <div key={row.id} className="ql-queue-row">
                  <span className="ql-number">{row.label}</span>
                  <span className="ql-state">{row.stage.replace(/_/g, ' ')}</span>
                  <span className="ql-eta">{row.eta_min} min</span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {modal && selected && (
        <div className="ql-backdrop" onClick={() => setModal(false)}>
          <section className="ql-modal" onClick={(e) => e.stopPropagation()}>
            <CloseButton onClick={() => setModal(false)} label="Close" />
            <span className="ql-kicker">REMOTE CHECK-IN</span>
            <h2>{t('citizen.confirmToken', 'Confirm your token')}</h2>
            <p>We’ll reserve your place in the {selected.name} queue at {selected.officeName}.</p>
            <div className="ql-modal-est">
              <Clock3 size={17} /> Estimated wait
              <b>{horizon ? `${horizon.minutes_low}–${horizon.minutes_high} min` : '—'}</b>
            </div>
            {selected.documents?.length ? (
              <div className="ql-docs">
                <b>Please carry</b>
                {selected.documents.map((d) => (
                  <div key={d}>
                    <CheckCircle2 size={16} /> {d}
                  </div>
                ))}
              </div>
            ) : null}
            <button className="ql-primary ql-wide" onClick={createToken} disabled={busy}>
              {busy ? 'Reserving…' : 'Confirm and get token'}
            </button>
          </section>
        </div>
      )}

      {token && (
        <aside className="ql-token-card">
          <CloseButton onClick={() => selectToken(null)} label="Hide token" />
          <span className="ql-kicker">YOUR VIRTUAL TOKEN</span>
          <div className="ql-token-title">
            <b>{token.label}</b>
            <Badge tone={token.status === 'COMPLETED' ? 'ok' : 'brand'}>{token.status}</Badge>
          </div>
          {token.stage_message && <p className="ql-stage-note">{token.stage_message}</p>}
          {token.scheduled_for && <p className="ql-note">Rescheduled for {token.scheduled_for}. Your earlier ticket history is preserved.</p>}
          {token.incident_response_status === 'PENDING' && (
            <div className="ql-docs">
              <b>Office incident: action required</b>
              <p>Choose whether to transfer this ticket to the next available working day or cancel it.</p>
              {token.incident_response_due && <small>Respond by {new Date(token.incident_response_due).toLocaleString()}.</small>}
              {incidentActionError && <p className="ql-error-text">{incidentActionError}</p>}
              {incidentActionToken ? (
                user ? (
                  <div className="ql-inline">
                    <button className="ql-primary ql-small" disabled={incidentBusy} onClick={() => void respondToIncident('TRANSFER')}>Transfer to next working day</button>
                    <button className="ql-secondary ql-small" disabled={incidentBusy} onClick={() => void respondToIncident('CANCEL')}>Cancel ticket</button>
                  </div>
                ) : (
                  <a className="ql-primary ql-small" href={`/login?return_to=${encodeURIComponent(`${window.location.pathname}${window.location.search}`)}`}>Sign in to respond</a>
                )
              ) : <small>Open the secure action link from your incident email to respond.</small>}
            </div>
          )}
          <div className="ql-token-data">
            <div>
              <small>POSITION</small>
              <b>{token.position || '—'}</b>
            </div>
            <div>
              <small>EST. WAIT</small>
              <b>{token.eta_min} min</b>
            </div>
          </div>
          {token.qr_data_url && <img className="ql-qr" src={token.qr_data_url} alt={`QR code for ${token.label}`} />}
          <small className="ql-qr-hint">
            <QrCode size={13} /> Show this QR at the office to check in.
          </small>

          <div className="ql-token-actions">
            {(token.status === 'WAITING' || token.status === 'APPROACHING') && (
                <button
                  onClick={async () => {
                    try {
                      const updated = await api.checkIn(token.reference)
                      selectToken(updated.reference)
                      setLoadedTokenList((current) => current.ownerKey === ownerKey
                        ? { ...current, tokens: current.tokens.map((saved) => saved.reference === updated.reference ? updated : saved) }
                        : current)
                  } catch (err) {
                    setError((err as Error).message)
                  }
                }}
              >
                <Bell size={15} /> I have arrived (check in)
              </button>
            )}
            {token.status === 'ARRIVED' && <p className="ql-note">Arrival confirmed. Please wait for your token to be called.</p>}
            {(token.status === 'WAITING' || token.status === 'APPROACHING' || token.status === 'ARRIVED') && (
              <button
                onClick={async () => {
                  try {
                    const updated = await api.transition(token.reference, 'CANCELLED')
                    setLoadedTokenList((current) => current.ownerKey === ownerKey
                      ? { ...current, tokens: current.tokens.map((saved) => saved.reference === updated.reference ? updated : saved) }
                      : current)
                    selectToken(updated.reference)
                  } catch (err) {
                    setError((err as Error).message)
                  }
                }}
              >
                Cancel token
              </button>
            )}
            {token.status === 'COMPLETED' && (
              <FeedbackForm reference={token.reference} onDone={() => selectToken(null)} />
            )}
          </div>
        </aside>
      )}
    </>
  )
}

function FeedbackForm({ reference, onDone }: { reference: string; onDone: () => void }) {
  const [rating, setRating] = useState(5)
  const [accurate, setAccurate] = useState<boolean | null>(null)
  const [comment, setComment] = useState('')
  const [done, setDone] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    setBusy(true)
    setError('')
    try {
      await api.feedback(reference, rating, accurate, comment)
      setDone(true)
      setTimeout(onDone, 1200)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  if (done) {
    return (
      <p className="ql-note">
        <CheckCircle2 size={14} /> Thanks — your feedback was recorded.
      </p>
    )
  }

  return (
    <div className="ql-feedback">
      <b>How was your visit?</b>
      {error && <p className="ql-muted">{error}</p>}
      <div className="ql-stars">
        {[1, 2, 3, 4, 5].map((n) => (
          <button key={n} type="button" className={rating >= n ? 'on' : ''} onClick={() => setRating(n)} aria-label={`${n} stars`}>
            ★
          </button>
        ))}
      </div>
      <div className="ql-eta-accuracy">
        <span>Was the wait estimate accurate?</span>
        <button type="button" className={accurate === true ? 'on' : ''} onClick={() => setAccurate(true)}>
          Yes
        </button>
        <button type="button" className={accurate === false ? 'on' : ''} onClick={() => setAccurate(false)}>
          No
        </button>
      </div>
      <textarea
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        placeholder="Optional comment"
        maxLength={1000}
        rows={2}
      />
      <button className="ql-primary ql-wide" onClick={submit} disabled={busy}>
        {busy ? 'Sending…' : 'Submit feedback'}
      </button>
    </div>
  )
}
