import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

export type Lang = 'en' | 'hi' | 'gu'
export const LANGUAGES: { code: Lang; label: string }[] = [
  { code: 'en', label: 'English' },
  { code: 'hi', label: 'हिन्दी' },
  { code: 'gu', label: 'ગુજરાતી' },
]

const LANG_KEY = 'ql_lang'

type Dict = Record<string, string>

interface I18nValue {
  lang: Lang
  setLang: (lang: Lang) => void
  t: (key: string, fallback?: string) => string
}

const I18nContext = createContext<I18nValue>({ lang: 'en', setLang: () => {}, t: (k, f) => f ?? k })

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(() => (localStorage.getItem(LANG_KEY) as Lang) || 'en')
  const [dict, setDict] = useState<Dict>({})

  useEffect(() => {
    let active = true
    fetch(`/locales/${lang}.json`)
      .then((r) => (r.ok ? r.json() : {}))
      .then((data: Dict) => active && setDict(data))
      .catch(() => active && setDict({}))
    return () => {
      active = false
    }
  }, [lang])

  const value = useMemo<I18nValue>(
    () => ({
      lang,
      setLang: (next) => {
        localStorage.setItem(LANG_KEY, next)
        setLangState(next)
      },
      t: (key, fallback) => dict[key] ?? fallback ?? key,
    }),
    [lang, dict],
  )
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useI18n(): I18nValue {
  return useContext(I18nContext)
}