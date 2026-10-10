import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Building2, Check, LayoutGrid, MapPin, Pencil, Plus, Power, Search, Server, Users,
} from 'lucide-react'
import {
  Badge,
  Button,
  Card,
  EmptyState,
  FormField,
  Modal,
  Page,
  SegmentedControl,
  Skeleton,
  useToast,
} from '../components/ui'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import type { AdminOffice, OfficeInput } from '../lib/types'

const DAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'] as const

type StatusFilter = 'all' | 'active' | 'inactive'

type OfficeFormState = {
  code: string
  name: string
  address: string
  city: string
  state: string
  pincode: string
  contact_email: string
  contact_phone: string
  description: string
  open_time: string
  close_time: string
  working_days: string[]
  latitude: string
  longitude: string
}

const EMPTY_FORM: OfficeFormState = {
  code: '',
  name: '',
  address: '',
  city: '',
  state: '',
  pincode: '',
  contact_email: '',
  contact_phone: '',
  description: '',
  open_time: '09:30',
  close_time: '18:00',
  working_days: ['mon', 'tue', 'wed', 'thu', 'fri', 'sat'],
  latitude: '',
  longitude: '',
}

function formFromOffice(office: AdminOffice): OfficeFormState {
  return {
    code: office.code,
    name: office.name,
    address: office.address,
    city: office.city,
    state: office.state,
    pincode: office.pincode,
    contact_email: office.contact_email,
    contact_phone: office.contact_phone,
    description: office.description,
    open_time: office.open_time || '09:30',
    close_time: office.close_time || '18:00',
    working_days: (office.working_days || 'mon,tue,wed,thu,fri,sat').split(',').map((d) => d.trim()).filter(Boolean),
    latitude: office.latitude != null ? String(office.latitude) : '',
    longitude: office.longitude != null ? String(office.longitude) : '',
  }
}

export default function OfficeManagementPage() {
  const { user } = useAuth()
  const { t } = useI18n()
  const toast = useToast()

  const [offices, setOffices] = useState<AdminOffice[]>([])
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState<StatusFilter>('all')

  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<AdminOffice | null>(null)
  const [form, setForm] = useState<OfficeFormState>(EMPTY_FORM)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [statusBusy, setStatusBusy] = useState<number | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params: { search?: string; status?: 'active' | 'inactive' } = {}
      if (query.trim()) params.search = query.trim()
      if (status !== 'all') params.status = status
      setOffices(await api.adminOffices(params))
    } catch (err) {
      toast.error(t('om.loadFailed', 'Could not load offices'), (err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [query, status, t, toast])

  useEffect(() => {
    const id = window.setTimeout(() => void load(), 250)
    return () => window.clearTimeout(id)
  }, [load])

  const openCreate = () => {
    setEditing(null)
    setForm(EMPTY_FORM)
    setErrors({})
    setModalOpen(true)
  }

  const openEdit = (office: AdminOffice) => {
    setEditing(office)
    setForm(formFromOffice(office))
    setErrors({})
    setModalOpen(true)
  }

  const setField = (key: keyof OfficeFormState, value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  const toggleDay = (day: string) => {
    setForm((prev) => ({
      ...prev,
      working_days: prev.working_days.includes(day)
        ? prev.working_days.filter((d) => d !== day)
        : [...prev.working_days, day],
    }))
  }

  const validate = (): boolean => {
    const errs: Record<string, string> = {}
    if (!form.name.trim()) errs.name = t('err.required', 'This field is required.')
    if (!editing && !form.code.trim()) errs.code = t('err.required', 'This field is required.')
    if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(form.open_time)) errs.open_time = t('om.timeFormat', 'Use HH:MM (24-hour).')
    if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(form.close_time)) errs.close_time = t('om.timeFormat', 'Use HH:MM (24-hour).')
    if (form.open_time >= form.close_time) errs.close_time = t('om.hoursOrder', 'Closing time must be after opening time.')
    if (form.contact_email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.contact_email.trim())) errs.contact_email = t('err.invalidEmail', 'Enter a valid email address.')
    if (form.pincode && !/^\d{4,12}$/.test(form.pincode.trim())) errs.pincode = t('om.pincodeFormat', 'PIN code must be 4-12 digits.')
    if (form.working_days.length === 0) errs.working_days = t('om.daysRequired', 'Pick at least one working day.')
    if (form.latitude && Number.isNaN(Number(form.latitude))) errs.latitude = t('om.numberInvalid', 'Enter a valid number.')
    if (form.longitude && Number.isNaN(Number(form.longitude))) errs.longitude = t('om.numberInvalid', 'Enter a valid number.')
    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  const submit = async () => {
    if (!validate()) return
    setBusy(true)
    try {
      const payload: OfficeInput = {
        code: form.code.trim(),
        name: form.name.trim(),
        address: form.address.trim(),
        city: form.city.trim(),
        state: form.state.trim(),
        pincode: form.pincode.trim(),
        contact_email: form.contact_email.trim(),
        contact_phone: form.contact_phone.trim(),
        description: form.description.trim(),
        open_time: form.open_time,
        close_time: form.close_time,
        working_days: form.working_days,
        latitude: form.latitude ? Number(form.latitude) : null,
        longitude: form.longitude ? Number(form.longitude) : null,
      }
      if (editing) {
        const { code: _code, ...update } = payload
        const result = await api.adminUpdateOffice(editing.id, update)
        toast.success(t('om.updated', 'Office updated'), result.name)
      } else {
        const result = await api.adminCreateOffice(payload)
        toast.success(t('om.created', 'Office created'), result.name)
      }
      setModalOpen(false)
      await load()
    } catch (err) {
      toast.error(t('admin.actionFailed', 'That did not work'), (err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const toggleStatus = async (office: AdminOffice) => {
    setStatusBusy(office.id)
    try {
      const result = await api.adminSetOfficeStatus(office.id, !office.is_active)
      setOffices((prev) => prev.map((o) => (o.id === result.id ? result : o)))
      toast.success(
        result.is_active ? t('om.activated', 'Office activated') : t('om.deactivated', 'Office deactivated'),
        result.name,
      )
    } catch (err) {
      toast.error(t('admin.actionFailed', 'That did not work'), (err as Error).message)
    } finally {
      setStatusBusy(null)
    }
  }

  const segments = useMemo(
    () => [
      { value: 'all' as StatusFilter, label: t('om.filterAll', 'All') },
      { value: 'active' as StatusFilter, label: t('om.filterActive', 'Active') },
      { value: 'inactive' as StatusFilter, label: t('om.filterInactive', 'Inactive') },
    ],
    [t],
  )

  if (!user || user.role !== 'ADMIN') {
    return (
      <Page title={t('om.title', 'Office management')}>
        <p className="text-sm text-ink-2">{t('om.notAdmin', 'Only administrators can manage offices.')}</p>
      </Page>
    )
  }

  return (
    <Page
      kicker={t('om.kicker', 'Network · Offices')}
      title={t('om.title', 'Office management')}
      actions={<Button icon={<Plus size={16} />} onClick={openCreate}>{t('om.addOffice', 'Add office')}</Button>}
    >
      <p className="text-sm text-ink-2 mt-0 mb-5 max-w-3xl">
        {t('om.subtitle', 'Create offices and keep their address, hours and location pin accurate so queues and travel estimates stay correct.')}
      </p>

      <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
        <label className="relative block flex-1 min-w-[220px] max-w-md">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-3 pointer-events-none" aria-hidden />
          <span className="sr-only">{t('sm.search', 'Search')}</span>
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('om.searchPlaceholder', 'Search by name, code or city')}
            className="w-full rounded-md border border-line bg-surface pl-9 pr-3.5 py-2.5 text-[15px] text-ink placeholder:text-ink-3 min-h-[44px] focus:outline-none focus:ring-2 focus:border-brand focus:ring-brand/25"
          />
        </label>
        <SegmentedControl options={segments} value={status} onChange={setStatus} label={t('om.statusFilter', 'Filter by status')} />
      </div>

      {loading && !offices.length ? (
        <Skeleton lines={4} />
      ) : offices.length === 0 ? (
        <EmptyState
          icon={<Building2 size={22} />}
          title={query || status !== 'all' ? t('om.noResults', 'No offices match your filters.') : t('om.none', 'No offices yet')}
          hint={query || status !== 'all' ? t('om.noResultsHint', 'Try a different search or status.') : t('om.noneHint', 'Add the first office to get started.')}
          action={<Button icon={<Plus size={16} />} onClick={openCreate}>{t('om.addOffice', 'Add office')}</Button>}
        />
      ) : (
        <ul className="m-0 p-0 list-none grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {offices.map((office) => (
            <li key={office.id} className="bg-surface border border-line rounded-md shadow-card p-4 flex flex-col gap-3">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="m-0 text-[15px] font-bold text-ink truncate">{office.name}</p>
                  <p className="m-0 mt-0.5 text-[13px] text-ink-2 truncate">
                    <span className="font-mono">{office.code}</span>
                    {office.city ? ` · ${office.city}` : ''}
                    {office.state ? `, ${office.state}` : ''}
                  </p>
                </div>
                <Badge tone={office.is_active ? 'ok' : 'alert'}>
                  {office.is_active ? <Check size={12} aria-hidden /> : <Power size={12} aria-hidden />}
                  {office.is_active ? t('om.active', 'Active') : t('om.inactive', 'Inactive')}
                </Badge>
              </div>

              <div className="flex flex-wrap items-center gap-1.5">
                <Badge tone="neutral"><LayoutGrid size={12} aria-hidden /> {t('om.servicesN', '{n} services').replace('{n}', String(office.services_count))}</Badge>
                <Badge tone="neutral"><Server size={12} aria-hidden /> {t('om.countersN', '{n} counters').replace('{n}', String(office.counters_count))}</Badge>
                <Badge tone="neutral"><Users size={12} aria-hidden /> {t('om.staffN', '{n} staff').replace('{n}', String(office.staff_count))}</Badge>
              </div>

              <p className="m-0 text-[12px] text-ink-2 flex items-center gap-1.5">
                <MapPin size={13} aria-hidden className={office.has_coordinates ? 'text-ok' : 'text-ink-3'} />
                {office.has_coordinates
                  ? t('om.pinned', 'Location pinned')
                  : t('om.notPinned', 'No location pin yet')}
                {office.open_time && office.close_time ? <span className="text-ink-3">· {office.open_time}–{office.close_time}</span> : null}
              </p>

              <div className="mt-auto flex flex-wrap items-center gap-2">
                <Link
                  to={`/admin/offices/${office.id}`}
                  className="inline-flex items-center justify-center gap-2 rounded-md border border-line bg-surface px-3 py-1.5 text-xs font-bold text-brand hover:bg-brand-soft hover:border-brand/35 shadow-sm transition-all active:scale-[0.985] min-h-[34px]"
                >
                  <Building2 size={14} aria-hidden /> {t('om.open', 'Open')}
                </Link>
                <Button size="sm" variant="secondary" icon={<Pencil size={14} />} onClick={() => openEdit(office)}>
                  {t('om.edit', 'Edit')}
                </Button>
                <Button
                  size="sm"
                  variant={office.is_active ? 'dangerGhost' : 'outline'}
                  loading={statusBusy === office.id}
                  icon={<Power size={14} />}
                  onClick={() => void toggleStatus(office)}
                >
                  {office.is_active ? t('om.deactivate', 'Deactivate') : t('om.activate', 'Activate')}
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <Modal
        open={modalOpen}
        onClose={() => (busy ? undefined : setModalOpen(false))}
        title={editing ? t('om.editTitle', 'Edit office') : t('om.createTitle', 'Add office')}
        description={editing ? editing.name : t('om.createHint', 'Offices group the services, counters and staff for one location.')}
        label="office-form"
        footer={
          <>
            <Button variant="secondary" onClick={() => setModalOpen(false)} disabled={busy}>
              {t('common.cancel', 'Cancel')}
            </Button>
            <Button loading={busy} onClick={() => void submit()} icon={<Check size={16} />}>
              {editing ? t('om.save', 'Save changes') : t('om.create', 'Create office')}
            </Button>
          </>
        }
      >
        <form
          className="grid gap-4 sm:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault()
            void submit()
          }}
          noValidate
        >
          <FormField
            id="office-code"
            label={t('om.code', 'Office code')}
            value={form.code}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setField('code', e.target.value)}
            placeholder="RJ-CIVIL-01"
            error={errors.code}
            disabled={!!editing}
            hint={editing ? t('om.codeImmutable', 'The code cannot be changed.') : undefined}
            required
          />
          <FormField
            id="office-name"
            label={t('om.name', 'Office name')}
            value={form.name}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setField('name', e.target.value)}
            placeholder="Rajkot Civil Registrar Office"
            error={errors.name}
            required
          />
          <FormField
            id="office-address"
            label={t('om.address', 'Address')}
            value={form.address}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setField('address', e.target.value)}
            placeholder="Near Kalavad Road"
            className="sm:col-span-2"
          />
          <FormField
            id="office-city"
            label={t('om.city', 'City')}
            value={form.city}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setField('city', e.target.value)}
            placeholder="Rajkot"
          />
          <FormField
            id="office-state"
            label={t('om.state', 'State')}
            value={form.state}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setField('state', e.target.value)}
            placeholder="Gujarat"
          />
          <FormField
            id="office-pincode"
            label={t('om.pincode', 'PIN code')}
            value={form.pincode}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setField('pincode', e.target.value)}
            placeholder="360004"
            inputMode="numeric"
            error={errors.pincode}
          />
          <FormField
            id="office-phone"
            label={t('om.phone', 'Contact phone')}
            value={form.contact_phone}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setField('contact_phone', e.target.value)}
            placeholder="+91 281 222 0000"
          />
          <FormField
            id="office-email"
            label={t('om.email', 'Contact email')}
            type="email"
            value={form.contact_email}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setField('contact_email', e.target.value)}
            placeholder="office@gov.in"
            error={errors.contact_email}
          />
          <FormField
            id="office-open"
            label={t('om.openTime', 'Opening time')}
            type="time"
            value={form.open_time}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setField('open_time', e.target.value)}
            error={errors.open_time}
          />
          <FormField
            id="office-close"
            label={t('om.closeTime', 'Closing time')}
            type="time"
            value={form.close_time}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setField('close_time', e.target.value)}
            error={errors.close_time}
          />
          <FormField
            id="office-lat"
            label={t('admin.latitude', 'Latitude')}
            value={form.latitude}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setField('latitude', e.target.value)}
            placeholder="22.3039"
            inputMode="decimal"
            error={errors.latitude}
          />
          <FormField
            id="office-lng"
            label={t('admin.longitude', 'Longitude')}
            value={form.longitude}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setField('longitude', e.target.value)}
            placeholder="70.8022"
            inputMode="decimal"
            error={errors.longitude}
          />

          <div className="sm:col-span-2 flex flex-col gap-1.5">
            <span className="text-sm font-semibold text-ink">{t('om.workingDays', 'Working days')}</span>
            <div className="flex flex-wrap gap-1.5">
              {DAYS.map((day) => {
                const active = form.working_days.includes(day)
                return (
                  <button
                    key={day}
                    type="button"
                    aria-pressed={active}
                    onClick={() => toggleDay(day)}
                    className={`rounded-md border px-3 py-1.5 text-xs font-bold uppercase tracking-wide transition-colors min-h-[34px] ${
                      active ? 'bg-brand text-white border-brand' : 'border-line text-ink-2 hover:bg-surface2'
                    }`}
                  >
                    {day}
                  </button>
                )
              })}
            </div>
            {errors.working_days && <small role="alert" className="text-[13px] font-medium text-alert">{errors.working_days}</small>}
          </div>

          <FormField
            id="office-description"
            label={t('om.description', 'Description')}
            as="textarea"
            value={form.description}
            onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setField('description', e.target.value)}
            placeholder={t('om.descriptionPlaceholder', 'What citizens can do here')}
            className="sm:col-span-2"
          />
        </form>
      </Modal>
    </Page>
  )
}
