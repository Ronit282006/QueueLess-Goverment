import type { ReactNode } from 'react'
import { AlertTriangle, X } from 'lucide-react'

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="ql-empty" role="status" aria-live="polite">
      <span className="ql-spinner" />
      <b>{label ?? 'Loading…'}</b>
    </div>
  )
}

export function ErrorBox({ message, onDismiss }: { message: string; onDismiss?: () => void }) {
  return (
    <div className="ql-error" role="alert">
      <span className="ql-error-text">
        <AlertTriangle size={16} /> {message}
      </span>
      {onDismiss && (
        <button onClick={onDismiss} aria-label="Dismiss">
          <X size={16} />
        </button>
      )}
    </div>
  )
}

export function Stat({ label, value, unit, hint }: { label: string; value: ReactNode; unit?: string; hint?: ReactNode }) {
  return (
    <article>
      <span>{label}</span>
      <b>
        {value} {unit && <em>{unit}</em>}
      </b>
      {hint && <small>{typeof hint === 'string' ? <><i />{hint}</> : hint}</small>}
    </article>
  )
}

export function Card({
  kicker,
  title,
  action,
  children,
  className = '',
}: {
  kicker?: string
  title?: ReactNode
  action?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={`ql-card ${className}`}>
      {(title || action) && (
        <div className="ql-card-title">
          <div>
            {kicker && <span className="ql-kicker">{kicker}</span>}
            {typeof title === 'string' ? <h2>{title}</h2> : title}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  )
}

export function Badge({ children, tone = 'brand' }: { children: ReactNode; tone?: 'brand' | 'ok' | 'warn' | 'alert' }) {
  return <span className={`ql-badge ql-badge-${tone}`}>{children}</span>
}

export function Empty({ icon, title, hint }: { icon?: ReactNode; title: string; hint?: string }) {
  return (
    <div className="ql-empty">
      {icon}
      <b>{title}</b>
      {hint && <span>{hint}</span>}
    </div>
  )
}

export function CloseButton({ onClick, label }: { onClick: () => void; label: string }) {
  return (
    <button className="ql-close" onClick={onClick} aria-label={label}>
      <X size={18} />
    </button>
  )
}