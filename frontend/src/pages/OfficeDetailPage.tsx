import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  ArrowLeft, Building2, Check, Clock, LayoutGrid, Mail, MapPin, Pencil, Phone, Plus, Power,
  Server, SlidersHorizontal, Users,
} from 'lucide-react'
import {
  Badge,
  Button,
  Card,
  DataTable,
  EmptyState,
  FormField,
  Modal,
  Page,
  SegmentedControl,
  Skeleton,
  Tabs,
  useToast,
} from '../components/ui'
import type { DataColumn } from '../components/ui'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import type {
  AdminDepartment, AdminOfficeCounter, AdminOfficeDetail, AdminOfficeService, OfficeServiceInput, QueueSnapshot, StaffMember,
} from '../lib/types'

const COUNTER_STATUSES = ['AVAILABLE', 'BUSY', 'BREAK', 'OFFLINE', 'MAINTENANCE'] as const

type CounterFormState = {
  number: string
  name: string
  code: string
  description: string
  status: string
  service_ids: number[]
}

const EMPTY_COUNTER: CounterFormState = {
  number: '',
  name: '',
  code: '',
  description: '',
  status: 'AVAILABLE',
  service_ids: [],
}

type ServiceFormState = {
  name: string
  code: string
  description: string
  average_service_min: string
  documents: string
  department_id: string
  new_department: string
  is_active: boolean
}

const EMPTY_SERVICE: ServiceFormState = {
  name: '',
  code: '',
  description: '',
  average_service_min: '6.2',
  documents: '',
  department_id: '__new__',
  new_department: '',
  is_active: true,
}

function counterTone(status: string) {
  const s = status.toUpperCase()
  if (s === 'AVAILABLE') return 'ok' as const
  if (s === 'BUSY') return 'info' as const
  if (s === 'BREAK') return 'warn' as const
  if (s === 'MAINTENANCE') return 'warn' as const
  return 'neutral' as const
}

export default function OfficeDetailPage() {
  const { officeId: officeIdParam } = useParams<{ officeId: string }>()
  const officeId = Number(officeIdParam)
  const { user } = useAuth()
  const { t } = useI18n()
  const toast = useToast()

  const [detail, setDetail] = useState<AdminOfficeDetail | null>(null)
  const [allServices, setAllServices] = useState<AdminOfficeService[]>([])
  const [departments, setDepartments] = useState<AdminDepartment[]>([])
  const [counters, setCounters] = useState<AdminOfficeCounter[]>([])
  const [staff, setStaff] = useState<StaffMember[] | null>(null)
  const [queues, setQueues] = useState<Record<number, QueueSnapshot>>({})
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState('overview')
  const [statusBusy, setStatusBusy] = useState(false)
  const [counterBusy, setCounterBusy] = useState<number | null>(null)
  const [serviceBusy, setServiceBusy] = useState<number | null>(null)

  const [counterModal, setCounterModal] = useState(false)
  const [editingCounter, setEditingCounter] = useState<AdminOfficeCounter | null>(null)
  const [counterForm, setCounterForm] = useState<CounterFormState>(EMPTY_COUNTER)
  const [counterErrors, setCounterErrors] = useState<Record<string, string>>({})
  const [savingCounter, setSavingCounter] = useState(false)

  const [serviceModal, setServiceModal] = useState(false)
  const [editingService, setEditingService] = useState<AdminOfficeService | null>(null)
  const [serviceForm, setServiceForm] = useState<ServiceFormState>(EMPTY_SERVICE)
  const [serviceErrors, setServiceErrors] = useState<Record<string, string>>({})
  const [savingService, setSavingService] = useState(false)

  const services = useMemo(() => allServices.filter((s) => s.is_active), [allServices])

  const load = useCallback(async () => {
    if (!Number.isFinite(officeId)) return
    setLoading(true)
    try {
      const [d, s, c, deps] = await Promise.all([
        api.adminOffice(officeId),
        api.adminOfficeServices(officeId, true),
        api.adminOfficeCounters(officeId),
        api.adminOfficeDepartments(officeId),
      ])
      setDetail(d)
      setAllServices(s)
      setCounters(c)
      setDepartments(deps)
    } catch (err) {
      toast.error(t('od.loadFailed', 'Could not load this office'), (err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [officeId, t, toast])

  useEffect(() => {
    void load()
  }, [load])

  const loadStaff = useCallback(async () => {
    try {
      const all = await api.adminStaff()
      setStaff(all.filter((m) => m.offices.includes(officeId)))
    } catch {
      setStaff([])
    }
  }, [officeId])

  useEffect(() => {
    if (tab === 'staff' && staff === null) void loadStaff()
  }, [tab, staff, loadStaff])

  useEffect(() => {
    if (tab !== 'queue') return
    let active = true
    void (async () => {
      const entries = await Promise.all(
        services.map(async (s) => {
          try {
            return [s.id, await api.queue(s.id, officeId)] as const
          } catch {
            return null
          }
        }),
      )
      if (!active) return
      const next: Record<number, QueueSnapshot> = {}
      for (const entry of entries) if (entry) next[entry[0]] = entry[1]
      setQueues(next)
    })()
    return () => {
      active = false
    }
  }, [tab, services, officeId])

  const toggleOfficeStatus = async () => {
    if (!detail) return
    setStatusBusy(true)
    try {
      const result = await api.adminSetOfficeStatus(detail.id, !detail.is_active)
      setDetail((prev) => (prev ? { ...prev, ...result } : prev))
      toast.success(
        result.is_active ? t('om.activated', 'Office activated') : t('om.deactivated', 'Office deactivated'),
        result.name,
      )
    } catch (err) {
      toast.error(t('admin.actionFailed', 'That did not work'), (err as Error).message)
    } finally {
      setStatusBusy(false)
    }
  }

  const openCreateCounter = () => {
    const nextNumber = counters.reduce((max, c) => Math.max(max, c.number), 0) + 1
    setEditingCounter(null)
    setCounterForm({ ...EMPTY_COUNTER, number: String(nextNumber) })
    setCounterErrors({})
    setCounterModal(true)
  }

  const openEditCounter = (counter: AdminOfficeCounter) => {
    setEditingCounter(counter)
    setCounterForm({
      number: String(counter.number),
      name: counter.name,
      code: counter.code ?? '',
      description: counter.description,
      status: counter.status,
      service_ids: [...counter.service_ids],
    })
    setCounterErrors({})
    setCounterModal(true)
  }

  const setCounterField = (key: keyof CounterFormState, value: string) => {
    setCounterForm((prev) => ({ ...prev, [key]: value }))
  }

  const toggleCounterService = (serviceId: number) => {
    setCounterForm((prev) => ({
      ...prev,
      service_ids: prev.service_ids.includes(serviceId)
        ? prev.service_ids.filter((id) => id !== serviceId)
        : [...prev.service_ids, serviceId],
    }))
  }

  const submitCounter = async () => {
    const errs: Record<string, string> = {}
    const number = Number(counterForm.number)
    if (!Number.isInteger(number) || number < 1 || number > 9999) {
      errs.number = t('od.counterNumberInvalid', 'Enter a number between 1 and 9999.')
    }
    setCounterErrors(errs)
    if (Object.keys(errs).length) return
    setSavingCounter(true)
    try {
      const payload = {
        number,
        name: counterForm.name.trim(),
        code: counterForm.code.trim() || null,
        description: counterForm.description.trim(),
        status: counterForm.status,
        service_ids: counterForm.service_ids,
      }
      if (editingCounter) {
        await api.adminUpdateCounter(editingCounter.id, payload)
        toast.success(t('od.counterUpdated', 'Counter updated'), `#${number}`)
      } else {
        await api.adminCreateCounter(officeId, payload)
        toast.success(t('od.counterCreated', 'Counter added'), `#${number}`)
      }
      setCounterModal(false)
      await load()
    } catch (err) {
      toast.error(t('admin.actionFailed', 'That did not work'), (err as Error).message)
    } finally {
      setSavingCounter(false)
    }
  }

  const changeCounterStatus = async (counter: AdminOfficeCounter, status: string) => {
    setCounterBusy(counter.id)
    try {
      const result = await api.adminSetCounterStatus(counter.id, status)
      setCounters((prev) => prev.map((c) => (c.id === result.id ? result : c)))
    } catch (err) {
      toast.error(t('admin.actionFailed', 'That did not work'), (err as Error).message)
    } finally {
      setCounterBusy(null)
    }
  }

  const setServiceField = (key: keyof ServiceFormState, value: string | boolean) => {
    setServiceForm((prev) => ({ ...prev, [key]: value } as ServiceFormState))
  }

  const openCreateService = () => {
    setEditingService(null)
    setServiceForm({
      ...EMPTY_SERVICE,
      department_id: departments.length ? String(departments[0].id) : '__new__',
    })
    setServiceErrors({})
    setServiceModal(true)
  }

  const openEditService = (service: AdminOfficeService) => {
    setEditingService(service)
    setServiceForm({
      name: service.name,
      code: service.code,
      description: service.description,
      average_service_min: String(service.average_service_min),
      documents: (service.documents ?? []).join('\n'),
      department_id: String(service.department_id),
      new_department: '',
      is_active: service.is_active,
    })
    setServiceErrors({})
    setServiceModal(true)
  }

  const submitService = async () => {
    const errs: Record<string, string> = {}
    const name = serviceForm.name.trim()
    if (name.length < 2) errs.name = t('od.serviceNameInvalid', 'Enter a service name.')
    const useNewDepartment = serviceForm.department_id === '__new__'
    const newDepartment = serviceForm.new_department.trim()
    if (useNewDepartment && newDepartment.length < 2) {
      errs.department = t('od.newDepartmentInvalid', 'Enter a department name.')
    }
    const avg = Number(serviceForm.average_service_min)
    if (!Number.isFinite(avg) || avg <= 0 || avg > 120) {
      errs.average_service_min = t('od.avgInvalid', 'Enter a number between 1 and 120.')
    }
    setServiceErrors(errs)
    if (Object.keys(errs).length) return

    const documents = serviceForm.documents
      .split(/[\n,]+/)
      .map((d) => d.trim())
      .filter(Boolean)
    const departmentId = useNewDepartment ? null : Number(serviceForm.department_id)

    setSavingService(true)
    try {
      if (editingService) {
        const payload: Partial<OfficeServiceInput> = {
          name,
          description: serviceForm.description.trim(),
          average_service_min: avg,
          documents,
          is_active: serviceForm.is_active,
        }
        if (departmentId !== null && departmentId !== editingService.department_id) {
          payload.department_id = departmentId
        }
        await api.adminUpdateService(editingService.id, payload)
        toast.success(t('od.serviceUpdated', 'Service updated'), name)
      } else {
        const payload: OfficeServiceInput = {
          name,
          code: serviceForm.code.trim() || null,
          description: serviceForm.description.trim(),
          average_service_min: avg,
          documents,
          is_active: serviceForm.is_active,
        }
        if (departmentId !== null) payload.department_id = departmentId
        else payload.department_name = newDepartment
        await api.adminCreateOfficeService(officeId, payload)
        toast.success(t('od.serviceCreated', 'Service added'), name)
      }
      setServiceModal(false)
      await load()
    } catch (err) {
      toast.error(t('admin.actionFailed', 'That did not work'), (err as Error).message)
    } finally {
      setSavingService(false)
    }
  }

  const toggleServiceActive = async (service: AdminOfficeService) => {
    setServiceBusy(service.id)
    try {
      await api.adminUpdateService(service.id, { is_active: !service.is_active })
      toast.success(
        service.is_active ? t('od.serviceDeactivated', 'Service deactivated') : t('od.serviceActivated', 'Service activated'),
        service.name,
      )
      await load()
    } catch (err) {
      toast.error(t('admin.actionFailed', 'That did not work'), (err as Error).message)
    } finally {
      setServiceBusy(null)
    }
  }

  const serviceColumns: DataColumn<AdminOfficeService>[] = [
    { header: t('om.service', 'Service'), render: (s) => <span className="font-semibold text-ink">{s.name}</span> },
    { header: t('om.serviceCode', 'Code'), render: (s) => <span className="font-mono text-[13px]">{s.code}</span> },
    { header: t('om.department', 'Department'), render: (s) => s.department_name || '—' },
    { header: t('om.avgMin', 'Avg (min)'), render: (s) => String(s.average_service_min) },
    {
      header: t('od.countersHeader', 'Counters'),
      render: (s) => (
        <Badge tone={s.counter_ids.length ? 'info' : 'neutral'}>
          {t('om.countersN', '{n} counters').replace('{n}', String(s.counter_ids.length))}
        </Badge>
      ),
    },
    {
      header: t('od.statusHeader', 'Status'),
      render: (s) => (
        <Badge tone={s.is_active ? 'ok' : 'neutral'}>
          {s.is_active ? t('om.active', 'Active') : t('om.inactive', 'Inactive')}
        </Badge>
      ),
    },
    {
      header: t('od.actionsHeader', 'Actions'),
      render: (s) => (
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant="secondary" icon={<Pencil size={14} />} onClick={() => openEditService(s)}>
            {t('om.edit', 'Edit')}
          </Button>
          <Button
            size="sm"
            variant="secondary"
            loading={serviceBusy === s.id}
            icon={<Power size={14} />}
            onClick={() => void toggleServiceActive(s)}
          >
            {s.is_active ? t('om.deactivate', 'Deactivate') : t('om.activate', 'Activate')}
          </Button>
        </div>
      ),
    },
  ]

  if (!user || user.role !== 'ADMIN') {
    return (
      <Page title={t('om.title', 'Office management')}>
        <p className="text-sm text-ink-2">{t('om.notAdmin', 'Only administrators can manage offices.')}</p>
      </Page>
    )
  }

  if (loading && !detail) {
    return (
      <Page title={t('od.title', 'Office')}>
        <Skeleton lines={5} />
      </Page>
    )
  }

  if (!detail) {
    return (
      <Page title={t('od.title', 'Office')}>
        <EmptyState
          icon={<Building2 size={22} />}
          title={t('od.notFound', 'Office not found')}
          hint={t('od.notFoundHint', 'It may have been removed.')}
          action={<Link to="/admin/offices" className="text-sm font-semibold text-brand">{t('od.back', 'Back to offices')}</Link>}
        />
      </Page>
    )
  }

  const metrics = detail.metrics
  const tabs = [
    { value: 'overview', label: t('od.tabOverview', 'Overview') },
    { value: 'services', label: t('od.tabServices', 'Services') },
    { value: 'counters', label: t('od.tabCounters', 'Counters') },
    { value: 'staff', label: t('od.tabStaff', 'Staff') },
    { value: 'queue', label: t('od.tabQueue', 'Live queue') },
  ]

  return (
    <Page
      kicker={t('om.title', 'Office management')}
      title={detail.name}
      actions={
        <>
          <Link
            to="/admin/offices"
            className="inline-flex items-center justify-center gap-2 rounded-md border border-line bg-surface px-3 py-2 text-sm font-semibold text-ink hover:bg-surface2 min-h-[42px]"
          >
            <ArrowLeft size={15} aria-hidden /> {t('od.back', 'Back to offices')}
          </Link>
          <Link
            to={`/admin/assignments?office=${detail.id}`}
            className="inline-flex items-center justify-center gap-2 rounded-md border border-line bg-surface px-3 py-2 text-sm font-semibold text-ink hover:bg-surface2 min-h-[42px]"
          >
            <SlidersHorizontal size={15} aria-hidden /> {t('od.assignments', 'Assign staff')}
          </Link>
          <Button
            variant={detail.is_active ? 'dangerGhost' : 'primary'}
            loading={statusBusy}
            icon={<Power size={16} />}
            onClick={() => void toggleOfficeStatus()}
          >
            {detail.is_active ? t('om.deactivate', 'Deactivate') : t('om.activate', 'Activate')}
          </Button>
        </>
      }
    >
      <div className="flex flex-wrap items-center gap-2 mb-5">
        <Badge tone={detail.is_active ? 'ok' : 'alert'}>
          {detail.is_active ? <Check size={12} aria-hidden /> : <Power size={12} aria-hidden />}
          {detail.is_active ? t('om.active', 'Active') : t('om.inactive', 'Inactive')}
        </Badge>
        <Badge tone="neutral"><span className="font-mono">{detail.code}</span></Badge>
        {detail.city && <Badge tone="neutral"><MapPin size={12} aria-hidden /> {detail.city}{detail.state ? `, ${detail.state}` : ''}</Badge>}
        {detail.has_coordinates ? (
          <Badge tone="info">{detail.latitude}, {detail.longitude}</Badge>
        ) : (
          <Badge tone="warn">{t('om.notPinned', 'No location pin yet')}</Badge>
        )}
      </div>

      <div className="mb-5">
        <Tabs tabs={tabs} active={tab} onChange={setTab} label={t('od.sections', 'Office sections')} />
      </div>

      {tab === 'overview' && (
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="lg:col-span-2 grid gap-3 sm:grid-cols-3">
            <MetricCard label={t('od.mServices', 'Services')} value={metrics.services_count} />
            <MetricCard label={t('od.mCounters', 'Counters')} value={metrics.counters_count} />
            <MetricCard label={t('om.activeCounters', 'Active counters')} value={metrics.active_counters_count} />
            <MetricCard label={t('od.mStaff', 'Staff')} value={metrics.staff_count} />
            <MetricCard label={t('om.inQueue', 'In queue now')} value={metrics.queue_length} />
            <MetricCard label={t('od.mServing', 'Serving now')} value={metrics.queue_length > 0 ? metrics.active_counters_count : 0} />
            <MetricCard label={t('om.doneToday', 'Completed today')} value={metrics.today.tokens_completed} />
            <MetricCard label={t('om.createdToday', 'Tokens today')} value={metrics.today.tokens_created} />
            <MetricCard label={t('om.cancelledToday', 'Cancelled today')} value={metrics.today.tokens_cancelled} />
          </div>

          <Card title={t('od.details', 'Office details')}>
            <dl className="m-0 flex flex-col gap-3 text-sm">
              <DetailRow icon={<MapPin size={15} />} label={t('om.address', 'Address')} value={[detail.address, detail.city, detail.state, detail.pincode].filter(Boolean).join(', ') || '—'} />
              <DetailRow icon={<Clock size={15} />} label={t('om.hours', 'Opening hours')} value={detail.open_time && detail.close_time ? `${detail.open_time}–${detail.close_time}` : detail.working_hours || '—'} />
              <DetailRow icon={<LayoutGrid size={15} />} label={t('om.workingDays', 'Working days')} value={detail.working_days || '—'} />
              <DetailRow icon={<Phone size={15} />} label={t('om.phone', 'Contact phone')} value={detail.contact_phone || '—'} />
              <DetailRow icon={<Mail size={15} />} label={t('om.email', 'Contact email')} value={detail.contact_email || '—'} />
            </dl>
            {detail.description && <p className="mt-4 mb-0 text-[13px] text-ink-2 leading-relaxed">{detail.description}</p>}
          </Card>
        </div>
      )}

      {tab === 'services' && (
        <Card
          title={t('od.servicesTitle', 'Services offered')}
          action={
            <div className="flex items-center gap-2">
              <Badge tone="neutral">{allServices.length}</Badge>
              <Button size="sm" icon={<Plus size={14} />} onClick={openCreateService}>{t('od.addService', 'Add service')}</Button>
            </div>
          }
        >
          {!detail.has_coordinates && (
            <div className="mb-4 rounded-md border border-warn/50 bg-warn-soft px-4 py-3 text-[13px] text-ink">
              {t('od.locationHint', 'Set the location pin for this office so GPS can rank it in recommendations.')}
            </div>
          )}
          <DataTable
            columns={serviceColumns}
            rows={allServices}
            rowKey={(s) => String(s.id)}
            noWrap={false}
            empty={<EmptyState icon={<LayoutGrid size={22} />} title={t('od.noServices', 'No services configured')} hint={t('od.noServicesHint', 'Add a service so citizens can book it and GPS can recommend this office.')} />}
          />
        </Card>
      )}

      {tab === 'counters' && (
        <Card
          title={t('od.countersTitle', 'Counters')}
          action={<Button size="sm" icon={<Plus size={14} />} onClick={openCreateCounter}>{t('od.addCounter', 'Add counter')}</Button>}
        >
          {counters.length === 0 ? (
            <EmptyState
              icon={<Server size={22} />}
              title={t('od.noCounters', 'No counters yet')}
              hint={t('od.noCountersHint', 'Add a counter and link the services it handles.')}
              action={<Button icon={<Plus size={16} />} onClick={openCreateCounter}>{t('od.addCounter', 'Add counter')}</Button>}
            />
          ) : (
            <ul className="m-0 p-0 list-none flex flex-col gap-2">
              {counters.map((counter) => (
                <li key={counter.id} className="rounded-md border border-line p-3.5 flex flex-wrap items-center justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="m-0 text-[15px] font-semibold text-ink">
                      {t('od.counterLabel', 'Counter {n}').replace('{n}', String(counter.number))}
                      {counter.name ? <span className="text-ink-2 font-normal"> · {counter.name}</span> : null}
                      {counter.code ? <span className="ml-2 font-mono text-[12px] text-ink-3">{counter.code}</span> : null}
                    </p>
                    <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                      <Badge tone={counterTone(counter.status)}>{counter.status}</Badge>
                      <Badge tone={counter.service_ids.length ? 'info' : 'neutral'}>
                        {counter.service_ids.length
                          ? t('od.servicesLinked', '{n} service(s)').replace('{n}', String(counter.service_ids.length))
                          : t('od.noServicesLinked', 'No services')}
                      </Badge>
                      <Badge tone={counter.staff.length ? 'neutral' : 'neutral'}>
                        {counter.staff.length
                          ? t('od.staffLinked', '{n} staff').replace('{n}', String(counter.staff.length))
                          : t('od.noStaffLinked', 'Unstaffed')}
                      </Badge>
                    </div>
                    {counter.staff.length > 0 && (
                      <p className="m-0 mt-1 text-[12px] text-ink-3 truncate">
                        {counter.staff.map((s) => s.full_name).join(', ')}
                      </p>
                    )}
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <label className="sr-only" htmlFor={`counter-status-${counter.id}`}>{t('od.counterStatus', 'Counter status')}</label>
                    <select
                      id={`counter-status-${counter.id}`}
                      value={counter.status}
                      disabled={counterBusy === counter.id}
                      onChange={(e) => void changeCounterStatus(counter, e.target.value)}
                      className="rounded-md border border-line bg-surface px-2.5 py-1.5 text-xs font-semibold text-ink min-h-[34px] focus:outline-none focus:ring-2 focus:border-brand focus:ring-brand/25"
                    >
                      {COUNTER_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                    <Button size="sm" variant="secondary" icon={<Pencil size={14} />} onClick={() => openEditCounter(counter)}>
                      {t('om.edit', 'Edit')}
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}

      {tab === 'staff' && (
        <Card title={t('od.staffTitle', 'Staff assigned here')} action={<Badge tone="neutral">{staff?.length ?? 0}</Badge>}>
          {staff === null ? (
            <Skeleton lines={3} />
          ) : staff.length === 0 ? (
            <EmptyState
              icon={<Users size={22} />}
              title={t('od.noStaff', 'No staff assigned')}
              hint={t('od.noStaffHint', 'Assign staff to counters from the assignments page.')}
              action={
                <Link to={`/admin/assignments?office=${detail.id}`} className="inline-flex items-center gap-2 rounded-md border border-line bg-surface px-4 py-2.5 text-sm font-semibold text-brand hover:bg-brand-soft min-h-[42px]">
                  <SlidersHorizontal size={16} aria-hidden /> {t('od.assignments', 'Assign staff')}
                </Link>
              }
            />
          ) : (
            <ul className="m-0 p-0 list-none flex flex-col gap-2">
              {staff.map((member) => (
                <li key={member.id} className="rounded-md border border-line p-3.5 flex flex-wrap items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="m-0 text-[15px] font-semibold text-ink truncate">{member.full_name}</p>
                    <p className="m-0 mt-0.5 text-[13px] text-ink-2 truncate">{member.email}</p>
                    <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                      <Badge tone={member.is_active ? 'ok' : 'alert'}>{member.is_active ? t('sm.active', 'Active') : t('sm.suspended', 'Suspended')}</Badge>
                      <Badge tone={member.counters.length ? 'info' : 'neutral'}>
                        {member.counters.length
                          ? t('sm.counters', '{n} counter(s)').replace('{n}', String(member.counters.length))
                          : t('sm.unassigned', 'Not assigned')}
                      </Badge>
                    </div>
                  </div>
                  <Link
                    to={`/admin/assignments?staff=${member.id}&office=${detail.id}`}
                    className="inline-flex items-center justify-center gap-2 rounded-md border border-line bg-surface px-3 py-1.5 text-xs font-semibold text-brand hover:bg-brand-soft hover:border-brand/35 shadow-sm transition-all active:scale-[0.985] min-h-[34px]"
                  >
                    <SlidersHorizontal size={14} aria-hidden /> {t('sm.assignCounters', 'Assign counters')}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}

      {tab === 'queue' && (
        <Card title={t('od.queueTitle', 'Live queue by service')}>
          {services.length === 0 ? (
            <EmptyState icon={<LayoutGrid size={22} />} title={t('od.noServices', 'No services configured')} />
          ) : (
            <ul className="m-0 p-0 list-none flex flex-col gap-2">
              {services.map((service) => {
                const snapshot = queues[service.id]
                return (
                  <li key={service.id} className="rounded-md border border-line p-3.5 flex flex-wrap items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="m-0 text-[15px] font-semibold text-ink truncate">{service.name}</p>
                      <p className="m-0 mt-0.5 text-[13px] text-ink-2">
                        {t('om.avgMin', 'Avg (min)')}: {service.average_service_min} · {service.department_name}
                      </p>
                    </div>
                    {snapshot ? (
                      <div className="flex flex-wrap items-center gap-1.5">
                        <Badge tone="brand">{t('od.waiting', 'Waiting')}: {snapshot.waiting}</Badge>
                        <Badge tone="ok">{t('od.serving', 'Serving')}: {snapshot.serving}</Badge>
                        <Badge tone="info">{t('om.activeCounters', 'Active counters')}: {snapshot.active_counters}</Badge>
                        <Badge tone="neutral">ETA ~{snapshot.prediction.minutes} {t('common.min', 'min')}</Badge>
                      </div>
                    ) : (
                      <Skeleton lines={1} />
                    )}
                  </li>
                )
              })}
            </ul>
          )}
        </Card>
      )}

      <Modal
        open={counterModal}
        onClose={() => (savingCounter ? undefined : setCounterModal(false))}
        title={editingCounter ? t('od.editCounter', 'Edit counter') : t('od.addCounter', 'Add counter')}
        description={editingCounter ? t('od.counterLabel', 'Counter {n}').replace('{n}', String(editingCounter.number)) : t('od.counterHint', 'Counters serve one or more services in this office.')}
        label="counter-form"
        footer={
          <>
            <Button variant="secondary" onClick={() => setCounterModal(false)} disabled={savingCounter}>
              {t('common.cancel', 'Cancel')}
            </Button>
            <Button loading={savingCounter} onClick={() => void submitCounter()} icon={<Check size={16} />}>
              {editingCounter ? t('om.save', 'Save changes') : t('od.addCounter', 'Add counter')}
            </Button>
          </>
        }
      >
        <form
          className="grid gap-4 sm:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault()
            void submitCounter()
          }}
          noValidate
        >
          <FormField
            id="counter-number"
            label={t('od.counterNumber', 'Counter number')}
            type="number"
            min={1}
            max={9999}
            value={counterForm.number}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setCounterField('number', e.target.value)}
            error={counterErrors.number}
            required
          />
          <FormField
            id="counter-code"
            label={t('od.counterCode', 'Short code')}
            value={counterForm.code}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setCounterField('code', e.target.value)}
            placeholder="C1"
            hint={t('od.counterCodeHint', 'Optional. Must be unique within the office.')}
          />
          <FormField
            id="counter-name"
            label={t('od.counterName', 'Name / window label')}
            value={counterForm.name}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setCounterField('name', e.target.value)}
            placeholder={t('od.counterNamePlaceholder', 'Window 1')}
            className="sm:col-span-2"
          />
          <FormField
            id="counter-status"
            label={t('od.counterStatus', 'Counter status')}
            as="select"
            value={counterForm.status}
            onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setCounterField('status', e.target.value)}
          >
            {COUNTER_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </FormField>
          <FormField
            id="counter-description"
            label={t('om.description', 'Description')}
            value={counterForm.description}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setCounterField('description', e.target.value)}
          />

          <div className="sm:col-span-2 flex flex-col gap-1.5">
            <span className="text-sm font-semibold text-ink">{t('od.counterServices', 'Services served')}</span>
            {services.length === 0 ? (
              <p className="m-0 text-[13px] text-ink-2">{t('od.noServicesForCounter', 'Add services in the Services tab first.')}</p>
            ) : (
              <div className="grid gap-1.5 sm:grid-cols-2">
                {services.map((service) => {
                  const active = counterForm.service_ids.includes(service.id)
                  return (
                    <label key={service.id} className={`flex items-center gap-2 rounded-md border px-3 py-2 text-sm cursor-pointer min-h-[42px] ${active ? 'border-brand bg-brand-soft' : 'border-line hover:bg-surface2'}`}>
                      <input type="checkbox" checked={active} onChange={() => toggleCounterService(service.id)} className="accent-brand" />
                      <span className="min-w-0 truncate text-ink font-medium">{service.name}</span>
                    </label>
                  )
                })}
              </div>
            )}
          </div>
        </form>
      </Modal>

      <Modal
        open={serviceModal}
        onClose={() => (savingService ? undefined : setServiceModal(false))}
        title={editingService ? t('od.editService', 'Edit service') : t('od.addService', 'Add service')}
        description={editingService ? editingService.name : t('od.serviceHint', 'Services let citizens book a slot and let GPS recommend this office.')}
        label="service-form"
        footer={
          <>
            <Button variant="secondary" onClick={() => setServiceModal(false)} disabled={savingService}>
              {t('common.cancel', 'Cancel')}
            </Button>
            <Button loading={savingService} onClick={() => void submitService()} icon={<Check size={16} />}>
              {editingService ? t('om.save', 'Save changes') : t('od.addService', 'Add service')}
            </Button>
          </>
        }
      >
        <form
          className="grid gap-4 sm:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault()
            void submitService()
          }}
          noValidate
        >
          <FormField
            id="service-name"
            label={t('od.serviceName', 'Service name')}
            value={serviceForm.name}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setServiceField('name', e.target.value)}
            placeholder={t('od.serviceNamePlaceholder', 'e.g. Income Certificate')}
            error={serviceErrors.name}
            className="sm:col-span-2"
            required
          />
          <FormField
            id="service-code"
            label={t('od.serviceCode', 'Code')}
            value={serviceForm.code}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setServiceField('code', e.target.value)}
            placeholder="income-cert"
            disabled={!!editingService}
            hint={editingService ? t('od.serviceCodeLocked', 'Codes cannot be changed.') : t('od.serviceCodeHint', 'Optional. Auto-generated from the name if left blank.')}
          />
          <FormField
            id="service-avg"
            label={t('od.avgServiceMin', 'Average handling time (min)')}
            type="number"
            min={1}
            max={120}
            step="0.1"
            value={serviceForm.average_service_min}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setServiceField('average_service_min', e.target.value)}
            error={serviceErrors.average_service_min}
          />
          <FormField
            id="service-department"
            label={t('om.department', 'Department')}
            as="select"
            value={serviceForm.department_id}
            onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setServiceField('department_id', e.target.value)}
            error={serviceErrors.department}
          >
            {departments.map((d) => <option key={d.id} value={String(d.id)}>{d.name}</option>)}
            {!editingService && <option value="__new__">{t('od.newDepartmentOption', '＋ New department…')}</option>}
          </FormField>
          {serviceForm.department_id === '__new__' && (
            <FormField
              id="service-new-department"
              label={t('od.newDepartment', 'New department name')}
              value={serviceForm.new_department}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setServiceField('new_department', e.target.value)}
              placeholder={t('od.newDepartmentPlaceholder', 'e.g. Revenue Department')}
              error={serviceErrors.department}
            />
          )}
          <FormField
            id="service-description"
            label={t('om.description', 'Description')}
            as="textarea"
            value={serviceForm.description}
            onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setServiceField('description', e.target.value)}
            placeholder={t('od.serviceDescriptionPlaceholder', 'What this service covers')}
            className="sm:col-span-2"
          />
          <FormField
            id="service-documents"
            label={t('od.serviceDocuments', 'Required documents')}
            as="textarea"
            value={serviceForm.documents}
            onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setServiceField('documents', e.target.value)}
            placeholder={t('od.serviceDocumentsPlaceholder', 'Aadhaar card\nAddress proof')}
            hint={t('od.serviceDocumentsHint', 'One document per line (commas also work).')}
            className="sm:col-span-2"
          />
          <label className="sm:col-span-2 flex items-center gap-2 rounded-md border border-line px-3 py-2.5 text-sm cursor-pointer min-h-[44px]">
            <input
              type="checkbox"
              checked={serviceForm.is_active}
              onChange={(e) => setServiceField('is_active', e.target.checked)}
              className="accent-brand"
            />
            <span className="text-ink font-medium">{t('od.serviceActiveLabel', 'Service is active and bookable')}</span>
          </label>
        </form>
      </Modal>
    </Page>
  )
}

function MetricCard({ label, value }: { label: string; value: number }) {
  return (
    <article className="bg-surface border border-line rounded-md shadow-card p-4 flex flex-col gap-1">
      <span className="text-[11px] font-bold uppercase tracking-[0.08em] text-ink-3">{label}</span>
      <b className="text-[1.6rem] leading-none font-bold text-ink tabular-nums">{value}</b>
    </article>
  )
}

function DetailRow({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="flex items-start gap-2.5">
      <span className="text-brand mt-0.5 shrink-0" aria-hidden>{icon}</span>
      <div className="min-w-0">
        <dt className="text-[11px] font-bold uppercase tracking-[0.08em] text-ink-3">{label}</dt>
        <dd className="m-0 text-[13px] text-ink break-words">{value}</dd>
      </div>
    </div>
  )
}
