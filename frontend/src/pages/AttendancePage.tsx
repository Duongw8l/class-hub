import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import {
  fetchClassAttendance,
  REASON_LABELS,
  shortDate,
  STATUS_LABELS,
  STATUS_SYMBOLS,
  todayIso,
  weekday,
} from '../api/attendance'
import type { AbsenceLevel, AttendanceRow, AttendanceStatus, ClassAttendance } from '../api/attendance'
import { DayDialog } from '../components/attendance/DayDialog'
import { Icon } from '../components/Icon'
import { PageTitle, Panel } from '../components/Panel'
import { QueryState } from '../components/QueryState'
import { StatCard, StatGrid } from '../components/StatCard'
import { useAuth } from '../auth/context'
import { formatMonth } from '../lib/format'

const CELL_STYLES: Record<AttendanceStatus, string> = {
  present: '',
  late: 'bg-amber-100 text-amber-900',
  absent_excused: 'bg-sky-100 text-sky-900',
  absent_unexcused: 'bg-red-100 text-red-900',
  school_duty: 'bg-violet-100 text-violet-900',
}

const LEVEL_BADGES: Record<AbsenceLevel, { label: string; className: string }> = {
  over: { label: 'Quá mức tối đa', className: 'badge-high' },
  high: { label: 'Mức cao', className: 'badge-medium' },
  notice: { label: 'Cần nhắc', className: 'badge-low' },
}

type Filter = 'all' | 'warned' | 'absent_month'

function useClassAttendance(classId: number, month: string | null) {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['class-attendance', token, classId, month],
    queryFn: ({ signal }) => fetchClassAttendance(classId, month, signal),
    enabled: token !== null && Number.isInteger(classId),
  })
}

function Legend() {
  const items: AttendanceStatus[] = ['late', 'absent_excused', 'absent_unexcused', 'school_duty']
  return (
    <p className="flex flex-wrap gap-3 text-xs text-slate-600">
      <span>Ô trống: có mặt.</span>
      {items.map((status) => (
        <span key={status} className="flex items-center gap-1">
          <span className={`rounded px-1 font-semibold ${CELL_STYLES[status]}`}>
            {STATUS_SYMBOLS[status]}
          </span>
          {STATUS_LABELS[status]}
          {status === 'school_duty' && ' (không tính buổi nghỉ)'}
        </span>
      ))}
    </p>
  )
}

function Summary({ data }: { data: ClassAttendance }) {
  const { limits, counts } = data
  return (
    <StatGrid>
      <StatCard
        label={`Nghỉ quá ${limits.maximum} buổi`}
        value={counts.over}
        valueClassName={counts.over > 0 ? 'text-red-700' : 'text-slate-900'}
        hint="Không đủ điều kiện lên lớp"
        icon="alert"
        tone={counts.over > 0 ? 'danger' : 'neutral'}
      />
      <StatCard
        label={`Nghỉ từ ${limits.high} buổi`}
        value={counts.high}
        valueClassName={counts.high > 0 ? 'text-amber-700' : 'text-slate-900'}
        hint="Cảnh báo mức cao"
        icon="bell"
        tone={counts.high > 0 ? 'warn' : 'neutral'}
      />
      <StatCard
        label={`Nghỉ từ ${limits.notice} buổi`}
        value={counts.notice}
        hint="Cần nhắc nhở, trao đổi với phụ huynh"
        icon="calendar"
        tone="neutral"
      />
      <StatCard
        label="Cần đối chiếu với tiết học"
        value={data.mismatches.length}
        valueClassName={data.mismatches.length > 0 ? 'text-amber-700' : 'text-slate-900'}
        hint={`Trong ${formatMonth(data.month).toLowerCase()}`}
        icon="search"
        tone={data.mismatches.length > 0 ? 'warn' : 'neutral'}
      />
    </StatGrid>
  )
}

function YearCell({ row, limits }: { row: AttendanceRow; limits: ClassAttendance['limits'] }) {
  const { year } = row
  return (
    <span className="flex flex-col items-end gap-0.5">
      <span className="tabular-nums font-semibold">
        {year.absent_total}
        <span className="font-normal text-slate-400">/{limits.maximum}</span>
      </span>
      {year.level && (
        <span className={LEVEL_BADGES[year.level].className}>{LEVEL_BADGES[year.level].label}</span>
      )}
    </span>
  )
}

function MonthGrid({
  data,
  onOpenDay,
}: {
  data: ClassAttendance
  onOpenDay: (day: string) => void
}) {
  const [filter, setFilter] = useState<Filter>('all')
  const filters: { value: Filter; label: string; test: (row: AttendanceRow) => boolean }[] = [
    { value: 'all', label: 'Tất cả', test: () => true },
    {
      value: 'warned',
      label: `Từ ${data.limits.notice} buổi trở lên`,
      test: (row) => row.year.level !== null,
    },
    {
      value: 'absent_month',
      label: 'Có vắng trong tháng',
      test: (row) => row.cells.some((c) => c.status !== 'present'),
    },
  ]
  const active = filters.find((f) => f.value === filter) ?? filters[0]
  const rows = data.rows.filter(active.test)

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div role="group" aria-label="Lọc học sinh" className="flex flex-wrap gap-2">
          {filters.map((item) => (
            <button
              key={item.value}
              type="button"
              aria-pressed={filter === item.value}
              onClick={() => setFilter(item.value)}
              className={`rounded-lg border px-2.5 py-1 text-xs font-medium transition-colors ${
                filter === item.value
                  ? 'border-brand-700 bg-brand-700 text-white'
                  : 'border-slate-300 hover:bg-slate-100'
              }`}
            >
              {item.label} ({data.rows.filter(item.test).length})
            </button>
          ))}
        </div>
        <Legend />
      </div>
      {data.days.length === 0 && (
        <p className="text-sm text-slate-600">
          Tháng này chưa có ngày nào được điểm danh.
          {data.can_edit && ' Bấm "Điểm danh ngày" ở trên để bắt đầu.'}
        </p>
      )}
      <div className="max-h-[70vh] overflow-auto rounded-xl ring-1 ring-slate-200">
        <table className="min-w-max border-collapse text-sm">
          <thead className="sticky top-0 z-10 bg-surface">
            <tr>
              <th scope="col" className="sticky left-0 z-20 bg-surface px-3 py-2 text-left font-medium">
                Học sinh
              </th>
              {data.days.map((day) => (
                <th key={day} scope="col" className="px-0.5 py-1 font-medium">
                  <button
                    type="button"
                    onClick={() => onOpenDay(day)}
                    title={`Mở điểm danh ngày ${shortDate(day)}`}
                    className="flex w-9 flex-col items-center rounded text-xs hover:bg-slate-100"
                  >
                    <span className="text-slate-500">{weekday(day)}</span>
                    <span className="tabular-nums">{shortDate(day).slice(0, 2)}</span>
                  </button>
                </th>
              ))}
              <th scope="col" className="px-3 py-2 text-right font-medium">
                Nghỉ cả năm
              </th>
              <th scope="col" className="px-3 py-2 text-right font-medium" title="Có phép / không phép">
                P / K
              </th>
              <th scope="col" className="px-3 py-2 text-right font-medium">
                Cử đi
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const byDay = new Map(row.cells.map((c) => [c.date, c]))
              return (
                <tr key={row.student_id} className="border-t border-slate-100">
                  <th scope="row" className="sticky left-0 bg-surface px-3 py-1.5 text-left font-normal">
                    <Link
                      to={`/classes/${data.class_info.id}/students/${row.student_id}?semester=year`}
                      className="link"
                    >
                      {row.full_name}
                    </Link>
                  </th>
                  {data.days.map((day) => {
                    const cell = byDay.get(day)
                    const status = cell?.status
                    const title = cell
                      ? [
                          STATUS_LABELS[cell.status],
                          cell.reason ? REASON_LABELS[cell.reason] : null,
                          cell.note,
                        ]
                          .filter(Boolean)
                          .join(' · ')
                      : 'Chưa điểm danh'
                    return (
                      <td key={day} className="px-0.5 py-0.5 text-center">
                        <span
                          title={title}
                          className={`inline-flex h-6 w-9 items-center justify-center rounded text-xs font-semibold ${
                            status ? CELL_STYLES[status] : 'text-slate-300'
                          }`}
                        >
                          {status ? STATUS_SYMBOLS[status] : '·'}
                          <span className="sr-only">{title}</span>
                        </span>
                      </td>
                    )
                  })}
                  <td className="px-3 py-1.5 text-right">
                    <YearCell row={row} limits={data.limits} />
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums text-slate-600">
                    {row.year.excused} / {row.year.unexcused}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums text-slate-600">
                    {row.year.school_duty}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Mismatches({
  data,
  onOpenDay,
}: {
  data: ClassAttendance
  onOpenDay: (day: string) => void
}) {
  if (data.mismatches.length === 0) {
    return (
      <p className="text-sm text-slate-600">
        Không có chỗ nào lệch giữa điểm danh tiết của giáo viên bộ môn và điểm danh ngày trong tháng
        này.
      </p>
    )
  }
  return (
    <div className="overflow-x-auto">
      <table className="data-table min-w-max text-sm">
        <thead>
          <tr>
            <th scope="col" className="px-3 py-2 font-medium">
              Ngày
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              Học sinh
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              Tiết học
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              Điểm danh ngày
            </th>
            <th scope="col" className="px-3 py-2">
              <span className="sr-only">Thao tác</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {data.mismatches.map((m, index) => (
            <tr key={index}>
              <td className="px-3 py-2 tabular-nums">
                {weekday(m.date)} {shortDate(m.date)}
              </td>
              <td className="px-3 py-2">{m.full_name}</td>
              <td className="px-3 py-2">
                Tiết {m.lesson_no} {m.subject_name}:{' '}
                <strong>{STATUS_LABELS[m.lesson_status]}</strong>
              </td>
              <td className="px-3 py-2">
                {m.day_status ? STATUS_LABELS[m.day_status] : 'Chưa điểm danh'}
              </td>
              <td className="px-3 py-2 text-right">
                <button type="button" onClick={() => onOpenDay(m.date)} className="link text-sm">
                  {data.can_edit ? 'Xem và sửa ngày' : 'Xem ngày'}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// Trang điểm danh của lớp (D-120): GVCN xem lưới theo tháng, tổng buổi nghỉ cả năm so với các mức
// trong `settings`, điểm danh / sửa từng ngày kèm lý do; đối chiếu với điểm danh theo tiết của GVBM.
// BGH chỉ xem. Mọi số đếm do back-end tính.
export default function AttendancePage() {
  const classId = Number(useParams().classId)
  const [params, setParams] = useSearchParams()
  const month = params.get('month')
  const attendance = useClassAttendance(classId, month)
  const [openDay, setOpenDay] = useState<string | null>(null)
  const [newDay, setNewDay] = useState(todayIso())
  const data = attendance.data

  function setMonth(next: string) {
    setParams(
      (current) => {
        const copy = new URLSearchParams(current)
        copy.set('month', next)
        return copy
      },
      { replace: true },
    )
  }

  return (
    <>
      <PageTitle
        title={data ? `Điểm danh · lớp ${data.class_info.name}` : 'Điểm danh'}
        subtitle="Theo ngày, do giáo viên chủ nhiệm ghi; đối chiếu với điểm danh tiết của giáo viên bộ môn"
        actions={
          <>
            {data && (
              <label className="flex items-center gap-2 text-sm font-medium text-slate-700">
                Tháng
                <select
                  value={data.month}
                  onChange={(event) => setMonth(event.target.value)}
                  className="input w-auto py-1.5"
                >
                  {data.months.map((item) => (
                    <option key={item} value={item}>
                      {formatMonth(item)}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {data?.can_edit && (
              <Link to={`/classes/${classId}/import?kind=attendance`} className="btn-secondary btn-sm">
                <Icon name="upload" className="h-4 w-4" />
                Nhập từ tệp
              </Link>
            )}
            <Link to={`/classes/${classId}`} className="link text-sm">
              Dashboard lớp
            </Link>
          </>
        }
      />
      <QueryState query={attendance}>
        {(result) => (
          <>
            <Summary data={result} />
            <Panel
              id="diem-danh-thang"
              title={`Điểm danh ${formatMonth(result.month).toLowerCase()}`}
              description={`Bấm vào ngày ở hàng tiêu đề để xem${result.can_edit ? ' và sửa' : ''}. Cột "Nghỉ cả năm" = có phép + không phép (Thông tư 22); vắng do trường cử đi không tính. Nhắc từ ${result.limits.notice} buổi, cảnh báo cao từ ${result.limits.high} buổi, quá ${result.limits.maximum} buổi thì không đủ điều kiện lên lớp.`}
              actions={
                result.can_edit && (
                  <form
                    className="flex items-center gap-2"
                    onSubmit={(event) => {
                      event.preventDefault()
                      if (newDay) setOpenDay(newDay)
                    }}
                  >
                    <label className="sr-only" htmlFor="ngay-diem-danh">
                      Ngày điểm danh
                    </label>
                    <input
                      id="ngay-diem-danh"
                      type="date"
                      value={newDay}
                      max={todayIso()}
                      onChange={(event) => setNewDay(event.target.value)}
                      className="input w-auto py-1.5"
                    />
                    <button type="submit" className="btn-primary btn-sm">
                      Điểm danh ngày
                    </button>
                  </form>
                )
              }
            >
              <MonthGrid data={result} onOpenDay={setOpenDay} />
            </Panel>
            <Panel
              id="doi-chieu"
              title="Đối chiếu với điểm danh theo tiết"
              description="Em vắng ở tiết học (giáo viên bộ môn ghi) nhưng điểm danh ngày ghi có mặt, hoặc ngược lại. Hãy xác minh rồi sửa điểm danh ngày nếu cần; nếu em được trường cử đi, chọn 'Vắng do trường cử đi'."
            >
              <Mismatches data={result} onOpenDay={setOpenDay} />
            </Panel>
            {openDay && (
              <DayDialog classId={classId} day={openDay} onClose={() => setOpenDay(null)} />
            )}
          </>
        )}
      </QueryState>
    </>
  )
}
