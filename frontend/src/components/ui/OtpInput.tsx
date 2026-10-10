import { useCallback, useMemo, useRef } from 'react'

/** Six-digit OTP input with paste support and automatic advance. */
export function OtpInput({
  length = 6, value, onChange, onComplete, disabled = false, name,
}: {
  length?: number
  value: string
  onChange: (v: string) => void
  onComplete?: (v: string) => void
  disabled?: boolean
  name?: string
}) {
  const refs = useRef<Array<HTMLInputElement | null>>([])

  const digits = useMemo(() => {
    const arr = value.split('')
    return Array.from({ length }, (_, i) => arr[i] ?? '')
  }, [value, length])

  const setDigit = useCallback(
    (idx: number, ch: string) => {
      const next = digits.slice()
      next[idx] = ch
      const joined = next.join('')
      onChange(joined)
      if (ch && idx < length - 1) refs.current[idx + 1]?.focus()
      if (joined.length === length) onComplete?.(joined)
    },
    [digits, length, onChange, onComplete],
  )

  const focusIndex = (idx: number) => {
    // Move focus to the first empty box, or the last box when full.
    const empty = digits.findIndex((d) => d === '')
    const target = empty >= 0 && empty < idx ? empty : Math.min(idx, length - 1)
    refs.current[target]?.focus()
  }

  return (
    <div className="flex gap-2 justify-center" role="group" aria-label="One-time code">
      {digits.map((d, i) => (
        <input
          key={i}
          ref={(el) => {
            refs.current[i] = el
          }}
          name={name ? `${name}-${i}` : undefined}
          type="text"
          inputMode="numeric"
          autoComplete={i === 0 ? 'one-time-code' : 'off'}
          maxLength={1}
          value={d}
          disabled={disabled}
          aria-label={`Digit ${i + 1} of ${length}`}
          className={`otp-box${d ? ' filled' : ''}`}
          onChange={(e) => {
            const ch = e.target.value.replace(/\D/g, '').slice(-1)
            setDigit(i, ch)
          }}
          onKeyDown={(e) => {
            if (e.key === 'Backspace' && !digits[i] && i > 0) {
              e.preventDefault()
              const next = digits.slice()
              next[i - 1] = ''
              onChange(next.join(''))
              refs.current[i - 1]?.focus()
            } else if (e.key === 'ArrowLeft' && i > 0) {
              e.preventDefault()
              refs.current[i - 1]?.focus()
            } else if (e.key === 'ArrowRight' && i < length - 1) {
              e.preventDefault()
              refs.current[i + 1]?.focus()
            }
          }}
          onFocus={(e) => setTimeout(() => e.target.select(), 0)}
          onPaste={(e) => {
            e.preventDefault()
            const text = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, length)
            if (!text) return
            const next = Array.from({ length }, (_, j) => text[j] ?? '')
            onChange(next.join(''))
            refs.current[Math.min(text.length, length - 1)]?.focus()
            if (text.length === length) onComplete?.(text)
          }}
        />
      ))}
    </div>
  )
}