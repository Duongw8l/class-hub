import type { UserRole } from '../../api/auth'

// Nhãn khớp backend/app/core/labels.py (UserRole); back-end cũng trả sẵn `role_label` cho từng tài khoản.
export const ROLE_OPTIONS: { value: UserRole; label: string }[] = [
  { value: 'teacher', label: 'Giáo viên' },
  { value: 'principal', label: 'Ban giám hiệu' },
  { value: 'admin', label: 'Quản trị viên' },
]

// Nhãn hiển thị "Giáo viên Toán" (D-112): vai trò Giáo viên kèm môn; các vai trò khác giữ nguyên.
export function roleText(role: UserRole, roleLabel: string, specialty: string | null): string {
  return role === 'teacher' && specialty ? `Giáo viên ${specialty}` : roleLabel
}

// Giá trị của ô "Vai trò" gộp: 'teacher' (chưa rõ môn), 'teacher:<id môn>', 'principal', 'admin'.
export type RoleChoice = string

export function toRoleChoice(role: UserRole, subjectId: number | null): RoleChoice {
  return role === 'teacher' && subjectId !== null ? `teacher:${subjectId}` : role
}

export function fromRoleChoice(choice: RoleChoice): { role: UserRole; subjectId: number | null } {
  if (choice.startsWith('teacher:')) {
    return { role: 'teacher', subjectId: Number(choice.slice('teacher:'.length)) }
  }
  return { role: choice as UserRole, subjectId: null }
}
