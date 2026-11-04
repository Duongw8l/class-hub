import { useState } from 'react'
import type { AdminUser, CreatedUser } from '../api/admin'
import { AdminGate, TempPasswordNotice } from '../components/admin/shared'
import { UserActionDialog } from '../components/admin/UserActionDialog'
import type { UserAction } from '../components/admin/UserActionDialog'
import { UserForm } from '../components/admin/UserForm'
import { UserImportWizard } from '../components/admin/UserImportWizard'
import { UserTable } from '../components/admin/UserTable'
import { Modal } from '../components/Modal'
import { PageTitle, Panel } from '../components/Panel'
import { QueryState } from '../components/QueryState'
import { useAdminUsers } from '../hooks/useAdmin'

// Quản lý tài khoản (Admin): tạo, sửa, đặt lại mật khẩu, khoá / mở khoá. Tài khoản không bị xoá vì
// điểm và nhật ký còn tham chiếu tới người dùng (D-096). Mật khẩu tạm chỉ hiện một lần (D-097).
// Sửa, đặt lại mật khẩu, khoá, mở khoá và mật khẩu tạm đều hiện trong hộp thoại; tài khoản bị khoá
// nằm ở danh sách riêng, mở bằng nút "Đã khoá" cạnh ô lọc Vai trò. Thêm tài khoản và nhập từ tệp đặt trên đầu để không phải cuộn qua danh sách.
export default function AdminUsersPage() {
  const users = useAdminUsers()
  const [dialog, setDialog] = useState<{ action: UserAction; user: AdminUser } | null>(null)
  const [created, setCreated] = useState<CreatedUser | null>(null)
  const [showLocked, setShowLocked] = useState(false)

  return (
    <AdminGate>
      {(admin) => (
        <>
          <PageTitle
            title="Tài khoản"
            subtitle="Giáo viên, Ban giám hiệu và quản trị viên. Giáo viên chủ nhiệm và giáo viên bộ môn được xác định theo phân công, không phải theo loại tài khoản."
          />
          <Panel
            id="them-tai-khoan"
            title="Thêm tài khoản"
            description="Sau khi tạo, hệ thống hiện mật khẩu tạm một lần để bạn đưa cho người dùng."
          >
            <UserForm mode="create" onCreated={setCreated} />
          </Panel>
          <Panel
            id="nhap-giao-vien"
            title="Nhập giáo viên từ tệp"
            description="Tải tệp Excel/CSV để tạo nhiều tài khoản giáo viên cùng lúc. Mỗi tài khoản được cấp một mật khẩu tạm, hiện một lần kèm nút tải CSV."
          >
            <UserImportWizard />
          </Panel>
          <QueryState query={users}>
            {(data) => {
              const active = data.filter((user) => user.is_active)
              const locked = data.filter((user) => !user.is_active)
              const open = (action: UserAction, user: AdminUser) => setDialog({ action, user })
              // Một khung, nút cạnh ô Vai trò chuyển qua lại giữa hai danh sách: không phải cuộn
              // hết danh sách đang hoạt động mới tới tài khoản đã khoá.
              const toggle = (
                <button
                  type="button"
                  onClick={() => setShowLocked((current) => !current)}
                  aria-pressed={showLocked}
                  className={showLocked ? 'btn-secondary' : 'btn-secondary text-red-700'}
                >
                  {showLocked
                    ? `← Đang hoạt động (${active.length})`
                    : `Đã khoá (${locked.length})`}
                </button>
              )
              return showLocked ? (
                <Panel
                  id="da-khoa"
                  title={`Đã khoá (${locked.length})`}
                  description="Tài khoản bị khoá không đăng nhập được. Mở khoá để dùng lại; tài khoản không bị xoá vì điểm và nhật ký còn tham chiếu tới họ."
                >
                  <UserTable
                    key="locked"
                    users={locked}
                    selfId={admin.id}
                    variant="locked"
                    onAction={open}
                    idPrefix="da-khoa"
                    extraControl={toggle}
                  />
                </Panel>
              ) : (
                <Panel id="dang-hoat-dong" title={`Đang hoạt động (${active.length})`}>
                  <UserTable
                    key="active"
                    users={active}
                    selfId={admin.id}
                    variant="active"
                    onAction={open}
                    idPrefix="hoat-dong"
                    extraControl={toggle}
                  />
                </Panel>
              )
            }}
          </QueryState>

          {dialog && (
            <UserActionDialog
              key={`${dialog.action}-${dialog.user.id}`}
              action={dialog.action}
              user={dialog.user}
              isSelf={dialog.user.id === admin.id}
              onClose={() => setDialog(null)}
            />
          )}
          {created && (
            <Modal title="Đã tạo tài khoản" dismissable={false} onClose={() => setCreated(null)}>
              <TempPasswordNotice
                email={created.user.email}
                password={created.temporary_password}
                onDone={() => setCreated(null)}
              />
            </Modal>
          )}
        </>
      )}
    </AdminGate>
  )
}
