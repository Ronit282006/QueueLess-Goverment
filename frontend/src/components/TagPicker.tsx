import { Check, X } from 'lucide-react'
import { useI18n } from '../lib/i18n'
import { CITIZEN_TAGS } from '../lib/citizenTags'

const chipClass = (active: boolean) =>
  `inline-flex items-center gap-1.5 rounded-full border px-3 py-2 text-[13px] font-semibold transition-all min-h-[36px] focus:outline-none focus:ring-2 ${
    active
      ? 'border-brand bg-brand-soft text-brand shadow-sm'
      : 'border-line bg-surface text-ink-2 hover:border-brand/50 hover:text-ink'
  }`

export default function TagPicker({
  id,
  label,
  selected,
  onChange,
  hint,
  extra = [],
  showNormal = false,
}: {
  id: string
  label: string
  selected: string[]
  onChange: (tags: string[]) => void
  hint?: string
  /** Legacy/unknown tags (from older data) rendered as removable chips so they are never silently dropped. */
  extra?: string[]
  /** When true, renders a “Normal” chip that clears every other selection. */
  showNormal?: boolean
}) {
  const { t } = useI18n()

  const toggle = (code: string) => {
    if (selected.includes(code)) onChange(selected.filter((tag) => tag !== code))
    else onChange([...selected, code])
  }

  const normal = selected.length === 0

  return (
    <div className="flex flex-col gap-1.5">
      <span id={id} className="text-sm font-semibold text-ink">
        {label}
      </span>
      <div role="group" aria-labelledby={id} className="flex flex-wrap gap-2">
        {showNormal && (
          <button
            type="button"
            aria-pressed={normal}
            onClick={() => onChange([])}
            className={chipClass(normal)}
          >
            {t('common.normal', 'Normal')}
          </button>
        )}
        {CITIZEN_TAGS.map((tag) => {
          const active = selected.includes(tag.code)
          return (
            <button
              key={tag.code}
              type="button"
              aria-pressed={active}
              onClick={() => toggle(tag.code)}
              className={chipClass(active)}
            >
              {active ? <Check size={14} aria-hidden /> : null}
              {t(`tag.${tag.code}`, tag.code)}
            </button>
          )
        })}
        {extra.map((tag) => {
          const active = selected.includes(tag)
          return (
            <button
              key={tag}
              type="button"
              aria-pressed={active}
              onClick={() => toggle(tag)}
              className={chipClass(active)}
            >
              {active ? <Check size={14} aria-hidden /> : null}
              {tag}
              <X size={13} aria-hidden />
            </button>
          )
        })}
      </div>
      {hint && (
        <small className="text-[13px] text-ink-2 leading-snug">{hint}</small>
      )}
    </div>
  )
}