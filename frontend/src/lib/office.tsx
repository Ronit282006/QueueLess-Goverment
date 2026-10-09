import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { api } from './api'
import type { Office, Service } from './types'

interface OfficeValue {
  offices: Office[]
  office: Office | null
  setOfficeId: (id: number) => void
  services: (Service & { officeId: number; officeName: string; departmentName: string })[]
  loading: boolean
  error: string | null
  reload: () => void
}

const OfficeContext = createContext<OfficeValue>({
  offices: [],
  office: null,
  setOfficeId: () => {},
  services: [],
  loading: true,
  error: null,
  reload: () => {},
})

export function OfficeProvider({ children }: { children: ReactNode }) {
  const [offices, setOffices] = useState<Office[]>([])
  const [officeId, setOfficeId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = () => {
    setLoading(true)
    api
      .offices()
      .then((data) => {
        setOffices(data)
        setOfficeId((current) => current ?? data[0]?.id ?? null)
        setError(null)
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const value = useMemo<OfficeValue>(() => {
    const office = offices.find((o) => o.id === officeId) ?? offices[0] ?? null
    const services = offices.flatMap((o) =>
      o.departments.flatMap((d) =>
        d.services.map((s) => ({ ...s, officeId: o.id, officeName: o.name, departmentName: d.name })),
      ),
    )
    return {
      offices,
      office,
      setOfficeId: (id) => setOfficeId(id),
      services,
      loading,
      error,
      reload: load,
    }
  }, [offices, officeId, loading, error])

  return <OfficeContext.Provider value={value}>{children}</OfficeContext.Provider>
}

export function useOffice(): OfficeValue {
  return useContext(OfficeContext)
}