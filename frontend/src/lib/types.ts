export type Role = 'CITIZEN' | 'STAFF' | 'ADMIN'

export interface User {
  id: number
  email: string
  full_name: string
  role: 'CITIZEN' | 'STAFF' | 'ADMIN'
  tags?: string[]
}

export interface AuthResponse {
  access_token: string
  token_type: string
  user: { id: number; email: string; full_name: string; role: string; tags?: string[] }
}

export interface Service {
  id: number
  code: string
  name: string
  description: string
  documents: string[]
  average_service_min: number
  is_active: boolean
}

export type Department = { id: number; name: string; description: string; services: Service[] }
export type Office = {
  id: number
  code: string
  name: string
  address: string
  location_instructions: string
  city?: string
  state?: string
  pincode?: string
  contact_email?: string
  contact_phone?: string
  description?: string
  latitude?: number | null
  longitude?: number | null
  open_time?: string
  close_time?: string
  working_hours: string
  working_days: string
  sla_target_wait_min: number
  no_show_grace_min: number
  eta_alert_threshold_min: number
  arrival_buffer_min: number
  incident_response_min: number
  is_active?: boolean
  departments: Department[]
}

export type AdminOffice = {
  id: number
  code: string
  name: string
  address: string
  city: string
  state: string
  pincode: string
  contact_email: string
  contact_phone: string
  description: string
  open_time: string
  close_time: string
  working_hours: string
  working_days: string
  latitude: number | null
  longitude: number | null
  is_active: boolean
  has_coordinates: boolean
  services_count: number
  counters_count: number
  active_counters_count: number
  staff_count: number
}

export type OfficeMetrics = {
  services_count: number
  counters_count: number
  active_counters_count: number
  staff_count: number
  queue_length: number
  today: { tokens_created: number; tokens_completed: number; tokens_cancelled: number }
}

export type AdminOfficeDetail = AdminOffice & { metrics: OfficeMetrics }

export type AdminOfficeService = {
  id: number
  code: string
  name: string
  description: string
  documents: string[]
  average_service_min: number
  is_active: boolean
  department_id: number
  department_name: string
  counter_ids: number[]
}

export type AdminDepartment = {
  id: number
  name: string
  description: string
  is_active: boolean
  services_count: number
}

export type OfficeServiceInput = {
  name: string
  code?: string | null
  description?: string
  average_service_min?: number
  documents?: string[]
  department_id?: number | null
  department_name?: string | null
  is_active?: boolean
}

export type AdminOfficeCounter = {
  id: number
  office_id: number
  number: number
  code: string | null
  name: string
  description: string
  status: string
  is_active: boolean
  service_ids: number[]
  staff: { user_id: number; email: string; full_name: string }[]
  updated_at: string | null
}

export type OfficeInput = {
  code: string
  name: string
  address?: string
  city?: string
  state?: string
  pincode?: string
  contact_email?: string
  contact_phone?: string
  description?: string
  open_time?: string
  close_time?: string
  working_days?: string[]
  latitude?: number | null
  longitude?: number | null
  is_active?: boolean
}

export type TravelEstimate = {
  available: boolean
  provider: string
  mode: string
  status: string
  distance_km: number | null
  duration_min: number | null
  message: string
  calculated_at: string
}

export type OfficeRecommendation = {
  office_id: number
  office_name: string
  office_address: string
  service_id: number
  queue_wait_min: number
  waiting: number
  active_counters: number
  has_coordinates: boolean
  travel: TravelEstimate | null
  total_min: number | null
  departure_in_min: number | null
  recommended: boolean
  note: string
}

export type OfficeAssessment = {
  office_id: number
  office_name: string
  offers_service: boolean
  is_best: boolean
  extra_min: number | null
  message: string
}

export type OfficeRecommendations = {
  service: { id: number; name: string }
  mode: string
  safety_buffer_min: number
  routing: { provider: string; mode: string; live: boolean; departure_buffer_min: number }
  offices: OfficeRecommendation[]
  best_office_id: number | null
  explanation: string
  selected?: OfficeRecommendation | null
  assessment?: OfficeAssessment | null
  origin?: { latitude: number; longitude: number }
}

export type DepartureGuidance = {
  token_id: number
  token_label: string
  office_id: number
  office_name: string
  eta_min: number
  safety_buffer_min: number
  mode: string
  expected_service_at: string
  travel: TravelEstimate | null
  departure_at: string | null
  leave_in_min: number | null
  available: boolean
  message: string
}

export type GraceInfo = {
  state: string
  started_at: string | null
  deadline: string | null
  remaining_sec: number | null
  grace_period_sec: number
  arrived: boolean
}

export type CounterGrace = {
  counter_id: number
  office_id?: number
  service_id: number | null
  previous_token: string | null
  next_token: Token | null
  grace: GraceInfo | null
}

export type Prediction = {
  minutes: number
  minutes_low: number
  minutes_high: number
  confidence: number
  people_ahead: number
  history_samples: number
  method: string
  factors?: { label: string; impact: number }[]
}

export type QueueToken = {
  id: number
  reference: string
  label: string
  status: string
  stage: string
  position: number
  eta_min: number
  grace_state?: string
  grace_deadline?: string | null
  grace_remaining_sec?: number | null
  arrived?: boolean
}

export type QueueSnapshot = {
  office_id: number
  waiting: number
  serving: number
  active_counters: number
  average_service_min: number
  tokens: QueueToken[]
  prediction: Prediction
}

export type Token = {
  id: number
  reference: string
  number: number
  label: string
  office_id: number
  office_name: string
  service_id: number
  service_name: string
  status: string
  stage: string
  stage_message: string
  counter_name: string | null
  people_ahead: number
  position: number
  eta_min: number
  expected_service_at: string | null
  qr_data_url: string | null
  prediction: Prediction
  scheduled_for?: string | null
  incident_id?: number | null
  incident_response_due?: string | null
  incident_response_status?: string
  grace?: GraceInfo
  cancellation_reason?: string
  cancelled_at?: string | null
  travel_min?: number | null
  travel_distance_km?: number | null
  travel_mode?: string
  travel_provider?: string
  next_grace?: GraceInfo & { token_label: string; token_reference: string; token_id: number }
}

export type StaffCounter = {
  id: number
  number: number
  name: string
  status: string
  office_id: number
  service_ids: number[]
  current_token: string | null
  current_status: string | null
}

export type AuthUser = { id: number; email: string; full_name: string; role: string }

export type StaffScope = {
  offices: number[]
  counters: number[]
  counters_by_office: Record<string, number[]>
  services: { id: number; name: string; office_id: number; department_name?: string }[]
}

export type StaffAssignment = {
  office_id: number
  counter_id: number | null
  service_ids: number[]
  title: string
  shift_start: string
  shift_end: string
  is_active: boolean
  created_at: string | null
  updated_at: string | null
}

export type StaffMember = {
  id: number
  email: string
  full_name: string
  role: string
  is_active: boolean
  created_at: string | null
  offices: number[]
  counters: number[]
  assignments: StaffAssignment[]
}

export type AdminCounter = {
  id: number
  number: number
  name: string
  status: string
  office_id: number
  staff: { user_id: number; email: string; full_name: string }[]
}

export type StaffOTPSendResult = { message: string; expires_in_seconds: number }
export type StaffOTPVerifyResult = { message: string; verified: boolean }
export type StaffCreatedResult = {
  id: number
  email: string
  full_name: string
  role: string
  is_active: boolean
  message: string
}
