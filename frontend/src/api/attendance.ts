import { apiDelete, apiGet, apiPut } from './client'
import type { ClassRef } from './auth'

// Điểm danh ngày (GVCN), theo tiết (GVBM) và đối chiếu (D-120). Khớp backend/app/attendance/schemas.py.
export type AttendanceStatus =
  | 'present'
  | 'absent_excused'
  | 'absent_unexcused'
  | 'late'
  | 'school_duty'
export type LessonStatus = 'absent_excused' | 'absent_unexcused' | 'late'
export type AbsenceReason = 'sick' | 'family' | 'competition' | 'school_activity' | 'other'
export type AbsenceLevel = 'over' | 'high' | 'notice'

export const STATUS_LABELS: Record<AttendanceStatus, string> = {
  present: 'Có mặt',
  late: 'Muộn',
  absent_excused: 'Nghỉ có phép',
  absent_unexcused: 'Nghỉ không phép',
  school_duty: 'Vắng do trường cử đi',
}

// Ký hiệu trên lưới tháng (luôn kèm chú giải, không chỉ dựa vào màu).
export const STATUS_SYMBOLS: Record<AttendanceStatus, string> = {
  present: '',
  late: 'M',
  absent_excused: 'P',
  absent_unexcused: 'K',
  school_duty: 'CĐ',
}

export const REASON_LABELS: Record<AbsenceReason, string> = {
  sick: 'Ốm, khám bệnh',
  family: 'Việc gia đình',
  competition: 'Thi học sinh giỏi, thi đấu',
  school_activity: 'Hoạt động do trường cử',
  other: 'Khác (ghi chú)',
}
export const REASONS = Object.keys(REASON_LABELS) as AbsenceReason[]

export interface AbsenceLimits {
  notice: number
  high: number
  maximum: number
}

export interface YearAbsence {
  excused: number
  unexcused: number
  late: number
  school_duty: number
  absent_total: number
  level: AbsenceLevel | null
}

export interface DayCell {
  date: string
  status: AttendanceStatus
  reason: AbsenceReason | null
  note: string | null
}

export interface AttendanceRow {
  student_id: number
  student_code: string
  full_name: string
  cells: DayCell[]
  year: YearAbsence
}

export interface Mismatch {
  kind: 'lesson_absent_day_present' | 'day_absent_lesson_present'
  student_id: number
  student_code: string
  full_name: string
  date: string
  subject_name: string
  lesson_no: number
  lesson_status: AttendanceStatus
  day_status: AttendanceStatus | null
}

export interface ClassAttendance {
  class_info: ClassRef
  month: string
  months: string[]
  days: string[]
  limits: AbsenceLimits
  can_edit: boolean
  counts: Record<AbsenceLevel, number>
  rows: AttendanceRow[]
  mismatches: Mismatch[]
}

export interface DayEntry {
  student_id: number
  student_code: string
  full_name: string
  status: AttendanceStatus | null
  reason: AbsenceReason | null
  note: string | null
  lesson_marks: string[]
}

export interface AttendanceChange {
  student_id: number
  full_name: string
  old_status: AttendanceStatus | null
  new_status: AttendanceStatus
  old_reason: AbsenceReason | null
  new_reason: AbsenceReason | null
  note: string | null
  changed_by: string
  changed_at: string
}

export interface DayAttendance {
  class_info: ClassRef
  date: string
  can_edit: boolean
  entries: DayEntry[]
  history: AttendanceChange[]
}

export interface EntryInput {
  student_id: number
  status: AttendanceStatus
  reason: AbsenceReason | null
  note: string | null
}

export interface LessonSummary {
  date: string
  lesson_no: number
  excused: number
  unexcused: number
  late: number
  recorded_by: string
  updated_at: string
}

export interface SubjectLessons {
  class_info: ClassRef
  subject_id: number
  subject_name: string
  can_edit: boolean
  month: string
  months: string[]
  lesson_count: number
  lessons: LessonSummary[]
  students: {
    student_id: number
    student_code: string
    full_name: string
    excused: number
    unexcused: number
    late: number
  }[]
}

export interface LessonDetail {
  class_info: ClassRef
  subject_id: number
  subject_name: string
  date: string
  lesson_no: number
  exists: boolean
  taken_by: string | null
  can_edit: boolean
  entries: {
    student_id: number
    student_code: string
    full_name: string
    status: AttendanceStatus
    reason: AbsenceReason | null
    note: string | null
  }[]
}

const monthQuery = (month: string | null) => (month ? `?month=${month}` : '')

export function fetchClassAttendance(classId: number, month: string | null, signal?: AbortSignal) {
  return apiGet<ClassAttendance>(`/classes/${classId}/attendance${monthQuery(month)}`, signal)
}

export function fetchDay(classId: number, day: string, signal?: AbortSignal) {
  return apiGet<DayAttendance>(`/classes/${classId}/attendance/days/${day}`, signal)
}

export function saveDay(classId: number, day: string, entries: EntryInput[]) {
  return apiPut<DayAttendance>(`/classes/${classId}/attendance/days/${day}`, { entries })
}

export function fetchSubjectLessons(
  classId: number,
  subjectId: number,
  month: string | null,
  signal?: AbortSignal,
) {
  return apiGet<SubjectLessons>(
    `/classes/${classId}/subjects/${subjectId}/lessons${monthQuery(month)}`,
    signal,
  )
}

const lessonPath = (classId: number, subjectId: number, day: string, lessonNo: number) =>
  `/classes/${classId}/subjects/${subjectId}/lessons/${day}/${lessonNo}`

export function fetchLesson(
  classId: number,
  subjectId: number,
  day: string,
  lessonNo: number,
  signal?: AbortSignal,
) {
  return apiGet<LessonDetail>(lessonPath(classId, subjectId, day, lessonNo), signal)
}

export function saveLesson(
  classId: number,
  subjectId: number,
  day: string,
  lessonNo: number,
  entries: EntryInput[],
) {
  return apiPut<LessonDetail>(lessonPath(classId, subjectId, day, lessonNo), { entries })
}

export function deleteLesson(classId: number, subjectId: number, day: string, lessonNo: number) {
  return apiDelete<{ deleted: boolean }>(lessonPath(classId, subjectId, day, lessonNo))
}

// "2026-10-05" thành "05/10"; "2026-10" thành "Tháng 10/2026".
export function shortDate(iso: string): string {
  const [, month, day] = iso.split('-')
  return `${day}/${month}`
}

export function weekday(iso: string): string {
  const names = ['CN', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7']
  return names[new Date(`${iso}T00:00:00`).getDay()]
}

export function todayIso(): string {
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}
