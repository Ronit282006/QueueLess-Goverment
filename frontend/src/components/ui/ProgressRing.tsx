/** Circular progress ring with an animated draw. */
export function ProgressRing({
  value, size = 84, stroke = 8, label, sub, tone = 'brand',
}: {
  /** 0–100 */
  value: number
  size?: number
  stroke?: number
  label?: string
  sub?: string
  tone?: 'brand' | 'ok' | 'warn' | 'alert'
}) {
  const radius = (size - stroke) / 2
  const circ = 2 * Math.PI * radius
  const pct = Math.max(0, Math.min(100, value))
  const color = tone === 'ok' ? 'var(--c-ok)' : tone === 'warn' ? 'var(--c-warn)' : tone === 'alert' ? 'var(--c-alert)' : 'var(--c-brand)'
  return (
    <div
      className="relative inline-grid place-items-center"
      role="img"
      aria-label={label ? `${label}${sub ? ` — ${sub}` : ''}` : undefined}
    >
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="var(--c-line)" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circ}
          strokeDashoffset={circ * (1 - pct / 100)}
          style={{ ['--ring-circ' as string]: `${circ}px`, animation: 'ring-draw .7s ease-out both' }}
        />
      </svg>
      <div className="absolute inset-0 grid place-items-center text-center" style={{ padding: stroke }}>
        <div>
          {label && <p className="font-bold leading-none text-ink" style={{ fontSize: size / 4 }}>{label}</p>}
          {sub && <p className="text-[10px] leading-tight text-ink-2 mt-1">{sub}</p>}
        </div>
      </div>
    </div>
  )
}

/** Linear progress meter. */
export function Meter({ pct, tone = 'brand', label }: { pct: number; tone?: 'brand' | 'ok' | 'warn' | 'alert'; label?: string }) {
  const color = tone === 'ok' ? 'var(--c-ok)' : tone === 'warn' ? 'var(--c-warn)' : tone === 'alert' ? 'var(--c-alert)' : 'var(--c-brand)'
  const safe = Math.max(0, Math.min(100, pct))
  return (
    <div
      className="flex items-center gap-3"
      role={label ? 'meter' : undefined}
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={safe}
    >
      <div className="h-2 flex-1 rounded-full bg-surface2 border border-line overflow-hidden">
        <div className="h-full rounded-full transition-all duration-700" style={{ width: `${safe}%`, background: color }} />
      </div>
      {label && <span className="text-sm font-semibold text-ink tabular-nums whitespace-nowrap">{safe}%</span>}
    </div>
  )
}