export function SegmentedControl<T extends string>({
  options, value, onChange, label,
}: {
  options: { value: T; label: string; hint?: string }[]
  value: T
  onChange: (v: T) => void
  label: string
}) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className="inline-flex flex-wrap items-center gap-1 rounded-md border border-line bg-surface2 p-1"
    >
      {options.map((opt) => {
        const active = opt.value === value
        return (
          <button
            key={opt.value}
            role="radio"
            aria-checked={active}
            onClick={() => onChange(opt.value)}
            className={`inline-flex items-center gap-1.5 rounded-md px-3.5 py-1.5 text-xs transition-all min-h-[34px] ${
              active ? 'bg-surface text-brand font-bold shadow-sm border border-line/80' : 'text-ink-2 hover:text-ink font-semibold'
            }`}
            title={opt.hint}
          >
            {opt.label}
          </button>
        )
      })}
    </div>
  )
}