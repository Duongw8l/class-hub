import { apiDelete, apiGet, apiPatch, apiPost, apiPut, apiUpload } from './client'
import type { UserRole } from './auth'

// Khớp schema của back-end: backend/app/auth/admin_schemas.py, backend/app/classes/admin_schemas.py.
// Chỉ Admin gọi được các endpoint này (back-end kiểm lại ở mọi yêu cầu).

export interface AdminUser {
  id: number
  email: string
  full_name: string
  role: UserRole
  role_label: string
  is_active: boolean
  homeroom_class: string | null
  assignment_count: number
}

export interface CreatedUser {
  user: AdminUser
  // Chỉ có trong phản hồi này: không thể xem lại sau đó.
  temporary_password: string
}

export interface UserUpdate {
  email?: string
  full_name?: string
  role?: UserRole
  is_active?: boolean
}

export interface TeacherRef {
  id: number
  full_name: string
}

export interface Teacher {
  id: number
  full_name: string
  email: string
  homeroom_class: string | null
}

export interface SchoolYear {
  id: number
  name: string
  start_date: string
  end_date: string
}

export interface AdminClass {
  id: number
  name: string
  grade_level: number
  homeroom_teacher: TeacherRef | null
  student_count: number
  assigned_subject_count: number
}

export interface School {
  school_year: SchoolYear | null
  classes: AdminClass[]
  subject_count: number
}

export interface AssignmentRow {
  subject_id: number
  subject_name: string
  is_elective: boolean
  assessment_type: 'score' | 'comment'
  teacher: TeacherRef | null
}

export interface ClassAssignments {
  class_id: number
  class_name: string
  grade_level: number
  subjects: AssignmentRow[]
}

export function fetchAdminUsers(signal?: AbortSignal): Promise<AdminUser[]> {
  return apiGet<AdminUser[]>('/admin/users', signal)
}

export function createUser(body: {
  email: string
  full_name: string
  role: UserRole
}): Promise<CreatedUser> {
  return apiPost<CreatedUser>('/admin/users', body)
}

export function updateUser(id: number, body: UserUpdate): Promise<AdminUser> {
  return apiPatch<AdminUser>(`/admin/users/${id}`, body)
}

export function resetPassword(id: number): Promise<{ temporary_password: string }> {
  return apiPost<{ temporary_password: string }>(`/admin/users/${id}/reset-password`, undefined)
}

// --- Nhập giáo viên từ tệp (khớp backend/app/auth/admin_schemas.py) ---

export type UserImportStatus = 'ok' | 'warning' | 'error'

export interface UserImportMessage {
  column: string | null
  message: string
}

export interface UserImportRow {
  line: number
  full_name: string | null
  email: string | null
  role: UserRole | null
  role_label: string | null
  status: UserImportStatus
  action: 'new' | null
  messages: UserImportMessage[]
}

export interface UserImportField {
  name: string
  label: string
  required: boolean
  column: string | null
}

export interface UserImportSummary {
  total_rows: number
  error_rows: number
  warning_rows: number
  new_rows: number
  has_changes: boolean
}

export interface UserImportPreview {
  job_id: string | null
  file_name: string
  header_line: number
  detected_columns: string[]
  fields: UserImportField[]
  missing_required: string[]
  ignored_columns: string[]
  notes: string[]
  summary: UserImportSummary
  can_confirm: boolean
  expires_at: string | null
  rows: UserImportRow[]
  truncated: boolean
}

export interface CreatedCredential {
  full_name: string
  email: string
  role: UserRole
  role_label: string
  // Chỉ có trong phản hồi này: không thể xem lại sau đó.
  temporary_password: string
}

export interface UserImportConfirm {
  job_id: string
  status: 'previewed' | 'confirmed'
  created: number
  already_confirmed: boolean
  credentials: CreatedCredential[]
}

// Tải tệp giáo viên lên và nhận bản xem trước. Chưa tạo tài khoản nào.
export function previewUserImport(request: {
  file: File
  mapping?: Record<string, string | null>
  headerRow?: number
}): Promise<UserImportPreview> {
  const form = new FormData()
  form.append('file', request.file)
  if (request.mapping !== undefined) form.append('mapping', JSON.stringify(request.mapping))
  if (request.headerRow !== undefined) form.append('header_row', String(request.headerRow))
  return apiUpload<UserImportPreview>('/admin/users/import', form)
}

export function confirmUserImport(jobId: string): Promise<UserImportConfirm> {
  return apiPost<UserImportConfirm>(`/admin/users/import/${jobId}/confirm`, undefined)
}

export function fetchSchool(signal?: AbortSignal): Promise<School> {
  return apiGet<School>('/admin/school', signal)
}

export function fetchTeachers(signal?: AbortSignal): Promise<Teacher[]> {
  return apiGet<Teacher[]>('/admin/teachers', signal)
}

export function saveSchoolYear(body: {
  name: string
  start_date: string
  end_date: string
}): Promise<SchoolYear> {
  return apiPut<SchoolYear>('/admin/school-year', body)
}

export function createClass(body: {
  grade_level: number
  name: string
  homeroom_teacher_id: number | null
}): Promise<AdminClass> {
  return apiPost<AdminClass>('/admin/classes', body)
}

export function updateClass(
  id: number,
  body: { name?: string; homeroom_teacher_id?: number | null },
): Promise<AdminClass> {
  return apiPatch<AdminClass>(`/admin/classes/${id}`, body)
}

export function deleteClass(id: number): Promise<{ detail: string }> {
  return apiDelete<{ detail: string }>(`/admin/classes/${id}`)
}

export function fetchClassAssignments(
  classId: number,
  signal?: AbortSignal,
): Promise<ClassAssignments> {
  return apiGet<ClassAssignments>(`/admin/classes/${classId}/assignments`, signal)
}

export function setAssignment(
  classId: number,
  subjectId: number,
  teacherId: number,
): Promise<ClassAssignments> {
  return apiPut<ClassAssignments>(`/admin/classes/${classId}/assignments/${subjectId}`, {
    teacher_id: teacherId,
  })
}

export function removeAssignment(classId: number, subjectId: number): Promise<ClassAssignments> {
  return apiDelete<ClassAssignments>(`/admin/classes/${classId}/assignments/${subjectId}`)
}

export function copyAssignments(classId: number, fromClassId: number): Promise<{ copied: number }> {
  return apiPost<{ copied: number }>(`/admin/classes/${classId}/assignments/copy`, {
    from_class_id: fromClassId,
  })
}

export function removeStudent(classId: number, studentCode: string): Promise<{ detail: string }> {
  return apiPost<{ detail: string }>(`/admin/classes/${classId}/students/remove`, {
    student_code: studentCode,
  })
}
