import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { fetchDay, saveDay, STATUS_LABELS, REASON_LABELS, shortDate, weekday } from '../../api/attendance'
import type { AttendanceStatus, DayAttendance } from '../../api/attendance'
import { useAuth } from '../../auth/context'
import { ErrorAlert, SuccessNote } from '../admin/shared'
import { Modal } from '../Modal'
import { QueryState } from '../QueryState'
import type { Draft } from './draft'
import { draftProblems } from './draft'
import { EntryEditor } from './EntryEditor'

const DAY_STATUSES: AttendanceStatus[] = [
  'present',
  'late',
  'absent_excused',
  'absent_unexcused',
  'school_duty',
]

function initialDraft(data: DayAttendance): Draft {
  // Ngày chưa điểm danh: mặc định cả lớp có mặt, chỉ cần đánh dấu em vắng.
  return Object.fromEntries(
    data.entries.map((e) => [
      e.student_id,
      { student_id: e.student_id, status: e.status ?? 'present', reason: e.reason, note: e.note },
    ]),
  )
}

function DayForm({ data, classId }: { data: DayAttendance; classId: number }) {
  const [draft, setDraft] = useState<Draft>(() => initialDraft(data))
  const [saved, setSaved] = useState<number | null>(null)
  const queryClient = useQueryClient()
  const fresh = data.entries.every((e) => e.status === null)
  const changed = data.entries.filter((e) => {
    const d = draft[e.student_id]
    return (
      e.status !== d.status || (e.reason ?? null) !== d.reason || (e.note ?? null) !== (d.note?.trim() || null)
    )
  })
  const problems = draftProblems(draft)
  const mutation = useMutation({
    mutationFn: () =>
      saveDay(
        classId,
        data.date,
        changed.map((e) => ({ ...draft[e.student_id], note: draft[e.student_id].note?.trim() || null })),
      ),
    onSuccess: (result) => {
      setSaved(changed.length)
      queryClient.setQueryData(['attendance-day', classId, data.date], result)
      void queryClient.invalidateQueries({
        predicate: (query) => query.queryKey[0] !== 'attendance-day',
      })
    },
  })
  const away = Object.values(draft).filter((d) => d.status !== 'present').length

  return (
    <div className="space-y-4">
      {fresh && data.can_edit && (
        <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900 ring-1 ring-amber-200">
          Ngày này chưa điểm danh: cả lớp đang để "Có mặt". Chỉ cần chọn trạng thái cho các em vắng
          hoặc đi muộn rồi bấm Lưu.
        </p>
      )}
      <EntryEditor
        rows={data.entries.map((e) => ({ ...e, hints: e.lesson_marks }))}
        draft={draft}
        statuses={DAY_STATUSES}
        readOnly={!data.can_edit || mutation.isPending}
        onChange={(next) => {
          setDraft(next)
          setSaved(null)
        }}
      />
      {data.can_edit && (
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            disabled={changed.length === 0 || problems.length > 0 || mutation.isPending}
            onClick={() => mutation.mutate()}
            className="btn-primary"
          >
            {mutation.isPending ? 'Đang lưu…' : `Lưu ${changed.length > 0 ? changed.length : ''} thay đổi`}
          </button>
          <span className="text-sm text-slate-600">
            {away} em vắng hoặc muộn.
            {problems.length > 0 && (
              <span className="ml-2 text-red-700">Lý do "Khác" cần ghi chú.</span>
            )}
          </span>
        </div>
      )}
      {saved !== null && <SuccessNote>Đã lưu điểm danh của {saved} học sinh.</SuccessNote>}
      {mutation.isError && <ErrorAlert error={mutation.error} />}
    </div>
  )
}

function History({ data }: { data: DayAttendance }) {
  if (data.history.length === 0) {
    return <p className="text-sm text-slate-600">Chưa có lần nhập tay nào cho ngày này.</p>
  }
  const time = new Intl.DateTimeFormat('vi-VN', { dateStyle: 'short', timeStyle: 'short' })
  const text = (status: AttendanceStatus | null) => (status ? STATUS_LABELS[status] : 'chưa có')
  return (
    <ul className="max-h-56 space-y-1 overflow-y-auto text-sm">
      {data.history.map((change, index) => (
        <li key={index}>
          <span className="tabular-nums text-slate-500">
            {time.format(new Date(change.changed_at))}
          </span>{' '}
          · {change.full_name}: {text(change.old_status)} →{' '}
          <strong>{text(change.new_status)}</strong>
          {change.new_reason && ` (${REASON_LABELS[change.new_reason]})`}
          {change.note && <span className="text-slate-500"> · {change.note}</span>}
          <span className="text-slate-500"> · {change.changed_by}</span>
        </li>
      ))}
    </ul>
  )
}

// Hộp thoại điểm danh một ngày của cả lớp (D-120): GVCN ghi trạng thái, lý do, ghi chú; chỉ GVCN
// ghi được "vắng do nhà trường cử đi" (không tính buổi nghỉ). BGH chỉ xem.
export function DayDialog({
  classId,
  day,
  onClose,
}: {
  classId: number
  day: string
  onClose: () => void
}) {
  const { token } = useAuth()
  const query = useQuery({
    queryKey: ['attendance-day', classId, day, token],
    queryFn: ({ signal }) => fetchDay(classId, day, signal),
  })
  return (
    <Modal title={`Điểm danh ${weekday(day)} ${shortDate(day)}/${day.slice(0, 4)}`} size="lg" onClose={onClose}>
      <QueryState query={query}>
        {(data) => (
          <div className="space-y-5">
            <p className="text-xs text-slate-500">
              "Vắng do trường cử đi" (thi học sinh giỏi, thi đấu, hoạt động của trường) không tính
              vào số buổi nghỉ. Nghỉ có phép và không phép đều tính, theo Thông tư 22. Dòng chữ màu
              cam dưới tên là tiết giáo viên bộ môn đã đánh dấu vắng hoặc muộn trong ngày.
            </p>
            <DayForm key={data.history.length} data={data} classId={classId} />
            <section aria-labelledby="lich-su-diem-danh" className="space-y-2">
              <h3 id="lich-su-diem-danh" className="text-sm font-semibold text-slate-900">
                Lịch sử nhập tay ngày này
              </h3>
              <History data={data} />
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
