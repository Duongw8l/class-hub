import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import type { ScoreRow, SubjectScores } from '../api/analytics'
import { DistributionChart } from '../components/charts/DistributionChart'
import { PageTitle, Panel } from '../components/Panel'
import { PeriodSelect } from '../components/PeriodSelect'
import { QueryState } from '../components/QueryState'
import { StudentScoresDialog } from '../components/scores/StudentScoresDialog'
import { StatCard, StatGrid } from '../components/StatCard'
import { SupportStudents } from '../components/support/SupportParts'
import { useAssignments } from '../hooks/useAssignments'
import { useSubjectScores, useSubjectSupport, usePeriod } from '../hooks/useAnalytics'
import { formatScore } from '../lib/format'
import { COMMENT_LABELS } from '../lib/labels'

const SEMESTERS = ['1', '2'] as const

function Missing() {
  return (
    <span className="rounded bg-red-100 px-1.5 py-0.5 text-xs font-medium text-red-800">thiếu</span>
  )
}

function ScoreCell({ value }: { value: number | undefined | null }) {
  return (
    <td className="px-2 py-1.5 text-right tabular-nums">
      {value === undefined || value === null ? <Missing /> : formatScore(value)}
    </td>
  )
}

function AverageCell({
  value,
  complete,
  scores,
}: {
  value: number | null
  complete: boolean
  scores: SubjectScores
}) {
  const { thresholds } = scores
  let tone = ''
  if (value !== null && value < thresholds.fail) tone = 'font-semibold text-red-700'
  else if (value !== null && value < thresholds.passing) tone = 'font-medium text-amber-700'
  return (
    <td
      className={`px-2 py-1.5 text-right tabular-nums ${tone}`}
      title={value !== null && !complete ? 'Tạm tính: còn thiếu đầu điểm' : undefined}
    >
      {formatScore(value)}
      {value !== null && !complete && <sup aria-label="tạm tính">*</sup>}
    </td>
  )
}

interface RowActions {
  canEdit: boolean
  onOpen: (row: ScoreRow) => void
}

// Nút ở cuối mỗi dòng: GVBM được phân công thấy "Sửa"; GVCN, BGH thấy "Lịch sử" (chỉ xem).
function ActionCell({ row, actions }: { row: ScoreRow; actions: RowActions }) {
  return (
    <td className="px-2 py-1">
      <button
        type="button"
        onClick={() => actions.onOpen(row)}
        aria-label={`${actions.canEdit ? 'Sửa điểm' : 'Lịch sử sửa điểm'} của ${row.full_name}`}
        className="btn-secondary px-2.5 py-1 text-xs"
      >
        {actions.canEdit ? 'Sửa' : 'Lịch sử'}
      </button>
    </td>
  )
}

function ActionHeader() {
  return (
    <th scope="col" className="px-2 py-2 font-medium">
      <span className="sr-only">Thao tác</span>
    </th>
  )
}

function missingCount(row: ScoreRow): number {
  return row.tx_missing + (row.midterm === null ? 1 : 0) + (row.final === null ? 1 : 0)
}

function ScoreGrid({
  scores,
  rows,
  actions,
}: {
  scores: SubjectScores
  rows: ScoreRow[]
  actions: RowActions
}) {
  const classId = scores.class_info.id
  const txColumns = Math.max(scores.subject.regular_required, ...rows.map((row) => row.tx.length))
  const txIndexes = Array.from({ length: txColumns }, (_, index) => index)
  return (
    <div className="overflow-x-auto">
      <table className="data-table min-w-max">
        <thead>
          <tr>
            <th scope="col" className="px-2 py-2 font-medium">
              STT
            </th>
            <th scope="col" className="px-2 py-2 font-medium">
              Mã HS
            </th>
            <th scope="col" className="px-2 py-2 font-medium">
              Họ và tên
            </th>
            {txIndexes.map((index) => (
              <th key={index} scope="col" className="px-2 py-2 text-right font-medium">
                TX{index + 1}
              </th>
            ))}
            <th scope="col" className="px-2 py-2 text-right font-medium">
              Giữa kỳ
            </th>
            <th scope="col" className="px-2 py-2 text-right font-medium">
              Cuối kỳ
            </th>
            <th scope="col" className="border-l border-slate-200 px-2 py-2 text-right font-medium">
              ĐTB kỳ này
            </th>
            <th scope="col" className="px-2 py-2 text-right font-medium">
              ĐTB HK I
            </th>
            <th scope="col" className="px-2 py-2 text-right font-medium">
              ĐTB HK II
            </th>
            <th scope="col" className="px-2 py-2 text-right font-medium">
              ĐTB cả năm
            </th>
            <th scope="col" className="px-2 py-2 font-medium">
              Ghi chú
            </th>
            <ActionHeader />
          </tr>
        </thead>
        <tbody>
          {rows.map((row, position) => (
            <tr key={row.student_id} className={row.complete ? '' : 'bg-red-50'}>
              <td className="px-2 py-1.5 text-slate-500">{position + 1}</td>
              <td className="px-2 py-1.5 font-mono">{row.student_code}</td>
              <th scope="row" className="px-2 py-1.5 font-normal">
                <Link
                  to={`/classes/${classId}/students/${row.student_id}`}
                  className="link"
                >
                  {row.full_name}
                </Link>
              </th>
              {txIndexes.map((index) => (
                <ScoreCell key={index} value={row.tx[index]} />
              ))}
              <ScoreCell value={row.midterm} />
              <ScoreCell value={row.final} />
              <AverageCell value={row.average} complete={row.complete} scores={scores} />
              <td className="px-2 py-1.5 text-right tabular-nums text-slate-600">
                {formatScore(row.average_semester1)}
              </td>
              <td className="px-2 py-1.5 text-right tabular-nums text-slate-600">
                {formatScore(row.average_semester2)}
              </td>
              <td className="px-2 py-1.5 text-right tabular-nums text-slate-600">
                {formatScore(row.year_average)}
              </td>
              <td className="px-2 py-1.5 text-xs text-red-800">
                {!row.complete && `Thiếu ${missingCount(row)} đầu điểm`}
              </td>
              <ActionCell row={row} actions={actions} />
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function CommentGrid({
  scores,
  rows,
  actions,
}: {
  scores: SubjectScores
  rows: ScoreRow[]
  actions: RowActions
}) {
  return (
    <div className="overflow-x-auto">
      <table className="data-table min-w-max">
        <thead>
          <tr>
            <th scope="col" className="px-2 py-2 font-medium">
              STT
            </th>
            <th scope="col" className="px-2 py-2 font-medium">
              Mã HS
            </th>
            <th scope="col" className="px-2 py-2 font-medium">
              Họ và tên
            </th>
            <th scope="col" className="px-2 py-2 font-medium">
              Nhận xét
            </th>
            <ActionHeader />
          </tr>
        </thead>
        <tbody>
          {rows.map((row, position) => (
            <tr key={row.student_id} className={row.complete ? '' : 'bg-red-50'}>
              <td className="px-2 py-1.5 text-slate-500">{position + 1}</td>
              <td className="px-2 py-1.5 font-mono">{row.student_code}</td>
              <th scope="row" className="px-2 py-1.5 font-normal">
                <Link
                  to={`/classes/${scores.class_info.id}/students/${row.student_id}`}
                  className="link"
                >
                  {row.full_name}
                </Link>
              </th>
              <td className="px-2 py-1.5">
                {row.comment_result ? (
                  <span className={row.comment_result === 'fail' ? 'font-medium text-red-700' : ''}>
                    {COMMENT_LABELS[row.comment_result]}
                  </span>
                ) : (
                  <Missing />
                )}
              </td>
              <ActionCell row={row} actions={actions} />
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Distribution({ scores }: { scores: SubjectScores }) {
  const { distribution: d, thresholds: t } = scores
  return (
    <DistributionChart
      label="Số học sinh theo khoảng điểm trung bình"
      data={[
        { name: `Dưới ${formatScore(t.fail)}`, value: d.below_fail, color: 'var(--chart-fail)' },
        {
          name: `${formatScore(t.fail)} đến dưới ${formatScore(t.passing)}`,
          value: d.fail_to_pass,
          color: 'var(--chart-orange)',
        },
        {
          name: `${formatScore(t.passing)} đến dưới ${formatScore(t.fair)}`,
          value: d.pass_to_fair,
          color: 'var(--chart-pass)',
        },
        {
          name: `${formatScore(t.fair)} đến dưới ${formatScore(t.good)}`,
          value: d.fair_to_good,
          color: 'var(--chart-fair)',
        },
        { name: `Từ ${formatScore(t.good)}`, value: d.at_least_good, color: 'var(--chart-good)' },
      ]}
    />
  )
}

type ScoreBand = 'below_fail' | 'fail_to_pass' | 'pass_to_fair' | 'fair_to_good' | 'at_least_good'
type RowFilter = 'all' | 'missing' | ScoreBand | 'comment_pass' | 'comment_fail'
type Basis = 'semester' | 'year'

// Khoảng điểm của một ĐTB theo ngưỡng do back-end trả (đọc từ bảng settings, nguyên tắc 2), cùng
// cách chia với biểu đồ phân bố. Chỉ để lọc hiển thị; ĐTB vẫn do server tính.
function bandOf(value: number | null, t: SubjectScores['thresholds']): ScoreBand | null {
  if (value === null) return null
  if (value < t.fail) return 'below_fail'
  if (value < t.passing) return 'fail_to_pass'
  if (value < t.fair) return 'pass_to_fair'
  if (value < t.good) return 'fair_to_good'
  return 'at_least_good'
}

function matches(row: ScoreRow, filter: RowFilter, basis: Basis, scores: SubjectScores): boolean {
  switch (filter) {
    case 'all':
      return true
    case 'missing':
      return !row.complete
    case 'comment_pass':
      return row.comment_result === 'pass'
    case 'comment_fail':
      return row.comment_result === 'fail'
    default:
      return (
        bandOf(basis === 'year' ? row.year_average : row.average, scores.thresholds) === filter
      )
  }
}

function filterOptions(
  scores: SubjectScores,
  isScore: boolean,
): { key: RowFilter; label: string }[] {
  const t = scores.thresholds
  const all = { key: 'all' as const, label: 'Tất cả' }
  const missing = { key: 'missing' as const, label: 'Còn thiếu đầu điểm' }
  if (!isScore) {
    return [
      all,
      { key: 'comment_pass', label: 'Đạt' },
      { key: 'comment_fail', label: 'Chưa đạt' },
      missing,
    ]
  }
  return [
    all,
    { key: 'below_fail', label: `Dưới ${formatScore(t.fail)}` },
    { key: 'fail_to_pass', label: `${formatScore(t.fail)} đến dưới ${formatScore(t.passing)}` },
    { key: 'pass_to_fair', label: `${formatScore(t.passing)} đến dưới ${formatScore(t.fair)}` },
    { key: 'fair_to_good', label: `${formatScore(t.fair)} đến dưới ${formatScore(t.good)}` },
    { key: 'at_least_good', label: `Từ ${formatScore(t.good)}` },
    missing,
  ]
}

const EMPTY_TEXT: Record<RowFilter, string> = {
  all: 'Lớp chưa có học sinh.',
  missing: 'Không có học sinh nào thiếu đầu điểm.',
  below_fail: 'Không có học sinh nào trong khoảng điểm này.',
  fail_to_pass: 'Không có học sinh nào trong khoảng điểm này.',
  pass_to_fair: 'Không có học sinh nào trong khoảng điểm này.',
  fair_to_good: 'Không có học sinh nào trong khoảng điểm này.',
  at_least_good: 'Không có học sinh nào trong khoảng điểm này.',
  comment_pass: 'Không có học sinh nào Đạt.',
  comment_fail: 'Không có học sinh nào Chưa đạt.',
}

function ScoresContent({ scores, canImport }: { scores: SubjectScores; canImport: boolean }) {
  const [filter, setFilter] = useState<RowFilter>('all')
  const [basis, setBasis] = useState<Basis>('semester')
  const [open, setOpen] = useState<ScoreRow | null>(null)
  const actions: RowActions = { canEdit: canImport, onOpen: setOpen }
  const isScore = scores.subject.assessment_type === 'score'
  const options = filterOptions(scores, isScore)
  const count = (key: RowFilter) =>
    scores.rows.filter((row) => matches(row, key, basis, scores)).length
  const rows = scores.rows.filter((row) => matches(row, filter, basis, scores))

  return (
    <>
      <StatGrid>
        <StatCard label="Sĩ số" value={scores.student_count} />
        {isScore ? (
          <StatCard label="ĐTB của lớp" value={formatScore(scores.mean)} />
        ) : (
          <StatCard
            label="Chưa đạt"
            value={scores.comment_fail_count}
            valueClassName={scores.comment_fail_count > 0 ? 'text-red-700' : 'text-slate-900'}
          />
        )}
        <StatCard
          label="Chưa đủ đầu điểm"
          value={scores.incomplete_count}
          valueClassName={scores.incomplete_count > 0 ? 'text-red-700' : 'text-slate-900'}
          hint={
            isScore
              ? `Mỗi học kỳ cần ${scores.subject.regular_required} đầu điểm thường xuyên`
              : undefined
          }
        />
        {canImport && (
          <div className="flex items-center card p-4">
            <Link
              to={`/classes/${scores.class_info.id}/import?kind=assessments&subject=${scores.subject.id}`}
              className="font-medium link"
            >
              Nhập điểm từ tệp
            </Link>
          </div>
        )}
      </StatGrid>

      {isScore && (
        <Panel id="phan-bo" title="Phân bố điểm trung bình">
          <Distribution scores={scores} />
        </Panel>
      )}

      <Panel
        id="luoi-diem"
        title={isScore ? 'Bảng điểm' : 'Nhận xét'}
        description={
          isScore
            ? `ĐTB do hệ thống tính theo Thông tư 22. Dấu * là điểm tạm tính vì còn thiếu đầu điểm.${
                canImport
                  ? ' Bấm "Sửa" ở cuối dòng để sửa hoặc nhập tay điểm của một học sinh.'
                  : ''
              }`
            : canImport
              ? 'Bấm "Sửa" ở cuối dòng để đổi nhận xét của một học sinh.'
              : undefined
        }
      >
        <div className="mb-4 space-y-3">
          {isScore && (
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <label htmlFor="loc-theo-dtb" className="text-slate-600">
                Lọc theo
              </label>
              <select
                id="loc-theo-dtb"
                value={basis}
                onChange={(event) => setBasis(event.target.value as Basis)}
                className="input w-auto py-1.5 text-sm"
              >
                <option value="semester">
                  ĐTB học kỳ {scores.semester === 1 ? 'I' : 'II'}
                </option>
                <option value="year">ĐTB cả năm</option>
              </select>
            </div>
          )}
          <div role="group" aria-label="Lọc học sinh" className="flex flex-wrap gap-2">
            {options.map((option) => {
              const active = filter === option.key
              return (
                <button
                  key={option.key}
                  type="button"
                  aria-pressed={active}
                  onClick={() => setFilter(option.key)}
                  className={`rounded-full px-3 py-1.5 text-sm ring-1 transition ${
                    active
                      ? 'bg-brand-700 text-white ring-brand-700'
                      : 'bg-surface text-slate-700 ring-slate-300 hover:bg-slate-100'
                  }`}
                >
                  {option.label}{' '}
                  <span className={active ? 'text-white/80' : 'text-slate-500'}>
                    ({count(option.key)})
                  </span>
                </button>
              )
            })}
          </div>
          {isScore && basis === 'year' && (
            <p className="text-xs text-slate-500">
              ĐTB cả năm chỉ có khi đủ điểm hai học kỳ; học sinh chưa có ĐTB cả năm không thuộc
              khoảng điểm nào.
            </p>
          )}
          <p aria-live="polite" className="text-sm text-slate-500">
            Hiện {rows.length} / {scores.rows.length} học sinh.
          </p>
        </div>
        {rows.length === 0 ? (
          <p className="text-sm text-slate-600">{EMPTY_TEXT[filter]}</p>
        ) : isScore ? (
          <ScoreGrid scores={scores} rows={rows} actions={actions} />
        ) : (
          <CommentGrid scores={scores} rows={rows} actions={actions} />
        )}
      </Panel>
      {open && (
        <StudentScoresDialog
          classId={scores.class_info.id}
          subjectId={scores.subject.id}
          studentId={open.student_id}
          studentName={open.full_name}
          semester={scores.semester === 2 ? 2 : 1}
          onClose={() => setOpen(null)}
        />
      )}
    </>
  )
}

// Bảng điểm một môn của lớp (GVBM đúng môn, GVCN, BGH): lưới đầu điểm, ĐTB do server tính, ô thiếu
// đầu điểm được tô nổi.
// Học sinh cần hỗ trợ trong môn này (D-118): cùng học kỳ với bảng điểm. GVBM của lớp–môn có thêm
// lối tới số liệu kế hoạch dạy học và gợi ý của AI.
function SupportPanel({
  classId,
  subjectId,
  semester,
  canPlan,
}: {
  classId: number
  subjectId: number
  semester: 1 | 2
  canPlan: boolean
}) {
  const support = useSubjectSupport(classId, subjectId, semester)
  return (
    <Panel
      id="hoc-sinh-can-ho-tro"
      title="Học sinh cần hỗ trợ trong môn"
      description="Chỉ dựa trên điểm môn này: ĐTB thấp, tụt khoảng điểm so với học kỳ I, bài giữa kỳ hoặc cuối kỳ thấp, còn thiếu đầu điểm."
      actions={
        canPlan && (
          <Link
            to={`/support?item=${classId}:${subjectId}&hk=${semester}`}
            className="link text-sm"
          >
            Số liệu & AI gợi ý kế hoạch dạy học
          </Link>
        )
      }
    >
      <QueryState query={support}>{(item) => <SupportStudents item={item} />}</QueryState>
    </Panel>
  )
}

export default function SubjectScoresPage() {
  const params = useParams()
  const classId = Number(params.classId)
  const subjectId = Number(params.subjectId)
  const [period, setPeriod] = usePeriod(SEMESTERS, '1')
  const scores = useSubjectScores(classId, subjectId, period === '2' ? 2 : 1)
  const assignments = useAssignments()
  const canImport =
    assignments.data?.teaching.some(
      (item) => item.class_id === classId && item.subject_id === subjectId,
    ) ?? false
  // Dashboard lớp chỉ dành cho GVCN của lớp và BGH (GVBM nhận 403), nên chỉ hiện liên kết cho họ.
  const canOpenDashboard =
    assignments.data !== undefined &&
    (assignments.data.user.role === 'principal' ||
      assignments.data.homeroom_classes.some((item) => item.id === classId))
  const data = scores.data

  return (
    <>
      <PageTitle
        title={
          data ? `Bảng điểm ${data.subject.name} · lớp ${data.class_info.name}` : 'Bảng điểm môn'
        }
        actions={
          <>
            <PeriodSelect value={period} options={SEMESTERS} onChange={setPeriod} />
            <Link to={`/classes/${classId}/subjects/${subjectId}/lessons`} className="link text-sm">
              Điểm danh tiết học
            </Link>
            {canOpenDashboard && (
              <Link
                to={`/classes/${classId}`}
                className="link text-sm"
              >
                Dashboard lớp
              </Link>
            )}
          </>
        }
      />
      <QueryState query={scores}>
        {(result) => <ScoresContent key={result.semester} scores={result} canImport={canImport} />}
      </QueryState>
      <SupportPanel
        classId={classId}
        subjectId={subjectId}
        semester={period === '2' ? 2 : 1}
        canPlan={canImport}
      />
    </>
  )
}
