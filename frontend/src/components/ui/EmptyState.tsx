import type { ReactNode } from 'react'

export function EmptyState({ icon, title, hint, action }: { icon?: ReactNode; title: string; hint?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-10 px-4 text-center">
      {icon && <div className="grid place-items-center w-12 h-12 rounded-full bg-brand-soft text-brand mb-1">{icon}</div>}
      <p className="text-base font-semibold text-ink m-0">{title}</p>
      {hint && <p className="text-sm text-ink-2 m-0 max-w-md">{hint}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-col items-center gap-2 rounded-md border border-alert/40 bg-alert-soft p-5 text-center">
      <p className="text-sm font-semibold text-alert m-0">{message}</p>
      {onRetry && (
        <button
          className="mt-1 inline-flex items-center gap-2 rounded-md border border-alert px-4 py-2 text-sm font-semibold text-alert bg-surface hover:bg-surface2"
          onClick={onRetry}
        >
          Try again
        </button>
      )}
    </div>
  )
}