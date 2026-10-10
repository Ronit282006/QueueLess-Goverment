import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { useEscape } from '../../lib/ui'

/** Lightweight anchored popover for menus / settings popups. */
export function Popover({
  trigger, children, align = 'right', label,
}: {
  trigger: (state: { open: boolean; toggle: () => void }) => ReactNode
  children: ReactNode
  align?: 'left' | 'right'
  label: string
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const toggle = () => setOpen((o) => !o)
  useEscape(() => setOpen(false))

  useEffect(() => {
    if (!open) return
    const onPointer = (e: PointerEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', onPointer)
    return () => document.removeEventListener('pointerdown', onPointer)
  }, [open])

  return (
    <div ref={ref} className="relative">
      {trigger({ open, toggle })}
      {open && (
        <div
          role={label ? 'menu' : undefined}
          aria-label={label || undefined}
          className={`absolute z-50 mt-2 min-w-[248px] max-w-[calc(100vw-24px)] rounded-md border border-line bg-surface shadow-pop animate-pop ${
            align === 'right' ? 'right-0' : 'left-0'
          }`}
        >
          {children}
        </div>
      )}
    </div>
  )
}