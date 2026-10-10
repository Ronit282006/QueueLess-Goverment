import type { ReactNode } from 'react'

export function Tabs({
  tabs, active, onChange, label,
}: {
  tabs: { value: string; label: string; icon?: ReactNode }[]
  active: string
  onChange: (v: string) => void
  label: string
}) {
  return (
    <div role="tablist" aria-label={label} className="flex flex-wrap gap-1 border-b border-line overflow-x-auto">
      {tabs.map((tab) => {
        const selected = tab.value === active
        return (
          <button
            key={tab.value}
            role="tab"
            aria-selected={selected}
            onClick={() => onChange(tab.value)}
            className={`inline-flex items-center gap-2 whitespace-nowrap border-b-2 px-3.5 py-2.5 text-sm transition-all ${
              selected ? 'border-brand text-brand font-bold' : 'border-transparent text-ink-2 hover:text-ink font-semibold'
            }`}
          >
            {tab.icon}
            {tab.label}
          </button>
        )
      })}
    </div>
  )
}

export function Stepper({ steps, current, label, onStep }: { steps: { label: string; icon?: ReactNode }[]; current: number; label: string; onStep?: (i: number) => void }) {
  return (
    <ol aria-label={label} className="flex items-start gap-2 overflow-x-auto pb-1">
      {steps.map((step, i) => {
        const state = i < current ? 'done' : i === current ? 'active' : 'todo'
        return (
          <li key={step.label} className="flex items-center gap-2 min-w-[max-content]">
            {i === 0 ? null : <span aria-hidden className={`h-px w-6 ${i <= current ? 'bg-brand' : 'bg-line'}`} />}
            <button
              type="button"
              disabled={!onStep}
              onClick={() => onStep?.(i)}
              aria-current={state === 'active' ? 'step' : undefined}
              className={`flex items-center gap-2 rounded-full px-3 py-1.5 text-sm font-semibold ${
                state === 'active' ? 'bg-brand text-white' : state === 'done' ? 'text-brand' : 'text-ink-3'
              }`}
            >
              <span
                aria-hidden
                className={`grid place-items-center w-5 h-5 rounded-full text-[11px] ${
                  state === 'active' ? 'bg-white/20' : state === 'done' ? 'bg-brand-soft' : 'bg-surface2 border border-line'
                }`}
              >
                {state === 'done' ? '✓' : i + 1}
              </span>
              {step.label}
            </button>
          </li>
        )
      })}
    </ol>
  )
}