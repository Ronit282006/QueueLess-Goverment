import type { ReactNode } from 'react'

export function Card({
  kicker, title, action, children, className = '', bodyClassName = '', container = 'section',
}: {
  kicker?: string
  title?: ReactNode
  action?: ReactNode
  children: ReactNode
  className?: string
  bodyClassName?: string
  container?: 'section' | 'div'
}) {
  const Tag = container as 'section'
  return (
    <Tag className={`bg-surface border border-line rounded-md shadow-card ${className}`}>
      {(title || action) && (
        <div className="flex items-start justify-between gap-3 px-5 pt-4 pb-3">
          <div className="min-w-0">
            {kicker && <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-brand mb-0.5">{kicker}</p>}
            {typeof title === 'string' ? <h2 className="text-lg font-bold m-0 text-ink">{title}</h2> : title}
          </div>
          {action && <div className="flex items-center gap-2 shrink-0">{action}</div>}
        </div>
      )}
      <div className={`px-5 pb-5 pt-1 ${bodyClassName}`}>{children}</div>
    </Tag>
  )
}