import type { CSSProperties } from 'react'
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
import type { ClassOverview, GradeOverview } from '../../api/analytics'
import { formatInt, formatPercent } from '../../lib/format'
import { ATTENTION_LABELS, LEVEL_LABELS } from '../../lib/labels'
import { axisTick, gridProps, legendProps, tooltipProps } from '../charts/theme'
import type { StackMode } from '../charts/ClassLevelsChart'
import { StatCard, StatGrid } from '../StatCard'

// Phần nhìn nhanh cho BGH ở trang Khối. Mọi số đếm do Analytics (back-end) tính; ở đây chỉ cộng các
// lớp thành toàn khối và chia cho sĩ số để hiển thị tỉ lệ (không phải số của Thông tư, D-117).

// Một chỉ số "cần quan tâm" của một lớp: số học sinh.
interface Indicator {
  key: string
  label: string
  color: string
  count: (item: ClassOverview) => number
}

const INDICATORS: Indicator[] = [
  {
    key: 'learning_fail',
    label: `Học tập ${LEVEL_LABELS.fail}`,
    color: 'var(--chart-fail)',
    count: (item) => item.learning_levels.fail ?? 0,
  },
  {
    key: 'below_fail',
    label: ATTENTION_LABELS.subject_below_fail,
    color: 'var(--chart-orange)',
    count: (item) => item.below_fail_students,
  },
  {
    key: 'absent_over',
    label: ATTENTION_LABELS.absent_over_limit,
    color: 'var(--chart-accent-2)',
    count: (item) => item.absent_over_limit_students,
  },
  {
    key: 'absent_notice',
    label: 'Nghỉ nhiều (từ mức nhắc)',
    color: 'var(--chart-neutral)',
    count: (item) => item.absent_notice_students,
  },
  {
    key: 'conduct_fail',
    label: `Rèn luyện ${LEVEL_LABELS.fail}`,
    color: 'var(--chart-pass)',
    count: (item) => item.conduct_levels.fail ?? 0,
  },
]

// Ba chỉ số chính vẽ trên biểu đồ; bảng có đủ năm.
const CHART_INDICATORS = INDICATORS.slice(0, 3)

// Tỉ lệ phần trăm (0 đến 100) chỉ để vẽ; lớp không có học sinh thì 0.
function percent(count: number, total: number): number {
  return total > 0 ? Math.round((count / total) * 1000) / 10 : 0
}

function sum(classes: ClassOverview[], pick: (item: ClassOverview) => number): number {
  return classes.reduce((acc, item) => acc + pick(item), 0)
}

// Lớp có tỉ lệ cao nhất của một chỉ số (bỏ qua khi mọi lớp đều 0).
function highest(classes: ClassOverview[], pick: (item: ClassOverview) => number) {
  let best: ClassOverview | undefined
  for (const item of classes) {
    if (item.student_count === 0 || pick(item) === 0) continue
    if (
      best === undefined ||
      pick(item) / item.student_count > pick(best) / best.student_count
    ) {
      best = item
    }
  }
  return best
}

function highestHint(classes: ClassOverview[], pick: (item: ClassOverview) => number): string {
  const best = highest(classes, pick)
  return best === undefined
    ? 'Không lớp nào có'
    : `Cao nhất: ${best.name} (${formatPercent(pick(best), best.student_count)})`
}

// --- Thẻ tỉ lệ toàn khối --------------------------------------------------------------------------

export function GradeKpis({ overview }: { overview: GradeOverview }) {
  const { classes } = overview
  const total = sum(classes, (item) => item.student_count)
  const level = (field: 'learning_levels' | 'conduct_levels', key: string) =>
    sum(classes, (item) => item[field][key] ?? 0)
  const good = level('learning_levels', 'good')
  const fair = level('learning_levels', 'fair')
  const fail = level('learning_levels', 'fail')
  const incomplete = level('learning_levels', 'incomplete')
  const conductGoodFair = level('conduct_levels', 'good') + level('conduct_levels', 'fair')
  const conductFail = level('conduct_levels', 'fail')
  const belowFail = sum(classes, (item) => item.below_fail_students)
  const over = sum(classes, (item) => item.absent_over_limit_students)
  const notice = sum(classes, (item) => item.absent_notice_students)
  const hasPromotion = classes.some((item) => item.promotion !== null)
  const eligible = sum(classes, (item) => item.promotion?.eligible ?? 0)
  const notEligible = sum(classes, (item) => item.promotion?.not_eligible ?? 0)
  const unknown = sum(classes, (item) => item.promotion?.unknown ?? 0)
  const danger = (count: number) => (count > 0 ? 'text-red-700' : 'text-slate-900')

  return (
    <StatGrid>
      <StatCard
        label="Học sinh toàn khối"
        value={formatInt(total)}
        hint={`${classes.length} lớp`}
        icon="users"
      />
      <StatCard
        label={`Học tập ${LEVEL_LABELS.good} + ${LEVEL_LABELS.fair}`}
        value={formatPercent(good + fair, total)}
        valueClassName="text-green-700"
        hint={`${LEVEL_LABELS.good} ${formatPercent(good, total)} · ${LEVEL_LABELS.fair} ${formatPercent(fair, total)}`}
        icon="chart"
        tone="good"
      />
      <StatCard
        label={`Học tập ${LEVEL_LABELS.fail}`}
        value={formatPercent(fail, total)}
        valueClassName={danger(fail)}
        hint={`${formatInt(fail)} học sinh · ${highestHint(classes, INDICATORS[0].count)}`}
        icon="alert"
        tone={fail > 0 ? 'danger' : 'neutral'}
      />
      <StatCard
        label={ATTENTION_LABELS.subject_below_fail}
        value={formatPercent(belowFail, total)}
        valueClassName={belowFail > 0 ? 'text-amber-700' : 'text-slate-900'}
        hint={`${formatInt(belowFail)} học sinh · ${highestHint(classes, INDICATORS[1].count)}`}
        icon="book"
        tone={belowFail > 0 ? 'warn' : 'neutral'}
      />
      <StatCard
        label={ATTENTION_LABELS.absent_over_limit}
        value={formatPercent(over, total)}
        valueClassName={danger(over)}
        hint={`${formatInt(over)} học sinh · nghỉ nhiều, cần nhắc: ${formatInt(notice)} (${formatPercent(notice, total)})`}
        icon="calendar"
        tone={over > 0 ? 'danger' : 'neutral'}
      />
      <StatCard
        label={`Rèn luyện ${LEVEL_LABELS.good} + ${LEVEL_LABELS.fair}`}
        value={formatPercent(conductGoodFair, total)}
        valueClassName="text-green-700"
        hint={`${LEVEL_LABELS.fail}: ${formatInt(conductFail)} học sinh (${formatPercent(conductFail, total)})`}
        icon="shield"
        tone="good"
      />
      <StatCard
        label={`Học tập ${LEVEL_LABELS.incomplete.toLowerCase()}`}
        value={formatPercent(incomplete, total)}
        hint={`${formatInt(incomplete)} học sinh còn thiếu điểm để xếp mức`}
        icon="clock"
        tone="neutral"
      />
      {hasPromotion ? (
        <StatCard
          label="Đủ điều kiện lên lớp"
          value={formatPercent(eligible, total)}
          valueClassName="text-green-700"
          hint={`Không đủ: ${formatInt(notEligible)} (${formatPercent(notEligible, total)}) · chưa đủ dữ liệu: ${formatInt(unknown)}`}
          icon="check"
          tone="good"
        />
      ) : (
        <StatCard
          label="Đủ điều kiện lên lớp"
          value="—"
          hint="Chọn “Cả năm” để xem"
          icon="check"
          tone="neutral"
        />
      )}
    </StatGrid>
  )
}

// --- Nút chọn Số học sinh / Tỉ lệ ---------------------------------------------------------------

export function ModeToggle({
  value,
  onChange,
  label,
}: {
  value: StackMode
  onChange: (mode: StackMode) => void
  label: string
}) {
  const choices: { value: StackMode; label: string }[] = [
    { value: 'percent', label: 'Tỉ lệ %' },
    { value: 'count', label: 'Số học sinh' },
  ]
  return (
    <div role="group" aria-label={label} className="flex gap-1">
      {choices.map((choice) => (
        <button
          key={choice.value}
          type="button"
          aria-pressed={value === choice.value}
          onClick={() => onChange(choice.value)}
          className={`rounded-lg border px-2.5 py-1 text-xs font-medium transition-colors ${
            value === choice.value
              ? 'border-brand-700 bg-brand-700 text-white'
              : 'border-slate-300 hover:bg-slate-100'
          }`}
        >
          {choice.label}
        </button>
      ))}
    </div>
  )
}

// --- Tỉ lệ học sinh cần quan tâm theo lớp ------------------------------------------------------

export function AttentionRateChart({ overview }: { overview: GradeOverview }) {
  const data = overview.classes.map((item) => ({
    name: item.name,
    total: item.student_count,
    ...Object.fromEntries(
      CHART_INDICATORS.flatMap((indicator) => [
        [indicator.key, percent(indicator.count(item), item.student_count)],
        [`${indicator.key}_count`, indicator.count(item)],
      ]),
    ),
  }))
  return (
    <figure
      aria-label="Tỉ lệ học sinh cần quan tâm của từng lớp"
      className="h-72 w-full min-w-0 overflow-hidden"
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, left: -8, bottom: 0 }} barGap={2}>
          <CartesianGrid {...gridProps} />
          <XAxis dataKey="name" tick={axisTick()} />
          <YAxis tickFormatter={(value: number) => `${value}%`} tick={axisTick()} />
          <Tooltip
            {...tooltipProps}
            formatter={(_value, _name, item) => {
              const row = item.payload as Record<string, number>
              const key = String(item.dataKey)
              return `${formatPercent(row[`${key}_count`], row.total)} (${row[`${key}_count`]} học sinh)`
            }}
          />
          <Legend itemSorter={null} {...legendProps} />
          {CHART_INDICATORS.map((indicator) => (
            <Bar
              key={indicator.key}
              dataKey={indicator.key}
              name={indicator.label}
              fill={indicator.color}
              radius={[4, 4, 0, 0]}
              isAnimationActive={false}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </figure>
  )
}

// Ô tô đậm theo tỉ lệ so với lớp cao nhất của cột; số luôn hiện nên không chỉ dựa vào màu.
function heat(rate: number, max: number): CSSProperties | undefined {
  if (rate <= 0 || max <= 0) return undefined
  const strength = Math.round(8 + (rate / max) * 30)
  return { backgroundColor: `color-mix(in srgb, var(--chart-fail) ${strength}%, transparent)` }
}

export function AttentionTable({ overview }: { overview: GradeOverview }) {
  const { classes } = overview
  const total = sum(classes, (item) => item.student_count)
  const maxRate = Object.fromEntries(
    INDICATORS.map((indicator) => [
      indicator.key,
      Math.max(0, ...classes.map((item) => percent(indicator.count(item), item.student_count))),
    ]),
  )
  return (
    <div className="overflow-x-auto">
      <table className="data-table min-w-max">
        <caption className="pb-2 text-left text-sm text-slate-500">
          Tỉ lệ trên sĩ số của lớp, kèm số học sinh. Ô càng đậm: tỉ lệ càng cao so với các lớp khác
          trong cùng cột. Một học sinh có thể thuộc nhiều cột.
        </caption>
        <thead>
          <tr>
            <th scope="col" className="px-3 py-2 font-medium">
              Lớp
            </th>
            <th scope="col" className="px-3 py-2 text-right font-medium">
              Sĩ số
            </th>
            {INDICATORS.map((indicator) => (
              <th key={indicator.key} scope="col" className="px-3 py-2 text-right font-medium">
                {indicator.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {classes.map((item) => (
            <tr key={item.class_id}>
              <th scope="row" className="px-3 py-2 font-normal">
                {item.name}
              </th>
              <td className="px-3 py-2 text-right tabular-nums">{item.student_count}</td>
              {INDICATORS.map((indicator) => {
                const count = indicator.count(item)
                return (
                  <td
                    key={indicator.key}
                    className="px-3 py-2 text-right tabular-nums"
                    style={heat(percent(count, item.student_count), maxRate[indicator.key])}
                  >
                    {formatPercent(count, item.student_count)}
                    <span className="ml-1 text-xs text-slate-500">({count})</span>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="font-semibold">
            <th scope="row" className="px-3 py-2 text-left">
              Toàn khối
            </th>
            <td className="px-3 py-2 text-right tabular-nums">{total}</td>
            {INDICATORS.map((indicator) => {
              const count = sum(classes, indicator.count)
              return (
                <td key={indicator.key} className="px-3 py-2 text-right tabular-nums">
                  {formatPercent(count, total)}
                  <span className="ml-1 text-xs font-normal text-slate-500">({count})</span>
                </td>
              )
            })}
          </tr>
        </tfoot>
      </table>
    </div>
  )
}
