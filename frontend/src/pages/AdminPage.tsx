import { useCallback, useEffect, useState } from 'react'
import { BadgeCheck, Brain, Check, GitPullRequest, RefreshCw, X } from 'lucide-react'
import { Badge, Card, Empty, ErrorBox, Spinner, Stat } from '../components/Bits'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useOffice } from '../lib/office'

type Json = Record<string, unknown>

// <input type="datetime-local"> reads and writes local wall-clock time. Building
// the value from toISOString() (UTC) made the default land hours in the past for
// any timezone ahead of UTC, so the API rejected it as an invalid window.
const toLocalInputValue = (date: Date) => {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export default function AdminPage() {
  const { user } = useAuth()
  const { office, services, reload: reloadOffices } = useOffice()
  const [health, setHealth] = useState<Json | null>(null)
  const [rules, setRules] = useState<Json[]>([])
  const [recommendations, setRecommendations] = useState<Json[]>([])
  const [audit, setAudit] = useState<Json[]>([])
  const [notifications, setNotifications] = useState<Json[]>([])
  const [holidays, setHolidays] = useState<Json[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const [ruleName, setRuleName] = useState('Senior citizens')
  const [ruleTags, setRuleTags] = useState('Senior Citizen')
  const [ruleBoost, setRuleBoost] = useState(25)
  const [scheduleHours, setScheduleHours] = useState('09:30-18:00')
  const [scheduleDays, setScheduleDays] = useState('mon,tue,wed,thu,fri,sat')
  const [arrivalBuffer, setArrivalBuffer] = useState(15)
  const [responseMinutes, setResponseMinutes] = useState(30)
  const [officeAddress, setOfficeAddress] = useState('')
  const [officeInstructions, setOfficeInstructions] = useState('')
  const [holidayDate, setHolidayDate] = useState('')
  const [holidayName, setHolidayName] = useState('Public holiday')
  const [incidentDescription, setIncidentDescription] = useState('Temporary counter closure')
  const [incidentType, setIncidentType] = useState('CLOSURE')
  const [incidentServiceId, setIncidentServiceId] = useState<number | ''>('')
  const [incidentEndsAt, setIncidentEndsAt] = useState(() => toLocalInputValue(new Date(Date.now() + 60 * 60_000)))
  const [incidentLocation, setIncidentLocation] = useState('')
  const [arrivedIncidentTickets, setArrivedIncidentTickets] = useState<Json[]>([])

  const officeId = office?.id

  const load = useCallback(async () => {
    if (!officeId) return
    setLoading(true)
    try {
      const [h, r, rec, a, n, days] = await Promise.all([
        api.adminHealth(),
        api.priorityRules(officeId),
        api.recommendations(officeId, false),
        api.auditLogs(30),
        api.notifications(20),
        api.officeHolidays(officeId),
      ])
      setHealth(h)
      setRules(r)
      setRecommendations(rec.items)
      setAudit(a)
      setNotifications(n)
      setHolidays(days)
      setError('')
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [officeId])

  useEffect(() => {
    if (!office) return
    setScheduleHours(office.working_hours)
    setScheduleDays(office.working_days)
    setArrivalBuffer(office.arrival_buffer_min ?? 15)
    setResponseMinutes(office.incident_response_min ?? 30)
    setOfficeAddress(office.address)
    setOfficeInstructions(office.location_instructions ?? '')
  }, [office?.id])

  useEffect(() => {
    void load()
  }, [load])

  if (!user || user.role !== 'ADMIN') {
    return (
      <Card title="Administrator access required">
        <p className="ql-muted">
          Sign in with <code>admin@queueless.demo</code> / <code>Demo@1234</code> to manage governance settings.
        </p>
      </Card>
    )
  }

  const createRule = async () => {
    setError('')
    try {
      await api.createPriorityRule({
        office_id: officeId,
        name: ruleName,
        tags: ruleTags.split(',').map((t) => t.trim()).filter(Boolean),
        boost: ruleBoost,
        is_active: true,
      })
      setNotice('Priority rule created.')
      await load()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const decide = async (id: number, status: string) => {
    try {
      await api.decideRecommendation(id, status)
      await load()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const generate = async () => {
    if (!officeId) return
    try {
      const result = await api.recommendations(officeId, true)
      setNotice(`Generated ${result.generated} recommendation(s).`)
      await load()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const retrain = async () => {
    setNotice('Training models…')
    try {
      const result = await api.retrain()
      setNotice(`Retrained ${result.trained} model(s).`)
      await load()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const saveSchedule = async () => {
    if (!officeId) return
    try {
      await api.updateOfficeSchedule(officeId, {
        working_hours: scheduleHours, working_days: scheduleDays,
        arrival_buffer_min: arrivalBuffer, incident_response_min: responseMinutes,
      })
      await reloadOffices()
      setNotice('Office hours and incident response policy saved.')
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const saveLocation = async () => {
    if (!officeId) return
    try {
      await api.updateOfficeLocation(officeId, officeAddress, officeInstructions)
      await reloadOffices()
      setNotice('Office location updated. Citizens with active tickets were notified.')
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const addHoliday = async () => {
    if (!officeId || !holidayDate) return
    try {
      await api.addOfficeHoliday(officeId, holidayDate, holidayName)
      setHolidayDate('')
      setNotice('Office holiday added.')
      await load()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const removeHoliday = async (id: number) => {
    if (!officeId) return
    try {
      await api.deleteOfficeHoliday(officeId, id)
      setNotice('Office holiday removed.')
      await load()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const createIncident = async () => {
    if (!officeId) return
    const endsAt = new Date(incidentEndsAt)
    if (Number.isNaN(endsAt.getTime())) {
      setError('Pick a valid expected resolution time.')
      return
    }
    if (endsAt.getTime() <= Date.now()) {
      setError('Expected resolution time must be later than now.')
      return
    }
    try {
      const result = await api.createIncident({
        office_id: officeId,
        service_id: incidentServiceId === '' ? null : incidentServiceId,
        incident_type: incidentType,
        description: incidentDescription,
        location_instructions: incidentLocation,
        starts_at: new Date().toISOString(),
        ends_at: endsAt.toISOString(),
      })
      setArrivedIncidentTickets((result.arrived_for_staff as Json[] | undefined) ?? [])
      setNotice(`Incident recorded. ${String(result.notified_count ?? 0)} citizen(s) were emailed; response deadline: ${new Date(String(result.response_deadline)).toLocaleString()}.`)
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const rebookArrivedTicket = async (tokenId: number) => {
    try {
      const result = await api.rebookArrivedIncidentTicket(tokenId)
      setArrivedIncidentTickets((current) => current.filter((ticket) => Number(ticket.id) !== tokenId))
      setNotice(`Arrived ticket rebooked for ${String(result.scheduled_for)}.`)
    } catch (err) {
      setError((err as Error).message)
    }
  }

  if (loading && !health) return <Spinner label="Loading administration…" />

  return (
    <>
      <div className="ql-welcome">
        <div>
          <span className="ql-kicker">GOVERNANCE · {office?.name}</span>
          <h1>Administration</h1>
          <p>Monitor system health, configure inclusive priority rules and act on AI counter recommendations.</p>
        </div>
        <div className="ql-inline">
          <button className="ql-secondary" onClick={generate}>
            <GitPullRequest size={16} /> Generate recommendations
          </button>
          <button className="ql-secondary" onClick={() => void retrain()}>
            <Brain size={16} /> Retrain AI models
          </button>
        </div>
      </div>

      {error && <ErrorBox message={error} onDismiss={() => setError('')} />}
      {notice && <div className="ql-notice"><BadgeCheck size={16} /> {notice}</div>}

      <div className="ql-stats">
        <Stat label="Database" value={String(health?.database ?? '—')} />
        <Stat label="Redis" value={String(health?.redis ?? '—')} />
        <Stat label="Active queues" value={Number(health?.active_queues ?? 0)} />
        <Stat label="Pending recommendations" value={Number(health?.pending_recommendations ?? 0)} />
      </div>

      <div className="ql-columns">
        <Card kicker="OFFICE OPERATIONS" title="Hours, holidays and location">
          <div className="ql-form">
            <label>Working hours<input value={scheduleHours} onChange={(e) => setScheduleHours(e.target.value)} placeholder="09:30-18:00" /></label>
            <label>Working days (mon,tue,...,sun)<input value={scheduleDays} onChange={(e) => setScheduleDays(e.target.value)} /></label>
            <div className="ql-form-inline">
              <label>Arrival buffer (minutes)<input type="number" min={0} max={240} value={arrivalBuffer} onChange={(e) => setArrivalBuffer(Number(e.target.value))} /></label>
              <label>Incident response deadline (minutes)<input type="number" min={5} max={1440} value={responseMinutes} onChange={(e) => setResponseMinutes(Number(e.target.value))} /></label>
            </div>
            <button className="ql-primary" onClick={() => void saveSchedule()}>Save office schedule</button>
            <label>Office address<input value={officeAddress} onChange={(e) => setOfficeAddress(e.target.value)} /></label>
            <label>Building / counter directions<input value={officeInstructions} onChange={(e) => setOfficeInstructions(e.target.value)} /></label>
            <button className="ql-secondary" onClick={() => void saveLocation()}>Update location and notify active citizens</button>
          </div>
          <div className="ql-form-inline">
            <label>Holiday date<input type="date" value={holidayDate} onChange={(e) => setHolidayDate(e.target.value)} /></label>
            <label>Holiday name<input value={holidayName} onChange={(e) => setHolidayName(e.target.value)} /></label>
            <button className="ql-secondary" onClick={() => void addHoliday()}>Add holiday</button>
          </div>
          {holidays.map((day) => (
            <div className="ql-list-row" key={String(day.id)}>
              <span>{String(day.holiday_date)} · {String(day.name)}</span>
              <button className="ql-linkish" onClick={() => void removeHoliday(Number(day.id))}>Remove</button>
            </div>
          ))}
        </Card>

        <Card kicker="SERVICE INCIDENT" title="Report closure or capacity issue">
          <p className="ql-muted">Affected citizens get an email with a response deadline and can choose transfer or cancellation. Already-arrived citizens are held for staff help.</p>
          <div className="ql-form">
            <label>Incident type
              <select value={incidentType} onChange={(e) => setIncidentType(e.target.value)}>
                <option value="CLOSURE">Temporary office/service closure</option>
                <option value="CAPACITY">Counter capacity reduction</option>
                <option value="DELAY">Significant queue delay</option>
                <option value="LOCATION">Temporary location change</option>
              </select>
            </label>
            <label>Service (optional)
              <select value={incidentServiceId} onChange={(e) => setIncidentServiceId(e.target.value ? Number(e.target.value) : '')}>
                <option value="">All services at this office</option>
                {services.filter((service) => service.officeId === officeId).map((service) => <option key={service.id} value={service.id}>{service.name}</option>)}
              </select>
            </label>
            <label>What happened<input value={incidentDescription} onChange={(e) => setIncidentDescription(e.target.value)} minLength={4} /></label>
            <label>Temporary directions (optional)<input value={incidentLocation} onChange={(e) => setIncidentLocation(e.target.value)} /></label>
            <label>Expected resolution time<input type="datetime-local" value={incidentEndsAt} min={toLocalInputValue(new Date())} onChange={(e) => setIncidentEndsAt(e.target.value)} /></label>
            <button className="ql-primary" onClick={() => void createIncident()}>Notify affected ticket holders</button>
          </div>
          {arrivedIncidentTickets.length > 0 && (
            <div className="ql-list">
              <b>Arrived citizens needing staff help</b>
              {arrivedIncidentTickets.map((ticket) => (
                <div className="ql-list-row" key={String(ticket.id)}>
                  <span>{String(ticket.label)} · checked in</span>
                  <button className="ql-secondary ql-small" onClick={() => void rebookArrivedTicket(Number(ticket.id))}>Rebook next working day</button>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <div className="ql-columns">
        <Card kicker="AI GOVERNANCE" title="Counter recommendations" action={<button className="ql-linkish" onClick={generate}>Refresh</button>}>
          {recommendations.length === 0 ? (
            <Empty title="No pending recommendations" hint="Generate to analyse current queue load." />
          ) : (
            <div className="ql-list">
              {recommendations.map((rec) => (
                <div key={String(rec.id)} className="ql-list-row">
                  <div>
                    <b>{String(rec.title)}</b>
                    <small>
                      Expected reduction ≈ {String(rec.expected_reduction_min)} min
                    </small>
                  </div>
                  <div className="ql-inline">
                    <button className="ql-primary ql-small" onClick={() => decide(Number(rec.id), 'ACCEPTED')}>
                      <Check size={14} /> Accept
                    </button>
                    <button className="ql-secondary ql-small" onClick={() => decide(Number(rec.id), 'REJECTED')}>
                      <X size={14} /> Reject
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card kicker="INCLUSION" title="Priority rules">
          <div className="ql-form ql-form-inline">
            <label>
              Name
              <input value={ruleName} onChange={(e) => setRuleName(e.target.value)} />
            </label>
            <label>
              Tags (comma separated)
              <input value={ruleTags} onChange={(e) => setRuleTags(e.target.value)} />
            </label>
            <label>
              Boost
              <input type="number" min={1} max={100} value={ruleBoost} onChange={(e) => setRuleBoost(Number(e.target.value))} />
            </label>
            <button className="ql-primary" onClick={createRule}>
              Add rule
            </button>
          </div>
          {rules.length === 0 ? (
            <Empty title="No priority rules" hint="Add tags such as “Senior Citizen” to fast-track inclusively." />
          ) : (
            <div className="ql-list">
              {rules.map((rule) => (
                <div key={String(rule.id)} className="ql-list-row">
                  <div>
                    <b>{String(rule.name)}</b>
                    <small>{(rule.tags as string[]).join(', ') || 'no tags'}</small>
                  </div>
                  <Badge tone={rule.is_active ? 'ok' : 'alert'}>boost {String(rule.boost)}</Badge>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <div className="ql-columns">
        <Card kicker="COMPLIANCE" title="Audit trail" action={<button className="ql-linkish" onClick={() => void load()}><RefreshCw size={13} /> Refresh</button>}>
          {audit.length === 0 ? (
            <Empty title="No audit events" />
          ) : (
            <div className="ql-table-wrap">
              <table className="ql-table">
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Action</th>
                    <th>Actor</th>
                    <th>Entity</th>
                  </tr>
                </thead>
                <tbody>
                  {audit.map((row, i) => (
                    <tr key={i}>
                      <td>{String(row.at ?? '').slice(0, 19).replace('T', ' ')}</td>
                      <td>{String(row.action)}</td>
                      <td>{String(row.actor_role ?? 'SYSTEM')}</td>
                      <td>{String(row.entity_type ?? '')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card kicker="COMMUNICATIONS" title="Notification log">
          {notifications.length === 0 ? (
            <Empty title="No notifications yet" />
          ) : (
            <div className="ql-list">
              {notifications.map((n, i) => (
                <div key={i} className="ql-list-row">
                  <div>
                    <b>{String(n.subject)}</b>
                    <small>{String(n.kind)} · {String(n.recipient ?? '')}</small>
                  </div>
                  <Badge tone={n.status === 'SENT' ? 'ok' : 'warn'}>{String(n.status)}</Badge>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

    </>
  )
}
