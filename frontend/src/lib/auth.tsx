import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { api, setToken } from './api'

export interface SessionUser {
  id: number
  email: string
  full_name: string
  role: string
  tags?: string[]
}

interface AuthContextValue {
  user: SessionUser | null
  ready: boolean
  login: (email: string, password: string) => Promise<SessionUser>
  register: (email: string, fullName: string, password: string, tags?: string[]) => Promise<void>
  resendRegistrationOtp: (email: string) => Promise<{ message: string; expires_in_seconds: number }>
  verifyRegistrationOtp: (email: string, otp: string) => Promise<{ user: SessionUser; message: string }>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    let active = true
    api
      .me()
      .then((me) => {
        if (active) setUser(me)
      })
      .catch(() => {
        setToken(null)
      })
      .finally(() => {
        if (active) setReady(true)
      })
    return () => {
      active = false
    }
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const result = await api.login(email, password)
    setToken(result.access_token)
    const session = result.user as SessionUser
    setUser(session)
    return session
  }, [])

  const register = useCallback(async (email: string, fullName: string, password: string, tags: string[] = []) => {
    await api.register(email, fullName, password, tags)
  }, [])

  const resendRegistrationOtp = useCallback((email: string) => api.resendRegistrationOtp(email), [])

  const verifyRegistrationOtp = useCallback(async (email: string, otp: string) => {
    const result = await api.verifyRegistrationOtp(email, otp)
    setToken(result.access_token)
    const session = result.user as SessionUser
    setUser(session)
    return { user: session, message: result.message }
  }, [])

  const logout = useCallback(() => {
    setToken(null)
    setUser(null)
  }, [])

  const value = useMemo(() => ({ user, ready, login, register, resendRegistrationOtp, verifyRegistrationOtp, logout }), [user, ready, login, register, resendRegistrationOtp, verifyRegistrationOtp, logout])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
