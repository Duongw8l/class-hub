import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  CONDUCT_LEVELS,
  CONDUCT_PERIODS,
  fetchClassConduct,
  fillYearFromHk2,
  PERIOD_NAMES,
} from '../api/conduct'
import type { ClassConduct, ConductEntry, ConductLevel, ConductRow } from '../api/conduct'
import { useAuth } from '../auth/context'
import { ErrorAlert, SuccessNote } from '../components/admin/shared'
import { ConductDialog } from '../components/conduct/ConductDialog'
import { Icon } from '../components/Icon'
import { PageTitle, Panel } from '../components/Panel'
import { QueryState } from '../components/QueryState'
import { formatPercent } from '../lib/format'
import { LEVEL_LABELS } from '../lib/labels'

const BADGES: Record<ConductLevel, string> = {
  good: 'badge-good',
  fair: 'badge-fair',
  pass: 'badge-pass',
  fail: 'badge-fail',
}
const RANK: Record<ConductLevel, number> = { good: 0, fair: 1, pass: 2, fail: 3 }

type Filter = 'all' | 'missing' | 'fail' | 'drop' | 'edited'

const FILTERS: { value: Filter; label: string; test: (row: ConductRow) => boolean }[] = [
  { value: 'all', label: 'Tất cả', test: () => true },
  { value: 'missing', label: 'Còn trống', test: (row) => row.entries.some((e) => e.level === null) },
  {
    value: 'fail',
    label: `Có kỳ ${LEVEL_LABELS.fail}`,
    test: (row) => row.entries.some((e) => e.level === 'fail'),
  },
  {
    value: 'drop',
    label: 'Học kỳ II thấp hơn học kỳ I',
    test: (row) => {
      const [first, second] = row.entries
      return first.level !== null && second.level !== null && RANK[second.level] > RANK[first.level]
    },
  },
  { value: 'edited', label: 'Đã sửa tay', test: (row) => row.change_count > 0 },
]

function useClassConduct(classId: number) {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['class-conduct', token, classId],
    queryFn: ({ signal }) => fetchClassConduct(classId, signal),
    enabled: token !== null && Number.isInteger(classId),
  })
}

function Counts({ data }: { data: ClassConduct }) {
  const total = data.rows.length
  return (
    <div className="overflow-x-auto">
      <table className="data-table min-w-max">
        <thead>
          <tr>
            <th scope="col" className="px-3 py-2 font-medium">
              Kỳ
            </th>
            {CONDUCT_LEVELS.map((level) => (
              <th key={level} scope="col" className="px-3 py-2 text-right font-medium">
                {LEVEL_LABELS[level]}
              </th>
            ))}
            <th scope="col" className="px-3 py-2 text-right font-medium">
              Chưa có
            </th>
          </tr>
        </thead>
        <tbody>
          {CONDUCT_PERIODS.map((period) => {
            const counts = data.counts[period]
            return (
              <tr key={period}>
                <th scope="row" className="px-3 py-2 text-left font-medium">
                  {PERIOD_NAMES[period]}
                </th>
                {[...CONDUCT_LEVELS, 'missing' as const].map((key) => (
                  <td key={key} className="px-3 py-2 text-right tabular-nums">
                    {counts[key]}
                    <span className="ml-1 text-xs text-slate-500">
                      ({formatPercent(counts[key], total)})
                    </span>
                  </td>
                ))}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function LevelCell({ entry, derivedFrom }: { entry: ConductEntry; derivedFrom?: ConductLevel | null }) {
  if (entry.level === null) {
    return derivedFrom ? (
      <span className="text-xs text-slate-500" title="Chưa nhập cả năm: hệ thống đang tạm lấy theo học kỳ II">
        — <span className="italic">(tạm theo HK II: {LEVEL_LABELS[derivedFrom]})</span>
      </span>
    ) : (
      <span className="text-slate-400">—</span>
    )
  }
  return (
    <span>
      <span className={BADGES[entry.level]}>{LEVEL_LABELS[entry.level]}</span>
      {entry.comment && (
        <span className="mt-1 block max-w-[14rem] truncate text-xs text-slate-500" title={entry.comment}>
          {entry.comment}
        </span>
      )}
    </span>
  )
}

function YearFill({ data }: { data: ClassConduct }) {
  const queryClient = useQueryClient()
  const [confirming, setConfirming] = useState(false)
  const mutation = useMutation({
    mutationFn: () => fillYearFromHk2(data.class_info.id),
    onSuccess: () => {
      setConfirming(false)
      void queryClient.invalidateQueries()
    },
  })
  if (!data.can_edit) return null
  if (mutation.isSuccess) {
    return <SuccessNote>Đã ghi cả năm theo học kỳ II cho {mutation.data.filled} học sinh.</SuccessNote>
  }
  if (data.year_fillable === 0) return null
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-xl bg-slate-50 p-3 text-sm ring-1 ring-slate-200">
      <span>
        {data.year_fillable} học sinh đã có học kỳ II nhưng chưa có kết quả cả năm.
      </span>
      {confirming ? (
        <>
          <button
            type="button"
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
            className="btn-primary btn-sm"
          >
            {mutation.isPending ? 'Đang ghi…' : `Xác nhận ghi cho ${data.year_fillable} em`}
          </button>
          <button type="button" onClick={() => setConfirming(false)} className="btn-secondary btn-sm">
            Huỷ
          </button>
        </>
      ) : (
        <button type="button" onClick={() => setConfirming(true)} className="btn-secondary btn-sm">
          Ghi cả năm theo học kỳ II
        </button>
      )}
      {mutation.isError && <ErrorAlert error={mutation.error} />}
    </div>
  )
}

function StudentTable({ data }: { data: ClassConduct }) {
  const [filter, setFilter] = useState<Filter>('all')
  const [search, setSearch] = useState('')
  const [open, setOpen] = useState<ConductRow | null>(null)
  const needle = search.trim().toLocaleLowerCase('vi')
  const active = FILTERS.find((item) => item.value === filter) ?? FILTERS[0]
  const rows = data.rows.filter(
    (row) =>
      active.test(row) &&
      (needle === '' ||
        row.full_name.toLocaleLowerCase('vi').includes(needle) ||
        row.student_code.toLocaleLowerCase('vi').includes(needle)),
  )

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div role="group" aria-label="Lọc học sinh" className="flex flex-wrap gap-2">
          {FILTERS.map((item) => (
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
        <label className="flex items-center gap-2 text-sm">
          <span className="sr-only">Tìm học sinh</span>
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Tìm theo tên hoặc mã HS"
            className="input w-56 py-1.5"
          />
        </label>
      </div>
      <div className="overflow-x-auto">
        <table className="data-table min-w-max">
          <thead>
            <tr>
              <th scope="col" className="px-3 py-2 text-right font-medium">
                STT
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                Học sinh
              </th>
              {CONDUCT_PERIODS.map((period) => (
                <th key={period} scope="col" className="px-3 py-2 font-medium">
                  {PERIOD_NAMES[period]}
                </th>
              ))}
              <th scope="col" className="px-3 py-2">
                <span className="sr-only">Thao tác</span>
              </th>
            </tr>
          </thead>
          <tbody className="align-top">
            {rows.map((row) => {
              const [first, second, year] = row.entries
              return (
                <tr key={row.student_id}>
                  <td className="px-3 py-2 text-right tabular-nums text-slate-500">
                    {data.rows.indexOf(row) + 1}
                  </td>
                  <th scope="row" className="px-3 py-2 text-left font-normal">
                    <Link
                      to={`/classes/${data.class_info.id}/students/${row.student_id}?semester=year`}
                      className="link"
                    >
                      {row.full_name}
                    </Link>
                    <span className="block font-mono text-xs text-slate-500">
                      {row.student_code}
                    </span>
                  </th>
                  <td className="px-3 py-2">
                    <LevelCell entry={first} />
                  </td>
                  <td className="px-3 py-2">
                    <LevelCell entry={second} />
                  </td>
                  <td className="px-3 py-2">
                    <LevelCell entry={year} derivedFrom={second.level} />
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button
                      type="button"
                      onClick={() => setOpen(row)}
                      aria-label={`${data.can_edit ? 'Sửa' : 'Lịch sử'} rèn luyện của ${row.full_name}`}
                      className="link text-sm"
                    >
                      {data.can_edit ? 'Sửa' : 'Lịch sử'}
                    </button>
                    {row.change_count > 0 && (
                      <span className="ml-2 text-xs text-slate-500">
                        đã sửa {row.change_count} lần
                      </span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
        {rows.length === 0 && (
          <p className="py-4 text-sm text-slate-600">Không có học sinh nào khớp bộ lọc.</p>
        )}
      </div>
      {open && (
        <ConductDialog
          classId={data.class_info.id}
          studentId={open.student_id}
          studentName={open.full_name}
          onClose={() => setOpen(null)}
        />
      )}
    </div>
  )
}

function Content({ data }: { data: ClassConduct }) {
  return (
    <>
      {!data.can_edit && (
        <p className="flex items-start gap-3 rounded-2xl bg-tint p-4 text-sm text-tint-text ring-1 ring-brand-200/70">
          <Icon name="info" className="mt-0.5 h-5 w-5 shrink-0" />
          <span>Chỉ giáo viên chủ nhiệm của lớp sửa được rèn luyện; bạn đang ở chế độ xem.</span>
        </p>
      )}
      <Panel id="tong-hop-ren-luyen" title="Tổng hợp theo kỳ" description="Số học sinh ở từng mức (tỉ lệ trên sĩ số).">
        <Counts data={data} />
      </Panel>
      <Panel
        id="bang-ren-luyen"
        title="Rèn luyện từng học sinh"
        description={
          data.can_edit
            ? 'Bấm "Sửa" để nhập hoặc điều chỉnh mức và nhận xét của từng kỳ; mỗi lần sửa cần chọn lý do và được lưu lại trong lịch sử.'
            : 'Bấm "Lịch sử" để xem các lần giáo viên chủ nhiệm sửa tay.'
        }
      >
        <div className="space-y-4">
          <YearFill data={data} />
          <StudentTable data={data} />
        </div>
      </Panel>
    </>
  )
}

// Trang rèn luyện của một lớp (D-119): GVCN xem đủ ba kỳ của cả lớp, sửa / nhập tay từng em (bắt
// chọn lý do, có lịch sử), ghi cả năm theo học kỳ II cho em còn trống; BGH chỉ xem.
export default function ConductPage() {
  const classId = Number(useParams().classId)
  const conduct = useClassConduct(classId)
  const data = conduct.data
  return (
    <>
      <PageTitle
        title={data ? `Rèn luyện · lớp ${data.class_info.name}` : 'Rèn luyện'}
        subtitle="Học kỳ I, học kỳ II và cả năm"
        actions={
          <>
            {data?.can_edit && (
              <Link to={`/classes/${classId}/import?kind=conduct`} className="btn-secondary btn-sm">
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
      <QueryState query={conduct}>{(result) => <Content data={result} />}</QueryState>
    </>
  )
}
