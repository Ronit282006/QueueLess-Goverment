import type { ReactNode } from 'react'

export type Tone = 'brand' | 'ok' | 'warn' | 'alert' | 'info' | 'neutral'

const tones: Record<Tone, string> = {
  brand: 'bg-brand-soft text-brand',
  ok: 'bg-ok-soft text-ok',
  warn: 'bg-warn-soft text-warn',
  alert: 'bg-alert-soft text-alert',
  info: 'bg-info-soft text-info',
  neutral: 'bg-surface2 text-ink-2 border border-line',
}

export function Badge({ children, tone = 'brand', className = '' }: { children: ReactNode; tone?: Tone; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-bold uppercase tracking-[0.04em] ${tones[tone]} ${className}`}>
      {children}
    </span>
  )
}

/** Semantic tone for a token status — colour is never the only signal (spans render inside a Badge with text). */
export function statusTone(status: string): Tone {
  const s = status.toUpperCase()
  if (s === 'SERVING' || s === 'COMPLETED') return 'ok'
  if (s === 'CALLED' || s === 'ARRIVED') return 'info'
  if (s === 'SKIPPED' || s === 'CANCELLED' || s === 'EXPIRED' || s === 'RESCHEDULED') return 'alert'
  if (s === 'APPROACHING') return 'warn'
  return 'brand'
}