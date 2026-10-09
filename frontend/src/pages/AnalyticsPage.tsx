import { useCallback, useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { BarChart3, RotateCw } from 'lucide-react'
import { Card, Empty, ErrorBox, Spinner, Stat } from '../components/Bits'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useOffice } from '../lib/office'

type Json = Record<string, number | string | null>

export default function AnalyticsPage() {
  const { user } = useAuth()
  const { office } = useOffice()
  const [overview, setOverview] = useState<Json | null>(null)
  const [hours, setHours] = useState<{ hour: number; avg_queue: number; avg_wait_min: number }[]>([])
  const [demand, setDemand] = useState<{ day: string; tokens: number }[]>([])
  const [efficiency, setEfficiency] = useState<Record<string, unknown>[]>([])
  const [sla, setSla] = useState<Json | null>(null)
  const [feedback, setFeedback] = useState<Record<string, unknown> | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const officeId = office?.id

  const load = useCallback(async () => {
    if (!officeId) return
    setLoading(true)
    try {
      const [o, h, d, e, s, f] = await Promise.all([
        api.analytics.overview(officeId),
        api.analytics.peakHours(officeId),
        api.analytics.demand(officeId),
        api.analytics.efficiency(officeId),
        api.analytics.sla(officeId),
        api.analytics.feedback(officeId),
      ])
      setOverview(o)
      setHours(h.hours)
      setDemand(d.series)
      setEfficiency(e.services)
      setSla(s)
      setFeedback(f)
      setError('')
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [officeId])

  useEffect(() => {
    void load()
  }, [load])

  if (!user || (user.role !== 'STAFF' && user.role !== 'ADMIN')) {
    return (
      <Card title="Staff access required">
        <p className="ql-muted">Analytics is available to staff and admin accounts.</p>
      </Card>
    )
  }

  if (loading && !overview) return <Spinner label="Crunching analytics…" />

  const distribution = (feedback?.distribution as Record<string, number>) ?? {}
  const maxRating = Math.max(1, ...Object.values(distribution).map(Number))

  return (
    <>
      <div className="ql-welcome">
        <div>
          <span className="ql-kicker">INSIGHTS · {office?.name}</span>
          <h1>Analytics</h1>
          <p>Demand patterns, service efficiency, SLA compliance and citizen satisfaction — all from real records.</p>
        </div>
        <button className="ql-secondary" onClick={() => void load()}>
          <RotateCw size={16} /> Refresh
        </button>
      </div>

      {error && <ErrorBox message={error} onDismiss={() => setError('')} />}

      <div className="ql-stats">
        <Stat label="Tokens today" value={Number(overview?.tokens_today ?? 0)} />
        <Stat label="Completed today" value={Number(overview?.completed_today ?? 0)} />
        <Stat label="Waiting now" value={Number(overview?.waiting_now ?? 0)} />
        <Stat label="Avg wait (7d)" value={overview?.avg_wait_min_7d ?? '—'} unit="min" />
        <Stat label="SLA target" value={Number(overview?.sla_target_wait_min ?? 0)} unit="min" />
        <Stat label="Satisfaction" value={overview?.satisfaction_avg ?? '—'} unit="/ 5" />
      </div>

      <div className="ql-columns">
        <Card kicker="DEMAND" title="Tokens issued per day">
          {demand.length === 0 ? (
            <Empty icon={<BarChart3 size={22} />} title="No demand data yet" />
          ) : (
            <div className="ql-chart">
              <ResponsiveContainer width="100%" height={240}>
                <LineChart data={demand} margin={{ top: 8, right: 12, bottom: 0, left: -18 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="day" fontSize={11} tickFormatter={(v: string) => v.slice(5)} />
                  <YAxis fontSize={11} allowDecimals={false} />
                  <Tooltip />
                  <Line type="monotone" dataKey="tokens" stroke="#1d4ed8" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>

        <Card kicker="PEAK HOURS" title="Average queue by hour">
          {hours.length === 0 ? (
            <Empty title="No hourly samples" hint="Snapshots build up as the office operates." />
          ) : (
            <div className="ql-chart">
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={hours} margin={{ top: 8, right: 12, bottom: 0, left: -18 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="hour" fontSize={11} tickFormatter={(v: number) => `${v}:00`} />
                  <YAxis fontSize={11} />
                  <Tooltip />
                  <Bar dataKey="avg_queue" fill="#1d4ed8" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>
      </div>

      <div className="ql-columns">
        <Card kicker="SERVICE LEVEL" title="SLA compliance">
          <div className="ql-stats ql-stats-inline">
            <Stat label="Served" value={Number(sla?.served ?? 0)} />
            <Stat label="Within target" value={Number(sla?.within_target ?? 0)} />
            <Stat label="Compliance" value={sla?.compliance_pct ?? '—'} unit="%" />
            <Stat label="Avg wait" value={sla?.avg_wait_min ?? '—'} unit="min" />
          </div>
          <div className="ql-meter">
            <div style={{ width: `${Math.min(100, Number(sla?.compliance_pct ?? 0))}%` }} />
          </div>
        </Card>

        <Card kicker="SATISFACTION" title="Citizen feedback">
          {feedback?.total ? (
            <>
              <div className="ql-stats ql-stats-inline">
                <Stat label="Responses" value={Number(feedback.total)} />
                <Stat label="Average" value={feedback.average_rating != null ? String(feedback.average_rating) : '—'} unit="/ 5" />
                <Stat label="ETA accuracy" value={feedback.eta_accuracy_pct != null ? String(feedback.eta_accuracy_pct) : '—'} unit="%" />
              </div>
              <div className="ql-bars">
                {[5, 4, 3, 2, 1].map((star) => (
                  <div key={star} className="ql-bar-row">
                    <span>{star}★</span>
                    <div className="ql-meter">
                      <div style={{ width: `${(Number(distribution[String(star)] ?? 0) / maxRating) * 100}%` }} />
                    </div>
                    <b>{Number(distribution[String(star)] ?? 0)}</b>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <Empty title="No feedback yet" />
          )}
        </Card>
      </div>

      <Card kicker="EFFICIENCY" title="Per-service performance">
        {efficiency.length === 0 ? (
          <Empty title="No service records yet" />
        ) : (
          <div className="ql-table-wrap">
            <table className="ql-table">
              <thead>
                <tr>
                  <th>Service</th>
                  <th>Avg service</th>
                  <th>Avg wait</th>
                  <th>Completed</th>
                  <th>Records</th>
                </tr>
              </thead>
              <tbody>
                {efficiency.map((row) => (
                  <tr key={String(row.service_id)}>
                    <td>{String(row.service_name)}</td>
                    <td>{row.avg_service_min != null ? `${row.avg_service_min} min` : '—'}</td>
                    <td>{row.avg_wait_min != null ? `${row.avg_wait_min} min` : '—'}</td>
                    <td>{String(row.completed ?? 0)}</td>
                    <td>{String(row.samples ?? 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  )
}