import { useCallback, useEffect, useRef, useState } from 'react'

/** Read / write a value in localStorage with JSON serialisation. */
export function useLocalStorage<T>(key: string, initial: T): [T, (next: T) => void] {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(key)
      return raw === null ? initial : (JSON.parse(raw) as T)
    } catch {
      return initial
    }
  })
  const set = useCallback((next: T) => {
    setValue(next)
    try {
      localStorage.setItem(key, JSON.stringify(next))
    } catch {
      /* storage unavailable */
    }
  }, [key])
  return [value, set]
}

export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches)
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    const onChange = () => setReduced(mq.matches)
    mq.addEventListener?.('change', onChange)
    return () => mq.removeEventListener?.('change', onChange)
  }, [])
  return reduced
}

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches)
  useEffect(() => {
    const mq = window.matchMedia(query)
    const onChange = () => setMatches(mq.matches)
    mq.addEventListener?.('change', onChange)
    return () => mq.removeEventListener?.('change', onChange)
  }, [query])
  return matches
}

/** Animate a number towards `target` whenever it changes. */
export function useCountUp(target: number, durationMs = 550): number {
  const reduced = useReducedMotion()
  const [value, setValue] = useState(target)
  const fromRef = useRef(target)
  const rafRef = useRef<number | null>(null)

  useEffect(() => {
    if (reduced) {
      setValue(target)
      fromRef.current = target
      return
    }
    if (target === fromRef.current) return
    const start = fromRef.current
    const delta = target - start
    const t0 = performance.now()
    const tick = (t: number) => {
      const p = Math.min(1, (t - t0) / durationMs)
      const eased = 1 - Math.pow(1 - p, 3)
      setValue(start + delta * eased)
      if (p < 1) {
        rafRef.current = requestAnimationFrame(tick)
      } else {
        fromRef.current = target
      }
    }
    rafRef.current = requestAnimationFrame(tick)
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
    }
  }, [target, durationMs, reduced])

  return Math.round(value)
}

/** Stagger delays (ms) for cards entering one-by-one; 0 under reduced motion. */
export function useStagger(count: number, baseMs = 45): number[] {
  const reduced = useReducedMotion()
  const delays = useRef<number[]>([])
  if (delays.current.length !== count) {
    delays.current = Array.from({ length: count }, (_, i) => i * baseMs)
  }
  return reduced ? delays.current.map(() => 0) : delays.current
}

/** Trap focus within a container while `active`. */
export function useFocusTrap(active: boolean): (el: HTMLElement | null) => void {
  const ref = useRef<HTMLElement | null>(null)
  const setRef = useCallback((el: HTMLElement | null) => {
    ref.current = el
  }, [])

  useEffect(() => {
    if (!active) return
    const node = ref.current
    if (!node) return
    const focusables = () =>
      Array.from(node.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      )).filter((el) => el.offsetParent !== null)

    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return
      const items = focusables()
      if (items.length === 0) {
        e.preventDefault()
        return
      }
      const first = items[0]
      const last = items[items.length - 1]
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }
    node.addEventListener('keydown', onKey)
    // Move focus into the dialog on open.
    const previous = document.activeElement as HTMLElement | null
    const firstFocus = focusables()[0] ?? node
    firstFocus.focus()
    return () => {
      node.removeEventListener('keydown', onKey)
      previous?.focus?.()
    }
  }, [active])

  return setRef
}

export function useLockBody(locked: boolean) {
  useEffect(() => {
    if (!locked) return
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = previous
    }
  }, [locked])
}

/** Invoke `handler` on Escape. */
export function useEscape(handler: () => void) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') handler()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [handler])
}