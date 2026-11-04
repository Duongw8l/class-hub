import type { AuthUser } from '../../api/auth'
import { Icon } from '../Icon'
import { Logo } from '../Logo'
import { ThemeToggle } from '../layout/ThemeToggle'
import { ChangePasswordForm } from './ChangePasswordForm'

interface ForcedPasswordChangeProps {
  user: AuthUser
  onChanged: () => void
  onLogout: () => void
}

// Màn hình duy nhất khi người dùng đăng nhập bằng mật khẩu tạm do Admin cấp (tạo tài khoản, đặt lại
// mật khẩu, nhập từ tệp): phải đặt mật khẩu riêng rồi mới vào được ứng dụng (D-114). Back-end cũng
// trả 403 cho mọi API khác tới khi đổi xong, nên đây không chỉ là chặn ở giao diện.
export function ForcedPasswordChange({ user, onChanged, onLogout }: ForcedPasswordChangeProps) {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center justify-between px-4 py-4 sm:px-8">
        <Logo />
        <ThemeToggle />
      </header>
      <main id="noi-dung" className="flex flex-1 items-start justify-center px-4 py-8">
        <section
          aria-labelledby="dat-mat-khau-moi"
          className="w-full max-w-lg space-y-5 rounded-2xl border border-slate-200 bg-surface p-6 shadow-pop sm:p-8"
        >
          <div className="space-y-2">
            <h1 id="dat-mat-khau-moi" className="text-xl font-semibold text-slate-900">
              Đặt mật khẩu của riêng bạn
            </h1>
            <p className="text-sm text-slate-600">
              Xin chào <strong>{user.full_name}</strong> ({user.email}). Bạn đang đăng nhập bằng
              mật khẩu tạm do quản trị viên cấp. Hãy đặt một mật khẩu mới, dễ nhớ với bạn, để tiếp
              tục sử dụng.
            </p>
          </div>
          <p className="flex items-start gap-2 rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-900 ring-1 ring-amber-200">
            <Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0" />
            <span>
              Ô đầu tiên nhập đúng mật khẩu tạm bạn vừa dùng để đăng nhập. Mật khẩu mới phải khác
              mật khẩu tạm.
            </span>
          </p>
          <ChangePasswordForm currentLabel="Mật khẩu tạm" onChanged={onChanged} />
          <div className="border-t border-slate-200 pt-4">
            <button type="button" onClick={onLogout} className="btn-secondary">
              Đăng xuất
            </button>
          </div>
        </section>
      </main>
    </div>
  )
}
