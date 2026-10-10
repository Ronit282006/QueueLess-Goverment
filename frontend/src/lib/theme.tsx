import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

export type Theme = 'light' | 'dark' | 'system'

const THEME_KEY = 'ql_theme'
const LARGE_KEY = 'ql_large_text'
const CONTRAST_KEY = 'ql_high_contrast'

interface ThemeValue {
  theme: Theme
  setTheme: (t: Theme) => void
  resolved: 'light' | 'dark'
  largeText: boolean
  setLargeText: (on: boolean) => void
  highContrast: boolean
  setHighContrast: (on: boolean) => void
}

const ThemeContext = createContext<ThemeValue | null>(null)

function systemIsDark(): boolean {
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => {
    const saved = localStorage.getItem(THEME_KEY)
    if (!saved || saved === 'dark' || saved === 'system') {
      localStorage.setItem(THEME_KEY, 'light')
      return 'light'
    }
    return (saved as Theme) || 'light'
  })
  const [systemDark, setSystemDark] = useState(systemIsDark)
  const [largeText, setLargeTextState] = useState(() => localStorage.getItem(LARGE_KEY) === '1')
  const [highContrast, setHighContrastState] = useState(() => localStorage.getItem(CONTRAST_KEY) === '1')

  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = () => setSystemDark(mq.matches)
    mq.addEventListener?.('change', onChange)
    return () => mq.removeEventListener?.('change', onChange)
  }, [])

  const resolved: 'light' | 'dark' = theme === 'system' ? (systemDark ? 'dark' : 'light') : theme

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', resolved)
  }, [resolved])

  useEffect(() => {
    document.documentElement.classList.toggle('ql-large-text', largeText)
    localStorage.setItem(LARGE_KEY, largeText ? '1' : '0')
  }, [largeText])

  useEffect(() => {
    document.documentElement.classList.toggle('ql-high-contrast', highContrast)
    localStorage.setItem(CONTRAST_KEY, highContrast ? '1' : '0')
  }, [highContrast])

  const setTheme = useCallback((t: Theme) => {
    localStorage.setItem(THEME_KEY, t)
    setThemeState(t)
  }, [])

  const value = useMemo<ThemeValue>(
    () => ({ theme, setTheme, resolved, largeText, setLargeText: setLargeTextState, highContrast, setHighContrast: setHighContrastState }),
    [theme, setTheme, resolved, largeText, highContrast],
  )
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme(): ThemeValue {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used inside ThemeProvider')
  return ctx
}