import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from 'react'
import { AlertCircle } from 'lucide-react'

export function inputClass(error?: string, extra = ''): string {
  return (
    'w-full rounded-md border bg-surface px-3.5 py-2.5 text-[15px] text-ink placeholder:text-ink-3 min-h-[44px] ' +
    'transition-colors focus:outline-none focus:ring-2 ' +
    (error ? 'border-alert focus:ring-alert/30' : 'border-line focus:border-brand focus:ring-brand/25') +
    ` ${extra}`
  )
}

export function FormField({
  id, label, error, hint, required, as: As = 'input', children, className = '', visuallyHideLabel,
  ...inputProps
}: {
  id: string
  label: string
  error?: string
  hint?: ReactNode
  required?: boolean
  as?: 'input' | 'select' | 'textarea'
  children?: ReactNode
  className?: string
  visuallyHideLabel?: boolean
} & (InputHTMLAttributes<HTMLInputElement> | SelectHTMLAttributes<HTMLSelectElement> | TextareaHTMLAttributes<HTMLTextAreaElement>)) {
  const describedBy = [
    error ? `${id}-error` : null,
    hint ? `${id}-hint` : null,
  ].filter(Boolean).join(' ') || undefined

  const labelEl = (
    <label htmlFor={id} className={`text-sm font-semibold text-ink ${visuallyHideLabel ? 'sr-only' : ''}`}>
      {label}
      {required && (
        <span className="text-alert" aria-hidden>
          {' '}
          *
        </span>
      )}
    </label>
  )

  const renderControl = () => {
    if (As === 'textarea') {
      return (
        <textarea
          id={id}
          aria-invalid={!!error}
          aria-describedby={describedBy}
          className={inputClass(error, 'min-h-[96px]')}
          {...(inputProps as TextareaHTMLAttributes<HTMLTextAreaElement>)}
        >
          {children}
        </textarea>
      )
    }
    if (As === 'select') {
      return (
        <select
          id={id}
          aria-invalid={!!error}
          aria-describedby={describedBy}
          className={inputClass(error)}
          {...(inputProps as SelectHTMLAttributes<HTMLSelectElement>)}
        >
          {children}
        </select>
      )
    }
    if (children) {
      return children
    }
    return (
      <input
        id={id}
        aria-invalid={!!error}
        aria-describedby={describedBy}
        className={inputClass(error)}
        {...(inputProps as InputHTMLAttributes<HTMLInputElement>)}
      />
    )
  }

  return (
    <div className={`flex flex-col gap-1.5 ${className}`}>
      {labelEl}
      {renderControl()}
      {hint && !error && (
        <small id={`${id}-hint`} className="text-[13px] text-ink-2 leading-snug">
          {hint}
        </small>
      )}
      {error && (
        <small id={`${id}-error`} role="alert" className="flex items-center gap-1 text-[13px] font-medium text-alert">
          <AlertCircle size={14} aria-hidden /> {error}
        </small>
      )}
    </div>
  )
}