import { useCallback, useEffect, useState } from 'react'
import { CheckCircle2, PhoneCall, Play, RefreshCw, SkipForward, Users } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import { useOffice } from '../lib/office'
import { statusTone, Badge, Button, Card, NStat, EmptyState, ErrorState, SegmentedControl, DataTable, Page, useToast } from '../components/ui'
import type { QueueSnapshot, StaffCounter } from '../lib/types'

const availabilityLabels = (t: (k: string, f?: string) => string) => [
  { value: 'AVAILABLE', label: t('staff.open', 'Open') },
  { value: 'BREAK', label: t('staff.onBreak', 'On break') },
  { value: 'OFFLINE', label: t('staff.offline', 'Offline') },
]

export default function StaffPage() {
  const { user } = useAuth()
  const { office, services } = useOffice()
  const { t } = useI18n()
  const toast = useToast()
  const [counters, setCounters] = useState<StaffCounter[]>([])
  const [queue, setQueue] = useState<QueueSnapshot | null>(null)
  const [serviceId, setServiceId] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [lastUpdated, setLastUpdated] = useState(0)
  const [, setSeconds] = useState(0)

  const officeId = office?.id
  const officeServices = services.filter((s) => s.officeId === officeId)

  const load = useCallback(async () => {
    if (!officeId) return
    setLoading(true)
    try {
      const [rows, snapshot] = await Promise.all([
        api.counters(officeId),
        serviceId ? api.staffQueue(officeId, serviceId) : Promise.resolve(null),
      ])
      setCounters(rows)
      if (snapshot) setQueue(snapshot)
      setError('')
      setLastUpdated(Date.now())
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [officeId, serviceId])

  useEffect(() => {
    void load()
    const id = setInterval(() => void load(), 12000)
    return () => clearInterval(id)
  }, [load])

  useEffect(() => {
    if (serviceId === null && officeServices.length) setServiceId(officeServices[0].id)
  }, [officeServices, serviceId])

  useEffect(() => {
    const id = setInterval(() => setSeconds((v) => v + 1), 1000)
    return () => clearInterval(id)
  }, [])

  const secondsAgo = Math.max(0, Math.round((Date.now() - lastUpdated) / 1000))

  const run = async (counterId: number, action: () => Promise<unknown>, success?: { tone: 'success' | 'info'; title: string; body?: string }) => {
    setBusyId(counterId)
    setError('')
    try {
      await action()
      await load()
      if (success) {
        if (success.tone === 'success') toast.success(success.title, success.body)
        else toast.info(success.title, success.body)
      }
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusyId(null)
    }
  }

  if (loading && !counters.length) {
    return (
      <div className="space-y-4" aria-hidden>
        <div className="h-6 w-1/3 skeleton" />
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-24 rounded-md skeleton" />
          ))}
        </div>
        <div className="h-72 rounded-md skeleton" />
      </div>
    )
  }

  if (!user || (user.role !== 'STAFF' && user.role !== 'ADMIN')) {
    return (
      <Card title="Staff access required">
        <p className="text-sm text-ink-2">
          This console is available to staff and admin accounts only. Sign in with{' '}
          <code className="rounded bg-surface2 px-1.5 py-0.5">staff@queueless.demo</code> /{' '}
          <code className="rounded bg-surface2 px-1.5 py-0.5">Demo@1234</code>.
        </p>
      </Card>
    )
  }

  const labels = availabilityLabels(t)
  const statusLabel = (status: string) =>
    labels.find((l) => l.value === status)?.label ?? status

  return (
    <Page
      kicker={`OPERATIONS · ${office?.name ?? ''}`}
      title={t('staff.title', 'Staff console')}
      actions={
        <div className="flex items-center gap-2">
          <span className="text-[12px] text-ink-3 tabular-nums" aria-live="polite">
            {secondsAgo <= 1 ? t('staff.updatedJustNow', 'Updated just now') : t('staff.updated', 'Updated {sec}s ago').replace('{sec}', String(secondsAgo))}
          </span>
          <Button variant="secondary" size="sm" onClick={() => void load()} icon={<RefreshCw size={15} />}>
            Refresh
          </Button>
        </div>
      }
    >
      {error && (
        <div className="mb-4">
          <ErrorState message={error} onRetry={() => void load()} />
        </div>
      )}

      <section aria-label={t('staff.overview', 'Live overview')} className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
        <NStat label={t('citizen.peopleWaiting', 'People waiting')} valueNumber={queue?.waiting ?? 0} hint={officeServices.find((s) => s.id === serviceId)?.name} />
        <NStat label={t('staff.open', 'Open')} valueNumber={counters.filter((c) => c.status !== 'OFFLINE').length} hint={`${counters.length} total`} />
        <NStat label={t('citizen.avgService', 'Avg service')} valueNumber={Math.round(queue?.average_service_min ?? 0)} unit="min" />
        <NStat label={t('citizen.peopleBefore', 'people ahead')} valueNumber={queue?.prediction.people_ahead ?? 0} hint={t('citizen.eta', 'Estimated wait')} />
      </section>

      {/* Queue panel */}
      <Card
        kicker="SERVICE FOCUS"
        title={t('staff.queuePanel', 'Waiting here')}
        action={
          <label className="relative block">
            <span className="sr-only">{t('staff.filterService', 'Filter by service')}</span>
            <select
              className="appearance-none rounded-md border border-line bg-surface px-3 py-2 pr-8 text-sm font-semibold text-ink min-h-[40px] focus:outline-none focus:ring-2 focus:border-brand focus:ring-brand/25"
              value={serviceId ?? ''}
              onChange={(e) => setServiceId(Number(e.target.value))}
            >
              {officeServices.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
        }
      >
        {!queue ? (
          <div className="space-y-2">
            <div className="h-5 skeleton" />
            <div className="h-5 skeleton" />
            <div className="h-5 skeleton" />
          </div>
        ) : (
          <DataTable
            rowKey={(row) => String(row.id)}
            columns={[
              { header: t('getToken', 'Get a virtual token'), render: (r) => <b className="text-brand">{r.label}</b> },
              { header: 'Status', render: (r) => <Badge tone={statusTone(r.status)}>{t(`status.${r.status}`, r.status)}</Badge> },
              { header: 'Stage', render: (r) => <span className="capitalize text-ink-2">{r.stage.replace(/_/g, ' ')}</span> },
              { header: t('estimatedWait', 'Estimated wait'), align: 'right', render: (r) => <span className="tabular-nums text-ink">{r.eta_min} min</span> },
              { header: '#', align: 'right', render: (r) => <span className="tabular-nums text-ink-3">pos {r.position || '—'}</span> },
            ]}
            rows={queue.tokens}
            empty={
              <EmptyState
                icon={<Users size={22} />}
                title={t('staff.noTokens', 'No one is waiting right now.')}
                hint={officeServices.find((s) => s.id === serviceId)?.name ?? ''}
              />
            }
          />
        )}
      </Card>

      {/* Counter grid */}
      <Card kicker={t('staff.counterGrid', 'Your counters')} title={t('staff.counterGridHint', 'Call the next citizen fairly, start service and keep the queue moving.')} bodyClassName="pt-3">
        {counters.length === 0 ? (
          <EmptyState
            icon={<Users size={22} />}
            title={t('staff.noCounters', 'No counters assigned yet')}
            hint={t('staff.noCountersHint', 'Ask an administrator to assign counters before you start taking citizens.')}
          />
        ) : (
          <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-3">
            {counters.map((counter) => {
              const busy = busyId === counter.id
              const serving = counter.current_status === 'SERVING'
              const called = counter.current_status === 'CALLED'
              const assigned = counter.service_ids.length === 0 || counter.service_ids.includes(serviceId ?? -1)
              const available = counter.status === 'AVAILABLE'
              const link = counter.current_token
              const serviceName = officeServices.find((s) => s.id === serviceId)?.name
              return (
                <article key={counter.id} className="rounded-md border border-line bg-surface p-4 shadow-card flex flex-col gap-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <b className="block text-[15px] text-ink">{counter.name}</b>
                      <span className="text-[12px] text-ink-3">#{counter.number}</span>
                    </div>
                    <Badge tone={counter.status === 'AVAILABLE' ? 'ok' : counter.status === 'BREAK' ? 'warn' : 'neutral'}>
                      {statusLabel(counter.status)}
                    </Badge>
                  </div>

                  <div className={`rounded-md px-3 py-2.5 ${link ? 'bg-info-soft text-info' : 'bg-surface2 text-ink-3'}`}>
                    {link ? (
                      <>
                        <span className="block text-[10px] font-bold uppercase tracking-[0.12em]">
                          {serving ? t('staff.servingToken', 'Serving') : t('status.CALLED', 'Called')}
                        </span>
                        <b className="block text-lg text-ink tabular-nums">{link}</b>
                      </>
                    ) : (
                      <span className="block text-sm font-medium">{t('staff.emptyToken', 'No active token')}</span>
                    )}
                  </div>

                  {!assigned && serviceId && (
                    <div className="rounded-md border border-warn/40 bg-warn-soft px-3 py-2">
                      <p className="text-[12px] text-warn">Not assigned to {serviceName}</p>
                      <Button
                        variant="secondary"
                        size="sm"
                        loading={busy}
                        className="mt-1.5"
                        onClick={() => serviceId && run(counter.id, () => api.assignCounterServices(counter.id, [...counter.service_ids, serviceId]))}
                      >
                        Assign this service
                      </Button>
                    </div>
                  )}

                  {/* State-based primary action */}
                  <div className="flex flex-wrap gap-2">
                    {!serving && !called && (
                      <Button
                        size="sm"
                        loading={busy}
                        disabled={!assigned || !available || !queue?.waiting}
                        icon={<PhoneCall size={15} />}
                        onClick={() => serviceId && run(counter.id, () => api.callNext(counter.id, serviceId), { tone: 'info', title: t('staff.tokenCalled', 'Token called') })}
                      >
                        {t('staff.callNext', 'Call next')}
                      </Button>
                    )}
                    {called && (
                      <Button size="sm" loading={busy} icon={<Play size={15} />} onClick={() => run(counter.id, () => api.start(counter.id), { tone: 'info', title: t('status.SERVING', 'Serving') })}>
                        {t('staff.startService', 'Start service')}
                      </Button>
                    )}
                    {serving && (
                      <Button size="sm" loading={busy} icon={<CheckCircle2 size={15} />} onClick={() => run(counter.id, () => api.complete(counter.id), { tone: 'success', title: t('staff.serviceCompleted', 'Service completed') })}>
                        {t('staff.complete', 'Complete')}
                      </Button>
                    )}
                    {(called || serving) && (
                      <Button size="sm" variant="secondary" loading={busy} icon={<SkipForward size={15} />} onClick={() => run(counter.id, () => api.skip(counter.id), { tone: 'info', title: t('staff.skipped', 'Token skipped') })}>
                        {t('staff.skip', 'Skip')}
                      </Button>
                    )}
                  </div>

                  {/* Availability */}
                  <SegmentedControl
                    label={`${counter.name} availability`}
                    value={counter.status}
                    onChange={(status) => {
                      if (status !== counter.status) {
                        void run(counter.id, () => api.setCounterStatus(counter.id, status), { tone: 'success', title: t('staff.statusChanged', 'Status updated'), body: statusLabel(status) })
                      }
                    }}
                    options={labels}
                  />
                </article>
              )
            })}
          </div>
        )}
      </Card>
    </Page>
  )
}