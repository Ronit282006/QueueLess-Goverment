import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { CheckCircle2, ClipboardList, RefreshCw, Save, Search, SlidersHorizontal, Users } from 'lucide-react'
import {
  Badge,
  Button,
  Card,
  EmptyState,
  FormField,
  Page,
  Skeleton,
  useToast,
} from '../components/ui'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import { useOffice } from '../lib/office'
import type { AdminCounter, StaffAssignment, StaffMember } from '../lib/types'

export default function CounterAssignmentsPage() {
  const { user } = useAuth()
  const { t } = useI18n()
  const { office, offices, setOfficeId } = useOffice()
  const toast = useToast()
  const [searchParams, setSearchParams] = useSearchParams()

  const [members, setMembers] = useState<StaffMember[]>([])
  const [counters, setCounters] = useState<AdminCounter[]>([])
  const [assignments, setAssignments] = useState<StaffAssignment[]>([])
  const [selectedStaff, setSelectedStaff] = useState<number | null>(() => Number(searchParams.get('staff')) || null)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [title, setTitle] = useState('Service Officer')
  const [shiftStart, setShiftStart] = useState('09:30')
  const [shiftEnd, setShiftEnd] = useState('18:00')
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)

  const officeId = office?.id

  const officeAssignments = useMemo(() => assignments.filter((a) => a.office_id === officeId), [assignments, officeId])
  const assignedSet = useMemo(
    () => new Set(officeAssignments.map((a) => a.counter_id).filter((id): id is number => id !== null)),
    [officeAssignments],
  )

  const officeName = (id: number) => offices.find((o) => o.id === id)?.name ?? `Office #${id}`

  const loadMembers = useCallback(async () => {
    try {
      setMembers(await api.adminStaff())
    } catch (err) {
      toast.error(t('admin.actionFailed', 'That did not work'), (err as Error).message)
    }
  }, [t, toast])

  const loadCounters = useCallback(async () => {
    if (!officeId) return
    try {
      setCounters(await api.adminCounters(officeId))
    } catch (err) {
      toast.error(t('admin.actionFailed', 'That did not work'), (err as Error).message)
    }
  }, [officeId, t, toast])

  const loadAssignments = useCallback(async () => {
    if (!selectedStaff) return
    try {
      setAssignments(await api.adminStaffAssignments(selectedStaff))
    } catch (err) {
      toast.error(t('admin.actionFailed', 'That did not work'), (err as Error).message)
    }
  }, [selectedStaff, t, toast])

  useEffect(() => {
    void loadMembers().finally(() => setLoading(false))
  }, [loadMembers])
  useEffect(() => {
    void loadCounters()
  }, [loadCounters])
  useEffect(() => {
    void loadAssignments()
  }, [loadAssignments])

  useEffect(() => {
    if (!selectedStaff || !officeId || loading) return
    const member = members.find((m) => m.id === selectedStaff)
    if (member) {
      const here = member.assignments.find((a) => a.office_id === officeId)
      setTitle((here?.title || member.assignments[0]?.title || 'Service Officer'))
      setShiftStart(here?.shift_start || member.assignments[0]?.shift_start || '09:30')
      setShiftEnd(here?.shift_end || member.assignments[0]?.shift_end || '18:00')
    }
    setSelected(new Set(assignedSet))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedStaff, officeId, members, assignments])

  useEffect(() => {
    const staffId = searchParams.get('staff')
    const officeParam = searchParams.get('office')
    if (staffId && Number(staffId) !== selectedStaff) setSelectedStaff(Number(staffId))
    if (officeParam && officeParam !== '' && Number(officeParam) !== officeId) setOfficeId(Number(officeParam))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams])

  const filteredMembers = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return members
    return members.filter((m) => m.full_name.toLowerCase().includes(q) || m.email.toLowerCase().includes(q))
  }, [members, query])

  if (!user || user.role !== 'ADMIN') {
    return (
      <Page title={t('ca.title', 'Counter assignments')}>
        <p className="text-sm text-ink-2">{t('ca.notAdmin', 'Only administrators can edit counter assignments.')}</p>
      </Page>
    )
  }

  const selectStaff = (id: number) => {
    setSelectedStaff(id)
    setSearchParams({ staff: String(id), office: office ? String(office.id) : '' })
  }

  const toggle = (counterId: number) => {
    setSelected((current) => {
      const next = new Set(current)
      if (next.has(counterId)) next.delete(counterId)
      else next.add(counterId)
      return next
    })
  }

  const save = async () => {
    if (!selectedStaff || !officeId) return
    setBusy(true)
    try {
      await api.adminSetStaffAssignments(selectedStaff, {
        office_id: officeId,
        counter_ids: [...selected].sort((a, b) => a - b),
        title,
        shift_start: shiftStart,
        shift_end: shiftEnd,
      })
      await loadAssignments()
      toast.success(
        t('ca.saved', 'Assignments saved'),
        t('ca.savedBody', 'Saved for {name}.').replace('{name}', members.find((m) => m.id === selectedStaff)?.full_name ?? ''),
      )
    } catch (err) {
      toast.error(t('admin.actionFailed', 'That did not work'), (err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const groupedAssignments = useMemo(() => {
    const map = new Map<number, StaffAssignment[]>()
    for (const a of assignments) {
      const list = map.get(a.office_id) ?? []
      list.push(a)
      map.set(a.office_id, list)
    }
    return [...map.entries()]
  }, [assignments])

  const selectedMember = members.find((m) => m.id === selectedStaff)

  if (loading && !members.length) {
    return (
      <Page kicker={t('ca.kicker', 'Counter control')} title={t('ca.title', 'Counter assignments')}>
        <Skeleton lines={5} />
      </Page>
    )
  }

  return (
    <Page kicker={`${t('ca.kicker', 'Counter control')} · ${office?.name ?? ''}`} title={t('ca.title', 'Counter assignments')}>
      <p className="text-sm text-ink-2 mt-0 mb-5 max-w-3xl">
        {t('ca.hint', 'Pick a staff member, then tick the counters they can operate this shift. Staff only see the counters you assign here.')}
      </p>

      <div className="grid lg:grid-cols-[minmax(280px,360px)_1fr] gap-5 items-start">
        {/* Master: staff list */}
        <Card kicker={t('ca.staffCol', 'Staff member')} title={t('ca.chooseStaff', 'Choose staff')} bodyClassName="pt-3">
          {members.length === 0 ? (
            <EmptyState
              icon={<ClipboardList size={22} />}
              title={t('ca.noStaff', 'No staff members yet. Add them in Staff management.')}
              action={
                <Link to="/admin/staff" className="inline-flex items-center gap-2 rounded-md bg-brand border border-brand/90 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-brand-strong transition-all active:scale-[0.985]">
                  {t('sm.createTitle', 'Add a staff member')}
                </Link>
              }
            />
          ) : (
            <>
              <label className="relative block mb-3">
                <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-3 pointer-events-none" aria-hidden />
                <span className="sr-only">{t('ca.searchStaff', 'Search staff')}</span>
                <input
                  type="search"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder={t('ca.searchStaff', 'Search staff')}
                  className="w-full rounded-md border border-line bg-surface pl-9 pr-3.5 py-2.5 text-[15px] text-ink placeholder:text-ink-3 min-h-[44px] focus:outline-none focus:ring-2 focus:border-brand focus:ring-brand/25"
                />
              </label>
              {filteredMembers.length === 0 ? (
                <EmptyState icon={<Search size={22} />} title={t('ca.noSearch', 'No staff found.')} />
              ) : (
                <ul className="m-0 p-0 list-none flex flex-col gap-1.5 max-h-[60vh] overflow-y-auto">
                  {filteredMembers.map((member) => {
                    const active = selectedStaff === member.id
                    return (
                      <li key={member.id}>
                        <button
                          type="button"
                          onClick={() => selectStaff(member.id)}
                          aria-pressed={active}
                          className={`w-full text-left rounded-md border px-3.5 py-2.5 flex items-center justify-between gap-3 min-h-[56px] transition-colors ${
                            active ? 'border-brand bg-brand-soft' : 'border-line hover:bg-surface2'
                          }`}
                        >
                          <span className="min-w-0">
                            <b className="block text-sm text-ink truncate">{member.full_name}</b>
                            <span className="block text-[12px] text-ink-2 truncate">{member.email}</span>
                          </span>
                          <Badge tone={member.counters.length ? 'ok' : 'warn'}>
                            {t('sm.counters', '{n} counter(s)').replace('{n}', String(member.counters.length))}
                          </Badge>
                        </button>
                      </li>
                    )
                  })}
                </ul>
              )}
            </>
          )}
        </Card>

        {/* Detail */}
        <div className="min-w-0">
          {!selectedStaff || !officeId ? (
            <Card>
              <EmptyState
                icon={<Users size={22} />}
                title={t('ca.pickFirst', 'Pick a staff member to assign counters')}
                hint={t('ca.pickFirstHint', 'Their counters for this office will appear here.')}
              />
            </Card>
          ) : (
            <div className="flex flex-col gap-5">
              <Card
                kicker={t('ca.title', 'Counter assignments')}
                title={t('ca.countersFor', 'Counters for {name}').replace('{name}', selectedMember?.full_name ?? '')}
                action={
                  <Button variant="secondary" size="sm" onClick={() => void loadCounters()} icon={<RefreshCw size={14} />}>
                    {t('common.refresh', 'Refresh')}
                  </Button>
                }
              >
                {counters.length === 0 ? (
                  <EmptyState icon={<SlidersHorizontal size={22} />} title={t('ca.noCounters', 'No counters to assign yet. Create an office first.')} />
                ) : (
                  <>
                    <div className="flex items-center justify-between mb-3">
                      <p className="text-[13px] text-ink-2 m-0">
                        {t('ca.selected', '{n} selected').replace('{n}', String(selected.size))}
                      </p>
                      <div className="flex gap-2">
                        <button type="button" className="text-[13px] font-semibold text-brand hover:underline" onClick={() => setSelected(new Set(counters.map((c) => c.id)))}>
                          {t('ca.selectAll', 'Select all')}
                        </button>
                        <button type="button" className="text-[13px] font-semibold text-ink-2 hover:underline" onClick={() => setSelected(new Set())}>
                          {t('ca.clearAll', 'Clear')}
                        </button>
                      </div>
                    </div>
                    <ul className="m-0 p-0 list-none grid sm:grid-cols-2 gap-2">
                      {counters.map((counter) => {
                        const checked = selected.has(counter.id)
                        return (
                          <li key={counter.id}>
                            <label
                              className={`flex items-center gap-3 rounded-md border px-3.5 py-3 min-h-[60px] cursor-pointer transition-colors ${
                                checked ? 'border-brand bg-brand-soft' : 'border-line hover:bg-surface2'
                              }`}
                            >
                              <input type="checkbox" checked={checked} onChange={() => toggle(counter.id)} className="w-5 h-5 accent-[color:var(--c-brand)]" />
                              <span className="min-w-0 flex-1">
                                <b className="block text-sm text-ink">
                                  <span className="inline-grid place-items-center min-w-[26px] h-6 px-1.5 rounded bg-surface2 text-[12px] tabular-nums mr-1.5">{counter.number}</span>
                                  {counter.name}
                                </b>
                                <small className="block text-[12px] text-ink-2 truncate mt-0.5">
                                  {counter.staff.length > 0 ? counter.staff.map((s) => s.full_name).join(', ') : t('ca.noStaffOnCounter', 'No staff assigned')}
                                </small>
                              </span>
                              <Badge tone={counter.status === 'BUSY' ? 'warn' : counter.status === 'AVAILABLE' ? 'ok' : 'alert'}>{counter.status}</Badge>
                            </label>
                          </li>
                        )
                      })}
                    </ul>
                  </>
                )}
              </Card>

              <Card kicker={t('ca.details', 'Details')} title={t('ca.settings', 'Assignment settings')}>
                <div className="grid sm:grid-cols-3 gap-4">
                  <FormField
                    id="ca-title"
                    label={t('ca.roleTitle', 'Role title')}
                    value={title}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => setTitle(e.target.value)}
                    maxLength={80}
                  />
                  <FormField
                    id="ca-shift-start"
                    label={t('ca.shiftStart', 'Shift start')}
                    value={shiftStart}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => setShiftStart(e.target.value)}
                    maxLength={10}
                    hint={t('ca.timeHint', 'e.g. 09:30')}
                  />
                  <FormField
                    id="ca-shift-end"
                    label={t('ca.shiftEnd', 'Shift end')}
                    value={shiftEnd}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => setShiftEnd(e.target.value)}
                    maxLength={10}
                    hint={t('ca.timeHint', 'e.g. 09:30')}
                  />
                </div>
              </Card>

              {/* Sticky save bar */}
              <div className="sticky bottom-20 lg:bottom-4 z-20">
                <div className="rounded-md border border-line bg-surface/95 backdrop-blur shadow-pop px-4 py-3 flex flex-wrap items-center justify-between gap-3">
                  <span className="text-sm text-ink-2">
                    {t('ca.selected', '{n} selected').replace('{n}', String(selected.size))} · {office?.name}
                  </span>
                  <Button onClick={() => void save()} loading={busy} icon={<Save size={16} />}>
                    {t('ca.save', 'Save assignments')}
                  </Button>
                </div>
              </div>

              <Card kicker={t('ca.currentState', 'Current state')} title={t('ca.assignedCounters', 'Assigned counters')}>
                {assignments.length === 0 ? (
                  <EmptyState title={t('ca.nothingAssigned', 'Nothing assigned yet')} hint={t('ca.nothingAssignedHint', 'Tick counters above and save.')} />
                ) : (
                  <div className="flex flex-col gap-4">
                    {groupedAssignments.map(([oid, list]) => (
                      <section key={oid}>
                        <h3 className="text-[11px] font-bold uppercase tracking-[0.12em] text-ink-3 m-0 mb-2">{officeName(oid)}</h3>
                        <ul className="m-0 p-0 list-none flex flex-col gap-2">
                          {list.map((a) => (
                            <li key={`${oid}-${a.counter_id}`} className="rounded-md border border-line px-3.5 py-2.5 flex items-center justify-between gap-3">
                              <span className="text-sm text-ink">
                                <b>#{a.counter_id ?? '—'}</b> · {a.title} · {a.shift_start}–{a.shift_end}
                              </span>
                              <Badge tone="ok">
                                <CheckCircle2 size={12} aria-hidden /> {t('ca.assigned', 'Assigned')}
                              </Badge>
                            </li>
                          ))}
                        </ul>
                      </section>
                    ))}
                  </div>
                )}
              </Card>
            </div>
          )}
        </div>
      </div>
    </Page>
  )
}
