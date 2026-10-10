import { useEffect, useState } from 'react'
import { Building2, CalendarPlus, MapPin, Save, Trash2 } from 'lucide-react'
import { Badge, Button, Card, EmptyState, FormField, useToast } from '../../components/ui'
import { api } from '../../lib/api'
import { useI18n } from '../../lib/i18n'
import { useOffice } from '../../lib/office'
import type { Json } from './types'

export default function OfficeOperations({ holidays, reload }: { holidays: Json[]; reload: () => Promise<void> }) {
  const { office, reload: reloadOffices } = useOffice()
  const { t } = useI18n()
  const toast = useToast()

  const [scheduleHours, setScheduleHours] = useState('09:30-18:00')
  const [scheduleDays, setScheduleDays] = useState('mon,tue,wed,thu,fri,sat')
  const [arrivalBuffer, setArrivalBuffer] = useState(15)
  const [responseMinutes, setResponseMinutes] = useState(30)
  const [address, setAddress] = useState('')
  const [instructions, setInstructions] = useState('')
  const [holidayDate, setHolidayDate] = useState('')
  const [holidayName, setHolidayName] = useState('Public holiday')
  const [busy, setBusy] = useState('')

  const officeId = office?.id

  useEffect(() => {
    if (!office) return
    setScheduleHours(office.working_hours)
    setScheduleDays(office.working_days)
    setArrivalBuffer(office.arrival_buffer_min ?? 15)
    setResponseMinutes(office.incident_response_min ?? 30)
    setAddress(office.address)
    setInstructions(office.location_instructions ?? '')
  }, [office?.id])

  const guard = async (key: string, fn: () => Promise<void>, ok: string) => {
    setBusy(key)
    try {
      await fn()
      await reloadOffices()
      await reload()
      toast.success(ok)
    } catch (err) {
      toast.error(t('admin.actionFailed', 'That did not work'), (err as Error).message)
    } finally {
      setBusy('')
    }
  }

  const saveSchedule = () =>
    guard('schedule', async () => {
      if (!officeId) return
      await api.updateOfficeSchedule(officeId, {
        working_hours: scheduleHours,
        working_days: scheduleDays,
        arrival_buffer_min: arrivalBuffer,
        incident_response_min: responseMinutes,
      })
    }, t('admin.scheduleSaved', 'Office hours and response policy saved.'))

  const saveLocation = () =>
    guard('location', async () => {
      if (!officeId) return
      await api.updateOfficeLocation(officeId, address, instructions)
    }, t('admin.locationSaved', 'Office location updated. Active citizens were notified.'))

  const addHoliday = () =>
    guard('holiday', async () => {
      if (!officeId || !holidayDate) return
      await api.addOfficeHoliday(officeId, holidayDate, holidayName)
      setHolidayDate('')
    }, t('admin.holidayAdded', 'Office holiday added.'))

  const removeHoliday = (id: number) =>
    guard(`del-${id}`, async () => {
      if (!officeId) return
      await api.deleteOfficeHoliday(officeId, id)
    }, t('admin.holidayRemoved', 'Office holiday removed.'))

  return (
    <div className="grid xl:grid-cols-2 gap-4">
      <Card kicker={t('admin.offices', 'Office operations')} title={office?.name ?? ''}>
        <div className="flex flex-col gap-4">
          <div className="rounded-md border border-line bg-surface2 p-3 flex items-start gap-3">
            <Building2 size={18} className="text-brand mt-0.5 shrink-0" aria-hidden />
            <p className="text-[13px] text-ink-2 m-0">
              {t('admin.scheduleHint', 'These hours shape the wait estimates citizens see. Set them before the office opens.')}
            </p>
          </div>

          <FormField
            id="working-hours"
            label={t('admin.workingHours', 'Working hours')}
            value={scheduleHours}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setScheduleHours(e.target.value)}
            placeholder="09:30-18:00"
            hint={t('admin.workingHoursHint', 'Use a start-end format, e.g. 09:30-18:00')}
          />
          <FormField
            id="working-days"
            label={t('admin.workingDays', 'Working days')}
            value={scheduleDays}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setScheduleDays(e.target.value)}
            hint={t('admin.workingDaysHint', 'Comma separated, e.g. mon,tue,wed,thu,fri')}
          />
          <div className="grid sm:grid-cols-2 gap-4">
            <FormField
              id="arrival-buffer"
              label={t('admin.arrivalBuffer', 'Arrival buffer (minutes)')}
              type="number"
              min={0}
              max={240}
              value={arrivalBuffer}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setArrivalBuffer(Number(e.target.value))}
            />
            <FormField
              id="response-minutes"
              label={t('admin.responseMinutes', 'Incident response deadline (minutes)')}
              type="number"
              min={5}
              max={1440}
              value={responseMinutes}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setResponseMinutes(Number(e.target.value))}
            />
          </div>
          <Button onClick={() => void saveSchedule()} loading={busy === 'schedule'} icon={<Save size={16} />}>
            {t('admin.saveSchedule', 'Save office schedule')}
          </Button>
        </div>
      </Card>

      <div className="flex flex-col gap-4">
        <Card kicker={t('admin.location', 'Location')} title={t('admin.locationTitle', 'Address and directions')}>
          <div className="flex flex-col gap-4">
            <FormField
              id="office-address"
              label={t('admin.address', 'Office address')}
              value={address}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setAddress(e.target.value)}
              autoComplete="street-address"
            />
            <FormField
              id="office-instructions"
              label={t('admin.instructions', 'Building / counter directions')}
              value={instructions}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setInstructions(e.target.value)}
              hint={t('admin.instructionsHint', 'Plain-language directions, e.g. “Second floor, counter 4”.')}
            />
            <Button variant="secondary" onClick={() => void saveLocation()} loading={busy === 'location'} icon={<MapPin size={16} />}>
              {t('admin.saveLocation', 'Update location and notify active citizens')}
            </Button>
          </div>
        </Card>

        <Card kicker={t('admin.holidays', 'Holidays')} title={t('admin.holidaysTitle', 'Closed days')}>
          <div className="flex flex-col gap-4">
            <div className="grid sm:grid-cols-[1fr_1fr_auto] gap-3 sm:items-end">
              <FormField
                id="holiday-date"
                label={t('admin.holidayDate', 'Holiday date')}
                type="date"
                value={holidayDate}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setHolidayDate(e.target.value)}
              />
              <FormField
                id="holiday-name"
                label={t('admin.holidayName', 'Holiday name')}
                value={holidayName}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setHolidayName(e.target.value)}
              />
              <Button
                variant="secondary"
                onClick={() => void addHoliday()}
                loading={busy === 'holiday'}
                disabled={!holidayDate}
                icon={<CalendarPlus size={16} />}
              >
                {t('admin.addHoliday', 'Add holiday')}
              </Button>
            </div>

            {holidays.length === 0 ? (
              <EmptyState title={t('admin.noHolidays', 'No closed days set')} hint={t('admin.noHolidaysHint', 'Add public holidays so citizens are not sent on a closed day.')} />
            ) : (
              <ul className="m-0 p-0 list-none flex flex-col gap-2">
                {holidays.map((day) => (
                  <li key={String(day.id)} className="flex items-center justify-between gap-3 rounded-md border border-line px-3 py-2.5">
                    <span className="text-sm text-ink">
                      <b>{String(day.holiday_date)}</b> · {String(day.name)}
                    </span>
                    <Button
                      variant="dangerGhost"
                      size="sm"
                      loading={busy === `del-${String(day.id)}`}
                      onClick={() => void removeHoliday(Number(day.id))}
                      icon={<Trash2 size={15} />}
                    >
                      {t('admin.remove', 'Remove')}
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Card>
      </div>

      <p className="text-[12px] text-ink-3 sm:col-span-2 m-0">
        <Badge tone="neutral">{t('admin.tip', 'Tip')}</Badge>{' '}
        {t('admin.schedulePrivacy', 'Changing hours or location emails citizens who hold an active token for this office.')}
      </p>
    </div>
  )
}
