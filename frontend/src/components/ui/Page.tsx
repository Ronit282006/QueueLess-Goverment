import type { ReactNode } from 'react'

/** Standard page wrapper with a subtle entrance animation (motion-aware). */
export function Page({ title, kicker, actions, children, wide = false }: { title?: string; kicker?: string; actions?: ReactNode; children: ReactNode; wide?: boolean }) {
  return (
    <div className={`animate-fade-slide w-full ${wide ? '' : 'max-w-[1280px]'} mx-auto`}>
      {(title || actions || kicker) && (
        <header className="flex flex-wrap items-end justify-between gap-3 mb-6">
          <div>
            {kicker && <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-brand mb-1">{kicker}</p>}
            {title && <h1 className="text-2xl sm:text-[1.9rem] font-extrabold text-ink m-0">{title}</h1>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      {children}
    </div>
  )
}