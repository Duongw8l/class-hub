import { REASON_LABELS, REASONS, STATUS_LABELS } from '../../api/attendance'
import type { AbsenceReason, AttendanceStatus, EntryInput } from '../../api/attendance'
import type { Draft } from './draft'

export interface EditorRow {
  student_id: number
  student_code: string
  full_name: string
  hints?: string[] // ví dụ các tiết GVBM đánh dấu vắng trong ngày
}

const STATUS_STYLES: Record<AttendanceStatus, string> = {
  present: 'border-green-600 bg-green-600 text-white',
  late: 'border-amber-500 bg-amber-500 text-white',
  absent_excused: 'border-sky-700 bg-sky-700 text-white',
  absent_unexcused: 'border-red-600 bg-red-600 text-white',
  school_duty: 'border-violet-600 bg-violet-600 text-white',
}

// Bảng điểm danh: mỗi em một dòng, chọn trạng thái bằng nút; khi vắng / muộn thì có lý do và ghi
// chú. `statuses` là các trạng thái được phép (GVBM không có "cử đi").
export function EntryEditor({
  rows,
  draft,
  statuses,
  readOnly,
  onChange,
}: {
  rows: EditorRow[]
  draft: Draft
  statuses: AttendanceStatus[]
  readOnly: boolean
  onChange: (next: Draft) => void
}) {
  function update(studentId: number, patch: Partial<EntryInput>) {
    const current = draft[studentId]
    const next = { ...current, ...patch }
    if (next.status === 'present') {
      next.reason = null
      next.note = null
    }
    onChange({ ...draft, [studentId]: next })
  }

  return (
    <div className="overflow-x-auto">
      <table className="data-table min-w-max text-sm">
        <thead>
          <tr>
            <th scope="col" className="px-2 py-2 text-right font-medium">
              STT
            </th>
            <th scope="col" className="px-2 py-2 font-medium">
              Học sinh
            </th>
            <th scope="col" className="px-2 py-2 font-medium">
              Trạng thái
            </th>
            <th scope="col" className="px-2 py-2 font-medium">
              Lý do và ghi chú
            </th>
          </tr>
        </thead>
        <tbody className="align-top">
          {rows.map((row, index) => {
            const entry = draft[row.student_id]
            const away = entry.status !== 'present'
            const needsNote = entry.reason === 'other' && !(entry.note ?? '').trim()
            return (
              <tr key={row.student_id} className={away ? 'bg-slate-50' : undefined}>
                <td className="px-2 py-1.5 text-right tabular-nums text-slate-500">{index + 1}</td>
                <th scope="row" className="px-2 py-1.5 text-left font-normal">
                  {row.full_name}
                  <span className="block font-mono text-xs text-slate-500">
                    {row.student_code}
                  </span>
                  {row.hints?.map((hint) => (
                    <span key={hint} className="block text-xs text-amber-700">
                      {hint}
                    </span>
                  ))}
                </th>
                <td className="px-2 py-1.5">
                  <div
                    role="radiogroup"
                    aria-label={`Trạng thái của ${row.full_name}`}
                    className="flex flex-wrap gap-1"
                  >
                    {statuses.map((status) => {
                      const chosen = entry.status === status
                      return (
                        <button
                          key={status}
                          type="button"
                          role="radio"
                          aria-checked={chosen}
                          disabled={readOnly}
                          onClick={() => update(row.student_id, { status })}
                          className={`rounded-md border px-2 py-0.5 text-xs font-medium transition-colors disabled:cursor-default ${
                            chosen
                              ? STATUS_STYLES[status]
                              : 'border-slate-300 text-slate-600 hover:bg-slate-100 disabled:hover:bg-transparent'
                          }`}
                        >
                          {STATUS_LABELS[status]}
                        </button>
                      )
                    })}
                  </div>
                </td>
                <td className="px-2 py-1.5">
                  {away && (
                    <div className="flex flex-wrap gap-2">
                      <select
                        aria-label={`Lý do của ${row.full_name}`}
                        value={entry.reason ?? ''}
                        disabled={readOnly}
                        onChange={(event) =>
                          update(row.student_id, {
                            reason: (event.target.value || null) as AbsenceReason | null,
                          })
                        }
                        className="input w-48 py-1 text-xs"
                      >
                        <option value="">— Lý do (tuỳ chọn) —</option>
                        {REASONS.map((reason) => (
                          <option key={reason} value={reason}>
                            {REASON_LABELS[reason]}
                          </option>
                        ))}
                      </select>
                      <input
                        aria-label={`Ghi chú của ${row.full_name}`}
                        value={entry.note ?? ''}
                        maxLength={255}
                        disabled={readOnly}
                        placeholder="Ghi chú"
                        onChange={(event) =>
                          update(row.student_id, { note: event.target.value || null })
                        }
                        className={`input w-56 py-1 text-xs ${needsNote ? 'ring-2 ring-red-400' : ''}`}
                      />
                    </div>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
