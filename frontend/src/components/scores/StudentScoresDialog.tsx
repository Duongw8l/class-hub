import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import type { FormEvent } from 'react'
import { fetchStudentScores, REASON_OPTIONS, saveStudentScores } from '../../api/scores'
import type {
  AssessmentKind,
  CommentResult,
  ScoreChange,
  ScoreChangeReason,
  ScoreEntryInput,
  StudentScores,
} from '../../api/scores'
import { useAuth } from '../../auth/context'
import { formatScore } from '../../lib/format'
import { COMMENT_LABELS } from '../../lib/labels'
import { ErrorAlert, SuccessNote } from '../admin/shared'
import { Modal } from '../Modal'
import { QueryState } from '../QueryState'

interface StudentScoresDialogProps {
  classId: number
  subjectId: number
  studentId: number
  studentName: string
  semester: 1 | 2
  onClose: () => void
}

interface Slot {
  key: string
  kind: AssessmentKind
  seq: number
  label: string
}

function slotLabel(kind: AssessmentKind, seq: number, isComment: boolean): string {
  if (isComment) return 'Nhận xét'
  if (kind === 'tx') return `TX${seq}`
  return kind === 'gk' ? 'Giữa kỳ' : 'Cuối kỳ'
}

function slotsOf(data: StudentScores): Slot[] {
  if (data.is_comment_subject) return [{ key: 'ck-1', kind: 'ck', seq: 1, label: 'Nhận xét' }]
  const tx = Array.from({ length: data.tx_slots }, (_, index) => ({
    key: `tx-${index + 1}`,
    kind: 'tx' as const,
    seq: index + 1,
    label: `TX${index + 1}`,
  }))
  return [
    ...tx,
    { key: 'gk-1', kind: 'gk', seq: 1, label: 'Giữa kỳ' },
    { key: 'ck-1', kind: 'ck', seq: 1, label: 'Cuối kỳ' },
  ]
}

// "7,5" hoặc "7.5" thành 7.5; null khi không hợp lệ (0 đến 10, tối đa 1 chữ số thập phân).
function parseScore(text: string): number | null {
  const trimmed = text.trim()
  if (!/^\d{1,2}([.,]\d)?$/.test(trimmed)) return null
  const value = Number(trimmed.replace(',', '.'))
  return value >= 0 && value <= 10 ? value : null
}

function scoreText(value: number | null): string {
  return value === null ? '' : formatScore(value)
}

function valueText(score: number | null, comment: CommentResult | null): string {
  if (comment) return COMMENT_LABELS[comment]
  return score === null ? 'thiếu' : formatScore(score)
}

function EditForm({
  data,
  classId,
  onSaved,
}: {
  data: StudentScores
  classId: number
  onSaved: (result: StudentScores, changed: number) => void
}) {
  const slots = slotsOf(data)
  const original = new Map(data.entries.map((entry) => [`${entry.kind}-${entry.seq}`, entry]))
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      slots.map((slot) => {
        const entry = original.get(slot.key)
        return [
          slot.key,
          data.is_comment_subject ? (entry?.comment_result ?? '') : scoreText(entry?.score ?? null),
        ]
      }),
    ),
  )
  const [reason, setReason] = useState<ScoreChangeReason | ''>('')
  const [note, setNote] = useState('')

  // So từng ô với giá trị đang có: chỉ gửi ô đổi; ô lỗi chặn lưu.
  const errors: Record<string, string> = {}
  const changes: ScoreEntryInput[] = []
  for (const slot of slots) {
    const text = values[slot.key] ?? ''
    const entry = original.get(slot.key)
    if (data.is_comment_subject) {
      if (text === '' || text === entry?.comment_result) continue
      changes.push({
        kind: slot.kind,
        seq: slot.seq,
        comment_result: text as CommentResult,
      })
      continue
    }
    if (text.trim() === '') {
      if (entry) errors[slot.key] = 'Không xoá được điểm; hãy nhập điểm mới.'
      continue
    }
    const score = parseScore(text)
    if (score === null) {
      errors[slot.key] = 'Từ 0 đến 10, tối đa 1 chữ số thập phân.'
      continue
    }
    if (entry?.score !== score) changes.push({ kind: slot.kind, seq: slot.seq, score })
  }
  const hasErrors = Object.keys(errors).length > 0
  const needsNote = reason === 'other' && note.trim() === ''

  const queryClient = useQueryClient()
  const mutation = useMutation({
    mutationFn: () =>
      saveStudentScores(classId, data.subject_id, data.student_id, {
        semester: data.semester,
        entries: changes,
        reason: reason as ScoreChangeReason,
        note: note.trim() || undefined,
      }),
    onSuccess: (result) => {
      // Bảng điểm, dashboard, cảnh báo... đều đổi theo điểm mới: nạp lại mọi thứ trừ hộp thoại này.
      void queryClient.invalidateQueries({
        predicate: (query) => query.queryKey[0] !== 'student-scores',
      })
      onSaved(result, changes.length)
    },
  })

  const canSave =
    changes.length > 0 && !hasErrors && reason !== '' && !needsNote && !mutation.isPending

  function submit(event: FormEvent) {
    event.preventDefault()
    if (canSave) mutation.mutate()
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="flex flex-wrap gap-3">
        {slots.map((slot) => {
          const entry = original.get(slot.key)
          const text = values[slot.key] ?? ''
          const changed = data.is_comment_subject
            ? text !== '' && text !== entry?.comment_result
            : text.trim() !== '' && parseScore(text) !== (entry?.score ?? null)
          const id = `sua-diem-${slot.key}`
          return (
            <div key={slot.key} className={data.is_comment_subject ? 'w-40' : 'w-20'}>
              <label htmlFor={id} className="label">
                {slot.label}
              </label>
              {data.is_comment_subject ? (
                <select
                  id={id}
                  value={text}
                  disabled={mutation.isPending}
                  onChange={(event) => setValues({ ...values, [slot.key]: event.target.value })}
                  className={`input mt-1 ${changed ? 'ring-2 ring-amber-400' : ''}`}
                >
                  <option value="">— Chưa có —</option>
                  <option value="pass">{COMMENT_LABELS.pass}</option>
                  <option value="fail">{COMMENT_LABELS.fail}</option>
                </select>
              ) : (
                <input
                  id={id}
                  inputMode="decimal"
                  value={text}
                  placeholder="thiếu"
                  disabled={mutation.isPending}
                  aria-invalid={errors[slot.key] ? true : undefined}
                  aria-describedby={errors[slot.key] ? `${id}-loi` : undefined}
                  onChange={(event) => setValues({ ...values, [slot.key]: event.target.value })}
                  className={`input mt-1 text-right tabular-nums ${
                    errors[slot.key]
                      ? 'ring-2 ring-red-400'
                      : changed
                        ? 'ring-2 ring-amber-400'
                        : ''
                  }`}
                />
              )}
              {errors[slot.key] && (
                <p id={`${id}-loi`} className="mt-1 text-xs text-red-700">
                  {errors[slot.key]}
                </p>
              )}
            </div>
          )
        })}
      </div>
      <p className="text-xs text-slate-500">
        Ô viền vàng là ô đã đổi. Điểm mới thay hẳn điểm cũ; điểm cũ vẫn lưu trong lịch sử bên dưới.
        ĐTB do hệ thống tự tính lại.
      </p>

      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor="ly-do-sua-diem" className="label">
            Lý do
          </label>
          <select
            id="ly-do-sua-diem"
            value={reason}
            disabled={mutation.isPending}
            onChange={(event) => setReason(event.target.value as ScoreChangeReason | '')}
            className="input mt-1"
          >
            <option value="">— Chọn lý do —</option>
            {REASON_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="ghi-chu-sua-diem" className="label">
            Ghi chú {reason === 'other' ? '' : '(tuỳ chọn)'}
          </label>
          <input
            id="ghi-chu-sua-diem"
            value={note}
            maxLength={255}
            disabled={mutation.isPending}
            placeholder="Ví dụ: kiểm tra lại ngày 10/12"
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
        {changes.length === 0 && !hasErrors && (
          <span className="text-sm text-slate-500">Chưa có ô nào thay đổi.</span>
        )}
      </div>
      {mutation.isError && <ErrorAlert error={mutation.error} />}
    </form>
  )
}

function History({ history, isComment }: { history: ScoreChange[]; isComment: boolean }) {
  if (history.length === 0) {
    return <p className="text-sm text-slate-600">Chưa có lần sửa điểm nào cho môn này.</p>
  }
  const time = new Intl.DateTimeFormat('vi-VN', {
    dateStyle: 'short',
    timeStyle: 'short',
  })
  return (
    <div className="max-h-72 overflow-auto">
      <table className="data-table min-w-max text-sm">
        <thead>
          <tr>
            <th scope="col" className="px-2 py-2 font-medium">
              Thời điểm
            </th>
            <th scope="col" className="px-2 py-2 font-medium">
              HK
            </th>
            <th scope="col" className="px-2 py-2 font-medium">
              Đầu điểm
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
            <tr key={index}>
              <td className="px-2 py-1.5 tabular-nums">
                {time.format(new Date(change.changed_at))}
              </td>
              <td className="px-2 py-1.5">{change.semester === 1 ? 'I' : 'II'}</td>
              <td className="px-2 py-1.5">{slotLabel(change.kind, change.seq, isComment)}</td>
              <td className="px-2 py-1.5 tabular-nums">
                {valueText(change.old_score, change.old_comment_result)} →{' '}
                <strong>{valueText(change.new_score, change.new_comment_result)}</strong>
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

// Hộp thoại điểm của một học sinh (D-115): GVBM được phân công sửa / nhập tay từng đầu điểm (bắt
// chọn lý do); GVCN, BGH chỉ xem lịch sử sửa điểm. Back-end kiểm quyền lần nữa khi lưu.
export function StudentScoresDialog({
  classId,
  subjectId,
  studentId,
  studentName,
  semester,
  onClose,
}: StudentScoresDialogProps) {
  const { token } = useAuth()
  const queryClient = useQueryClient()
  const queryKey = ['student-scores', token, classId, subjectId, studentId, semester]
  const query = useQuery({
    queryKey,
    queryFn: ({ signal }) => fetchStudentScores(classId, subjectId, studentId, semester, signal),
  })
  const [saved, setSaved] = useState<number | null>(null)
  const [version, setVersion] = useState(0)

  return (
    <Modal
      title={`${studentName} · học kỳ ${semester === 1 ? 'I' : 'II'}`}
      size="lg"
      onClose={onClose}
    >
      <QueryState query={query}>
        {(data) => (
          <div className="space-y-5">
            <p className="text-sm text-slate-600">
              Môn <strong>{data.subject_name}</strong> · mã HS {data.student_code}
            </p>
            {data.can_edit ? (
              <EditForm
                key={version}
                data={data}
                classId={classId}
                onSaved={(result, changed) => {
                  queryClient.setQueryData(queryKey, result)
                  setSaved(changed)
                  setVersion((current) => current + 1) // ô nhập lấy lại giá trị mới
                }}
              />
            ) : (
              <p className="text-sm text-slate-600">
                Chỉ giáo viên bộ môn được phân công mới sửa được điểm. Bạn xem được lịch sử sửa điểm
                bên dưới.
              </p>
            )}
            {saved !== null && <SuccessNote>Đã lưu {saved} đầu điểm.</SuccessNote>}
            <section aria-labelledby="lich-su-sua-diem" className="space-y-2">
              <h3 id="lich-su-sua-diem" className="text-sm font-semibold text-slate-900">
                Lịch sử sửa điểm môn này (cả năm)
              </h3>
              <History history={data.history} isComment={data.is_comment_subject} />
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
