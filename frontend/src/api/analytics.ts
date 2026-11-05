import type { AlertCounts, ProfileAlert } from './warning'
import type { ClassRef } from './auth'
import { apiGet } from './client'
import { withYear } from './years'

// Khớp schema của back-end (backend/app/analytics/schemas.py). Điểm là số thực trong JSON; giao diện
// chỉ định dạng (lib/format.ts), không tính lại.
export type Period = '1' | '2' | 'year'
export type AssessmentType = 'score' | 'comment'
export type CommentResult = 'pass' | 'fail'

export interface Thresholds {
  fail: number
  passing: number
  fair: number
  good: number
}

export interface MonthAbsence {
  month: string // YYYY-MM
  excused: number
  unexcused: number
  total: number
}

export interface AbsenceLimits {
  notice: number
  maximum: number
}

// --- Dashboard lớp ---

export interface SubjectStat {
  subject_id: number
  name: string
  assessment_type: AssessmentType
  student_count: number
  mean: number | null
  below_pass: number
  below_fail: number
  comment_fail: number
  incomplete: number
}

export interface Attention {
  student_id: number
  student_code: string
  full_name: string
  absent_sessions: number
  reasons: string[]
}

export interface Dashboard {
  class_info: ClassRef
  period: Period
  student_count: number
  learning_levels: Record<string, number>
  conduct_levels: Record<string, number>
  conduct_derived_count: number
  absent_notice_students: number
  absent_over_limit_students: number
  subjects: SubjectStat[]
  attention: Attention[]
  promotion: PromotionCounts | null
  absences_by_month: MonthAbsence[]
  absence_limits: AbsenceLimits
  thresholds: Thresholds
  alert_counts: AlertCounts
}

// --- Bảng điểm môn ---

export interface ScoreRow {
  student_id: number
  student_code: string
  full_name: string
  tx: number[]
  tx_missing: number
  midterm: number | null
  final: number | null
  average: number | null
  comment_result: CommentResult | null
  complete: boolean
  average_semester1: number | null
  average_semester2: number | null
  year_average: number | null
}

export interface SubjectScores {
  class_info: ClassRef
  subject: {
    id: number
    name: string
    assessment_type: AssessmentType
    periods_per_year: number
    regular_required: number
  }
  semester: number
  thresholds: Thresholds
  student_count: number
  mean: number | null
  distribution: {
    below_fail: number
    fail_to_pass: number
    pass_to_fair: number
    fair_to_good: number
    at_least_good: number
  }
  incomplete_count: number
  comment_fail_count: number
  rows: ScoreRow[]
}

// --- Tổng quan khối ---

export interface ClassOverview {
  class_id: number
  name: string
  student_count: number
  learning_levels: Record<string, number>
  conduct_levels: Record<string, number>
  absent_notice_students: number
  absent_over_limit_students: number
  below_fail_students: number
  // Chỉ khi xem cả năm (null ở học kỳ I, II).
  promotion: PromotionCounts | null
}

export interface PromotionCounts {
  eligible: number
  not_eligible: number
  unknown: number
}

export interface GradeOverview {
  grade_level: number
  period: Period
  classes: ClassOverview[]
  // Mọi môn của khối (D-116), môn điểm số trước; class_means chỉ có các lớp học môn đó.
  subjects: GradeSubject[]
}

export interface GradeSubject {
  subject_id: number
  name: string
  assessment_type: 'score' | 'comment'
  class_count: number
  class_means: ClassSubjectResult[]
}

export interface ClassSubjectResult {
  class_id: number
  mean: number | null
  comment_pass: number
  comment_fail: number
}

// --- Hồ sơ học sinh ---

export interface ProfileSemester {
  semester: number
  tx: number[]
  tx_missing: number
  midterm: number | null
  final: number | null
  average: number | null
  comment_result: CommentResult | null
  complete: boolean
}

export interface ProfileSubject {
  subject_id: number
  name: string
  assessment_type: AssessmentType
  periods_per_year: number
  regular_required: number
  semesters: ProfileSemester[]
  year_average: number | null
  year_comment_result: CommentResult | null
}

interface ProfileBase {
  class_info: ClassRef
  student: { id: number; student_code: string; full_name: string }
  subjects: ProfileSubject[]
  thresholds: Thresholds
}

export interface StudentProfileFull extends ProfileBase {
  scope: 'full'
  period: Period
  guardian_name: string | null
  guardian_phone: string | null
  learning: {
    level: string | null
    base_level: string | null
    adjusted: boolean
    incomplete_subjects: string[]
    below_fail_subjects: string[]
    below_pass_subjects: string[]
    failed_comment_subjects: string[]
  }
  conduct: { level: string | null; derived: boolean }
  attendance: {
    excused: number
    unexcused: number
    late: number
    absent_total: number
    school_duty: number // vắng do nhà trường cử đi, không tính buổi nghỉ (D-120)
    limits: AbsenceLimits
    by_month: MonthAbsence[]
  }
  promotion: {
    eligible: boolean | null
    reasons: string[]
    retake_subjects: { subject_id: number; name: string; reason: string }[]
  } | null
  attention_reasons: string[]
  // Cảnh báo sớm hiện hành (null: chưa chạy cảnh báo).
  alert: ProfileAlert | null
}

// GVBM nhận hồ sơ không có các khoá phụ huynh, chuyên cần, rèn luyện, xếp loại (không phải khoá rỗng).
export interface StudentProfileSubjects extends ProfileBase {
  scope: 'subjects'
}

export type StudentProfile = StudentProfileFull | StudentProfileSubjects

export function fetchDashboard(classId: number, period: Period, signal?: AbortSignal) {
  return apiGet<Dashboard>(`/classes/${classId}/dashboard?semester=${period}`, signal)
}

export function fetchSubjectScores(
  classId: number,
  subjectId: number,
  semester: 1 | 2,
  signal?: AbortSignal,
) {
  return apiGet<SubjectScores>(
    `/classes/${classId}/subjects/${subjectId}/scores?semester=${semester}`,
    signal,
  )
}

export function fetchGradeOverview(
  level: number,
  period: Period,
  yearId: number | null,
  signal?: AbortSignal,
) {
  return apiGet<GradeOverview>(
    withYear(`/grades/${level}/overview?semester=${period}`, yearId),
    signal,
  )
}

export function fetchStudentProfile(
  classId: number,
  studentId: number,
  period: Period,
  signal?: AbortSignal,
) {
  return apiGet<StudentProfile>(
    `/classes/${classId}/students/${studentId}/profile?semester=${period}`,
    signal,
  )
}

// --- Học sinh cần hỗ trợ trong một môn (GVBM, D-118) ---
// Chỉ dựa trên điểm của chính môn đó; mọi lý do, mức và thống kê do back-end tính.

export type SupportLevel = 'high' | 'medium' | 'low'

export interface SupportReason {
  code: string
  level: SupportLevel
  message: string
}

export interface SupportStudent {
  student_id: number
  student_code: string
  full_name: string
  level: SupportLevel
  reasons: SupportReason[]
  average: number | null
  average_semester1: number | null
  comment_result: CommentResult | null
}

export interface ComponentStat {
  count: number
  mean: number | null
  below_pass: number
}

export interface SubjectSupport {
  class_info: ClassRef
  subject: SubjectScores['subject']
  semester: number
  thresholds: Thresholds
  student_count: number
  mean: number | null
  distribution: SubjectScores['distribution']
  counts: Record<SupportLevel, number>
  students: SupportStudent[]
  advanced_students: { student_id: number; student_code: string; full_name: string; average: number | null }[]
  stats: {
    regular: ComponentStat
    midterm: ComponentStat
    final: ComponentStat
    support_group: number
    advanced_group: number
    previous_mean: number | null
    comment_pass: number
    comment_fail: number
    comment_missing: number
  }
}

export interface MySupport {
  school_year_id: number | null
  items: SubjectSupport[]
}

// `semester` null: học kỳ II nếu môn đã có điểm học kỳ II, không thì học kỳ I (back-end chọn).
export function fetchSubjectSupport(
  classId: number,
  subjectId: number,
  semester: 1 | 2 | null,
  signal?: AbortSignal,
) {
  const query = semester === null ? '' : `?semester=${semester}`
  return apiGet<SubjectSupport>(`/classes/${classId}/subjects/${subjectId}/support${query}`, signal)
}

export function fetchMySupport(semester: 1 | 2 | null, yearId: number | null, signal?: AbortSignal) {
  const query = semester === null ? '/me/support' : `/me/support?semester=${semester}`
  return apiGet<MySupport>(withYear(query, yearId), signal)
}
