import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Activity, BarChart3, Clock, Gauge, RefreshCw, Smile, Star } from 'lucide-react'
import { Card, DataTable, EmptyState, Meter, NStat, Page, Skeleton, Button, useToast } from '../components/ui'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import { useOffice } from '../lib/office'
import { useTheme } from '../lib/theme'

type Json = Record<string, number | string | null>

function useChartPalette() {
  const { resolved, highContrast } = useTheme()
  return useMemo(() => {
    if (highContrast) {
      return resolved === 'dark'
        ? { line: '#9db9fd', bar: '#9db9fd', grid: '#ffffff', axis: '#ffffff' }
        : { line: '#0000cc', bar: '#0000cc', grid: '#000000', axis: '#000000' }
    }
    return resolved === 'dark'
      ? { line: '#6a93f4', bar: '#6a93f4', grid: '#273349', axis: '#b6c1d8' }
      : { line: '#1d4ed8', bar: '#1d4ed8', grid: '#e4e7ec', axis: '#475467' }
  }, [resolved, highContrast])
}

function ChartTip({ active, payload, label }: { active?: boolean; payload?: { name: string; value: number }[]; label?: string | number }) {
  if (!active || !payload?.length) return null
  return (
    <div className="ql-chart-tip">
      <b className="text-ink">{label}</b>
      {payload.map((p) => (
        <span key={p.name} className="text-ink-2">
          {p.value}
        </span>
      ))}
    </div>
  )
}

export default function AnalyticsPage() {
  const { user } = useAuth()
  const { office } = useOffice()
  const { t } = useI18n()
  const toast = useToast()
  const chart = useChartPalette()

  const [overview, setOverview] = useState<Json | null>(null)
  const [hours, setHours] = useState<{ hour: number; avg_queue: number; avg_wait_min: number }[]>([])
  const [demand, setDemand] = useState<{ day: string; tokens: number }[]>([])
  const [efficiency, setEfficiency] = useState<Record<string, unknown>[]>([])
  const [sla, setSla] = useState<Json | null>(null)
  const [feedback, setFeedback] = useState<Record<string, unknown> | null>(null)
  const [loading, setLoading] = useState(true)

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
    } catch (err) {
      toast.error(t('an.loadFailed', 'Could not load analytics'), (err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [officeId, t, toast])

  useEffect(() => {
    void load()
  }, [load])

  if (!user || (user.role !== 'STAFF' && user.role !== 'ADMIN')) {
    return (
      <Page title={t('an.title', 'Analytics')}>
        <p className="text-sm text-ink-2">{t('an.notAllowed', 'Analytics is available to staff and admin accounts.')}</p>
      </Page>
    )
  }

  const distribution = (feedback?.distribution as Record<string, number>) ?? {}
  const maxRating = Math.max(1, ...Object.values(distribution).map(Number))
  const compliance = Math.min(100, Number(sla?.compliance_pct ?? 0))

  if (loading && !overview) {
    return (
      <Page kicker={t('an.kicker', 'Service delivery dashboard')} title={t('an.title', 'Analytics')}>
        <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-28 rounded-md skeleton" />
          ))}
        </div>
        <div className="mt-4 grid lg:grid-cols-2 gap-4">
          <div className="h-72 rounded-md skeleton" />
          <div className="h-72 rounded-md skeleton" />
        </div>
      </Page>
    )
  }

  return (
    <Page
      kicker={`${t('an.kicker', 'Service delivery dashboard')} · ${office?.name ?? ''}`}
      title={t('an.title', 'Analytics')}
      actions={
        <Button variant="secondary" size="sm" onClick={() => void load()} loading={loading} icon={<RefreshCw size={15} />}>
          {t('common.refresh', 'Refresh')}
        </Button>
      }
    >
      <p className="text-sm text-ink-2 mt-0 mb-5 max-w-3xl">
        {t('an.subtitle', 'Demand patterns, service efficiency, SLA compliance and citizen satisfaction — all from real records.')}
      </p>

      <section aria-label={t('an.overviewStats', 'Key numbers')} className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3 mb-6">
        <NStat label={t('an.tokensToday', 'Tokens today')} valueNumber={Number(overview?.tokens_today ?? 0)} hint={t('an.tokensTodayHint', 'Issued since midnight')} />
        <NStat label={t('an.completedToday', 'Completed today')} valueNumber={Number(overview?.completed_today ?? 0)} />
        <NStat label={t('an.waitingNow', 'Waiting now')} valueNumber={Number(overview?.waiting_now ?? 0)} />
        <NStat label={t('an.avgWait', 'Avg wait (7d)')} valueNumber={Number(overview?.avg_wait_min_7d ?? 0)} unit="min" />
        <NStat label={t('an.slaTarget', 'SLA target')} valueNumber={Number(overview?.sla_target_wait_min ?? 0)} unit="min" />
        <NStat label={t('an.satisfaction', 'Satisfaction')} valueNumber={Number(overview?.satisfaction_avg ?? 0)} unit="/ 5" />
      </section>

      <div className="grid lg:grid-cols-2 gap-4 mb-4">
        <Card kicker={t('an.demand', 'Demand over time')} title={t('an.demandTitle', 'Tokens issued per day')}>
          {demand.length === 0 ? (
            <EmptyState icon={<BarChart3 size={22} />} title={t('an.empty', 'Not enough data yet. Check back after the office opens.')} />
          ) : (
            <div style={{ width: '100%', height: 260 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={demand} margin={{ top: 8, right: 12, bottom: 0, left: -18 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={chart.grid} />
                  <XAxis dataKey="day" fontSize={11} stroke={chart.axis} tickFormatter={(v: string) => v.slice(5)} />
                  <YAxis fontSize={11} stroke={chart.axis} allowDecimals={false} />
                  <Tooltip content={<ChartTip />} cursor={{ stroke: chart.grid }} />
                  <Line type="monotone" dataKey="tokens" stroke={chart.line} strokeWidth={2} dot={false} name={t('an.tokens', 'Tokens')} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>

        <Card kicker={t('an.peakHours', 'Peak hours')} title={t('an.peakTitle', 'Average queue by hour')}>
          {hours.length === 0 ? (
            <EmptyState icon={<Clock size={22} />} title={t('an.peakEmpty', 'No hourly samples yet')} hint={t('an.peakEmptyHint', 'Snapshots build up as the office operates.')} />
          ) : (
            <div style={{ width: '100%', height: 260 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={hours} margin={{ top: 8, right: 12, bottom: 0, left: -18 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={chart.grid} />
                  <XAxis dataKey="hour" fontSize={11} stroke={chart.axis} tickFormatter={(v: number) => `${v}:00`} />
                  <YAxis fontSize={11} stroke={chart.axis} />
                  <Tooltip content={<ChartTip />} cursor={{ fill: chart.grid, opacity: 0.3 }} />
                  <Bar dataKey="avg_queue" fill={chart.bar} radius={[4, 4, 0, 0]} name={t('an.avgQueue', 'Avg queue')} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>
      </div>

      <div className="grid lg:grid-cols-2 gap-4 mb-4">
        <Card kicker={t('an.sla', 'SLA performance')} title={t('an.slaTitle', 'Compliance with the wait target')}>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
            <NStat label={t('an.served', 'Served today')} valueNumber={Number(sla?.served ?? 0)} />
            <NStat label={t('an.withinTarget', 'Within target')} valueNumber={Number(sla?.within_target ?? 0)} />
            <NStat label={t('an.compliance', 'Compliance')} valueNumber={Math.round(compliance)} unit="%" />
            <NStat label={t('an.avgWait', 'Avg wait')} valueNumber={Number(sla?.avg_wait_min ?? 0)} unit="min" />
          </div>
          <div className="flex items-center gap-3">
            <Gauge size={18} className="text-brand shrink-0" aria-hidden />
            <Meter
              pct={compliance}
              tone={compliance >= 80 ? 'ok' : compliance >= 50 ? 'warn' : 'alert'}
              label={t('an.slaMeter', 'SLA compliance')}
            />
          </div>
          <p className="text-[12px] text-ink-3 mt-3 mb-0">
            {t('an.slaHint', 'Target: most citizens are served within the office wait target. {missed} missed the target.').replace('{missed}', String(sla?.over_target ?? 0))}
          </p>
        </Card>

        <Card kicker={t('an.satisfaction', 'Satisfaction')} title={t('an.feedbackTitle', 'Citizen feedback')}>
          {feedback?.total ? (
            <div className="flex flex-col gap-4">
              <div className="grid grid-cols-3 gap-3">
                <NStat label={t('an.responses', 'Responses')} valueNumber={Number(feedback.total)} />
                <NStat label={t('an.average', 'Average')} valueNumber={Number(feedback.average_rating ?? 0)} unit="/ 5" />
                <NStat label={t('an.etaAccuracy', 'ETA accuracy')} valueNumber={Number(feedback.eta_accuracy_pct ?? 0)} unit="%" />
              </div>
              <ul className="m-0 p-0 list-none flex flex-col gap-2" aria-label={t('an.starBreakdown', 'Ratings breakdown')}>
                {[5, 4, 3, 2, 1].map((star) => {
                  const count = Number(distribution[String(star)] ?? 0)
                  const pct = (count / maxRating) * 100
                  return (
                    <li key={star} className="flex items-center gap-3">
                      <span className="inline-flex items-center gap-1 w-10 text-sm font-semibold text-ink-2 tabular-nums">
                        {star}
                        <Star size={13} className="text-star" aria-hidden fill="currentColor" />
                      </span>
                      <div className="h-2.5 flex-1 rounded-full bg-surface2 border border-line overflow-hidden">
                        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: 'var(--c-star)' }} />
                      </div>
                      <b className="w-8 text-right text-sm text-ink tabular-nums">{count}</b>
                    </li>
                  )
                })}
              </ul>
            </div>
          ) : (
            <EmptyState icon={<Smile size={22} />} title={t('an.noFeedback', 'No feedback yet')} hint={t('an.noFeedbackHint', 'Citizens are asked to rate their visit after service.')} />
          )}
        </Card>
      </div>

      <Card kicker={t('an.services', 'Service efficiency')} title={t('an.efficiencyTitle', 'Per-service performance')}>
        {efficiency.length === 0 ? (
          <EmptyState icon={<Activity size={22} />} title={t('an.noServices', 'No service records yet')} hint={t('an.noServicesHint', 'Data appears once services are used.')} />
        ) : (
          <DataTable
            rowKey={(row) => String(row.service_id)}
            rows={efficiency}
            columns={[
              { header: t('an.colService', 'Service'), render: (row) => <b className="text-ink">{String(row.service_name)}</b> },
              { header: t('an.colAvgService', 'Avg service'), align: 'right', render: (row) => (row.avg_service_min != null ? `${row.avg_service_min} min` : '—') },
              { header: t('an.colAvgWait', 'Avg wait'), align: 'right', render: (row) => (row.avg_wait_min != null ? `${row.avg_wait_min} min` : '—') },
              { header: t('an.colCompleted', 'Completed'), align: 'right', render: (row) => String(row.completed ?? 0) },
              { header: t('an.colRecords', 'Records'), align: 'right', render: (row) => String(row.samples ?? 0) },
            ]}
          />
        )}
      </Card>
    </Page>
  )
}
