import { apiDelete, apiGet, apiPatch, apiPost, apiPut, apiUpload } from './client'
import type { UserRole } from './auth'
import { withYear } from './years'

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
  // Nhãn nhận diện (không cấp quyền): bộ môn và ghi chú, để phân biệt giáo viên trùng tên.
  specialty_subject_id: number | null
  specialty: string | null
  note: string | null
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
  // null = xoá nhãn (khác các trường trên, nơi vắng mặt = không đổi).
  specialty_subject_id?: number | null
  note?: string | null
}

// Một trong 17 môn GDPT 2018 có sẵn; dùng cho vai trò "Giáo viên <môn>".
export interface Subject {
  id: number
  name: string
  is_elective: boolean
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
  // Môn của giáo viên ("Giáo viên Toán"): hiện cạnh tên, và đưa GV đúng môn lên đầu khi phân công.
  specialty_subject_id: number | null
  specialty: string | null
}

export interface SchoolYear {
  id: number
  name: string
  start_date: string
  end_date: string
  is_current: boolean
}

export interface SchoolYearInput {
  name: string
  start_date: string
  end_date: string
}

export interface SchoolYearCreated {
  school_year: SchoolYear
  classes_created: number
  students_promoted: number
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
  school_year: SchoolYear | null // năm đang xem (mặc định năm hiện hành)
  years: SchoolYear[] // mọi năm học, mới nhất trước
  classes: AdminClass[] // các lớp của năm đang xem
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
  specialty_subject_id?: number | null
  note?: string | null
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
  specialty: string | null
  note: string | null
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

export function fetchSchool(yearId: number | null, signal?: AbortSignal): Promise<School> {
  return apiGet<School>(withYear('/admin/school', yearId), signal)
}

// `homeroom_class` là lớp chủ nhiệm trong năm được chọn (mỗi năm mỗi GV chủ nhiệm một lớp).
export function fetchTeachers(yearId: number | null, signal?: AbortSignal): Promise<Teacher[]> {
  return apiGet<Teacher[]>(withYear('/admin/teachers', yearId), signal)
}

export function fetchSubjects(signal?: AbortSignal): Promise<Subject[]> {
  return apiGet<Subject[]>('/admin/subjects', signal)
}


// Tạo năm học đầu tiên của trường (thành năm hiện hành).
export function saveSchoolYear(body: SchoolYearInput): Promise<SchoolYear> {
  return apiPut<SchoolYear>('/admin/school-year', body)
}

// Tạo thêm một năm học; `rollover`: chép lớp từ năm trước và cho học sinh lên lớp (D-113).
export function createSchoolYear(
  body: SchoolYearInput & { make_current: boolean; rollover: boolean },
): Promise<SchoolYearCreated> {
  return apiPost<SchoolYearCreated>('/admin/school-years', body)
}

export function updateSchoolYear(id: number, body: SchoolYearInput): Promise<SchoolYear> {
  return apiPatch<SchoolYear>(`/admin/school-years/${id}`, body)
}

export function setCurrentYear(id: number): Promise<SchoolYear> {
  return apiPost<SchoolYear>(`/admin/school-years/${id}/current`, undefined)
}

export function createClass(body: {
  grade_level: number
  name: string
  homeroom_teacher_id: number | null
  school_year_id: number | null // năm học của lớp; null là năm hiện hành
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
