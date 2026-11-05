import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import {
  deleteLesson,
  fetchLesson,
  fetchSubjectLessons,
  saveLesson,
  shortDate,
  todayIso,
  weekday,
} from '../api/attendance'
import type { AttendanceStatus, LessonDetail, SubjectLessons } from '../api/attendance'
import { useAuth } from '../auth/context'
import { ErrorAlert, SuccessNote } from '../components/admin/shared'
import { EntryEditor } from '../components/attendance/EntryEditor'
import type { Draft } from '../components/attendance/draft'
import { draftProblems } from '../components/attendance/draft'
import { PageTitle, Panel } from '../components/Panel'
import { QueryState } from '../components/QueryState'
import { formatMonth } from '../lib/format'

// Giáo viên bộ môn chỉ ghi vắng có phép / không phép / muộn; "cử đi" do GVCN xác nhận (D-120).
const LESSON_STATUSES: AttendanceStatus[] = ['present', 'late', 'absent_excused', 'absent_unexcused']
const LESSON_NUMBERS = Array.from({ length: 10 }, (_, index) => index + 1)

function LessonForm({ detail, classId }: { detail: LessonDetail; classId: number }) {
  const [draft, setDraft] = useState<Draft>(() =>
    Object.fromEntries(
      detail.entries.map((e) => [
        e.student_id,
        { student_id: e.student_id, status: e.status, reason: e.reason, note: e.note },
      ]),
    ),
  )
  const [message, setMessage] = useState<string | null>(null)
  const queryClient = useQueryClient()
  const marked = Object.values(draft).filter((d) => d.status !== 'present')
  const problems = draftProblems(draft)

  const refresh = () =>
    void queryClient.invalidateQueries({
      predicate: (query) => ['subject-lessons', 'lesson'].includes(String(query.queryKey[0])),
    })
  const save = useMutation({
    mutationFn: () =>
      saveLesson(
        classId,
        detail.subject_id,
        detail.date,
        detail.lesson_no,
        marked.map((d) => ({ ...d, note: d.note?.trim() || null })),
      ),
    onSuccess: () => {
      setMessage(
        marked.length === 0
          ? 'Đã lưu: cả lớp có mặt.'
          : `Đã lưu: ${marked.length} em vắng hoặc muộn.`,
      )
      refresh()
    },
  })
  const remove = useMutation({
    mutationFn: () => deleteLesson(classId, detail.subject_id, detail.date, detail.lesson_no),
    onSuccess: () => {
      setMessage('Đã xoá tiết này khỏi sổ.')
      refresh()
    },
  })
  const busy = save.isPending || remove.isPending

  if (detail.taken_by) {
    return (
      <p role="alert" className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900 ring-1 ring-amber-200">
        Tiết {detail.lesson_no} ngày {shortDate(detail.date)} của lớp đã được điểm danh cho môn{' '}
        <strong>{detail.taken_by}</strong>. Hãy kiểm tra lại ngày và tiết thứ mấy.
      </p>
    )
  }
  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-600">
        {detail.exists
          ? 'Tiết này đã điểm danh; có thể sửa rồi lưu lại.'
          : 'Tiết này chưa điểm danh: cả lớp đang để "Có mặt". Chỉ cần chọn các em vắng hoặc đi muộn.'}
      </p>
      <EntryEditor
        rows={detail.entries}
        draft={draft}
        statuses={LESSON_STATUSES}
        readOnly={!detail.can_edit || busy}
        onChange={(next) => {
          setDraft(next)
          setMessage(null)
        }}
      />
      {detail.can_edit && (
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            disabled={busy || problems.length > 0}
            onClick={() => save.mutate()}
            className="btn-primary"
          >
            {save.isPending ? 'Đang lưu…' : 'Lưu điểm danh tiết'}
          </button>
          <span className="text-sm text-slate-600">
            {marked.length} em vắng hoặc muộn.
            {problems.length > 0 && (
              <span className="ml-2 text-red-700">Lý do "Khác" cần ghi chú.</span>
            )}
          </span>
          {detail.exists && (
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                if (window.confirm('Xoá tiết này khỏi sổ điểm danh (ví dụ do chọn nhầm ngày, tiết)?'))
                  remove.mutate()
              }}
              className="btn-secondary btn-sm ml-auto"
            >
              Xoá tiết này
            </button>
          )}
        </div>
      )}
      {message && <SuccessNote>{message}</SuccessNote>}
      {save.isError && <ErrorAlert error={save.error} />}
      {remove.isError && <ErrorAlert error={remove.error} />}
    </div>
  )
}

function LessonEditor({
  classId,
  subjectId,
  day,
  lessonNo,
}: {
  classId: number
  subjectId: number
  day: string
  lessonNo: number
}) {
  const { token } = useAuth()
  const detail = useQuery({
    queryKey: ['lesson', token, classId, subjectId, day, lessonNo],
    queryFn: ({ signal }) => fetchLesson(classId, subjectId, day, lessonNo, signal),
  })
  return (
    <QueryState query={detail}>
      {(data) => (
        <LessonForm
          key={`${data.date}-${data.lesson_no}-${data.exists}-${data.taken_by}`}
          detail={data}
          classId={classId}
        />
      )}
    </QueryState>
  )
}

function Recorded({
  data,
  onPick,
  onMonth,
}: {
  data: SubjectLessons
  onPick: (day: string, lessonNo: number) => void
  onMonth: (month: string) => void
}) {
  return (
    <div className="space-y-3">
      <label className="flex items-center gap-2 text-sm font-medium text-slate-700">
        Tháng
        <select
          value={data.month}
          onChange={(event) => onMonth(event.target.value)}
          className="input w-auto py-1.5"
        >
          {data.months.map((item) => (
            <option key={item} value={item}>
              {formatMonth(item)}
            </option>
          ))}
        </select>
      </label>
      {data.lessons.length === 0 ? (
        <p className="text-sm text-slate-600">Chưa điểm danh tiết nào trong tháng này.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="data-table min-w-max text-sm">
            <thead>
              <tr>
                <th scope="col" className="px-3 py-2 font-medium">
                  Ngày
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Tiết
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  Vắng có phép
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  Vắng không phép
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  Muộn
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Người ghi
                </th>
                <th scope="col" className="px-3 py-2">
                  <span className="sr-only">Thao tác</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {data.lessons.map((lesson) => (
                <tr key={`${lesson.date}-${lesson.lesson_no}`}>
                  <td className="px-3 py-2 tabular-nums">
                    {weekday(lesson.date)} {shortDate(lesson.date)}
                  </td>
                  <td className="px-3 py-2">{lesson.lesson_no}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{lesson.excused}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{lesson.unexcused}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{lesson.late}</td>
                  <td className="px-3 py-2">{lesson.recorded_by}</td>
                  <td className="px-3 py-2 text-right">
                    <button
                      type="button"
                      onClick={() => onPick(lesson.date, lesson.lesson_no)}
                      className="link text-sm"
                    >
                      {data.can_edit ? 'Mở / sửa' : 'Xem'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function StudentTotals({ data }: { data: SubjectLessons }) {
  const rows = [...data.students]
    .map((s) => ({ ...s, absent: s.excused + s.unexcused }))
    .sort((a, b) => b.absent - a.absent || b.late - a.late)
  return (
    <div className="overflow-x-auto">
      <table className="data-table min-w-max text-sm">
        <thead>
          <tr>
            <th scope="col" className="px-3 py-2 font-medium">
              Học sinh
            </th>
            <th scope="col" className="px-3 py-2 text-right font-medium">
              Vắng có phép
            </th>
            <th scope="col" className="px-3 py-2 text-right font-medium">
              Vắng không phép
            </th>
            <th scope="col" className="px-3 py-2 text-right font-medium">
              Tổng tiết vắng
            </th>
            <th scope="col" className="px-3 py-2 text-right font-medium">
              Muộn
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((s) => (
            <tr key={s.student_id}>
              <th scope="row" className="px-3 py-2 text-left font-normal">
                {s.full_name}
                <span className="block font-mono text-xs text-slate-500">{s.student_code}</span>
              </th>
              <td className="px-3 py-2 text-right tabular-nums">{s.excused}</td>
              <td className="px-3 py-2 text-right tabular-nums">{s.unexcused}</td>
              <td className="px-3 py-2 text-right font-semibold tabular-nums">
                {s.absent}
                <span className="font-normal text-slate-400">/{data.lesson_count}</span>
              </td>
              <td className="px-3 py-2 text-right tabular-nums">{s.late}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// Sổ điểm danh theo tiết của một lớp–môn (D-120). GVBM được phân công điểm danh từng tiết mình
// dạy (mặc định cả lớp có mặt, chỉ đánh dấu em vắng / muộn kèm lý do); GVCN và BGH xem. Sổ này để
// theo dõi tham gia tiết học; số buổi nghỉ chính thức (mức 45 buổi) vẫn theo điểm danh ngày của GVCN.
export default function LessonsPage() {
  const params = useParams()
  const classId = Number(params.classId)
  const subjectId = Number(params.subjectId)
  const [search, setSearch] = useSearchParams()
  const { token } = useAuth()
  const month = search.get('month')
  const lessons = useQuery({
    queryKey: ['subject-lessons', token, classId, subjectId, month],
    queryFn: ({ signal }) => fetchSubjectLessons(classId, subjectId, month, signal),
    enabled: token !== null && Number.isInteger(classId) && Number.isInteger(subjectId),
  })
  const [day, setDay] = useState(search.get('day') ?? todayIso())
  const [lessonNo, setLessonNo] = useState(Number(search.get('tiet')) || 1)
  const [opened, setOpened] = useState<{ day: string; lessonNo: number } | null>(null)
  const data = lessons.data

  function setParam(key: string, value: string) {
    setSearch(
      (current) => {
        const copy = new URLSearchParams(current)
        copy.set(key, value)
        return copy
      },
      { replace: true },
    )
  }

  function open(nextDay: string, nextNo: number) {
    setDay(nextDay)
    setLessonNo(nextNo)
    setOpened({ day: nextDay, lessonNo: nextNo })
  }

  return (
    <>
      <PageTitle
        title={
          data
            ? `Điểm danh tiết học · ${data.subject_name} · lớp ${data.class_info.name}`
            : 'Điểm danh tiết học'
        }
        subtitle="Sổ theo dõi tham gia tiết học của môn; số buổi nghỉ chính thức do giáo viên chủ nhiệm điểm danh theo ngày"
        actions={
          <>
            {data?.can_edit && (
              <Link
                to={`/classes/${classId}/import?kind=lessons&subject=${subjectId}`}
                className="btn-secondary btn-sm"
              >
                Nhập từ tệp Excel
              </Link>
            )}
            <Link to={`/classes/${classId}/subjects/${subjectId}`} className="link text-sm">
              Bảng điểm
            </Link>
          </>
        }
      />
      <QueryState query={lessons}>
        {(result) => (
          <>
            <Panel
              id="diem-danh-tiet"
              title={result.can_edit ? 'Điểm danh một tiết' : 'Xem một tiết'}
              description={
                result.can_edit
                  ? 'Chọn ngày và tiết thứ mấy rồi bấm "Mở danh sách". Học sinh được trường cử đi (thi học sinh giỏi…) thì ghi "Vắng có phép" kèm lý do; giáo viên chủ nhiệm sẽ xác nhận ở điểm danh ngày để em không bị tính buổi nghỉ.'
                  : 'Chỉ giáo viên bộ môn được phân công mới điểm danh được tiết học.'
              }
            >
              <form
                className="mb-4 flex flex-wrap items-end gap-3"
                onSubmit={(event) => {
                  event.preventDefault()
                  open(day, lessonNo)
                }}
              >
                <label className="text-sm font-medium text-slate-700">
                  Ngày
                  <input
                    type="date"
                    value={day}
                    max={todayIso()}
                    onChange={(event) => setDay(event.target.value)}
                    className="input mt-1 w-auto"
                  />
                </label>
                <label className="text-sm font-medium text-slate-700">
                  Tiết thứ
                  <select
                    value={lessonNo}
                    onChange={(event) => setLessonNo(Number(event.target.value))}
                    className="input mt-1 w-auto"
                  >
                    {LESSON_NUMBERS.map((n) => (
                      <option key={n} value={n}>
                        {n}
                      </option>
                    ))}
                  </select>
                </label>
                <button type="submit" className="btn-primary">
                  Mở danh sách
                </button>
              </form>
              {opened && (
                <LessonEditor
                  key={`${opened.day}-${opened.lessonNo}`}
                  classId={classId}
                  subjectId={subjectId}
                  day={opened.day}
                  lessonNo={opened.lessonNo}
                />
              )}
            </Panel>
            <Panel
              id="tiet-da-diem-danh"
              title="Các tiết đã điểm danh"
              description={`Cả năm: ${result.lesson_count} tiết.`}
            >
              <Recorded data={result} onPick={open} onMonth={(m) => setParam('month', m)} />
            </Panel>
            <Panel
              id="tiet-vang-tung-em"
              title="Số tiết vắng của từng em trong môn (cả năm)"
              description="Tính trên các tiết đã điểm danh. Em vắng nhiều tiết có thể cần được hỗ trợ học bù."
            >
              <StudentTotals data={result} />
            </Panel>
          </>
        )}
      </QueryState>
    </>
  )
}
