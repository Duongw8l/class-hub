import { apiGet, apiPut } from './client'

// Sửa / nhập tay điểm của một học sinh (D-115). Khớp backend/app/imports/manual_schemas.py.
export type AssessmentKind = 'tx' | 'gk' | 'ck'
export type CommentResult = 'pass' | 'fail'
export type ScoreChangeReason = 'retest' | 'makeup' | 'correction' | 'other'

export const REASON_OPTIONS: { value: ScoreChangeReason; label: string }[] = [
  { value: 'retest', label: 'Kiểm tra lại' },
  { value: 'makeup', label: 'Kiểm tra bù (đầu điểm còn thiếu)' },
  { value: 'correction', label: 'Nhập sai' },
  { value: 'other', label: 'Khác (ghi chú)' },
]

export interface ScoreEntry {
  kind: AssessmentKind
  seq: number
  score: number | null
  comment_result: CommentResult | null
}

export interface ScoreChange {
  semester: number
  kind: AssessmentKind
  seq: number
  old_score: number | null
  new_score: number | null
  old_comment_result: CommentResult | null
  new_comment_result: CommentResult | null
  reason: ScoreChangeReason
  reason_label: string
  note: string | null
  changed_by: string
  changed_at: string
}

export interface StudentScores {
  student_id: number
  student_code: string
  full_name: string
  subject_id: number
  subject_name: string
  is_comment_subject: boolean
  semester: number
  tx_slots: number
  entries: ScoreEntry[]
  can_edit: boolean
  history: ScoreChange[]
}

export interface ScoreEntryInput {
  kind: AssessmentKind
  seq: number
  score?: number
  comment_result?: CommentResult
}

export interface StudentScoresInput {
  semester: number
  entries: ScoreEntryInput[]
  reason: ScoreChangeReason
  note?: string
}

function path(classId: number, subjectId: number, studentId: number): string {
  return `/classes/${classId}/subjects/${subjectId}/students/${studentId}/scores`
}

export function fetchStudentScores(
  classId: number,
  subjectId: number,
  studentId: number,
  semester: number,
  signal?: AbortSignal,
): Promise<StudentScores> {
  return apiGet<StudentScores>(
    `${path(classId, subjectId, studentId)}?semester=${semester}`,
    signal,
  )
}

export function saveStudentScores(
  classId: number,
  subjectId: number,
  studentId: number,
  input: StudentScoresInput,
): Promise<StudentScores> {
  return apiPut<StudentScores>(path(classId, subjectId, studentId), input)
}
