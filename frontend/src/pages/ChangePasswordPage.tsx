import { ChangePasswordForm } from '../components/auth/ChangePasswordForm'
import { PageTitle, Panel } from '../components/Panel'

// Đổi mật khẩu của chính mình, cho mọi vai trò (D-097).
export default function ChangePasswordPage() {
  return (
    <>
      <PageTitle title="Đổi mật khẩu" />
      <Panel
        id="doi-mat-khau"
        title="Mật khẩu của bạn"
        description="Dùng mật khẩu dài, khó đoán và không dùng lại ở nơi khác."
      >
        <ChangePasswordForm />
      </Panel>
    </>
  )
}
