import { useCallback, useEffect, useState } from 'react'
import { Brain, Building2, ClipboardList, LayoutDashboard, ScrollText, ShieldCheck } from 'lucide-react'
import { Page, Skeleton, Tabs } from '../components/ui'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import { useOffice } from '../lib/office'
import AdminOverview from './admin/AdminOverview'
import AiGovernance from './admin/AiGovernance'
import AuditNotifications from './admin/AuditNotifications'
import IncidentsPanel from './admin/IncidentsPanel'
import OfficeOperations from './admin/OfficeOperations'
import PriorityRules from './admin/PriorityRules'
import type { Json } from './admin/types'

export default function AdminPage() {
  const { user } = useAuth()
  const { t } = useI18n()
  const { office } = useOffice()
  const [health, setHealth] = useState<Json | null>(null)
  const [rules, setRules] = useState<Json[]>([])
  const [recommendations, setRecommendations] = useState<Json[]>([])
  const [audit, setAudit] = useState<Json[]>([])
  const [notifications, setNotifications] = useState<Json[]>([])
  const [holidays, setHolidays] = useState<Json[]>([])
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState('overview')

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
    } finally {
      setLoading(false)
    }
  }, [officeId])

  useEffect(() => {
    void load()
  }, [load])

  if (!user || user.role !== 'ADMIN') {
    return (
      <Page title={t('admin.title', 'Administration')}>
        <p className="text-sm text-ink-2">
          {t('admin.notAdmin', 'Sign in with an administrator account to manage governance settings.')}
        </p>
      </Page>
    )
  }

  const tabs = [
    { value: 'overview', label: t('admin.overview', 'Overview'), icon: <LayoutDashboard size={16} /> },
    { value: 'offices', label: t('admin.offices', 'Office operations'), icon: <Building2 size={16} /> },
    { value: 'incidents', label: t('admin.incidents', 'Incidents'), icon: <ClipboardList size={16} /> },
    { value: 'ai', label: t('admin.ai', 'AI governance'), icon: <Brain size={16} /> },
    { value: 'priority', label: t('admin.priority', 'Priority rules'), icon: <ShieldCheck size={16} /> },
    { value: 'audit', label: t('admin.audit', 'Audit and notifications'), icon: <ScrollText size={16} /> },
  ]

  return (
    <Page kicker={`${t('admin.governance', 'Governance')} · ${office?.name ?? ''}`} title={t('admin.title', 'Administration')}>
      <p className="text-sm text-ink-2 mt-0 mb-5 max-w-3xl">
        {t('admin.subtitle', 'Monitor system health, configure inclusive priority rules and act on AI counter recommendations.')}
      </p>

      <div className="mb-5">
        <Tabs tabs={tabs} active={tab} onChange={setTab} label={t('admin.sections', 'Administration sections')} />
      </div>

      {loading && !health ? (
        <div className="space-y-4">
          <div className="grid sm:grid-cols-2 xl:grid-cols-4 gap-3">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="h-32 rounded-md skeleton" />
            ))}
          </div>
          <div className="h-64 rounded-md skeleton" />
          <Skeleton lines={2} />
        </div>
      ) : (
        <div role="tabpanel" aria-label={tabs.find((x) => x.value === tab)?.label}>
          {tab === 'overview' && <AdminOverview health={health} />}
          {tab === 'offices' && <OfficeOperations holidays={holidays} reload={load} />}
          {tab === 'incidents' && <IncidentsPanel />}
          {tab === 'ai' && <AiGovernance recommendations={recommendations} officeId={officeId} reload={load} />}
          {tab === 'priority' && <PriorityRules rules={rules} officeId={officeId} reload={load} />}
          {tab === 'audit' && <AuditNotifications audit={audit} notifications={notifications} reload={load} loading={loading} />}
        </div>
      )}
    </Page>
  )
}
