import { apiGet, apiPost, apiPut } from './client'
import type { ClassRef } from './auth'

// Rèn luyện của lớp chủ nhiệm (D-119). Khớp backend/app/imports/conduct_schemas.py.
export type ConductPeriod = 'hk1' | 'hk2' | 'year'
export type ConductLevel = 'good' | 'fair' | 'pass' | 'fail'
export type ConductChangeReason = 'review' | 'correction' | 'supplement' | 'other'

export const CONDUCT_PERIODS: ConductPeriod[] = ['hk1', 'hk2', 'year']
export const CONDUCT_LEVELS: ConductLevel[] = ['good', 'fair', 'pass', 'fail']

export const PERIOD_NAMES: Record<ConductPeriod, string> = {
  hk1: 'Học kỳ I',
  hk2: 'Học kỳ II',
  year: 'Cả năm',
}

export const CONDUCT_REASONS: { value: ConductChangeReason; label: string }[] = [
  { value: 'review', label: 'Xét lại' },
  { value: 'supplement', label: 'Bổ sung kết quả còn thiếu' },
  { value: 'correction', label: 'Nhập sai' },
  { value: 'other', label: 'Khác (ghi chú)' },
]

export interface ConductEntry {
  period: ConductPeriod
  level: ConductLevel | null
  comment: string | null
}

export interface ConductRow {
  student_id: number
  student_code: string
  full_name: string
  entries: ConductEntry[]
  change_count: number
}

export interface ClassConduct {
  class_info: ClassRef
  can_edit: boolean
  counts: Record<ConductPeriod, Record<ConductLevel | 'missing', number>>
  year_fillable: number
  rows: ConductRow[]
}

export interface ConductChange {
  period: ConductPeriod
  old_level: ConductLevel | null
  new_level: ConductLevel
  old_comment: string | null
  new_comment: string | null
  reason: ConductChangeReason
  reason_label: string
  note: string | null
  changed_by: string
  changed_at: string
}

export interface StudentConduct {
  student_id: number
  student_code: string
  full_name: string
  entries: ConductEntry[]
  can_edit: boolean
  history: ConductChange[]
}

export interface StudentConductInput {
  entries: { period: ConductPeriod; level: ConductLevel; comment: string | null }[]
  reason: ConductChangeReason
  note?: string
}

const studentPath = (classId: number, studentId: number) =>
  `/classes/${classId}/conduct/students/${studentId}`

export function fetchClassConduct(classId: number, signal?: AbortSignal) {
  return apiGet<ClassConduct>(`/classes/${classId}/conduct`, signal)
}

export function fetchStudentConduct(classId: number, studentId: number, signal?: AbortSignal) {
  return apiGet<StudentConduct>(studentPath(classId, studentId), signal)
}

export function saveStudentConduct(classId: number, studentId: number, input: StudentConductInput) {
  return apiPut<StudentConduct>(studentPath(classId, studentId), input)
}

export function fillYearFromHk2(classId: number) {
  return apiPost<{ filled: number }>(`/classes/${classId}/conduct/year-from-hk2`, {})
}
