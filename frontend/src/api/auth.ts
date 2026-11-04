import { apiGet, apiPost } from './client'
import { withYear } from './years'
import type { SchoolYear } from './years'

// Khớp schema của back-end (backend/app/auth/schemas.py, backend/app/classes/schemas.py).
export type UserRole = 'teacher' | 'principal' | 'admin'

export interface AuthUser {
  id: number
  email: string
  full_name: string
  role: UserRole
  // true: đang dùng mật khẩu tạm do Admin cấp, phải đặt mật khẩu mới trước khi dùng (D-114).
  must_change_password: boolean
}

export interface LoginResponse {
  access_token: string
  token_type: 'bearer'
  expires_in: number
  user: AuthUser
}

export interface ClassRef {
  id: number
  name: string
  grade_level: number
}

export interface TeachingItem {
  class_id: number
  class_name: string
  grade_level: number
  subject_id: number
  subject_name: string
}

export interface Assignments {
  user: AuthUser
  // Năm học của các danh sách dưới (năm đang chọn, mặc định năm hiện hành); null khi chưa có năm.
  school_year: SchoolYear | null
  homeroom_classes: ClassRef[]
  teaching: TeachingItem[]
  grades: number[]
}

export function login(email: string, password: string): Promise<LoginResponse> {
  return apiPost<LoginResponse>('/auth/login', { email, password }, { authenticated: false })
}

export function fetchAssignments(
  yearId: number | null,
  signal?: AbortSignal,
): Promise<Assignments> {
  return apiGet<Assignments>(withYear('/me/assignments', yearId), signal)
}

// Tài khoản của chính mình; vẫn trả lời khi còn dùng mật khẩu tạm (các API khác thì 403).
export function fetchMe(signal?: AbortSignal): Promise<AuthUser> {
  return apiGet<AuthUser>('/auth/me', signal)
}

// Tự đổi mật khẩu của chính mình (mọi vai trò). Back-end trả {detail} khi xong.
export function changePassword(
  currentPassword: string,
  newPassword: string,
): Promise<{ detail: string }> {
  return apiPost<{ detail: string }>('/auth/change-password', {
    current_password: currentPassword,
    new_password: newPassword,
  })
}
