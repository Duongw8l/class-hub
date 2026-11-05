import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import type { FormEvent } from 'react'
import {
  CONDUCT_LEVELS,
  CONDUCT_PERIODS,
  CONDUCT_REASONS,
  fetchStudentConduct,
  PERIOD_NAMES,
  saveStudentConduct,
} from '../../api/conduct'
import type {
  ConductChange,
  ConductChangeReason,
  ConductLevel,
  ConductPeriod,
  StudentConduct,
} from '../../api/conduct'
import { useAuth } from '../../auth/context'
import { LEVEL_LABELS } from '../../lib/labels'
import { ErrorAlert, SuccessNote } from '../admin/shared'
import { Modal } from '../Modal'
import { QueryState } from '../QueryState'

interface Draft {
  level: ConductLevel | ''
  comment: string
}

const levelText = (level: ConductLevel | null) => (level ? LEVEL_LABELS[level] : 'chưa có')

function EditForm({
  data,
  classId,
  onSaved,
}: {
  data: StudentConduct
  classId: number
  onSaved: (result: StudentConduct, changed: number) => void
}) {
  const original = Object.fromEntries(data.entries.map((e) => [e.period, e])) as Record<
    ConductPeriod,
    StudentConduct['entries'][number]
  >
  const [drafts, setDrafts] = useState<Record<ConductPeriod, Draft>>(() => {
    const result = {} as Record<ConductPeriod, Draft>
    for (const period of CONDUCT_PERIODS) {
      result[period] = {
        level: original[period].level ?? '',
        comment: original[period].comment ?? '',
      }
    }
    return result
  })
  const [reason, setReason] = useState<ConductChangeReason | ''>('')
  const [note, setNote] = useState('')

  // Chỉ gửi kỳ đổi mức hoặc nhận xét; kỳ chưa có mà vẫn để trống thì bỏ qua.
  const changes = CONDUCT_PERIODS.flatMap((period) => {
    const draft = drafts[period]
    if (draft.level === '') return []
    const comment = draft.comment.trim() || null
    const before = original[period]
    if (draft.level === before.level && comment === (before.comment ?? null)) return []
    return [{ period, level: draft.level, comment }]
  })
  const needsNote = reason === 'other' && note.trim() === ''

  const queryClient = useQueryClient()
  const mutation = useMutation({
    mutationFn: () =>
      saveStudentConduct(classId, data.student_id, {
        entries: changes,
        reason: reason as ConductChangeReason,
        note: note.trim() || undefined,
      }),
    onSuccess: (result) => {
      // Bảng rèn luyện, dashboard, trang khối, cảnh báo... đổi theo: nạp lại mọi thứ trừ hộp này.
      void queryClient.invalidateQueries({
        predicate: (query) => query.queryKey[0] !== 'student-conduct',
      })
      onSaved(result, changes.length)
    },
  })
  const canSave = changes.length > 0 && reason !== '' && !needsNote && !mutation.isPending

  function submit(event: FormEvent) {
    event.preventDefault()
    if (canSave) mutation.mutate()
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-3">
        {CONDUCT_PERIODS.map((period) => {
          const draft = drafts[period]
          const before = original[period]
          const changed = changes.some((c) => c.period === period)
          const id = `ren-luyen-${period}`
          return (
            <fieldset
              key={period}
              className={`space-y-2 rounded-xl p-3 ring-1 ${changed ? 'ring-2 ring-amber-400' : 'ring-slate-200'}`}
            >
              <legend className="px-1 text-sm font-semibold text-slate-800">
                {PERIOD_NAMES[period]}
              </legend>
              <div>
                <label htmlFor={`${id}-muc`} className="label">
                  Mức
                </label>
                <select
                  id={`${id}-muc`}
                  value={draft.level}
                  disabled={mutation.isPending}
                  onChange={(event) =>
                    setDrafts({
                      ...drafts,
                      [period]: { ...draft, level: event.target.value as ConductLevel | '' },
                    })
                  }
                  className="input mt-1"
                >
                  {/* Không xoá được kết quả đã có: chỉ kỳ chưa có mới có lựa chọn trống. */}
                  {before.level === null && <option value="">— Chưa có —</option>}
                  {CONDUCT_LEVELS.map((level) => (
                    <option key={level} value={level}>
                      {LEVEL_LABELS[level]}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor={`${id}-nhan-xet`} className="label">
                  Nhận xét (tuỳ chọn)
                </label>
                <textarea
                  id={`${id}-nhan-xet`}
                  value={draft.comment}
                  maxLength={500}
                  rows={3}
                  disabled={mutation.isPending || draft.level === ''}
                  onChange={(event) =>
                    setDrafts({ ...drafts, [period]: { ...draft, comment: event.target.value } })
                  }
                  className="input mt-1 text-sm"
                />
              </div>
            </fieldset>
          )
        })}
      </div>
      <p className="text-xs text-slate-500">
        Khung viền vàng là kỳ đã đổi. Mức mới thay hẳn mức cũ; mức cũ vẫn lưu trong lịch sử bên
        dưới. Không xoá được kết quả đã có.
      </p>

      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor="ly-do-ren-luyen" className="label">
            Lý do
          </label>
          <select
            id="ly-do-ren-luyen"
            value={reason}
            disabled={mutation.isPending}
            onChange={(event) => setReason(event.target.value as ConductChangeReason | '')}
            className="input mt-1"
          >
            <option value="">— Chọn lý do —</option>
            {CONDUCT_REASONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="ghi-chu-ren-luyen" className="label">
            Ghi chú {reason === 'other' ? '' : '(tuỳ chọn)'}
          </label>
          <input
            id="ghi-chu-ren-luyen"
            value={note}
            maxLength={255}
            disabled={mutation.isPending}
            placeholder="Ví dụ: theo biên bản họp lớp ngày 20/12"
            onChange={(event) => setNote(event.target.value)}
            className="input mt-1"
          />
          {needsNote && <p className="mt-1 text-xs text-red-700">Lý do "Khác" cần ghi chú.</p>}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button type="submit" disabled={!canSave} className="btn-primary">
          {mutation.isPending
            ? 'Đang lưu…'
            : `Lưu ${changes.length > 0 ? changes.length : ''} thay đổi`}
        </button>
        {changes.length === 0 && (
          <span className="text-sm text-slate-500">Chưa có kỳ nào thay đổi.</span>
        )}
      </div>
      {mutation.isError && <ErrorAlert error={mutation.error} />}
    </form>
  )
}

function History({ history }: { history: ConductChange[] }) {
  if (history.length === 0) {
    return <p className="text-sm text-slate-600">Chưa có lần sửa tay nào.</p>
  }
  const time = new Intl.DateTimeFormat('vi-VN', { dateStyle: 'short', timeStyle: 'short' })
  return (
    <div className="max-h-72 overflow-auto">
      <table className="data-table min-w-max text-sm">
        <thead>
          <tr>
            <th scope="col" className="px-2 py-2 font-medium">
              Thời điểm
            </th>
            <th scope="col" className="px-2 py-2 font-medium">
              Kỳ
            </th>
            <th scope="col" className="px-2 py-2 font-medium">
              Cũ → Mới
            </th>
            <th scope="col" className="px-2 py-2 font-medium">
              Lý do
            </th>
            <th scope="col" className="px-2 py-2 font-medium">
              Người sửa
            </th>
          </tr>
        </thead>
        <tbody>
          {history.map((change, index) => (
            <tr key={index} className="align-top">
              <td className="px-2 py-1.5 tabular-nums">
                {time.format(new Date(change.changed_at))}
              </td>
              <td className="px-2 py-1.5">{PERIOD_NAMES[change.period]}</td>
              <td className="px-2 py-1.5">
                {levelText(change.old_level)} → <strong>{levelText(change.new_level)}</strong>
                {change.old_comment !== change.new_comment && (
                  <span className="block max-w-xs whitespace-normal text-xs text-slate-500">
                    Nhận xét: {change.new_comment ?? '(đã xoá)'}
                  </span>
                )}
              </td>
              <td className="px-2 py-1.5">
                {change.reason_label}
                {change.note && (
                  <span className="block max-w-xs whitespace-normal text-xs text-slate-500">
                    {change.note}
                  </span>
                )}
              </td>
              <td className="px-2 py-1.5">{change.changed_by}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// Hộp thoại rèn luyện của một học sinh (D-119): GVCN của lớp sửa / nhập tay ba kỳ (bắt chọn lý
// do); BGH chỉ xem lịch sử. Back-end kiểm quyền lần nữa khi lưu.
export function ConductDialog({
  classId,
  studentId,
  studentName,
  onClose,
}: {
  classId: number
  studentId: number
  studentName: string
  onClose: () => void
}) {
  const { token } = useAuth()
  const queryClient = useQueryClient()
  const queryKey = ['student-conduct', token, classId, studentId]
  const query = useQuery({
    queryKey,
    queryFn: ({ signal }) => fetchStudentConduct(classId, studentId, signal),
  })
  const [saved, setSaved] = useState<number | null>(null)
  const [version, setVersion] = useState(0)

  return (
    <Modal title={`Rèn luyện · ${studentName}`} size="lg" onClose={onClose}>
      <QueryState query={query}>
        {(data) => (
          <div className="space-y-5">
            <p className="text-sm text-slate-600">Mã HS {data.student_code}</p>
            {data.can_edit ? (
              <EditForm
                key={version}
                data={data}
                classId={classId}
                onSaved={(result, changed) => {
                  queryClient.setQueryData(queryKey, result)
                  setSaved(changed)
                  setVersion((current) => current + 1)
                }}
              />
            ) : (
              <p className="text-sm text-slate-600">
                Chỉ giáo viên chủ nhiệm của lớp mới sửa được rèn luyện. Bạn xem được lịch sử sửa bên
                dưới.
              </p>
            )}
            {saved !== null && <SuccessNote>Đã lưu {saved} kỳ.</SuccessNote>}
            <section aria-labelledby="lich-su-ren-luyen" className="space-y-2">
              <h3 id="lich-su-ren-luyen" className="text-sm font-semibold text-slate-900">
                Lịch sử sửa tay
              </h3>
              <History history={data.history} />
            </section>
            <div className="flex justify-end">
              <button type="button" onClick={onClose} className="btn-secondary">
                Đóng
              </button>
            </div>
          </div>
        )}
      </QueryState>
    </Modal>
  )
}
