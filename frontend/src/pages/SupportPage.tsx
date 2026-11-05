import { Link, useSearchParams } from 'react-router-dom'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { MySupport, SubjectSupport } from '../api/analytics'
import { axisTick, gridProps, legendProps, tooltipProps } from '../components/charts/theme'
import { Icon } from '../components/Icon'
import { PageTitle, Panel } from '../components/Panel'
import { QueryState } from '../components/QueryState'
import { StatCard, StatGrid } from '../components/StatCard'
import { SEMESTER_LABELS, SUPPORT_LEVELS } from '../components/support/levels'
import { PlanStats, SupportStudents, TeachingPlanDraft } from '../components/support/SupportParts'
import { useMySupport } from '../hooks/useAnalytics'
import { useAssignments } from '../hooks/useAssignments'
import { formatInt, formatPercent, formatScore } from '../lib/format'
import { RISK_LABELS } from '../lib/labels'

const LEVEL_FILLS = {
  high: 'var(--chart-fail)',
  medium: 'var(--chart-pass)',
  low: 'var(--chart-neutral)',
} as const

const keyOf = (item: SubjectSupport) => `${item.class_info.id}:${item.subject.id}`
const labelOf = (item: SubjectSupport) => `${item.class_info.name} · ${item.subject.name}`

function SemesterChoice({
  value,
  onChange,
}: {
  value: 1 | 2 | null
  onChange: (value: 1 | 2 | null) => void
}) {
  return (
    <label className="flex items-center gap-2 text-sm font-medium text-slate-700">
      Học kỳ
      <select
        value={value ?? 'auto'}
        onChange={(event) =>
          onChange(event.target.value === 'auto' ? null : (Number(event.target.value) as 1 | 2))
        }
        className="input w-auto py-1.5"
      >
        <option value="auto">Mới nhất có điểm</option>
        <option value="1">Học kỳ I</option>
        <option value="2">Học kỳ II</option>
      </select>
    </label>
  )
}

function Summary({ data }: { data: MySupport }) {
  const sum = (level: 'high' | 'medium' | 'low') =>
    data.items.reduce((acc, item) => acc + item.counts[level], 0)
  const students = data.items.reduce((acc, item) => acc + item.student_count, 0)
  const support = data.items.reduce((acc, item) => acc + item.stats.support_group, 0)
  return (
    <StatGrid>
      <StatCard
        label={RISK_LABELS.high}
        value={formatInt(sum('high'))}
        valueClassName={sum('high') > 0 ? 'text-red-700' : 'text-slate-900'}
        hint="ĐTB môn dưới ngưỡng quá thấp"
        icon="alert"
        tone={sum('high') > 0 ? 'danger' : 'neutral'}
      />
      <StatCard
        label={RISK_LABELS.medium}
        value={formatInt(sum('medium'))}
        valueClassName={sum('medium') > 0 ? 'text-amber-700' : 'text-slate-900'}
        hint="Chưa đạt, hoặc tụt khoảng điểm so với học kỳ I"
        icon="bell"
        tone={sum('medium') > 0 ? 'warn' : 'neutral'}
      />
      <StatCard
        label={RISK_LABELS.low}
        value={formatInt(sum('low'))}
        hint="Bài kiểm tra thấp hoặc còn thiếu đầu điểm"
        icon="clock"
        tone="neutral"
      />
      <StatCard
        label="Cần phụ đạo (ĐTB chưa đạt)"
        value={formatPercent(support, students)}
        hint={`${formatInt(support)}/${formatInt(students)} lượt học sinh ở ${data.items.length} lớp–môn`}
        icon="users"
      />
    </StatGrid>
  )
}

function OverviewChart({ items }: { items: SubjectSupport[] }) {
  const data = items.map((item) => ({ name: labelOf(item), ...item.counts }))
  return (
    <figure
      aria-label="Số học sinh cần hỗ trợ theo mức của từng lớp–môn"
      className="h-72 w-full min-w-0 overflow-hidden"
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
          <CartesianGrid {...gridProps} />
          <XAxis dataKey="name" tick={axisTick(11)} interval={0} />
          <YAxis allowDecimals={false} tick={axisTick()} />
          <Tooltip {...tooltipProps} />
          <Legend itemSorter={null} {...legendProps} />
          {SUPPORT_LEVELS.map((level) => (
            <Bar
              key={level}
              dataKey={level}
              name={RISK_LABELS[level]}
              stackId="levels"
              fill={LEVEL_FILLS[level]}
              stroke="var(--color-surface)"
              strokeWidth={1}
              isAnimationActive={false}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </figure>
  )
}

function OverviewTable({
  items,
  selected,
  onSelect,
}: {
  items: SubjectSupport[]
  selected: string
  onSelect: (key: string) => void
}) {
  return (
    <div className="overflow-x-auto">
      <table className="data-table min-w-max">
        <thead>
          <tr>
            <th scope="col" className="px-3 py-2 font-medium">
              Lớp · môn
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              Học kỳ
            </th>
            <th scope="col" className="px-3 py-2 text-right font-medium">
              ĐTB lớp
            </th>
            {SUPPORT_LEVELS.map((level) => (
              <th key={level} scope="col" className="px-3 py-2 text-right font-medium">
                {RISK_LABELS[level]}
              </th>
            ))}
            <th scope="col" className="px-3 py-2 text-right font-medium">
              Cần phụ đạo
            </th>
            <th scope="col" className="px-3 py-2 text-right font-medium">
              Có thể bồi dưỡng
            </th>
            <th scope="col" className="px-3 py-2">
              <span className="sr-only">Thao tác</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const key = keyOf(item)
            const isScore = item.subject.assessment_type === 'score'
            return (
              <tr key={key} className={key === selected ? 'bg-tint' : undefined}>
                <th scope="row" className="px-3 py-2 text-left font-medium">
                  {labelOf(item)}
                </th>
                <td className="px-3 py-2">{SEMESTER_LABELS[item.semester]}</td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {isScore ? formatScore(item.mean) : '—'}
                </td>
                {SUPPORT_LEVELS.map((level) => (
                  <td key={level} className="px-3 py-2 text-right tabular-nums">
                    {item.counts[level]}
                  </td>
                ))}
                <td className="px-3 py-2 text-right tabular-nums">
                  {isScore
                    ? `${item.stats.support_group} (${formatPercent(item.stats.support_group, item.student_count)})`
                    : '—'}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {isScore ? item.stats.advanced_group : '—'}
                </td>
                <td className="px-3 py-2 text-right">
                  <button
                    type="button"
                    onClick={() => onSelect(key)}
                    aria-pressed={key === selected}
                    aria-label={`Xem chi tiết ${labelOf(item)}`}
                    className="link text-sm"
                  >
                    {key === selected ? 'Đang xem' : 'Xem'}
                  </button>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function Detail({ item }: { item: SubjectSupport }) {
  const title = `${labelOf(item)} · ${SEMESTER_LABELS[item.semester]}`
  return (
    <>
      <Panel
        id="chi-tiet-ho-tro"
        title={`Học sinh cần hỗ trợ · ${title}`}
        description="Chỉ dựa trên điểm môn này. Đây là gợi ý để thầy/cô quyết định, không tự gửi cho học sinh hay phụ huynh."
        actions={
          <Link
            to={`/classes/${item.class_info.id}/subjects/${item.subject.id}?semester=${item.semester}`}
            className="link text-sm"
          >
            Bảng điểm
          </Link>
        }
      >
        <SupportStudents key={keyOf(item)} item={item} />
      </Panel>
      <Panel
        id="ke-hoach-day-hoc"
        title="Số liệu để điều chỉnh kế hoạch dạy học"
        description={`${title} · sĩ số ${item.student_count}. Số liệu do hệ thống tính từ điểm đã nhập.`}
      >
        <PlanStats item={item} />
      </Panel>
      <Panel
        id="goi-y-ai"
        title="AI gợi ý điều chỉnh kế hoạch dạy học"
        description="AI chỉ diễn giải số liệu ở trên (không có tên học sinh). Bản luôn là bản nháp cho tới khi thầy/cô sửa và duyệt; xuất PDF được sau khi duyệt."
      >
        <TeachingPlanDraft key={`${keyOf(item)}-${item.semester}`} item={item} />
      </Panel>
    </>
  )
}

function Workspace({ data }: { data: MySupport }) {
  const [params, setParams] = useSearchParams()
  const items = data.items
  if (items.length === 0) {
    return (
      <p className="card p-6 text-slate-600">
        Tài khoản này chưa được phân công dạy lớp–môn nào trong năm học đang xem.
      </p>
    )
  }
  // Mặc định: lớp–môn có nhiều em mức cao nhất, rồi mức trung bình.
  const busiest = [...items].sort(
    (a, b) => b.counts.high - a.counts.high || b.counts.medium - a.counts.medium,
  )[0]
  const selected = items.find((item) => keyOf(item) === params.get('item')) ?? busiest

  function select(key: string) {
    setParams(
      (current) => {
        const next = new URLSearchParams(current)
        next.set('item', key)
        return next
      },
      { replace: true },
    )
  }

  return (
    <>
      <Summary data={data} />
      <Panel
        id="tong-quan-lop-mon"
        title="Các lớp–môn đang dạy"
        description="Số học sinh cần hỗ trợ theo mức. Chọn một lớp–môn để xem danh sách, số liệu và gợi ý kế hoạch."
      >
        <div className="space-y-6">
          <OverviewChart items={items} />
          <OverviewTable items={items} selected={keyOf(selected)} onSelect={select} />
        </div>
      </Panel>
      <Detail item={selected} />
    </>
  )
}

// Trang của giáo viên bộ môn: học sinh cần hỗ trợ ở mọi lớp–môn mình dạy (D-118). Chỉ dựa trên điểm
// của các môn đó; chuyên cần, rèn luyện và cảnh báo sớm tổng hợp vẫn chỉ GVCN và BGH xem (D-073).
export default function SupportPage() {
  const [params, setParams] = useSearchParams()
  const raw = params.get('hk')
  const semester = raw === '1' ? 1 : raw === '2' ? 2 : null
  const assignments = useAssignments()
  const teaches = (assignments.data?.teaching.length ?? 0) > 0
  const support = useMySupport(semester, teaches)

  function setSemester(value: 1 | 2 | null) {
    setParams(
      (current) => {
        const next = new URLSearchParams(current)
        if (value === null) next.delete('hk')
        else next.set('hk', String(value))
        return next
      },
      { replace: true },
    )
  }

  return (
    <>
      <PageTitle
        title="Học sinh cần hỗ trợ"
        subtitle="Theo điểm các môn tôi dạy"
        actions={<SemesterChoice value={semester} onChange={setSemester} />}
      />
      <p className="flex items-start gap-3 rounded-2xl bg-tint p-4 text-sm text-tint-text ring-1 ring-brand-200/70">
        <Icon name="info" className="mt-0.5 h-5 w-5 shrink-0" />
        <span>
          Danh sách chỉ dựa trên điểm của môn thầy/cô dạy: ĐTB thấp, tụt khoảng điểm so với học kỳ
          I, bài giữa kỳ hoặc cuối kỳ thấp, còn thiếu đầu điểm. Chuyên cần và rèn luyện do giáo viên
          chủ nhiệm theo dõi.
        </span>
      </p>
      <QueryState query={assignments}>
        {() =>
          teaches ? (
            <QueryState query={support}>{(data) => <Workspace data={data} />}</QueryState>
          ) : (
            <p className="card p-6 text-slate-600">
              Trang này dành cho giáo viên bộ môn có phân công giảng dạy.
            </p>
          )
        }
      </QueryState>
    </>
  )
}
