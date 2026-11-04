import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { fetchMe } from '../api/auth'
import { ForcedPasswordChange } from '../components/auth/ForcedPasswordChange'
import { useAuth } from './context'

// Route cha của mọi trang cần đăng nhập: chưa có token thì chuyển về /login và nhớ trang đang mở.
// Đăng nhập bằng mật khẩu tạm thì chỉ hiện màn hình đặt mật khẩu mới (D-114).
export function RequireAuth() {
  const { token, logout } = useAuth()
  const location = useLocation()
  const queryClient = useQueryClient()
  const me = useQuery({
    queryKey: ['auth-me', token],
    queryFn: ({ signal }) => fetchMe(signal),
    enabled: token !== null,
  })

  if (token === null) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  if (me.isPending) {
    return (
      <div aria-live="polite" aria-busy="true" className="p-8 text-sm text-slate-500">
        Đang tải…
      </div>
    )
  }
  if (me.data?.must_change_password) {
    return (
      <ForcedPasswordChange
        user={me.data}
        onLogout={logout}
        onChanged={() => {
          // Bỏ mọi kết quả 403 cũ (nếu có) rồi nạp lại tài khoản: cờ đã tắt, vào ứng dụng.
          void queryClient.invalidateQueries()
        }}
      />
    )
  }
  // Lỗi mạng khi đọc /auth/me: vẫn vào ứng dụng, các trang tự báo lỗi tải của mình.
  return <Outlet />
}
