import type { ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import { useEscape, useFocusTrap, useLockBody } from '../../lib/ui'
import { Button } from './Button'

export function Backdrop({ onBackdrop, children, label }: { onBackdrop: () => void; children: ReactNode; label: string }) {
  return createPortal(
    <div className="fixed inset-0 z-50 grid place-items-center p-4 animate-fade-in" role="presentation">
      <div className="absolute inset-0 bg-black/45 backdrop-blur-[2px]" onClick={onBackdrop} aria-hidden />
      <div role="dialog" aria-modal="true" aria-label={label} className="relative w-full max-w-lg">
        {children}
      </div>
    </div>,
    document.body,
  )
}

export function Modal({
  open, onClose, title, description, children, footer, label,
}: {
  open: boolean
  onClose: () => void
  title: string
  description?: string
  children: ReactNode
  footer?: ReactNode
  label?: string
}) {
  useLockBody(open)
  useEscape(onClose)
  const trapRef = useFocusTrap(open)
  if (!open) return null

  return createPortal(
    <div className="fixed inset-0 z-50 grid place-items-center p-4" role="presentation">
      <div className="absolute inset-0 bg-black/45 backdrop-blur-[2px]" onClick={onClose} aria-hidden />
      <div
        ref={trapRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="ql-modal-title"
        aria-describedby={description ? 'ql-modal-desc' : undefined}
        className="relative w-full max-w-lg bg-surface border border-line rounded-lg shadow-pop animate-pop overflow-hidden"
      >
        <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
          <div>
            <h2 id="ql-modal-title" className="text-lg font-bold text-ink m-0">{title}</h2>
            {description && <p id="ql-modal-desc" className="text-sm text-ink-2 m-0 mt-1">{description}</p>}
          </div>
          <button onClick={onClose} aria-label="Close" className="grid place-items-center w-10 h-10 rounded-full text-ink-2 hover:bg-surface2">
            <X size={20} />
          </button>
        </div>
        <div id={label} className="px-5 py-4 max-h-[60vh] overflow-y-auto">{children}</div>
        {footer && <div className="flex flex-wrap justify-end gap-2 border-t border-line px-5 py-4">{footer}</div>}
      </div>
    </div>,
    document.body,
  )
}

export function ConfirmDialog({
  open, onClose, onConfirm, title, body, confirmLabel = 'Confirm', danger = false, loading = false,
}: {
  open: boolean
  onClose: () => void
  onConfirm: () => void
  title: string
  body: string
  confirmLabel?: string
  danger?: boolean
  loading?: boolean
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={loading}>
            Cancel
          </Button>
          <Button variant={danger ? 'danger' : 'primary'} onClick={onConfirm} disabled={loading} loading={loading}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <p className="text-sm text-ink-2 m-0">{body}</p>
    </Modal>
  )
}

export function SlideOver({
  open, onClose, title, children, label, rail = false,
}: {
  open: boolean
  onClose: () => void
  title: string
  children: ReactNode
  label: string
  /** Rail slides from the left (mobile sidebar) instead of the right (panel). */
  rail?: boolean
}) {
  useLockBody(open)
  useEscape(onClose)
  if (!open) return null
  return createPortal(
    <div className="fixed inset-0 z-50" role="presentation">
      <div className="absolute inset-0 bg-black/45 backdrop-blur-[2px]" onClick={onClose} aria-hidden />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={label}
        className={`absolute top-0 bottom-0 w-[86%] max-w-sm bg-surface shadow-pop flex flex-col outline-none ${
          rail ? 'left-0 animate-drawer' : 'right-0 animate-sheet'
        }`}
      >
        <div className="flex items-center justify-between border-b border-line px-4 py-3">
          <h2 className="text-base font-bold m-0 text-ink">{title}</h2>
          <button onClick={onClose} aria-label="Close" className="grid place-items-center w-10 h-10 rounded-full text-ink-2 hover:bg-surface2">
            <X size={20} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">{children}</div>
      </div>
    </div>,
    document.body,
  )
}