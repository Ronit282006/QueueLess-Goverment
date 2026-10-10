import { BellRing, RefreshCw, ScrollText } from 'lucide-react'
import { Badge, Button, Card, DataTable, EmptyState } from '../../components/ui'
import { useI18n } from '../../lib/i18n'
import type { Json } from './types'

export default function AuditNotifications({
  audit,
  notifications,
  reload,
  loading,
}: {
  audit: Json[]
  notifications: Json[]
  reload: () => Promise<void>
  loading: boolean
}) {
  const { t } = useI18n()

  return (
    <div className="flex flex-col gap-4">
      <Card
        kicker={t('admin.audit', 'Audit log')}
        title={t('admin.auditTitle', 'Every administrative action')}
        action={
          <Button variant="secondary" size="sm" onClick={() => void reload()} loading={loading} icon={<RefreshCw size={14} />}>
            {t('common.refresh', 'Refresh')}
          </Button>
        }
      >
        <p className="text-[13px] text-ink-2 mt-0 mb-3">{t('admin.auditHint', 'Every administrative action is recorded here.')}</p>
        <DataTable
          rowKey={(row, i) => `${String(row.action)}-${i}`}
          rows={audit}
          empty={
            <EmptyState
              icon={<ScrollText size={22} />}
              title={t('admin.emptyLog', 'No entries yet.')}
              hint={t('admin.emptyLogHint', 'Actions you take in this console will appear here.')}
            />
          }
          columns={[
            { header: t('admin.date', 'Time'), render: (row) => <span className="text-ink-2 tabular-nums">{String(row.at ?? '').slice(0, 19).replace('T', ' ')}</span> },
            { header: t('admin.action', 'Action'), render: (row) => <b className="text-ink">{String(row.action)}</b> },
            { header: t('admin.actor', 'Actor'), render: (row) => <Badge tone="neutral">{String(row.actor_role ?? 'SYSTEM')}</Badge> },
            { header: t('admin.details', 'Details'), render: (row) => <span className="text-ink-2">{String(row.entity_type ?? '')}</span> },
          ]}
        />
      </Card>

      <Card kicker={t('admin.notifs', 'Notification log')} title={t('admin.notifsTitle', 'Messages sent to citizens')}>
        {notifications.length === 0 ? (
          <EmptyState
            icon={<BellRing size={22} />}
            title={t('admin.noNotifs', 'No notifications yet')}
            hint={t('admin.noNotifsHint', 'Emails and alerts sent by the system appear here.')}
          />
        ) : (
          <ul className="m-0 p-0 list-none flex flex-col gap-2">
            {notifications.map((n, i) => (
              <li key={i} className="rounded-md border border-line p-3.5 flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="m-0 text-sm font-semibold text-ink truncate">{String(n.subject)}</p>
                  <p className="m-0 mt-0.5 text-[13px] text-ink-2">
                    {String(n.kind)} · {String(n.recipient ?? '')}
                  </p>
                </div>
                <Badge tone={String(n.status) === 'SENT' ? 'ok' : 'warn'}>{String(n.status)}</Badge>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}
