import { useCallback, useEffect, useState } from 'react'
import {
  AlertTriangle,
  Bell,
  CalendarClock,
  CheckCircle2,
  Clock,
  MapPin,
  RefreshCw,
  Repeat,
  ShieldAlert,
} from 'lucide-react'
import { Badge, Button, Card, EmptyState, FormField, useToast } from '../../components/ui'
import { api } from '../../lib/api'
import { useI18n } from '../../lib/i18n'
import { useOffice } from '../../lib/office'
import { toLocalInputValue } from './types'
import type { Json } from './types'

export default function IncidentsPanel() {
  const { office, services } = useOffice()
  const { t } = useI18n()
  const toast = useToast()
  const officeId = office?.id

  const [type, setType] = useState('CLOSURE')
  const [serviceId, setServiceId] = useState<number | ''>('')
  const [description, setDescription] = useState('Temporary counter closure')
  const [location, setLocation] = useState('')
  const [endsAt, setEndsAt] = useState(() => toLocalInputValue(new Date(Date.now() + 60 * 60_000)))
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(false)
  const [incidents, setIncidents] = useState<Json[]>([])
  const [arrived, setArrived] = useState<Json[]>([])
  const [error, setError] = useState('')

  const loadData = useCallback(async () => {
    if (!officeId) return
    setLoading(true)
    try {
      const [incList, arrList] = await Promise.all([
        api.listIncidents(officeId).catch(() => []),
        api.listArrivedIncidentTokens(officeId).catch(() => []),
      ])
      setIncidents(incList)
      if (arrList && arrList.length > 0) {
        setArrived(arrList)
      }
    } finally {
      setLoading(false)
    }
  }, [officeId])

  useEffect(() => {
    void loadData()
  }, [loadData])

  const submit = async () => {
    setError('')
    if (!officeId) return
    const ends = new Date(endsAt)
    if (Number.isNaN(ends.getTime())) return setError(t('admin.invalidTime', 'Pick a valid expected resolution time.'))
    if (ends.getTime() <= Date.now()) return setError(t('admin.pastTime', 'The expected resolution time must be later than now.'))
    if (description.trim().length < 4) return setError(t('admin.describeMore', 'Please describe what happened in a few words.'))

    setBusy(true)
    try {
      const result = await api.createIncident({
        office_id: officeId,
        service_id: serviceId === '' ? null : serviceId,
        incident_type: type,
        description,
        location_instructions: location,
        starts_at: new Date().toISOString(),
        ends_at: ends.toISOString(),
      })
      const arrivedList = (result.arrived_for_staff as Json[] | undefined) ?? []
      if (arrivedList.length > 0) {
        setArrived((prev) => [...arrivedList, ...prev.filter((p) => !arrivedList.some((a) => a.id === p.id))])
      }
      toast.success(
        t('admin.incidentSent', 'Incident reported'),
        t('admin.incidentNotified', '{count} citizen(s) were emailed. Response deadline: {when}.')
          .replace('{count}', String(result.notified_count ?? 0))
          .replace('{when}', new Date(String(result.response_deadline)).toLocaleString()),
      )
      void loadData()
    } catch (err) {
      toast.error(t('admin.actionFailed', 'That did not work'), (err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const handleResolve = async (incidentId: number) => {
    try {
      await api.resolveIncident(incidentId)
      toast.success(t('admin.incidentResolved', 'Incident marked as resolved'))
      void loadData()
    } catch (err) {
      toast.error(t('admin.actionFailed', 'That did not work'), (err as Error).message)
    }
  }

  const rebook = async (tokenId: number) => {
    try {
      const result = await api.rebookArrivedIncidentTicket(tokenId)
      setArrived((current) => current.filter((ticket) => Number(ticket.id) !== tokenId))
      toast.success(
        t('admin.rebooked', 'Rebooked'),
        t('admin.rebookedBody', 'The citizen was moved to {when}.').replace('{when}', String(result.scheduled_for)),
      )
    } catch (err) {
      toast.error(t('admin.actionFailed', 'That did not work'), (err as Error).message)
    }
  }

  const activeIncidents = incidents.filter((inc) => String(inc.status).toUpperCase() === 'ACTIVE')
  const pastIncidents = incidents.filter((inc) => String(inc.status).toUpperCase() !== 'ACTIVE')

  const getServiceName = (id?: number | null) => {
    if (!id) return t('admin.allServices', 'All office services')
    return services.find((s) => s.id === id)?.name ?? `Service #${id}`
  }

  return (
    <div className="flex flex-col gap-5">
      {/* Active Incidents Overview Banner */}
      {activeIncidents.length > 0 && (
        <div className="rounded-lg border border-amber-300 bg-amber-50/70 p-4 shadow-sm animate-fade-in">
          <div className="flex items-center justify-between gap-2 mb-3">
            <span className="flex items-center gap-2 font-bold text-amber-900 text-sm">
              <ShieldAlert size={18} className="text-amber-600 shrink-0" />
              {activeIncidents.length} Active {activeIncidents.length === 1 ? 'Incident' : 'Incidents'} Underway
            </span>
            <Button
              variant="secondary"
              size="sm"
              icon={<RefreshCw size={14} className={loading ? 'animate-spin' : ''} />}
              onClick={() => void loadData()}
            >
              {t('common.refresh', 'Refresh')}
            </Button>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {activeIncidents.map((inc) => (
              <div
                key={String(inc.id)}
                className="rounded-md border border-amber-200 bg-white p-3.5 shadow-sm flex flex-col justify-between gap-3"
              >
                <div>
                  <div className="flex items-center justify-between gap-2 mb-1.5">
                    <Badge tone="warn">{String(inc.incident_type)}</Badge>
                    <span className="text-[11px] font-semibold text-amber-800 bg-amber-100/80 px-2 py-0.5 rounded">
                      Deadline: {new Date(String(inc.response_deadline)).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>
                  <h4 className="text-sm font-bold text-slate-900 m-0">{String(inc.description)}</h4>
                  <p className="text-[12px] text-slate-600 mt-1 mb-0 flex items-center gap-1.5">
                    <MapPin size={13} className="text-slate-400 shrink-0" />
                    {getServiceName(inc.service_id as number | undefined)}
                  </p>
                  {Boolean(inc.location_instructions) && (
                    <p className="text-[12px] text-slate-500 mt-1 mb-0 italic">
                      Directions: {String(inc.location_instructions)}
                    </p>
                  )}
                </div>
                <div className="flex items-center justify-between gap-2 pt-2 border-t border-slate-100">
                  <span className="text-[11px] text-slate-500 flex items-center gap-1">
                    <Clock size={12} />
                    Ends ~{new Date(String(inc.ends_at)).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </span>
                  <Button
                    variant="secondary"
                    size="sm"
                    icon={<CheckCircle2 size={14} className="text-emerald-600" />}
                    onClick={() => void handleResolve(Number(inc.id))}
                  >
                    Mark Resolved
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Main Grid: Form and Arrived Citizens */}
      <div className="grid xl:grid-cols-2 gap-5">
        <Card
          kicker={t('admin.incidents', 'Incidents')}
          title={t('admin.reportIncident', 'Report a closure or capacity issue')}
          action={
            <Button
              variant="secondary"
              size="sm"
              icon={<RefreshCw size={14} className={loading ? 'animate-spin' : ''} />}
              onClick={() => void loadData()}
              title="Refresh incident list"
            >
              Refresh
            </Button>
          }
        >
          <div className="rounded-md border border-amber-200 bg-amber-50/60 p-3.5 flex items-start gap-3 mb-4">
            <AlertTriangle size={18} className="text-amber-600 mt-0.5 shrink-0" aria-hidden />
            <p className="text-[13px] text-slate-700 m-0 leading-relaxed">
              {t(
                'admin.incidentHint',
                'Affected citizens get an email with a response deadline and can choose to transfer or cancel. Citizens already at the office are held for staff help.',
              )}
            </p>
          </div>

          <div className="flex flex-col gap-4">
            <FormField
              id="incident-type"
              as="select"
              label={t('admin.incidentType', 'Type of incident')}
              value={type}
              onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setType(e.target.value)}
            >
              <option value="CLOSURE">{t('admin.incidentClosure', 'Temporary office/service closure')}</option>
              <option value="CAPACITY">{t('admin.incidentCapacity', 'Counter capacity reduction')}</option>
              <option value="DELAY">{t('admin.incidentDelay', 'Significant queue delay')}</option>
              <option value="LOCATION">{t('admin.incidentLocation', 'Temporary location change')}</option>
            </FormField>

            <FormField
              id="incident-service"
              as="select"
              label={`${t('admin.serviceOptional', 'Service')} (${t('common.optional', 'optional')})`}
              value={serviceId}
              onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setServiceId(e.target.value ? Number(e.target.value) : '')}
            >
              <option value="">{t('admin.allServices', 'All services at this office')}</option>
              {services
                .filter((service) => service.officeId === officeId)
                .map((service) => (
                  <option key={service.id} value={service.id}>
                    {service.name}
                  </option>
                ))}
            </FormField>

            <FormField
              id="incident-description"
              label={t('admin.incidentDesc', 'Describe what happened')}
              value={description}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setDescription(e.target.value)}
              error={error && description.trim().length < 4 ? error : undefined}
            />

            <FormField
              id="incident-location"
              label={`${t('admin.incidentDirections', 'Temporary directions')} (${t('common.optional', 'optional')})`}
              value={location}
              placeholder="e.g. Please proceed to Building B Counter 4"
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setLocation(e.target.value)}
            />

            <FormField
              id="incident-ends"
              label={t('admin.incidentEnds', 'Expected resolution time')}
              type="datetime-local"
              value={endsAt}
              min={toLocalInputValue(new Date())}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setEndsAt(e.target.value)}
            />

            {error && description.trim().length >= 4 && (
              <p role="alert" className="text-[13px] font-medium text-alert m-0">
                {error}
              </p>
            )}

            <Button onClick={() => void submit()} loading={busy} icon={<Bell size={16} />}>
              {t('admin.incidentNotify', 'Notify affected ticket holders')}
            </Button>
          </div>
        </Card>

        <div className="flex flex-col gap-5">
          <Card
            kicker={t('admin.incidents', 'Incidents')}
            title={t('admin.arrivedHelp', 'Arrived citizens needing staff help')}
          >
            {arrived.length === 0 ? (
              <EmptyState
                icon={<CalendarClock size={22} />}
                title={t('admin.noArrived', 'No one is waiting for help')}
                hint={t('admin.noArrivedHint', 'When an incident affects citizens already at the office, they appear here.')}
              />
            ) : (
              <ul className="m-0 p-0 list-none flex flex-col gap-2.5">
                {arrived.map((ticket) => (
                  <li
                    key={String(ticket.id)}
                    className="flex items-center justify-between gap-3 rounded-md border border-line bg-surface p-3 shadow-sm"
                  >
                    <div className="min-w-0">
                      <b className="block text-sm font-bold text-ink truncate">{String(ticket.label)}</b>
                      <div className="mt-1 flex items-center gap-2">
                        <Badge tone="info">{t('admin.checkedIn', 'Checked in')}</Badge>
                        <span className="text-[12px] text-ink-3">Requires transfer</span>
                      </div>
                    </div>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => void rebook(Number(ticket.id))}
                      icon={<Repeat size={15} />}
                    >
                      {t('admin.rebook', 'Rebook next working day')}
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          {/* Past Incidents History */}
          {pastIncidents.length > 0 && (
            <Card kicker="History" title="Recently Resolved Incidents">
              <ul className="m-0 p-0 list-none flex flex-col gap-2">
                {pastIncidents.slice(0, 5).map((inc) => (
                  <li
                    key={String(inc.id)}
                    className="flex items-center justify-between gap-2 rounded-md border border-line bg-surface2 px-3 py-2 text-xs"
                  >
                    <div className="min-w-0">
                      <span className="font-semibold text-ink truncate block">{String(inc.description)}</span>
                      <span className="text-ink-3">
                        {getServiceName(inc.service_id as number | undefined)} · {String(inc.incident_type)}
                      </span>
                    </div>
                    <Badge tone="ok">Resolved</Badge>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}
