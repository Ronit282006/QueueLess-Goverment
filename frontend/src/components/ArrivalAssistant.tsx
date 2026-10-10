import { useEffect, useState } from 'react'
import { AlertTriangle, BadgeCheck, BellRing, Bike, Car, Clock3, Footprints, LocateFixed, MapPin, Navigation, Timer, Users } from 'lucide-react'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { useLocation } from '../lib/location'
import type { TravelMode } from '../lib/location'
import { Badge, Button, Card, EmptyState, Skeleton, useToast } from './ui'
import type { DepartureGuidance, GraceInfo, OfficeRecommendation, OfficeRecommendations, Token } from '../lib/types'

const MODES: { value: TravelMode; icon: typeof Car; labelKey: string; fallback: string }[] = [
  { value: 'driving', icon: Car, labelKey: 'arrival.mode.driving', fallback: 'Driving' },
  { value: 'walking', icon: Footprints, labelKey: 'arrival.mode.walking', fallback: 'Walking' },
  { value: 'cycling', icon: Bike, labelKey: 'arrival.mode.cycling', fallback: 'Cycling' },
]

/** Cosmetic countdown derived from a server deadline — the server owns cancellation. */
export function useCountdown(deadline: string | null | undefined): number | null {
  const target = deadline ? new Date(deadline).getTime() : null
  const [remaining, setRemaining] = useState<number | null>(() =>
    target ? Math.max(0, Math.floor((target - Date.now()) / 1000)) : null,
  )
  useEffect(() => {
    if (!target) {
      setRemaining(null)
      return
    }
    const tick = () => setRemaining(Math.max(0, Math.floor((target - Date.now()) / 1000)))
    tick()
    const id = window.setInterval(tick, 1000)
    return () => window.clearInterval(id)
  }, [target])
  return remaining
}

export function formatClock(totalSeconds: number | null): string {
  if (totalSeconds === null) return '--:--'
  const m = Math.floor(totalSeconds / 60)
  const s = totalSeconds % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

/** First-run / opt-in location permission card. */
export function LocationOnboarding() {
  const { t } = useI18n()
  const { coords, permission, requesting, error, requestLocation, clear, mode, setMode } = useLocation()

  return (
    <Card
      kicker={t('arrival.kicker', 'Smart arrival')}
      title={t('arrival.locationTitle', 'Plan your journey')}
      action={<Badge tone={coords ? 'ok' : 'neutral'}>{coords ? t('arrival.enabled', 'Location on') : t('arrival.optional', 'Optional')}</Badge>}
      className="mb-6"
    >
      {coords ? (
        <div className="flex flex-col gap-3">
          <p className="text-[13px] text-ink-2">
            {t('arrival.locationOn', 'We use your location only to estimate travel time to the office. It is never shared with staff.')}
          </p>
          <div className="flex items-center gap-2 text-[12px] text-ink-3">
            <MapPin size={14} aria-hidden /> {coords.latitude.toFixed(3)}, {coords.longitude.toFixed(3)}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {MODES.map((m) => (
              <button
                key={m.value}
                type="button"
                onClick={() => setMode(m.value)}
                aria-pressed={mode === m.value}
                className={`inline-flex items-center gap-1.5 rounded-md border px-3 py-2 text-sm font-semibold min-h-[40px] ${
                  mode === m.value ? 'border-brand bg-brand-soft text-brand' : 'border-line bg-surface text-ink-2 hover:border-brand/40'
                }`}
              >
                <m.icon size={15} aria-hidden /> {t(m.labelKey, m.fallback)}
              </button>
            ))}
            <Button variant="ghost" size="sm" onClick={clear}>{t('arrival.forget', 'Forget my location')}</Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          <p className="text-[13px] text-ink-2">
            {t('arrival.enablePrompt', 'Share your location to see the best office to visit, your travel time and when to leave. Entirely optional.')}
          </p>
          {error && <p className="text-[13px] text-ink-2">{error}</p>}
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => void requestLocation()} loading={requesting} icon={<LocateFixed size={16} />}>
              {t('arrival.useLocation', 'Use my location')}
            </Button>
          </div>
          {permission === 'denied' && (
            <p className="text-[12px] text-ink-3">{t('arrival.denied', 'You can enable location later from your browser settings.')}</p>
          )}
        </div>
      )}
    </Card>
  )
}

/** Cross-office recommendation list for the currently selected service. */
export function OfficeRecommendations({
  serviceId,
  selectedOfficeId,
  onSelect,
}: {
  serviceId: number | null
  selectedOfficeId: number | null
  onSelect: (officeId: number | null, serviceId: number, officeName: string) => void
}) {
  const { t } = useI18n()
  const { coords, mode } = useLocation()
  const [data, setData] = useState<OfficeRecommendations | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!serviceId || !coords) {
      setData(null)
      return
    }
    let active = true
    setLoading(true)
    setError(null)
    api
      .recommendOffices(serviceId, coords.latitude, coords.longitude, mode, selectedOfficeId ?? undefined)
      .then((result) => active && setData(result))
      .catch((err: Error) => active && setError(err.message))
      .finally(() => active && setLoading(false))
    return () => {
      active = false
    }
  }, [serviceId, coords, mode, selectedOfficeId])

  if (!coords || !serviceId) return null

  const assessment = data?.assessment ?? null

  return (
    <section id="arrival" className="mb-6">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h2 className="text-lg font-bold">{t('arrival.recommendTitle', 'Best office for you')}</h2>
          <p className="text-[13px] text-ink-2">{t('arrival.recommendHint', 'Comparing travel time and live queue length.')}</p>
        </div>
        {data && <Badge tone={data.routing.live ? 'ok' : 'neutral'}>{data.routing.provider}</Badge>}
      </div>

      {loading && <Skeleton className="h-24 w-full" />}
      {error && <EmptyState icon={<MapPin size={22} />} title={t('arrival.unavailable', 'Recommendations unavailable')} hint={error} />}
      {data && (
        <div className="grid gap-3">
          {data.explanation && (
            <p className="text-[13px] font-medium text-ink">{t('arrival.explanation', data.explanation)}</p>
          )}

          {assessment && (
            <div
              role="status"
              className={`rounded-md border px-4 py-3 flex items-start gap-3 ${
                assessment.is_best ? 'border-ok/50 bg-ok-soft' : 'border-warn/50 bg-warn-soft'
              }`}
            >
              {assessment.is_best ? (
                <BadgeCheck size={18} className="text-ok shrink-0 mt-0.5" aria-hidden />
              ) : (
                <AlertTriangle size={18} className="text-warn shrink-0 mt-0.5" aria-hidden />
              )}
              <div>
                <b className={`block text-sm ${assessment.is_best ? 'text-ok' : 'text-warn'}`}>
                  {assessment.is_best
                    ? t('arrival.youPickedBest', 'You picked the best office for you')
                    : t('arrival.youPickedNotBest', 'Not the fastest option right now')}
                </b>
                <p className="text-[13px] text-ink mt-0.5">{assessment.message}</p>
              </div>
            </div>
          )}

          <ul className="grid sm:grid-cols-2 gap-3">
            {data.offices.map((row) => (
              <RecommendationRow
                key={row.office_id}
                row={row}
                selected={row.office_id === selectedOfficeId}
                onSelect={() => onSelect(row.office_id, row.service_id, row.office_name)}
              />
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}

function RecommendationRow({
  row,
  selected,
  onSelect,
}: {
  row: OfficeRecommendation
  selected: boolean
  onSelect: () => void
}) {
  const { t } = useI18n()
  const travel = row.travel
  const best = row.recommended
  return (
    <li
      className={`rounded-md border p-4 transition-all ${
        selected
          ? 'border-brand ring-2 ring-brand/30 bg-surface shadow-card'
          : best
            ? 'border-brand/60 bg-surface shadow-card'
            : 'border-line bg-surface'
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <b className="block text-[15px] text-ink truncate">{row.office_name}</b>
          <span className="block text-[12px] text-ink-3 truncate">{row.office_address}</span>
        </div>
        <span className="flex items-center gap-1.5 shrink-0">
          {best && <Badge tone="brand">{t('arrival.best', 'Best')}</Badge>}
          {selected && <Badge tone="ok">{t('arrival.selected', 'Selected')}</Badge>}
        </span>
      </div>
      <div className="mt-3 flex flex-wrap gap-3 text-[12px] text-ink-2">
        <span className="inline-flex items-center gap-1">
          <Navigation size={13} aria-hidden /> {travel?.duration_min != null ? `${travel.duration_min} min` : t('arrival.na', 'n/a')}
        </span>
        <span className="inline-flex items-center gap-1">
          <Users size={13} aria-hidden /> {row.queue_wait_min} min {t('arrival.queue', 'queue')}
        </span>
        {row.total_min != null && (
          <span className="inline-flex items-center gap-1 font-semibold text-ink">
            <Clock3 size={13} aria-hidden /> {row.total_min} min {t('arrival.total', 'total')}
          </span>
        )}
      </div>
      {row.departure_in_min != null && row.departure_in_min > 0 && (
        <p className="mt-2 text-[12px] font-semibold text-brand">
          {t('arrival.leaveIn', 'Leave in about {n} min').replace('{n}', String(row.departure_in_min))}
        </p>
      )}
      {row.note && <p className="mt-2 text-[12px] text-ink-3">{row.note}</p>}
      {travel && !travel.available && <p className="mt-2 text-[12px] text-ink-3">{travel.message}</p>}
      <Button
        size="sm"
        variant={selected ? 'secondary' : 'outline'}
        className="mt-3"
        onClick={onSelect}
        aria-pressed={selected}
      >
        {selected ? t('arrival.selectedOffice', 'Selected office') : t('arrival.selectOffice', 'Select this office')}
      </Button>
    </li>
  )
}

/** Departure guidance + reminder opt-in for an active token. */
export function DepartureGuidancePanel({ token }: { token: Token }) {
  const { t } = useI18n()
  const { coords, mode } = useLocation()
  const toast = useToast()
  const [guidance, setGuidance] = useState<DepartureGuidance | null>(null)
  const [busy, setBusy] = useState(false)
  const active = ['WAITING', 'APPROACHING'].includes(token.status)
  const arrivalDeadline = token.grace?.state === 'ACTIVE' ? token.grace.deadline : null

  useEffect(() => {
    if (!coords || !active) {
      setGuidance(null)
      return
    }
    let alive = true
    api
      .tokenGuidance(token.reference, coords.latitude, coords.longitude, mode)
      .then((result) => alive && setGuidance(result))
      .catch(() => alive && setGuidance(null))
    return () => {
      alive = false
    }
  }, [coords, mode, active, token.reference])

  if (!coords || !active) return null

  const scheduleReminder = async () => {
    if (!coords) return
    setBusy(true)
    try {
      const result = await api.scheduleReminder(token.reference, coords.latitude, coords.longitude, mode)
      toast.success(
        t('arrival.reminderSet', 'Reminder set'),
        result.reminder.due_at ? new Date(result.reminder.due_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '',
      )
    } catch (err) {
      toast.error(t('arrival.reminderFailed', 'Could not set reminder'), (err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mt-4 rounded-md border border-info/40 bg-info-soft px-4 py-3">
      <b className="flex items-center gap-1.5 text-sm text-info">
        <Navigation size={15} aria-hidden /> {t('arrival.departureTitle', 'When to leave')}
      </b>
      {guidance ? (
        <>
          <p className="mt-1 flex items-center gap-1.5 text-[13px] font-semibold text-ink">
            <MapPin size={13} aria-hidden /> {guidance.office_name}
          </p>
          <p className="mt-1 text-[13px] text-ink">{guidance.message}</p>
          <div className="mt-1.5 flex flex-wrap gap-3 text-[12px] text-ink-2">
            <span>
              {t('arrival.travel', 'Travel')}: {guidance.travel?.duration_min ?? '-'} min
              {guidance.travel?.distance_km != null ? ` (~${guidance.travel.distance_km} km)` : ''}
            </span>
            <span>{t('arrival.eta', 'Turn in')}: ~{guidance.eta_min} min</span>
            <span>{t('arrival.buffer', 'Buffer')}: {guidance.safety_buffer_min} min</span>
          </div>
          {guidance.travel && !guidance.travel.available && (
            <p className="mt-1 text-[12px] text-warn">{guidance.travel.message}</p>
          )}
        </>
      ) : (
        <p className="mt-1 text-[13px] text-ink-2">{t('arrival.calculating', 'Calculating travel time…')}</p>
      )}
      <Button size="sm" variant="secondary" className="mt-2" loading={busy} onClick={scheduleReminder} icon={<BellRing size={15} />}>
        {t('arrival.setReminder', 'Email me when to leave')}
      </Button>
    </div>
  )
}

/** Server-driven no-show grace countdown for the citizen's token. */
export function GraceStatusBanner({ grace }: { grace?: GraceInfo | null }) {
  const { t } = useI18n()
  const remaining = useCountdown(grace?.state === 'ACTIVE' ? grace.deadline : null)
  if (!grace || grace.state !== 'ACTIVE') return null
  return (
    <div className="mt-3 rounded-md border border-warn/50 bg-warn-soft px-4 py-3" role="status" aria-live="polite">
      <b className="flex items-center gap-1.5 text-sm text-warn">
        <Timer size={15} aria-hidden /> {t('arrival.graceTitle', 'Check in soon')}
      </b>
      <p className="mt-1 text-[13px] text-ink">
        {t('arrival.graceBody', 'Your turn is next. Please check in before the timer runs out or the token will be cancelled.')}
      </p>
      <p className="mt-1 text-lg font-bold text-warn tabular-nums">{formatClock(remaining)}</p>
    </div>
  )
}

/** Compact grace status used on the staff dashboard. */
export function StaffGraceCountdown({ deadline, label }: { deadline: string | null | undefined; label?: string | null }) {
  const { t } = useI18n()
  const remaining = useCountdown(deadline)
  if (!deadline) return null
  const tone = remaining !== null && remaining <= 60 ? 'text-alert' : 'text-warn'
  return (
    <span className={`inline-flex items-center gap-1.5 text-[12px] font-semibold ${tone}`}>
      <Timer size={13} aria-hidden />
      {label ? `${label} · ` : ''}
      {formatClock(remaining)} {t('staff.graceLeft', 'left')}
    </span>
  )
}


