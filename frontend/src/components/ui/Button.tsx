import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { Loader2 } from 'lucide-react'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'outline' | 'danger' | 'dangerGhost'
export type ButtonSize = 'sm' | 'md' | 'lg'

const base =
  'inline-flex items-center justify-center gap-2 font-semibold tracking-[-0.01em] rounded-md transition-all duration-150 ' +
  'disabled:opacity-50 disabled:pointer-events-none select-none whitespace-nowrap active:scale-[0.985]'

const variants: Record<ButtonVariant, string> = {
  primary: 'bg-brand text-white border border-brand/90 hover:bg-brand-strong shadow-sm',
  secondary: 'bg-surface text-ink border border-line hover:bg-surface2 hover:border-slate-300 shadow-sm',
  ghost: 'bg-transparent text-ink-2 hover:text-ink hover:bg-surface2',
  outline: 'bg-transparent text-brand border border-brand/35 hover:bg-brand-soft',
  danger: 'bg-alert text-white border border-alert/90 hover:bg-red-700 shadow-sm',
  dangerGhost: 'bg-transparent text-alert hover:bg-alert-soft border border-alert/35',
}

const sizes: Record<ButtonSize, string> = {
  sm: 'text-xs font-semibold px-3 py-1.5 min-h-[34px] rounded-md',
  md: 'text-sm font-semibold px-4 py-2.5 min-h-[42px] rounded-md',
  lg: 'text-[15px] font-bold px-5 py-3 min-h-[46px] rounded-lg',
}

export function buttonClass(variant: ButtonVariant = 'primary', size: ButtonSize = 'md', extra = ''): string {
  return `${base} ${variants[variant]} ${sizes[size]} ${extra}`
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  loading?: boolean
  loadingLabel?: string
  icon?: ReactNode
}

export function Button({
  variant = 'primary', size = 'md', loading = false, loadingLabel, icon, disabled, children, className = '', ...rest
}: ButtonProps) {
  return (
    <button className={buttonClass(variant, size, className)} disabled={disabled || loading} {...rest}>
      {loading && <Loader2 size={16} className="animate-spin" aria-hidden />}
      {!loading && icon}
      <span>{loading && loadingLabel ? loadingLabel : children}</span>
    </button>
  )
}