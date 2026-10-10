import type { ReactNode } from 'react'
import { Activity, Brain, Database, Layers } from 'lucide-react'
import { Badge, Card, NStat } from '../../components/ui'
import { useI18n } from '../../lib/i18n'
import type { Json } from './types'

function healthTone(value: unknown): 'ok' | 'warn' | 'alert' {
  const s = String(value ?? '').toLowerCase()
  if (!s) return 'alert'
  if (/(ok|up|healthy|connected|online|ready)/.test(s)) return 'ok'
  if (/(degraded|starting|pending|slow)/.test(s)) return 'warn'
  return 'alert'
}

function HealthTile({ icon, label, value, hint }: { icon: ReactNode; label: string; value: unknown; hint?: string }) {
  const tone = healthTone(value)
  const toneLabel = tone === 'ok' ? 'Healthy' : tone === 'warn' ? 'Needs attention' : 'Unavailable'
  return (
    <article className="bg-surface border border-line rounded-md shadow-card p-4 flex flex-col gap-2 animate-fade-slide">
      <div className="flex items-center justify-between gap-2">
        <span className="grid place-items-center w-9 h-9 rounded-lg bg-brand-soft text-brand" aria-hidden>
          {icon}
        </span>
        <Badge tone={tone}>
          <span aria-hidden className={`w-1.5 h-1.5 rounded-full ${tone === 'ok' ? 'bg-ok' : tone === 'warn' ? 'bg-warn' : 'bg-alert'}`} />
          {toneLabel}
        </Badge>
      </div>
      <span className="text-[11px] font-bold uppercase tracking-[0.08em] text-ink-3">{label}</span>
      <b className="text-lg font-bold text-ink break-words">{String(value ?? '—')}</b>
      {hint && <small className="text-[13px] text-ink-2">{hint}</small>}
    </article>
  )
}

export default function AdminOverview({ health }: { health: Json | null }) {
  const { t } = useI18n()
  return (
    <div className="flex flex-col gap-5">
      <p className="text-sm text-ink-2 m-0 max-w-2xl">
        {t('admin.healthHint', 'Live status of the services that power QueueLess. Anything not marked Healthy needs attention.')}
      </p>

      <section aria-label={t('admin.health', 'System health')} className="grid sm:grid-cols-2 xl:grid-cols-4 gap-3">
        <HealthTile
          icon={<Database size={18} />}
          label={t('admin.database', 'Database')}
          value={health?.database}
          hint={t('admin.databaseHint', 'Stores offices, tokens and records')}
        />
        <HealthTile
          icon={<Activity size={18} />}
          label="Redis"
          value={health?.redis}
          hint={t('admin.redisHint', 'Live queue cache and rate limits')}
        />
        <HealthTile
          icon={<Layers size={18} />}
          label={t('admin.activeQueues', 'Active queues')}
          value={health?.active_queues ?? 0}
          hint={t('admin.activeQueuesHint', 'Services with people waiting')}
        />
        <HealthTile
          icon={<Brain size={18} />}
          label={t('admin.pendingRecs', 'Pending recommendations')}
          value={health?.pending_recommendations ?? 0}
          hint={t('admin.pendingRecsHint', 'Awaiting a human decision')}
        />
      </section>

      <div className="grid sm:grid-cols-3 gap-3">
        <NStat label={t('admin.activeQueues', 'Active queues')} valueNumber={Number(health?.active_queues ?? 0)} />
        <NStat label={t('admin.pendingRecs', 'Pending recommendations')} valueNumber={Number(health?.pending_recommendations ?? 0)} />
        <NStat label={t('admin.servicesTotal', 'Services')} valueNumber={Number(health?.services_total ?? 0)} hint={t('admin.servicesTotalHint', 'Active services across offices')} />
      </div>

      <Card kicker={t('admin.overview', 'Overview')} title={t('admin.whatNext', 'What would you like to do?')}>
        <ul className="m-0 p-0 list-none grid sm:grid-cols-2 gap-3 text-sm">
          <li className="rounded-md border border-line bg-surface2 px-4 py-3">
            <b className="block text-ink">{t('admin.offices', 'Office operations')}</b>
            <span className="text-ink-2">{t('admin.officesHint', 'Adjust hours, holidays and the office location.')}</span>
          </li>
          <li className="rounded-md border border-line bg-surface2 px-4 py-3">
            <b className="block text-ink">{t('admin.ai', 'AI governance')}</b>
            <span className="text-ink-2">{t('admin.aiHint', 'Review AI scheduling recommendations before they are applied.')}</span>
          </li>
          <li className="rounded-md border border-line bg-surface2 px-4 py-3">
            <b className="block text-ink">{t('admin.priority', 'Priority rules')}</b>
            <span className="text-ink-2">{t('admin.priorityHint', 'Fast-track citizens who need extra help.')}</span>
          </li>
          <li className="rounded-md border border-line bg-surface2 px-4 py-3">
            <b className="block text-ink">{t('admin.audit', 'Audit log')}</b>
            <span className="text-ink-2">{t('admin.auditHint', 'Every administrative action is recorded here.')}</span>
          </li>
        </ul>
      </Card>
    </div>
  )
}
