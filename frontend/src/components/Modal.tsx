import { useEffect, useId, useRef } from 'react'
import type { ReactNode } from 'react'
import { Icon } from './Icon'

interface ModalProps {
  title: string
  onClose: () => void
  children: ReactNode
  // false: không đóng bằng Esc, bấm nền hay nút ×; chỉ đóng bằng nút trong nội dung (ví dụ mật khẩu
  // tạm chỉ hiện một lần, hoặc đang gửi yêu cầu).
  dismissable?: boolean
  size?: 'md' | 'lg'
}

// Hộp thoại dùng thẻ <dialog> gốc (showModal): trình duyệt tự giữ tiêu điểm trong hộp, khoá phần
// còn lại của trang, và trả tiêu điểm về chỗ cũ khi đóng. Gắn vào cây là mở, gỡ ra là đóng.
export function Modal({ title, onClose, children, dismissable = true, size = 'md' }: ModalProps) {
  const ref = useRef<HTMLDialogElement>(null)
  const titleId = useId()

  useEffect(() => {
    const dialog = ref.current
    if (dialog && !dialog.open) dialog.showModal()
    return () => dialog?.close()
  }, [])

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault() // tự quyết định đóng hay không, thay vì để trình duyệt đóng ngay
        if (dismissable) onClose()
      }}
      onClick={(event) => {
        // Bấm vào nền mờ: sự kiện rơi đúng thẻ <dialog> (nội dung nằm trong div bên dưới).
        if (dismissable && event.target === event.currentTarget) onClose()
      }}
      className={`m-auto w-[calc(100%-2rem)] ${size === 'lg' ? 'max-w-3xl' : 'max-w-lg'} rounded-2xl border border-slate-200 bg-surface p-0 text-slate-900 shadow-pop backdrop:bg-slate-900/50`}
    >
      <div className="space-y-4 p-6">
        <div className="flex items-start justify-between gap-4">
          <h2 id={titleId} className="text-lg font-semibold">
            {title}
          </h2>
          {dismissable && (
            <button
              type="button"
              onClick={onClose}
              aria-label="Đóng"
              className="-m-1.5 rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-800"
            >
              <Icon name="x" className="h-5 w-5" />
            </button>
          )}
        </div>
        {children}
      </div>
    </dialog>
  )
}
