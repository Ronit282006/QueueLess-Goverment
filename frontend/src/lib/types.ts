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
  working_hours: string
  working_days: string
  sla_target_wait_min: number
  no_show_grace_min: number
  eta_alert_threshold_min: number
  arrival_buffer_min: number
  incident_response_min: number
  departments: Department[]
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
}

export type StaffAssignment = {
  office_id: number
  counter_id: number | null
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
