import { useCallback, useEffect, useRef, useState } from 'react'
import { API_BASE, api } from './api'
import type { QueueSnapshot } from './types'

/** Defer socket creation one task so Strict Mode's simulated cleanup can cancel it. */
function scheduleWebSocket(url: string, onMessage: (event: MessageEvent) => void) {
  let disposed = false
  let ws: WebSocket | undefined
  const timer = window.setTimeout(() => {
    if (disposed) return
    try {
      ws = new WebSocket(url)
      ws.onmessage = onMessage
      ws.onopen = () => {
        if (disposed) ws?.close()
      }
    } catch {
      /* WebSocket unavailable — polling continues */
    }
  }, 0)

  return () => {
    disposed = true
    window.clearTimeout(timer)
    if (ws?.readyState === WebSocket.OPEN) ws.close()
    else if (ws?.readyState === WebSocket.CONNECTING) {
      // Closing a CONNECTING socket emits a browser console error. Close it
      // cleanly if it opens after its owning effect has been disposed.
      ws.onopen = () => ws?.close()
    }
  }
}

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const fnRef = useRef(fn)
  fnRef.current = fn

  const reload = useCallback(() => {
    let active = true
    setLoading(true)
    fnRef
      .current()
      .then((result) => active && (setData(result), setError(null)))
      .catch((err: Error) => active && setError(err.message))
      .finally(() => active && setLoading(false))
    return () => {
      active = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  useEffect(() => reload(), [reload])
  return { data, error, loading, reload, setData }
}

/** Live queue for one service, refreshed on WebSocket events with a polling fallback. */
export function useQueue(serviceId: number | null, officeId?: number) {
  const [queue, setQueue] = useState<QueueSnapshot | null>(null)
  const [error, setError] = useState<string | null>(null)

  const fetchQueue = useCallback(async () => {
    if (!serviceId) return
    try {
      setQueue(await api.queue(serviceId, officeId))
      setError(null)
    } catch (err) {
      setError((err as Error).message)
    }
  }, [serviceId, officeId])

  useEffect(() => {
    fetchQueue()
    const id = setInterval(fetchQueue, 15000)
    const closeWebSocket = scheduleWebSocket(`${API_BASE.replace(/^http/, 'ws')}/ws/queue`, (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'queue.updated' && (!data.service_id || data.service_id === serviceId)) fetchQueue()
      } catch {
        /* ignore malformed frames */
      }
    })
    return () => {
      clearInterval(id)
      closeWebSocket()
    }
  }, [fetchQueue, serviceId])

  return { queue, error, refresh: fetchQueue }
}

/** Track a single token live via its WebSocket room with polling fallback. */
export function useToken(reference: string | null) {
  const [token, setToken] = useState<Awaited<ReturnType<typeof api.token>> | null>(null)
  const [error, setError] = useState<string | null>(null)

  const fetchToken = useCallback(async () => {
    if (!reference) return
    try {
      setToken(await api.token(reference))
      setError(null)
    } catch (err) {
      setError((err as Error).message)
    }
  }, [reference])

  useEffect(() => {
    if (!reference) {
      setToken(null)
      return
    }
    fetchToken()
    const id = setInterval(fetchToken, 10000)
    const closeWebSocket = scheduleWebSocket(`${API_BASE.replace(/^http/, 'ws')}/ws/tokens/${reference}`, (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.token) setToken(data.token)
      } catch {
        /* ignore malformed frames */
      }
    })
    return () => {
      clearInterval(id)
      closeWebSocket()
    }
  }, [reference, fetchToken])

  return { token, error, refresh: fetchToken }
}
