import { useState } from 'react'
import { Check, Pencil, Plus, ShieldCheck, X } from 'lucide-react'
import TagPicker from '../../components/TagPicker'
import { Badge, Button, Card, EmptyState, FormField, useToast } from '../../components/ui'
import { api } from '../../lib/api'
import { useI18n } from '../../lib/i18n'
import { CITIZEN_TAG_CODES } from '../../lib/citizenTags'
import type { Json } from './types'

export default function PriorityRules({ rules, officeId, reload }: { rules: Json[]; officeId?: number; reload: () => Promise<void> }) {
  const { t } = useI18n()
  const toast = useToast()
  const [name, setName] = useState('Senior citizens')
  const [selectedTags, setSelectedTags] = useState<string[]>(['senior'])
  const [boost, setBoost] = useState(25)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)

  const reset = () => {
    setEditingId(null)
    setName('Senior citizens')
    setSelectedTags(['senior'])
    setBoost(25)
  }

  const save = async () => {
    if (!name.trim()) {
      toast.error(t('admin.ruleNameRequired', 'Give the rule a name'))
      return
    }
    if (selectedTags.length === 0) {
      toast.error(t('admin.ruleTagsRequired', 'Select at least one citizen category'))
      return
    }
    setBusy(true)
    const payload = { office_id: officeId, name: name.trim(), tags: selectedTags, boost, is_active: true }
    try {
      if (editingId) {
        await api.updatePriorityRule(editingId, payload)
        toast.success(t('admin.ruleUpdated', 'Priority rule updated'))
      } else {
        await api.createPriorityRule(payload)
        toast.success(t('admin.prioritySaved', 'Priority rules updated'))
      }
      reset()
      await reload()
    } catch (err) {
      toast.error(t('admin.actionFailed', 'That did not work'), (err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const toggleActive = async (rule: Json) => {
    setBusy(true)
    try {
      await api.updatePriorityRule(Number(rule.id), {
        office_id: rule.office_id ?? officeId,
        name: String(rule.name),
        tags: (rule.tags as string[]) ?? [],
        boost: Number(rule.boost),
        is_active: !rule.is_active,
      })
      toast.success(rule.is_active ? t('admin.rulePaused', 'Rule paused') : t('admin.ruleResumed', 'Rule resumed'))
      await reload()
    } catch (err) {
      toast.error(t('admin.actionFailed', 'That did not work'), (err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const startEdit = (rule: Json) => {
    const tags = (rule.tags as string[]) ?? []
    setEditingId(Number(rule.id))
    setName(String(rule.name))
    setSelectedTags(tags)
    setBoost(Number(rule.boost))
  }

  const extraTags = selectedTags.filter((tag) => !CITIZEN_TAG_CODES.includes(tag))

  return (
    <div className="grid xl:grid-cols-2 gap-4">
      <Card
        kicker={t('admin.priority', 'Priority rules')}
        title={editingId ? t('admin.editRule', 'Edit rule') : t('admin.addRule', 'Add rule')}
      >
        <div className="flex flex-col gap-4">
          <div className="rounded-md border border-line bg-surface2 p-3 flex items-start gap-3">
            <ShieldCheck size={18} className="text-brand mt-0.5 shrink-0" aria-hidden />
            <p className="text-[13px] text-ink-2 m-0">
              {t('admin.priorityHint', 'Fast-track citizens who need extra help. A boost moves matching tags ahead in the queue.')}
            </p>
          </div>

          <FormField
            id="rule-name"
            label={t('admin.ruleName', 'Rule name')}
            value={name}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setName(e.target.value)}
            autoComplete="off"
          />
          <TagPicker
            id="rule-tags"
            label={t('admin.ruleTags', 'Citizen category tags')}
            selected={selectedTags}
            onChange={setSelectedTags}
            extra={extraTags}
            hint={t('admin.ruleTagsHint', 'Select the categories that should be fast-tracked.')}
          />
          <FormField
            id="rule-boost"
            label={t('admin.ruleBoost', 'Boost (1–100)')}
            type="number"
            min={1}
            max={100}
            value={boost}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setBoost(Number(e.target.value))}
          />

          <div className="flex flex-wrap gap-2">
            <Button onClick={() => void save()} loading={busy} icon={editingId ? <Check size={16} /> : <Plus size={16} />}>
              {editingId ? t('admin.saveRule', 'Save rule') : t('admin.addRule', 'Add rule')}
            </Button>
            {editingId && (
              <Button variant="secondary" onClick={reset} icon={<X size={16} />}>
                {t('common.cancel', 'Cancel')}
              </Button>
            )}
          </div>
        </div>
      </Card>

      <Card kicker={t('admin.priority', 'Priority rules')} title={t('admin.activeRules', 'Active rules')}>
        {rules.length === 0 ? (
          <EmptyState
            icon={<ShieldCheck size={22} />}
            title={t('admin.noRules', 'No priority rules yet')}
            hint={t('admin.noRulesHint', 'Add tags such as “Senior Citizen” to fast-track inclusively.')}
          />
        ) : (
          <ul className="m-0 p-0 list-none flex flex-col gap-2">
            {rules.map((rule) => (
              <li key={String(rule.id)} className="rounded-md border border-line p-3.5 flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="m-0 text-[15px] font-semibold text-ink">{String(rule.name)}</p>
                  <p className="m-0 mt-0.5 text-[13px] text-ink-2 truncate">{((rule.tags as string[]) ?? []).map((tag) => t(`tag.${tag}`, tag)).join(', ') || t('admin.noTags', 'no tags')}</p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge tone={rule.is_active ? 'ok' : 'alert'}>
                    {rule.is_active ? <Check size={12} aria-hidden /> : <X size={12} aria-hidden />}
                    {t('admin.boost', 'boost {n}').replace('{n}', String(rule.boost))}
                  </Badge>
                  <Button variant="ghost" size="sm" onClick={() => startEdit(rule)} icon={<Pencil size={14} />}>
                    {t('admin.edit', 'Edit')}
                  </Button>
                  <Button variant="secondary" size="sm" disabled={busy} onClick={() => void toggleActive(rule)}>
                    {rule.is_active ? t('admin.pause', 'Pause') : t('admin.resume', 'Resume')}
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}
