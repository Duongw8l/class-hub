import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { SubjectSupport, SupportLevel } from '../../api/analytics'
import type { ReportTarget } from '../../api/reports'
import { useReportList } from '../../hooks/useReports'
import { formatPercent, formatScore } from '../../lib/format'
import { COMMENT_LABELS, RISK_LABELS } from '../../lib/labels'
import { RiskBadge } from '../alerts/AlertParts'
import { axisTick, gridProps, labelFill, tooltipProps } from '../charts/theme'
import { QueryState } from '../QueryState'
import { AggregateReport } from '../reports/AggregateReport'
import { SEMESTER_LABELS, SUPPORT_LEVELS } from './levels'

// Học sinh cần hỗ trợ trong một môn của GVBM (D-118). Mọi lý do, mức, trung bình do back-end tính
// từ điểm của chính môn đó; giao diện chỉ hiển thị (phần trăm chỉ là số đếm / sĩ số).

function LevelFilter({
  value,
  onChange,
  counts,
}: {
  value: SupportLevel | 'all'
  onChange: (value: SupportLevel | 'all') => void
  counts: Record<SupportLevel, number>
}) {
  const total = counts.high + counts.medium + counts.low
  const choices: { value: SupportLevel | 'all'; label: string }[] = [
    { value: 'all', label: `Tất cả (${total})` },
    ...SUPPORT_LEVELS.map((level) => ({
      value: level,
      label: `${RISK_LABELS[level]} (${counts[level]})`,
    })),
  ]
  return (
    <div role="group" aria-label="Lọc theo mức" className="flex flex-wrap gap-2">
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

// Bảng học sinh cần hỗ trợ của một lớp–môn, lọc theo mức.
export function SupportStudents({ item }: { item: SubjectSupport }) {
  const [level, setLevel] = useState<SupportLevel | 'all'>('all')
  const isScore = item.subject.assessment_type === 'score'
  const rows =
    level === 'all' ? item.students : item.students.filter((student) => student.level === level)

  if (item.students.length === 0) {
    return (
      <p className="text-sm text-slate-600">
        Chưa có học sinh nào cần hỗ trợ thêm trong môn này ở {SEMESTER_LABELS[item.semester]}.
      </p>
    )
  }
  return (
    <div className="space-y-3">
      <LevelFilter value={level} onChange={setLevel} counts={item.counts} />
      <div className="overflow-x-auto">
        <table className="data-table min-w-max">
          <thead>
            <tr>
              <th scope="col" className="py-2 pr-4 font-medium">
                Học sinh
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                Mức
              </th>
              <th scope="col" className="px-3 py-2 text-right font-medium">
                {isScore ? (item.semester === 2 ? 'ĐTB HK I → HK II' : 'ĐTB') : 'Kết quả'}
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                Lý do
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 align-top">
            {rows.map((student) => (
              <tr key={student.student_id}>
                <th scope="row" className="py-2 pr-4 text-left font-normal">
                  <Link
                    to={`/classes/${item.class_info.id}/students/${student.student_id}`}
                    className="link"
                  >
                    {student.full_name}
                  </Link>
                  <span className="block font-mono text-xs text-slate-500">
                    {student.student_code}
                  </span>
                </th>
                <td className="px-3 py-2">
                  <RiskBadge level={student.level} />
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {isScore ? (
                    item.semester === 2 ? (
                      <>
                        {formatScore(student.average_semester1)}
                        <span aria-hidden="true"> → </span>
                        <span className="sr-only"> sang </span>
                        {formatScore(student.average)}
                      </>
                    ) : (
                      formatScore(student.average)
                    )
                  ) : student.comment_result ? (
                    COMMENT_LABELS[student.comment_result]
                  ) : (
                    '—'
                  )}
                </td>
                <td className="max-w-xl px-3 py-2">
                  <ul className="list-inside list-disc space-y-0.5 text-sm text-slate-800">
                    {student.reasons.map((reason) => (
                      <li key={reason.code}>{reason.message}</li>
                    ))}
                  </ul>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// --- Thống kê để điều chỉnh kế hoạch dạy học ------------------------------------------------

function Fact({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-xl bg-slate-50 p-3 ring-1 ring-slate-200">
      <dt className="text-xs font-medium text-slate-500">{label}</dt>
      <dd className="mt-1 text-xl font-semibold tabular-nums text-slate-900">{value}</dd>
      {hint && <dd className="text-xs text-slate-500">{hint}</dd>}
    </div>
  )
}

function ComponentChart({ item }: { item: SubjectSupport }) {
  const { stats, thresholds } = item
  const data = [
    { name: 'Thường xuyên', ...stats.regular },
    { name: 'Giữa kỳ', ...stats.midterm },
    { name: 'Cuối kỳ', ...stats.final },
  ].filter((row) => row.count > 0)
  if (data.length === 0) {
    return <p className="text-sm text-slate-500">Chưa có đầu điểm nào trong học kỳ này.</p>
  }
  return (
    <figure
      aria-label="Điểm trung bình của lớp theo loại đầu điểm"
      className="h-56 w-full min-w-0 overflow-hidden"
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 20, right: 8, left: -16, bottom: 0 }}>
          <CartesianGrid {...gridProps} />
          <XAxis dataKey="name" tick={axisTick()} interval={0} />
          <YAxis domain={[0, 10]} ticks={[0, 2, 4, 6, 8, 10]} tick={axisTick()} />
          <Tooltip
            {...tooltipProps}
            formatter={(_value, _name, entry) => {
              const row = entry.payload as (typeof data)[number]
              return [
                `TB ${formatScore(row.mean)} · ${row.below_pass}/${row.count} điểm dưới ${formatScore(thresholds.passing)}`,
                '',
              ]
            }}
            separator=""
          />
          <ReferenceLine
            y={thresholds.passing}
            stroke="var(--chart-fail)"
            strokeDasharray="4 4"
            label={{
              value: `Mức đạt ${formatScore(thresholds.passing)}`,
              position: 'insideTopRight',
              fill: labelFill,
              fontSize: 11,
            }}
          />
          <Bar dataKey="mean" isAnimationActive={false} radius={[4, 4, 0, 0]} maxBarSize={56}>
            {data.map((row) => (
              <Cell
                key={row.name}
                fill={
                  row.mean !== null && row.mean < thresholds.passing
                    ? 'var(--chart-fail)'
                    : 'var(--chart-accent)'
                }
              />
            ))}
            <LabelList
              dataKey="mean"
              position="top"
              fill={labelFill}
              fontSize={12}
              formatter={(value) => (typeof value === 'number' ? formatScore(value) : '')}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </figure>
  )
}

export function PlanStats({ item }: { item: SubjectSupport }) {
  const { stats, thresholds } = item
  const total = item.student_count
  if (item.subject.assessment_type === 'comment') {
    return (
      <dl className="grid gap-3 sm:grid-cols-3">
        <Fact label="Đạt" value={formatPercent(stats.comment_pass, total)} hint={`${stats.comment_pass} học sinh`} />
        <Fact label="Chưa đạt" value={formatPercent(stats.comment_fail, total)} hint={`${stats.comment_fail} học sinh`} />
        <Fact label="Chưa đánh giá" value={formatPercent(stats.comment_missing, total)} hint={`${stats.comment_missing} học sinh`} />
      </dl>
    )
  }
  return (
    <div className="space-y-4">
      <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Fact
          label="ĐTB lớp"
          value={formatScore(item.mean)}
          hint={
            stats.previous_mean !== null ? `Học kỳ I: ${formatScore(stats.previous_mean)}` : undefined
          }
        />
        <Fact
          label={`Cần phụ đạo (dưới ${formatScore(thresholds.passing)})`}
          value={formatPercent(stats.support_group, total)}
          hint={`${stats.support_group} học sinh`}
        />
        <Fact
          label={`Có thể bồi dưỡng (từ ${formatScore(thresholds.good)})`}
          value={formatPercent(stats.advanced_group, total)}
          hint={`${stats.advanced_group} học sinh`}
        />
        <Fact
          label="Bài thường xuyên dưới mức đạt"
          value={formatPercent(stats.regular.below_pass, stats.regular.count)}
          hint={`${stats.regular.below_pass}/${stats.regular.count} bài`}
        />
      </dl>
      <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <p className="mb-1 text-sm font-medium text-slate-700">Trung bình theo loại đầu điểm</p>
          <ComponentChart item={item} />
          <p className="text-xs text-slate-500">
            Cột đỏ: trung bình dưới mức đạt. So các loại đầu điểm để biết khâu nào (bài thường
            xuyên, giữa kỳ, cuối kỳ) cần ôn tập thêm.
          </p>
        </div>
        <div>
          <p className="mb-1 text-sm font-medium text-slate-700">
            Nhóm có thể bồi dưỡng ({item.advanced_students.length})
          </p>
          {item.advanced_students.length === 0 ? (
            <p className="text-sm text-slate-500">Chưa có học sinh nào ở mức này.</p>
          ) : (
            <ul className="max-h-56 space-y-1 overflow-y-auto text-sm">
              {item.advanced_students.map((student) => (
                <li key={student.student_id} className="flex justify-between gap-3">
                  <Link
                    to={`/classes/${item.class_info.id}/students/${student.student_id}`}
                    className="link"
                  >
                    {student.full_name}
                  </Link>
                  <span className="tabular-nums text-slate-600">
                    {formatScore(student.average)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}

// Bản nháp AI gợi ý điều chỉnh kế hoạch dạy học (luồng báo cáo sẵn có: nháp → sửa → duyệt → PDF).
export function TeachingPlanDraft({ item }: { item: SubjectSupport }) {
  const target: ReportTarget = {
    type: 'teaching_plan',
    semester: item.semester === 2 ? '2' : '1',
    classId: item.class_info.id,
    subjectId: item.subject.id,
  }
  const list = useReportList(target)
  return (
    <QueryState query={list}>
      {(result) => (
        <AggregateReport
          target={target}
          report={result.items[0]?.report ?? null}
          scopeLabel={`lớp ${item.class_info.name}, môn ${item.subject.name}, ${SEMESTER_LABELS[item.semester].toLowerCase()}`}
        />
      )}
    </QueryState>
  )
}
