import { useState } from 'react'
import type { FormEvent } from 'react'
import type { AdminUser, CreatedUser } from '../../api/admin'
import { useCreateUser, useSubjects, useUpdateUser } from '../../hooks/useAdmin'
import { ErrorAlert } from './shared'
import { fromRoleChoice, toRoleChoice } from './roles'
import type { RoleChoice } from './roles'

const EMAIL_SHAPE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/
const MAX_NOTE = 255

interface CreateProps {
  mode: 'create'
  onCreated: (created: CreatedUser) => void
}

interface EditProps {
  mode: 'edit'
  user: AdminUser
  // Đang sửa chính tài khoản đăng nhập: không đổi được vai trò (back-end cũng chặn).
  isSelf: boolean
  onDone: () => void
}

// Biểu mẫu tạo tài khoản (hệ thống sinh mật khẩu tạm) hoặc sửa họ tên, email, vai trò, ghi chú.
// Ô "Vai trò" gộp sẵn môn: "Giáo viên Toán", "Giáo viên Ngữ văn"… (D-112). Môn chỉ là nhãn nhận
// diện; quyền dạy lớp nào môn nào vẫn theo phân công giảng dạy.
export function UserForm(props: CreateProps | EditProps) {
  const editing = props.mode === 'edit' ? props.user : null
  const create = useCreateUser()
  const update = useUpdateUser()
  const subjects = useSubjects()
  const [fullName, setFullName] = useState(editing?.full_name ?? '')
  const [email, setEmail] = useState(editing?.email ?? '')
  const [choice, setChoice] = useState<RoleChoice>(
    editing ? toRoleChoice(editing.role, editing.specialty_subject_id) : '',
  )
  const [note, setNote] = useState(editing?.note ?? '')
  const mutation = props.mode === 'create' ? create : update

  const { role, subjectId } = fromRoleChoice(choice)
  const currentNote = note.trim() === '' ? null : note.trim()

  const valid = fullName.trim() !== '' && EMAIL_SHAPE.test(email.trim()) && choice !== ''
  const dirty =
    editing === null ||
    fullName.trim() !== editing.full_name ||
    email.trim().toLowerCase() !== editing.email ||
    role !== editing.role ||
    subjectId !== editing.specialty_subject_id ||
    currentNote !== editing.note

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!valid || !dirty || mutation.isPending) return
    if (props.mode === 'create') {
      create.mutate(
        {
          email: email.trim(),
          full_name: fullName.trim(),
          role,
          specialty_subject_id: subjectId,
          note: currentNote,
        },
        {
          onSuccess: (created) => {
            setFullName('')
            setEmail('')
            setChoice('')
            setNote('')
            props.onCreated(created)
          },
        },
      )
    } else {
      update.mutate(
        {
          id: props.user.id,
          body: {
            ...(fullName.trim() !== props.user.full_name ? { full_name: fullName.trim() } : {}),
            ...(email.trim().toLowerCase() !== props.user.email ? { email: email.trim() } : {}),
            ...(role !== props.user.role ? { role } : {}),
            ...(subjectId !== props.user.specialty_subject_id
              ? { specialty_subject_id: subjectId }
              : {}),
            ...(currentNote !== props.user.note ? { note: currentNote } : {}),
          },
        },
        { onSuccess: props.onDone },
      )
    }
  }

  const idPrefix = editing ? `sua-${editing.id}` : 'moi'
  const lockedRole = props.mode === 'edit' && props.isSelf
  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="grid gap-4 md:grid-cols-3">
        <div>
          <label htmlFor={`${idPrefix}-ten`} className="label">
            Họ và tên
          </label>
          <input
            id={`${idPrefix}-ten`}
            type="text"
            value={fullName}
            maxLength={100}
            disabled={mutation.isPending}
            onChange={(event) => setFullName(event.target.value)}
            className="input mt-1"
            autoComplete="off"
          />
        </div>
        <div>
          <label htmlFor={`${idPrefix}-email`} className="label">
            Email đăng nhập
          </label>
          <input
            id={`${idPrefix}-email`}
            type="email"
            value={email}
            maxLength={255}
            disabled={mutation.isPending}
            onChange={(event) => setEmail(event.target.value)}
            className="input mt-1"
            autoComplete="off"
          />
        </div>
        <div>
          <label htmlFor={`${idPrefix}-vai-tro`} className="label">
            Vai trò
          </label>
          <select
            id={`${idPrefix}-vai-tro`}
            value={choice}
            disabled={mutation.isPending || lockedRole}
            onChange={(event) => setChoice(event.target.value)}
            className="input mt-1"
          >
            {choice === '' && <option value="">— Chọn vai trò —</option>}
            <optgroup label="Giáo viên">
              {(subjects.data ?? []).map((subject) => (
                <option key={subject.id} value={`teacher:${subject.id}`}>
                  Giáo viên {subject.name}
                </option>
              ))}
              <option value="teacher">Giáo viên (chưa chọn môn)</option>
            </optgroup>
            <optgroup label="Khác">
              <option value="principal">Ban giám hiệu</option>
              <option value="admin">Quản trị viên</option>
            </optgroup>
          </select>
          {lockedRole && (
            <p className="mt-1 text-xs text-slate-500">Không đổi được vai trò của chính mình.</p>
          )}
          {subjects.isError && (
            <p className="mt-1 text-xs text-amber-700">
              Không tải được danh sách môn; vẫn chọn được "Giáo viên (chưa chọn môn)".
            </p>
          )}
        </div>
      </div>

      <div>
        <label htmlFor={`${idPrefix}-ghi-chu`} className="label">
          Ghi chú <span className="font-normal text-slate-500">(tuỳ chọn)</span>
        </label>
        <input
          id={`${idPrefix}-ghi-chu`}
          type="text"
          value={note}
          maxLength={MAX_NOTE}
          disabled={mutation.isPending}
          onChange={(event) => setNote(event.target.value)}
          className="input mt-1"
          autoComplete="off"
          placeholder="Ví dụ: Tổ Tự nhiên, dạy khối 10 — để phân biệt khi trùng tên"
        />
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button type="submit" disabled={!valid || !dirty || mutation.isPending} className="btn-primary">
          {props.mode === 'create'
            ? mutation.isPending
              ? 'Đang tạo…'
              : 'Tạo tài khoản'
            : mutation.isPending
              ? 'Đang lưu…'
              : 'Lưu thay đổi'}
        </button>
        {props.mode === 'edit' && (
          <button type="button" onClick={props.onDone} className="btn-secondary">
            Huỷ
          </button>
        )}
        {props.mode === 'create' && (
          <p className="text-sm text-slate-500">
            Hệ thống tự sinh mật khẩu tạm và chỉ hiện cho bạn một lần.
          </p>
        )}
      </div>
      {mutation.isError && <ErrorAlert error={mutation.error} />}
    </form>
  )
}
