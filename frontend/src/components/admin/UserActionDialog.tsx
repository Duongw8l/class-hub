import { useState } from 'react'
import type { AdminUser } from '../../api/admin'
import { useResetPassword, useUpdateUser } from '../../hooks/useAdmin'
import { Modal } from '../Modal'
import { ErrorAlert, TempPasswordNotice } from './shared'
import { UserForm } from './UserForm'

export type UserAction = 'edit' | 'reset' | 'lock' | 'unlock'

interface UserActionDialogProps {
  action: UserAction
  user: AdminUser
  isSelf: boolean
  onClose: () => void
}

const TITLES: Record<Exclude<UserAction, 'edit'>, string> = {
  reset: 'Đặt lại mật khẩu',
  lock: 'Khoá tài khoản',
  unlock: 'Mở khoá tài khoản',
}

function confirmText(action: Exclude<UserAction, 'edit'>, user: AdminUser): string {
  if (action === 'reset') {
    return 'Mật khẩu hiện tại sẽ không dùng được nữa. Mật khẩu tạm mới chỉ hiện một lần.'
  }
  if (action === 'unlock') {
    return 'Người này sẽ đăng nhập lại được và chuyển về danh sách đang hoạt động.'
  }
  const duties =
    user.assignment_count > 0 || user.homeroom_class
      ? ' Họ còn phân công giảng dạy hoặc chủ nhiệm; hãy giao lại cho giáo viên khác.'
      : ''
  return `Người này sẽ bị đăng xuất ngay, không đăng nhập được và chuyển sang danh sách Đã khoá.${duties}`
}

// Hộp thoại cho các thao tác trên một tài khoản: sửa thông tin, đặt lại mật khẩu (xong thì hiện mật
// khẩu tạm ngay trong hộp), khoá, mở khoá. Đang gửi yêu cầu thì không đóng được.
export function UserActionDialog({ action, user, isSelf, onClose }: UserActionDialogProps) {
  const update = useUpdateUser()
  const reset = useResetPassword()
  const [password, setPassword] = useState<string | null>(null)

  if (password !== null) {
    return (
      <Modal title="Mật khẩu tạm mới" dismissable={false} onClose={onClose}>
        <TempPasswordNotice email={user.email} password={password} onDone={onClose} />
      </Modal>
    )
  }

  if (action === 'edit') {
    return (
      <Modal title={`Sửa tài khoản: ${user.full_name}`} size="lg" onClose={onClose}>
        <UserForm mode="edit" user={user} isSelf={isSelf} onDone={onClose} />
      </Modal>
    )
  }

  const busy = update.isPending || reset.isPending
  const error = update.error ?? reset.error

  function confirm() {
    if (action === 'reset') {
      reset.mutate(user.id, { onSuccess: (data) => setPassword(data.temporary_password) })
    } else {
      update.mutate({ id: user.id, body: { is_active: action === 'unlock' } }, { onSuccess: onClose })
    }
  }

  return (
    <Modal title={TITLES[action]} dismissable={!busy} onClose={onClose}>
      <div className="rounded-xl bg-slate-50 px-4 py-3 text-sm ring-1 ring-slate-200">
        <p className="font-medium">{user.full_name}</p>
        <p className="text-slate-500">{user.email}</p>
      </div>
      <p className="text-sm text-slate-700">{confirmText(action, user)}</p>
      {error && <ErrorAlert error={error} />}
      <div className="flex flex-wrap justify-end gap-3">
        {/* Khoá là thao tác có hậu quả: tiêu điểm đầu ở "Huỷ" để Enter không khoá nhầm. */}
        <button
          type="button"
          onClick={onClose}
          disabled={busy}
          className="btn-secondary"
          autoFocus={action === 'lock'}
        >
          Huỷ
        </button>
        <button
          type="button"
          onClick={confirm}
          disabled={busy}
          className={action === 'lock' ? 'btn-danger' : 'btn-primary'}
          autoFocus={action !== 'lock'}
        >
          {busy ? 'Đang xử lý…' : TITLES[action]}
        </button>
      </div>
    </Modal>
  )
}
