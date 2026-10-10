import { createContext, useContext, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

export type TravelMode = 'driving' | 'walking' | 'cycling'

export type Coords = { latitude: number; longitude: number }

type Permission = 'unknown' | 'prompt' | 'granted' | 'denied' | 'unavailable'

interface LocationValue {
  coords: Coords | null
  mode: TravelMode
  setMode: (mode: TravelMode) => void
  permission: Permission
  requesting: boolean
  error: string | null
  /** Ask the browser for the current position; resolves to coords or null. */
  requestLocation: () => Promise<Coords | null>
  clear: () => void
}

const STORAGE_KEY = 'ql_location'
const MODE_KEY = 'ql_travel_mode'

function loadStored(): Coords | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Coords
    if (typeof parsed.latitude === 'number' && typeof parsed.longitude === 'number') return parsed
  } catch {
    /* ignore malformed storage */
  }
  return null
}

const LocationContext = createContext<LocationValue>({
  coords: null,
  mode: 'driving',
  setMode: () => {},
  permission: 'unknown',
  requesting: false,
  error: null,
  requestLocation: async () => null,
  clear: () => {},
})

export function LocationProvider({ children }: { children: ReactNode }) {
  const [coords, setCoords] = useState<Coords | null>(() => loadStored())
  const [mode, setModeState] = useState<TravelMode>(() => (localStorage.getItem(MODE_KEY) as TravelMode) || 'driving')
  const [permission, setPermission] = useState<Permission>(() => (loadStored() ? 'granted' : 'unknown'))
  const [requesting, setRequesting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const requestLocation = (): Promise<Coords | null> =>
    new Promise((resolve) => {
      if (typeof navigator === 'undefined' || !navigator.geolocation) {
        setPermission('unavailable')
        setError('Location is not supported on this device.')
        resolve(null)
        return
      }
      setRequesting(true)
      setError(null)
      navigator.geolocation.getCurrentPosition(
        (position) => {
          const next: Coords = {
            latitude: position.coords.latitude,
            longitude: position.coords.longitude,
          }
          setCoords(next)
          setPermission('granted')
          setRequesting(false)
          localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
          resolve(next)
        },
        (err) => {
          setRequesting(false)
          setPermission(err.code === err.PERMISSION_DENIED ? 'denied' : 'unknown')
          setError(
            err.code === err.PERMISSION_DENIED
              ? 'Location permission was denied. You can still book and track your token.'
              : 'Could not determine your location. Please try again.',
          )
          resolve(null)
        },
        { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 },
      )
    })

  const value = useMemo<LocationValue>(
    () => ({
      coords,
      mode,
      setMode: (next) => {
        localStorage.setItem(MODE_KEY, next)
        setModeState(next)
      },
      permission,
      requesting,
      error,
      requestLocation,
      clear: () => {
        localStorage.removeItem(STORAGE_KEY)
        setCoords(null)
        setPermission('unknown')
      },
    }),
    [coords, mode, permission, requesting, error],
  )

  return <LocationContext.Provider value={value}>{children}</LocationContext.Provider>
}

export function useLocation(): LocationValue {
  return useContext(LocationContext)
}
