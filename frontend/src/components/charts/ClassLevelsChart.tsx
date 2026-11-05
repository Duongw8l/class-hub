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
import type { ClassOverview } from '../../api/analytics'
import { formatPercent } from '../../lib/format'
import { LEVEL_COLORS, LEVEL_LABELS } from '../../lib/labels'
import { axisTick, gridProps, legendProps, tooltipProps } from './theme'

// 'count': số học sinh (cột cao hơn là lớp đông hơn). 'percent': mỗi cột là 100% sĩ số của lớp,
// để so các lớp khác sĩ số.
export type StackMode = 'count' | 'percent'

export interface StackSeries {
  key: string
  label: string
  color: string
}

export interface StackRow {
  name: string
  total: number
  counts: Record<string, number>
}

const PERCENT_TICKS = [0, 0.25, 0.5, 0.75, 1]

// Cột chồng theo lớp. Số đếm do API trả; tỉ lệ chỉ là cách hiển thị (Recharts chia cho tổng cột).
export function ClassStackChart({
  rows,
  series,
  mode,
  label,
}: {
  rows: StackRow[]
  series: StackSeries[]
  mode: StackMode
  label: string
}) {
  const data = rows.map((row) => ({ name: row.name, total: row.total, ...row.counts }))
  return (
    <figure aria-label={label} className="h-72 w-full min-w-0 overflow-hidden">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={data}
          stackOffset={mode === 'percent' ? 'expand' : 'none'}
          margin={{ top: 8, right: 8, left: mode === 'percent' ? -8 : -16, bottom: 0 }}
        >
          <CartesianGrid {...gridProps} />
          <XAxis dataKey="name" tick={axisTick()} />
          {mode === 'percent' ? (
            <YAxis
              domain={[0, 1]}
              ticks={PERCENT_TICKS}
              tickFormatter={(value: number) => `${value * 100}%`}
              tick={axisTick()}
            />
          ) : (
            <YAxis allowDecimals={false} tick={axisTick()} />
          )}
          <Tooltip
            {...tooltipProps}
            formatter={(value, _name, item) => {
              const total = (item.payload as { total: number }).total
              return typeof value === 'number'
                ? `${value} học sinh (${formatPercent(value, total)})`
                : value
            }}
          />
          <Legend itemSorter={null} {...legendProps} />
          {series.map((item) => (
            <Bar
              key={item.key}
              dataKey={item.key}
              name={item.label}
              stackId="levels"
              fill={item.color}
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

const LEARNING = ['good', 'fair', 'pass', 'fail', 'incomplete'] as const
const CONDUCT = ['good', 'fair', 'pass', 'fail', 'missing'] as const

function levelSeries(keys: readonly string[]): StackSeries[] {
  return keys.map((key) => ({ key, label: LEVEL_LABELS[key], color: LEVEL_COLORS[key] }))
}

// Số học sinh (hoặc tỉ lệ) ở từng mức học tập hay rèn luyện của mỗi lớp trong khối.
export function ClassLevelsChart({
  classes,
  label,
  field = 'learning_levels',
  mode = 'count',
}: {
  classes: ClassOverview[]
  label: string
  field?: 'learning_levels' | 'conduct_levels'
  mode?: StackMode
}) {
  return (
    <ClassStackChart
      rows={classes.map((item) => ({
        name: item.name,
        total: item.student_count,
        counts: item[field],
      }))}
      series={levelSeries(field === 'learning_levels' ? LEARNING : CONDUCT)}
      mode={mode}
      label={label}
    />
  )
}
