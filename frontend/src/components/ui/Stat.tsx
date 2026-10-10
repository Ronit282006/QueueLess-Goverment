import type { ReactNode } from 'react'
import { useCountUp } from '../../lib/ui'

export function Stat({
  label, value, unit, hint, delay = 0,
}: {
  label: string
  value: ReactNode
  /** Render numeric values with a count-up animation. */
  valueNumber?: number
  unit?: string
  hint?: ReactNode
  delay?: number
}) {
  return (
    <article
      className="bg-surface border border-line rounded-md shadow-card p-4 flex flex-col gap-1 animate-fade-slide"
      style={{ animationDelay: `${delay}ms` }}
    >
      <span className="text-[11px] font-bold uppercase tracking-[0.08em] text-ink-3">{label}</span>
      <b className="text-[1.75rem] leading-none font-bold text-ink tabular-nums">
        {value}
        {unit && <em className="ml-1 text-sm font-semibold text-ink-2 not-italic">{unit}</em>}
      </b>
      {hint && <small className="text-[13px] text-ink-2 leading-snug">{hint}</small>}
    </article>
  )
}

/** Stat that animates a numeric value with count-up when it changes. */
export function NStat({ label, valueNumber, unit, hint, delay = 0 }: { label: string; valueNumber: number; unit?: string; hint?: ReactNode; delay?: number }) {
  const rendered = useCountUp(valueNumber)
  return <Stat label={label} value={rendered} unit={unit} hint={hint} delay={delay} />
}