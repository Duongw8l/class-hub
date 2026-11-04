import { useMemo, useState } from 'react'
import type { AdminUser } from '../../api/admin'
import type { UserRole } from '../../api/auth'
import { ROLE_OPTIONS, roleText } from './roles'
import type { UserAction } from './UserActionDialog'

interface UserTableProps {
  users: AdminUser[]
  selfId: number
  // 'active': Sửa, Đặt lại mật khẩu, Khoá. 'locked': Sửa, Mở khoá.
  variant: 'active' | 'locked'
  onAction: (action: UserAction, user: AdminUser) => void
  // Tiền tố id cho ô lọc, để hai bảng trên cùng trang không trùng id.
  idPrefix: string
}

function dutiesText(user: AdminUser): string {
  if (user.role !== 'teacher') return '—'
  const parts: string[] = []
  if (user.homeroom_class) parts.push(`Chủ nhiệm ${user.homeroom_class}`)
  if (user.assignment_count > 0) parts.push(`${user.assignment_count} lớp–môn`)
  return parts.length > 0 ? parts.join(', ') : 'Chưa phân công'
}

// Danh sách tài khoản với bộ lọc. Mọi thao tác (sửa, đặt lại mật khẩu, khoá, mở khoá) mở hộp thoại
// riêng ở trang cha; bảng không tự gọi API.
export function UserTable({ users, selfId, variant, onAction, idPrefix }: UserTableProps) {
  const [text, setText] = useState('')
  const [role, setRole] = useState<UserRole | ''>('')

  const shown = useMemo(() => {
    const needle = text.trim().toLowerCase()
    return users.filter(
      (user) =>
        (role === '' || user.role === role) &&
        (needle === '' ||
          user.full_name.toLowerCase().includes(needle) ||
          user.email.toLowerCase().includes(needle) ||
          (user.specialty?.toLowerCase().includes(needle) ?? false) ||
          (user.note?.toLowerCase().includes(needle) ?? false)),
    )
  }, [users, text, role])

  if (users.length === 0) {
    return (
      <p className="text-sm text-slate-600">
        {variant === 'locked'
          ? 'Chưa có tài khoản nào bị khoá.'
          : 'Chưa có tài khoản nào đang hoạt động.'}
      </p>
    )
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:max-w-3xl">
        <div>
          <label htmlFor={`${idPrefix}-loc-ten`} className="label">
            Tìm theo tên, email, môn hoặc ghi chú
          </label>
          <input
            id={`${idPrefix}-loc-ten`}
            type="search"
            value={text}
            onChange={(event) => setText(event.target.value)}
            className="input mt-1"
          />
        </div>
        <div>
          <label htmlFor={`${idPrefix}-loc-vai-tro`} className="label">
            Vai trò
          </label>
          <select
            id={`${idPrefix}-loc-vai-tro`}
            value={role}
            onChange={(event) => setRole(event.target.value as UserRole | '')}
            className="input mt-1"
          >
            <option value="">Tất cả</option>
            {ROLE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <p aria-live="polite" className="text-sm text-slate-500">
        Hiện {shown.length} / {users.length} tài khoản.
      </p>

      <div className="overflow-x-auto">
        <table className="data-table min-w-max">
          <thead>
            <tr>
              <th scope="col" className="py-2 pr-4 font-medium">
                Người dùng
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                Vai trò
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                Công việc
              </th>
              <th scope="col" className="py-2 pl-3 font-medium">
                <span className="sr-only">Thao tác</span>
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 align-top">
            {shown.map((user) => {
              const self = user.id === selfId
              return (
                <tr key={user.id}>
                  <th scope="row" className="py-2 pr-4 text-left font-normal">
                    <span className="block font-medium">
                      {user.full_name}
                      {self && <span className="ml-2 text-xs font-normal text-slate-500">(bạn)</span>}
                    </span>
                    <span className="block text-xs text-slate-500">{user.email}</span>
                    {user.note && (
                      // Ghi chú dài (danh sách lớp) xuống dòng thay vì kéo giãn cả cột.
                      <span className="block max-w-md text-xs whitespace-normal text-slate-500 italic">
                        {user.note}
                      </span>
                    )}
                  </th>
                  <td className="px-3 py-2">
                    {roleText(user.role, user.role_label, user.specialty)}
                  </td>
                  <td className="px-3 py-2">{dutiesText(user)}</td>
                  <td className="py-2 pl-3">
                    <span className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => onAction('edit', user)}
                        aria-label={`Sửa ${user.full_name}`}
                        className="btn-secondary px-3 py-1.5"
                      >
                        Sửa
                      </button>
                      {variant === 'active' ? (
                        <>
                          <button
                            type="button"
                            onClick={() => onAction('reset', user)}
                            aria-label={`Đặt lại mật khẩu của ${user.full_name}`}
                            className="btn-secondary px-3 py-1.5"
                          >
                            Đặt lại mật khẩu
                          </button>
                          <button
                            type="button"
                            disabled={self}
                            title={self ? 'Không thể khoá chính mình' : undefined}
                            onClick={() => onAction('lock', user)}
                            aria-label={`Khoá ${user.full_name}`}
                            className="btn-secondary px-3 py-1.5 text-red-700"
                          >
                            Khoá
                          </button>
                        </>
                      ) : (
                        <button
                          type="button"
                          onClick={() => onAction('unlock', user)}
                          aria-label={`Mở khoá ${user.full_name}`}
                          className="btn-secondary px-3 py-1.5"
                        >
                          Mở khoá
                        </button>
                      )}
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {shown.length === 0 && (
        <p className="text-sm text-slate-600">Không có tài khoản nào khớp bộ lọc.</p>
      )}
    </div>
  )
}
