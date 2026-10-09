import type {
  AuthResponse,
  AuthUser,
  Office,
  QueueSnapshot,
  Service,
  StaffCounter,
  Token,
} from './types'

export const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) || 'http://localhost:8000'

const TOKEN_KEY = 'ql_access_token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}
export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

export class ApiError extends Error {
  status: number
  code: string
  constructor(status: number, code: string, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !headers.has('content-type')) headers.set('content-type', 'application/json')
  const token = getToken()
  if (token) headers.set('authorization', `Bearer ${token}`)

  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, headers })
  } catch {
    throw new ApiError(0, 'network_error', 'Cannot reach the QueueLess API. Check your connection.')
  }
  const text = await response.text()
  const data = text ? JSON.parse(text) : null
  if (!response.ok) {
    const detail = data?.error ?? data?.detail
    const message =
      (typeof detail === 'string' && detail) ||
      detail?.message ||
      'Something went wrong. Please try again.'
    const code = (typeof detail === 'object' && detail?.code) || 'error'
    throw new ApiError(response.status, code, message)
  }
  return data as T
}

export const api = {
  // Catalog & queue
  offices: () => request<Office[]>('/api/offices'),
  service: (id: number) => request<Record<string, unknown>>(`/api/services/${id}`),
  queue: (serviceId: number, officeId?: number) =>
    request<QueueSnapshot>(`/api/queue?service_id=${serviceId}${officeId ? `&office_id=${officeId}` : ''}`),

  // Tokens
  createToken: (serviceId: number, officeId?: number, documentsConfirmed: string[] = []) =>
    request<Token>('/api/tokens', {
      method: 'POST',
      body: JSON.stringify({ service_id: serviceId, office_id: officeId ?? null, documents_confirmed: documentsConfirmed }),
    }),
  token: (reference: string) => request<Token>(`/api/tokens/${reference}`),
  transition: (reference: string, status: string) =>
    request<Token>(`/api/tokens/${reference}/transition`, { method: 'POST', body: JSON.stringify({ status }) }),
  incidentResponse: (reference: string, action: 'TRANSFER' | 'CANCEL', actionToken: string) =>
    request<{ action: string; scheduled_for?: string; token: Token }>(`/api/tokens/${reference}/incident-response`, {
      method: 'POST', body: JSON.stringify({ action, action_token: actionToken }),
    }),
  checkIn: (reference: string) =>
    request<Token>('/api/tokens/check-in', { method: 'POST', body: JSON.stringify({ reference }) }),
  feedback: (reference: string, rating: number, etaAccurate: boolean | null, comment = '') =>
    request<{ message: string }>(`/api/tokens/${reference}/feedback`, {
      method: 'POST',
      body: JSON.stringify({ rating, eta_accurate: etaAccurate, comment }),
    }),

  // Auth
  login: (email: string, password: string) =>
    request<AuthResponse>('/api/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) }),
  register: (email: string, fullName: string, password: string, tags: string[] = []) =>
    request<{ message: string; expires_in_seconds: number }>('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, full_name: fullName, password, tags }),
    }),
  resendRegistrationOtp: (email: string) =>
    request<{ message: string; expires_in_seconds: number }>('/api/auth/register/resend', {
      method: 'POST', body: JSON.stringify({ email }),
    }),
  verifyRegistrationOtp: (email: string, otp: string) =>
    request<AuthResponse & { message: string }>('/api/auth/register/verify', {
      method: 'POST', body: JSON.stringify({ email, otp }),
    }),
  me: () => request<AuthUser>('/api/auth/me'),

  // Staff
  dashboard: (officeId?: number) =>
    request<Record<string, unknown>>(`/api/staff/dashboard${officeId ? `?office_id=${officeId}` : ''}`),
  counters: (officeId: number) => request<StaffCounter[]>(`/api/staff/counters?office_id=${officeId}`),
  setCounterStatus: (counterId: number, status: string) =>
    request<StaffCounter>(`/api/staff/counters/${counterId}`, { method: 'PATCH', body: JSON.stringify({ status }) }),
  assignCounterServices: (counterId: number, serviceIds: number[]) =>
    request<StaffCounter>(`/api/staff/counters/${counterId}/services`, {
      method: 'PUT',
      body: JSON.stringify({ service_ids: serviceIds }),
    }),
  callNext: (counterId: number, serviceId: number) =>
    request<Token>(`/api/staff/counters/${counterId}/call-next`, {
      method: 'POST',
      body: JSON.stringify({ service_id: serviceId }),
    }),
  start: (counterId: number) => request<Token>(`/api/staff/counters/${counterId}/start`, { method: 'POST' }),
  complete: (counterId: number) => request<Token>(`/api/staff/counters/${counterId}/complete`, { method: 'POST' }),
  skip: (counterId: number) => request<Token>(`/api/staff/counters/${counterId}/skip`, { method: 'POST' }),
  staffQueue: (officeId: number, serviceId: number) =>
    request<QueueSnapshot>(`/api/staff/queue?office_id=${officeId}&service_id=${serviceId}`),

  // Admin
  adminHealth: () => request<Record<string, unknown>>('/api/admin/health'),
  priorityRules: (officeId?: number) =>
    request<Record<string, unknown>[]>(`/api/admin/priority-rules${officeId ? `?office_id=${officeId}` : ''}`),
  createPriorityRule: (payload: Record<string, unknown>) =>
    request<Record<string, unknown>>('/api/admin/priority-rules', { method: 'POST', body: JSON.stringify(payload) }),
  recommendations: (officeId: number, refresh: boolean) =>
    request<{ generated: number; items: Record<string, unknown>[] }>(
      `/api/admin/recommendations?office_id=${officeId}&refresh=${refresh}`,
    ),
  decideRecommendation: (id: number, status: string) =>
    request<Record<string, unknown>>(`/api/admin/recommendations/${id}/decide?status=${status}`, { method: 'POST' }),
  auditLogs: (limit = 50) => request<Record<string, unknown>[]>(`/api/admin/audit-logs?limit=${limit}`),
  notifications: (limit = 50) => request<Record<string, unknown>[]>(`/api/admin/notifications?limit=${limit}`),
  retrain: () => request<Record<string, unknown>>('/api/admin/models/retrain', { method: 'POST' }),
  createIncident: (payload: Record<string, unknown>) => request<Record<string, unknown>>('/api/staff/incidents', { method: 'POST', body: JSON.stringify(payload) }),
  rebookArrivedIncidentTicket: (tokenId: number) => request<Record<string, unknown>>(`/api/staff/incidents/tokens/${tokenId}/transfer`, { method: 'POST' }),
  updateOfficeSchedule: (officeId: number, payload: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/api/admin/offices/${officeId}/schedule`, { method: 'PATCH', body: JSON.stringify(payload) }),
  officeHolidays: (officeId: number) => request<Record<string, unknown>[]>(`/api/admin/offices/${officeId}/holidays`),
  addOfficeHoliday: (officeId: number, holidayDate: string, name: string) =>
    request<Record<string, unknown>>(`/api/admin/offices/${officeId}/holidays`, { method: 'POST', body: JSON.stringify({ holiday_date: holidayDate, name }) }),
  deleteOfficeHoliday: (officeId: number, holidayId: number) =>
    request<Record<string, unknown>>(`/api/admin/offices/${officeId}/holidays/${holidayId}`, { method: 'DELETE' }),
  updateOfficeLocation: (officeId: number, address: string, locationInstructions: string) =>
    request<Record<string, unknown>>(`/api/admin/offices/${officeId}/location`, { method: 'PATCH', body: JSON.stringify({ address, location_instructions: locationInstructions }) }),

  // Analytics
  analytics: {
    overview: (officeId: number) =>
      request<Record<string, number>>(`/api/analytics/overview?office_id=${officeId}`),
    peakHours: (officeId: number) =>
      request<{ hours: { hour: number; avg_queue: number; avg_wait_min: number }[] }>(
        `/api/analytics/peak-hours?office_id=${officeId}`,
      ),
    demand: (officeId: number) =>
      request<{ series: { day: string; tokens: number }[] }>(`/api/analytics/demand?office_id=${officeId}`),
    efficiency: (officeId: number) =>
      request<{ services: Record<string, unknown>[] }>(`/api/analytics/efficiency?office_id=${officeId}`),
    sla: (officeId: number) => request<Record<string, number>>(`/api/analytics/sla?office_id=${officeId}`),
    feedback: (officeId: number) =>
      request<Record<string, unknown>>(`/api/analytics/feedback?office_id=${officeId}`),
  },
}

export type { Office, QueueSnapshot, Service, StaffCounter, Token }
