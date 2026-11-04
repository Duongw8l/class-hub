import type { UseQueryResult } from '@tanstack/react-query'
import { useState } from 'react'
import type { ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import type { ClassSubjectResult, GradeOverview, GradeSubject } from '../api/analytics'
import { ClassLevelsChart } from '../components/charts/ClassLevelsChart'
import { CompareChart } from '../components/charts/CompareChart'
import type { CompareDatum } from '../components/charts/CompareChart'
import { PageTitle, Panel } from '../components/Panel'
import { PeriodSelect } from '../components/PeriodSelect'
import { QueryState } from '../components/QueryState'
import { useGradeOverview, usePeriod } from '../hooks/useAnalytics'
import { formatScore } from '../lib/format'
import { LEVEL_LABELS, PERIOD_LABELS } from '../lib/labels'

const PERIODS = ['1', '2', 'year'] as const

function Th({ children, right = true }: { children: ReactNode; right?: boolean }) {
  return (
    <th scope="col" className={`px-3 py-2 font-medium ${right ? 'text-right' : ''}`}>
      {children}
    </th>
  )
}

function ClassesTable({ overview }: { overview: GradeOverview }) {
  return (
    <div className="overflow-x-auto">
      <table className="data-table min-w-max">
        <thead>
          <tr>
            <Th right={false}>Lớp</Th>
            <Th>Sĩ số</Th>
            <Th>{LEVEL_LABELS.good}</Th>
            <Th>{LEVEL_LABELS.fair}</Th>
            <Th>{LEVEL_LABELS.pass}</Th>
            <Th>{LEVEL_LABELS.fail}</Th>
            <Th>{LEVEL_LABELS.incomplete}</Th>
            <Th>Nghỉ nhiều</Th>
            <Th>Nghỉ quá số buổi</Th>
            <Th>Có môn điểm quá thấp</Th>
          </tr>
        </thead>
        <tbody>
          {overview.classes.map((item) => (
            <tr key={item.class_id}>
              <th scope="row" className="px-3 py-2 font-normal">
                <Link to={`/classes/${item.class_id}`} className="link">
                  {item.name}
                </Link>
              </th>
              <td className="px-3 py-2 text-right tabular-nums">{item.student_count}</td>
              <td className="px-3 py-2 text-right tabular-nums">{item.learning_levels.good}</td>
              <td className="px-3 py-2 text-right tabular-nums">{item.learning_levels.fair}</td>
              <td className="px-3 py-2 text-right tabular-nums">{item.learning_levels.pass}</td>
              <td className="px-3 py-2 text-right tabular-nums">{item.learning_levels.fail}</td>
              <td className="px-3 py-2 text-right tabular-nums">
                {item.learning_levels.incomplete}
              </td>
              <td className="px-3 py-2 text-right tabular-nums">{item.absent_notice_students}</td>
              <td className="px-3 py-2 text-right tabular-nums">
                {item.absent_over_limit_students}
              </td>
              <td className="px-3 py-2 text-right tabular-nums">{item.below_fail_students}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function resultOf(
  overview: GradeOverview,
  subjectId: number,
  classId: number,
): ClassSubjectResult | undefined {
  return overview.subjects
    .find((subject) => subject.subject_id === subjectId)
    ?.class_means.find((item) => item.class_id === classId)
}

// Một ô của bảng: ĐTB lớp (môn điểm số) hoặc số Chưa đạt (môn nhận xét), học kỳ I → học kỳ II.
function CompareCell({
  subject,
  classId,
  first,
  second,
}: {
  subject: GradeSubject
  classId: number
  first: GradeOverview
  second: GradeOverview
}) {
  const a = resultOf(first, subject.subject_id, classId)
  const b = resultOf(second, subject.subject_id, classId)
  if (a === undefined && b === undefined) {
    return (
      <td className="px-3 py-2 text-right text-slate-400" title="Lớp không học môn này">
        <span aria-hidden="true">·</span>
        <span className="sr-only">Không học</span>
      </td>
    )
  }
  const isScore = subject.assessment_type === 'score'
  const show = (item: ClassSubjectResult | undefined) =>
    item === undefined ? '—' : isScore ? formatScore(item.mean) : String(item.comment_fail)
  return (
    <td className="px-3 py-2 text-right tabular-nums">
      {show(a)}
      <span aria-hidden="true"> → </span>
      <span className="sr-only"> sang </span>
      {show(b)}
    </td>
  )
}

function SubjectName({ subject, total }: { subject: GradeSubject; total: number }) {
  return (
    <th scope="row" className="px-3 py-2 font-normal">
      {subject.name}
      {subject.class_count < total && (
        <span className="ml-1.5 text-xs text-slate-500">
          ({subject.class_count}/{total} lớp)
        </span>
      )}
    </th>
  )
}

function SubjectRows({
  subjects,
  total,
  first,
  second,
}: {
  subjects: GradeSubject[]
  total: number
  first: GradeOverview
  second: GradeOverview
}) {
  return subjects.map((item) => (
    <tr key={item.subject_id}>
      <SubjectName subject={item} total={total} />
      {first.classes.map((klass) => (
        <CompareCell
          key={klass.class_id}
          subject={item}
          classId={klass.class_id}
          first={first}
          second={second}
        />
      ))}
    </tr>
  ))
}

function classCountNote(subject: GradeSubject, total: number): string {
  return subject.class_count < total ? ` (${subject.class_count}/${total} lớp)` : ''
}

function Comparison({ first, second }: { first: GradeOverview; second: GradeOverview }) {
  const [chosen, setChosen] = useState<number | null>(null)
  const subjects = first.subjects
  const scoreSubjects = subjects.filter((subject) => subject.assessment_type === 'score')
  const commentSubjects = subjects.filter((subject) => subject.assessment_type === 'comment')
  const subject =
    subjects.find((item) => item.subject_id === chosen) ?? scoreSubjects[0] ?? subjects[0]
  const total = first.classes.length
  const isScore = subject?.assessment_type !== 'comment'

  // Biểu đồ chỉ có các lớp học môn đang chọn.
  const subjectData: CompareDatum[] =
    subject === undefined
      ? []
      : first.classes
          .filter((item) => subject.class_means.some((result) => result.class_id === item.class_id))
          .map((item) => {
            const a = resultOf(first, subject.subject_id, item.class_id)
            const b = resultOf(second, subject.subject_id, item.class_id)
            return isScore
              ? { name: item.name, first: a?.mean ?? null, second: b?.mean ?? null }
              : { name: item.name, first: a?.comment_fail ?? 0, second: b?.comment_fail ?? 0 }
          })
  const failData: CompareDatum[] = first.classes.map((item) => ({
    name: item.name,
    first: item.learning_levels.fail ?? 0,
    second: second.classes.find((other) => other.class_id === item.class_id)?.learning_levels.fail ?? 0,
  }))

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-2">
        <div>
          <label className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-700">
            Môn
            <select
              value={subject?.subject_id ?? ''}
              onChange={(event) => setChosen(Number(event.target.value))}
              className="input w-auto py-1.5"
            >
              <optgroup label="Môn tính điểm">
                {scoreSubjects.map((item) => (
                  <option key={item.subject_id} value={item.subject_id}>
                    {item.name}
                    {classCountNote(item, total)}
                  </option>
                ))}
              </optgroup>
              {commentSubjects.length > 0 && (
                <optgroup label="Môn đánh giá bằng nhận xét">
                  {commentSubjects.map((item) => (
                    <option key={item.subject_id} value={item.subject_id}>
                      {item.name}
                      {classCountNote(item, total)}
                    </option>
                  ))}
                </optgroup>
              )}
            </select>
          </label>
          <CompareChart
            data={subjectData}
            kind={isScore ? 'score' : 'count'}
            label={
              isScore
                ? 'ĐTB của lớp: học kỳ I so với học kỳ II'
                : 'Số học sinh Chưa đạt của môn: học kỳ I so với học kỳ II'
            }
          />
        </div>
        <div>
          <p className="mb-2 text-sm font-medium text-slate-700">
            Số học sinh xếp loại {LEVEL_LABELS.fail}
          </p>
          <CompareChart
            data={failData}
            kind="count"
            label="Số học sinh Chưa đạt: học kỳ I so với học kỳ II"
          />
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="data-table min-w-max">
          <caption className="pb-2 text-left text-sm text-slate-500">
            Học kỳ I → học kỳ II. Môn tính điểm: ĐTB của lớp. Môn nhận xét: số học sinh Chưa đạt.
            Dấu · là lớp không học môn đó.
          </caption>
          <thead>
            <tr>
              <Th right={false}>Môn</Th>
              {first.classes.map((item) => (
                <Th key={item.class_id}>{item.name}</Th>
              ))}
            </tr>
          </thead>
          <tbody>
            <SubjectRows subjects={scoreSubjects} total={total} first={first} second={second} />
            {commentSubjects.length > 0 && (
              <tr>
                <th
                  scope="rowgroup"
                  colSpan={total + 1}
                  className="bg-slate-50 px-3 py-2 text-left text-xs font-semibold text-slate-600"
                >
                  Môn đánh giá bằng nhận xét · số học sinh Chưa đạt
                </th>
              </tr>
            )}
            <SubjectRows subjects={commentSubjects} total={total} first={first} second={second} />
          </tbody>
        </table>
      </div>
    </div>
  )
}

function CompareSection({
  first,
  second,
}: {
  first: UseQueryResult<GradeOverview>
  second: UseQueryResult<GradeOverview>
}) {
  // Cần cả hai học kỳ: hiện lỗi của bên nào hỏng trước, còn lại thì chờ.
  if (first.isError) return <QueryState query={first}>{() => null}</QueryState>
  if (second.isError) return <QueryState query={second}>{() => null}</QueryState>
  if (first.isPending || second.isPending) {
    return (
      <p aria-live="polite" className="text-slate-600">
        Đang tải…
      </p>
    )
  }
  return <Comparison first={first.data} second={second.data} />
}

// Dashboard khối (BGH): so sánh các lớp trong khối, học kỳ I cạnh học kỳ II. Chỉ số liệu gộp theo
// lớp, không có tên học sinh.
export default function GradeOverviewPage() {
  const level = Number(useParams().level)
  const [period, setPeriod] = usePeriod(PERIODS, '1')
  const selected = useGradeOverview(level, period)
  const first = useGradeOverview(level, '1')
  const second = useGradeOverview(level, '2')

  return (
    <>
      <PageTitle
        title={`Khối ${level}`}
        subtitle="So sánh các lớp trong khối"
        actions={<PeriodSelect value={period} options={PERIODS} onChange={setPeriod} />}
      />
      <QueryState query={selected}>
        {(overview) => (
          <>
            <Panel id="cac-lop" title={`Các lớp · ${PERIOD_LABELS[period]}`}>
              <ClassesTable overview={overview} />
            </Panel>
            <Panel
              id="muc-hoc-tap"
              title="Kết quả học tập theo lớp"
              description="Số học sinh ở từng mức; cột cao hơn nghĩa là lớp đông hơn."
            >
              <ClassLevelsChart
                classes={overview.classes}
                label="Số học sinh theo kết quả học tập của từng lớp"
              />
            </Panel>
          </>
        )}
      </QueryState>
      <Panel
        id="hk1-hk2"
        title="Học kỳ I so với học kỳ II"
        description="Mọi môn của khối, kể cả môn lựa chọn (chỉ các lớp học môn đó) và môn đánh giá bằng nhận xét. ĐTB của lớp là số mô tả để so sánh, không phải số của Thông tư."
      >
        <CompareSection first={first} second={second} />
      </Panel>
    </>
  )
}
