import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { CheckCircle2, Info, X, XCircle } from 'lucide-react'

type ToastTone = 'success' | 'error' | 'info'
interface ToastItem { id: number; tone: ToastTone; title: string; body?: string }
interface ToastApi {
  success: (title: string, body?: string) => void
  error: (title: string, body?: string) => void
  info: (title: string, body?: string) => void
}

const ToastContext = createContext<ToastApi | null>(null)

const tones = {
  success: { icon: CheckCircle2, ring: 'text-ok' },
  error: { icon: XCircle, ring: 'text-alert' },
  info: { icon: Info, ring: 'text-info' },
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])
  const nextId = useRef(1)

  const push = useCallback((tone: ToastTone, title: string, body?: string) => {
    const id = nextId.current++
    setItems((prev) => [...prev.slice(-3), { id, tone, title, body }])
    window.setTimeout(() => setItems((prev) => prev.filter((t) => t.id !== id)), 4500)
  }, [])

  const api = useMemo<ToastApi>(
    () => ({
      success: (t, b) => push('success', t, b),
      error: (t, b) => push('error', t, b),
      info: (t, b) => push('info', t, b),
    }),
    [push],
  )

  return (
    <ToastContext.Provider value={api}>
      {children}
      {createPortal(
        <div aria-live="polite" role="region" aria-label="Notifications" className="fixed top-4 right-4 left-4 sm:left-auto z-[60] flex flex-col gap-2 w-auto sm:w-[360px]">
          {items.map((t) => {
            const C = tones[t.tone]
            const Icon = C.icon
            return (
              <div key={t.id} className="animate-toast flex items-start gap-3 rounded-md border border-line bg-surface px-4 py-3 shadow-pop">
                <Icon size={20} className={`shrink-0 mt-0.5 ${C.ring}`} aria-hidden />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-ink m-0">{t.title}</p>
                  {t.body && <p className="text-[13px] text-ink-2 m-0 mt-0.5">{t.body}</p>}
                </div>
                <button
                  aria-label="Dismiss"
                  className="grid place-items-center w-8 h-8 rounded-full text-ink-3 hover:bg-surface2"
                  onClick={() => setItems((prev) => prev.filter((x) => x.id !== t.id))}
                >
                  <X size={16} />
                </button>
              </div>
            )
          })}
        </div>,
        document.body,
      )}
    </ToastContext.Provider>
  )
}

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used inside ToastProvider')
  return ctx
}