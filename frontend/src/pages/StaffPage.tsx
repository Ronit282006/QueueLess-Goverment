import { useCallback, useEffect, useState } from 'react'
import { CheckCircle2, Coffee, PauseCircle, PhoneCall, Play, RotateCw, SkipForward, Users } from 'lucide-react'
import { Badge, Card, Empty, ErrorBox, Spinner, Stat } from '../components/Bits'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useOffice } from '../lib/office'
import { statusClass } from '../lib/hooks'
import type { QueueSnapshot, StaffCounter } from '../lib/types'

export default function StaffPage() {
  const { user } = useAuth()
  const { office, services } = useOffice()
  const [counters, setCounters] = useState<StaffCounter[]>([])
  const [queue, setQueue] = useState<QueueSnapshot | null>(null)
  const [serviceId, setServiceId] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState<number | null>(null)

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

  const run = async (counterId: number, action: () => Promise<unknown>) => {
    setBusyId(counterId)
    setError('')
    try {
      await action()
      await load()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusyId(null)
    }
  }

  if (loading && !counters.length) return <Spinner label="Loading staff console…" />

  if (!user || (user.role !== 'STAFF' && user.role !== 'ADMIN')) {
    return (
      <Card title="Staff access required">
        <p className="ql-muted">
          This console is available to staff and admin accounts only. Sign in with <code>staff@queueless.demo</code> /{' '}
          <code>Demo@1234</code>.
        </p>
      </Card>
    )
  }

  return (
    <>
      <div className="ql-welcome">
        <div>
          <span className="ql-kicker">OPERATIONS · {office?.name}</span>
          <h1>Staff queue console</h1>
          <p>Call the next citizen fairly, start service and keep the queue moving.</p>
        </div>
        <button className="ql-secondary" onClick={() => void load()}>
          <RotateCw size={16} /> Refresh
        </button>
      </div>

      {error && <ErrorBox message={error} onDismiss={() => setError('')} />}

      <div className="ql-stats">
        <Stat label="Waiting" value={queue?.waiting ?? '—'} hint="In selected service" />
        <Stat label="Open counters" value={counters.filter((c) => c.status !== 'OFFLINE').length} hint={`${counters.length} total`} />
        <Stat label="Avg service" value={queue?.average_service_min ?? '—'} unit="min" />
        <Stat label="People ahead" value={queue?.prediction.people_ahead ?? '—'} hint="For a new arrival" />
      </div>

      <Card
        kicker="SERVICE FOCUS"
        title="Queue being served"
        action={
          <select className="ql-mini-select" value={serviceId ?? ''} onChange={(e) => setServiceId(Number(e.target.value))}>
            {officeServices.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        }
      >
        {!queue ? (
          <Spinner />
        ) : (
          <>
            <div className="ql-stats ql-stats-inline">
              <Stat label="Waiting" value={queue.waiting} />
              <Stat label="Serving" value={queue.serving} />
              <Stat label="Open counters" value={queue.active_counters} />
              <Stat label="ETA next" value={queue.prediction.minutes_low} unit="min" />
            </div>
            {queue.tokens.length === 0 ? (
              <Empty icon={<Users size={22} />} title="Queue is empty" hint="No citizens are waiting for this service." />
            ) : (
              <div className="ql-token-list">
                {queue.tokens.map((row) => (
                  <div key={row.id} className="ql-queue-row ql-queue-row-wide">
                    <span className="ql-number">{row.label}</span>
                    <span className={statusClass(row.status)}>{row.status}</span>
                    <span className="ql-state">{row.stage.replace(/_/g, ' ')}</span>
                    <span className="ql-eta">{row.eta_min} min</span>
                    <span className="ql-state">pos {row.position || '—'}</span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </Card>

      <Card kicker="COUNTERS" title="Counter operations">
        {counters.length === 0 ? (
          <Empty title="No counters configured" />
        ) : (
          <div className="ql-counter-grid">
            {counters.map((counter) => {
              const disabled = busyId === counter.id || !serviceId
              const serving = counter.current_status === 'SERVING'
              const called = counter.current_status === 'CALLED'
              const assigned = counter.service_ids.length === 0 || counter.service_ids.includes(serviceId ?? -1)
              const available = counter.status === 'AVAILABLE'
              return (
                <div key={counter.id} className="ql-counter">
                  <div className="ql-counter-head">
                    <div>
                      <b>{counter.name}</b>
                      <small>#{counter.number}</small>
                    </div>
                    <Badge tone={counter.status === 'BUSY' ? 'warn' : counter.status === 'AVAILABLE' ? 'ok' : 'alert'}>
                      {counter.status}
                    </Badge>
                  </div>
                  <div className="ql-counter-token">
                    {counter.current_token ? (
                      <>
                        <span>Now serving</span>
                        <b>{counter.current_token}</b>
                      </>
                    ) : (
                      <span className="ql-muted">Idle</span>
                    )}
                  </div>
                  <div className="ql-counter-actions">
                    <button
                      className="ql-primary ql-small"
                      disabled={disabled || !assigned || !available || called || serving || !queue?.waiting}
                      title={!assigned ? 'This counter is not assigned to the selected service.' : !available ? 'This counter is not available.' : !queue?.waiting ? 'No citizens are waiting for this service.' : undefined}
                      onClick={() => serviceId && run(counter.id, () => api.callNext(counter.id, serviceId))}
                    >
                      <PhoneCall size={15} /> Call next
                    </button>
                    <button
                      className="ql-secondary ql-small"
                      disabled={disabled || !called}
                      onClick={() => run(counter.id, () => api.start(counter.id))}
                    >
                      <Play size={15} /> Start
                    </button>
                    <button
                      className="ql-primary ql-small"
                      disabled={disabled || !serving}
                      onClick={() => run(counter.id, () => api.complete(counter.id))}
                    >
                      <CheckCircle2 size={15} /> Complete
                    </button>
                    <button
                      className="ql-secondary ql-small"
                      disabled={disabled || (!called && !serving)}
                      onClick={() => run(counter.id, () => api.skip(counter.id))}
                    >
                      <SkipForward size={15} /> Skip
                    </button>
                  </div>
                  {!assigned && (
                    <div className="ql-counter-assignment">
                      <small className="ql-muted">
                        Not assigned to {officeServices.find((s) => s.id === serviceId)?.name ?? 'this service'}
                      </small>
                      <button
                        className="ql-secondary ql-small"
                        disabled={busyId === counter.id}
                        onClick={() => serviceId && run(counter.id, () => api.assignCounterServices(counter.id, [...counter.service_ids, serviceId]))}
                      >
                        Assign this service
                      </button>
                    </div>
                  )}
                  <div className="ql-counter-status">
                    <button
                      disabled={busyId === counter.id}
                      onClick={() => run(counter.id, () => api.setCounterStatus(counter.id, 'AVAILABLE'))}
                    >
                      <PhoneCall size={14} /> Available
                    </button>
                    <button
                      disabled={disabled}
                      onClick={() => run(counter.id, () => api.setCounterStatus(counter.id, 'BREAK'))}
                    >
                      <Coffee size={14} /> Break
                    </button>
                    <button
                      disabled={disabled}
                      onClick={() => run(counter.id, () => api.setCounterStatus(counter.id, 'OFFLINE'))}
                    >
                      <PauseCircle size={14} /> Offline
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </Card>
    </>
  )
}
