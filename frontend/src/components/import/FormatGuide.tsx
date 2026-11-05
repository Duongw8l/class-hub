import { useState } from 'react'
import type { ReactNode } from 'react'
import { fetchSubjectScores } from '../../api/analytics'
import { fetchClassStudents } from '../../api/imports'
import type { ConductPeriod, ImportKind } from '../../api/imports'
import { Icon } from '../Icon'
import { PERIOD_LABELS } from './format'

// Hướng dẫn cấu trúc tệp cho từng loại nhập, ngay trên ô chọn tệp. Nội dung khớp quy tắc của
// back-end: tên cột và bí danh ở backend/app/imports/columns.py, giá trị hợp lệ ở values.py.

interface Column {
  name: string
  required: boolean
  content: ReactNode
  aliases: string
}

interface GuideProps {
  kind: ImportKind
  classId: number
  className: string
  subjectId: number | null
  subjectName: string | null
  semester: number
  period: ConductPeriod
}

const STUDENT_COLUMNS: Column[] = [
  {
    name: 'Mã HS',
    required: true,
    content: 'Mã học sinh trong lớp, mỗi em một dòng, không trùng.',
    aliases: 'Mã học sinh, MSHS, Mã số HS',
  },
  {
    name: 'Họ và tên',
    required: false,
    content: 'Chỉ để đối chiếu. Khác tên trong hệ thống thì chỉ cảnh báo, không chặn.',
    aliases: 'Họ tên, Tên học sinh',
  },
]

function ColumnTable({ columns }: { columns: Column[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="data-table min-w-max text-sm">
        <thead>
          <tr>
            <th scope="col" className="px-3 py-2 font-medium">
              Tên cột
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              Bắt buộc
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              Nội dung hợp lệ
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              Tên cột khác cũng nhận
            </th>
          </tr>
        </thead>
        <tbody className="align-top">
          {columns.map((column) => (
            <tr key={column.name}>
              <th scope="row" className="px-3 py-2 text-left font-semibold">
                {column.name}
              </th>
              <td className="px-3 py-2">
                {column.required ? (
                  <span className="badge-fail">Bắt buộc</span>
                ) : (
                  <span className="badge-neutral">Tuỳ chọn</span>
                )}
              </td>
              <td className="max-w-md whitespace-normal px-3 py-2">{column.content}</td>
              <td className="max-w-xs whitespace-normal px-3 py-2 text-slate-600">
                {column.aliases}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Example({ headers, rows }: { headers: string[]; rows: string[][] }) {
  return (
    <div className="overflow-x-auto">
      <p className="mb-1 text-xs font-medium text-slate-500">Ví dụ (dòng đầu là tiêu đề cột):</p>
      <table className="min-w-max border-collapse font-mono text-xs">
        <thead>
          <tr>
            {headers.map((header) => (
              <th key={header} className="border border-slate-300 bg-slate-100 px-2 py-1 text-left">
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index}>
              {row.map((cell, col) => (
                <td key={col} className="border border-slate-300 px-2 py-1">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Rules({ items }: { items: ReactNode[] }) {
  return (
    <ul className="list-inside list-disc space-y-1 text-sm text-slate-700">
      {items.map((item, index) => (
        <li key={index}>{item}</li>
      ))}
    </ul>
  )
}

const COMMON_RULES: ReactNode[] = [
  <>
    Tệp <strong>.xlsx</strong> (chỉ đọc <strong>sheet đầu tiên</strong>) hoặc <strong>.csv</strong>{' '}
    mã UTF-8, tối đa 5 MB.
  </>,
  'Dòng tiêu đề cột có thể nằm dưới vài dòng tiêu đề lớn (tên trường, tên lớp…): hệ thống tự dò trong 15 dòng đầu.',
  'Tên cột không phân biệt hoa thường, có dấu hay không dấu, có khoảng trắng hay không. Cột thừa (STT, ĐTB…) được bỏ qua.',
  'Tên cột khác hẳn? Ở bước Xem trước có thể tự chọn cột nào ứng với thông tin nào.',
  'Xem trước không ghi gì vào hệ thống. Chỉ khi bấm Xác nhận và tệp không còn dòng lỗi thì dữ liệu mới được lưu.',
]

// --- Tệp mẫu ------------------------------------------------------------------------------------

function csvCell(value: string): string {
  return /[",\n;]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value
}

// CSV UTF-8 có BOM để Excel mở đúng tiếng Việt.
function downloadCsv(fileName: string, headers: string[], rows: string[][]) {
  const text = [headers, ...rows].map((row) => row.map(csvCell).join(',')).join('\r\n')
  const blob = new Blob(['﻿', text], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  link.click()
  URL.revokeObjectURL(url)
}

function slugClass(name: string): string {
  return name.replace(/[^A-Za-z0-9]+/g, '')
}

function TemplateButton({ label, build }: { label: string; build: () => Promise<void> }) {
  const [state, setState] = useState<'idle' | 'busy' | 'error'>('idle')
  return (
    <div className="flex flex-wrap items-center gap-3">
      <button
        type="button"
        disabled={state === 'busy'}
        onClick={() => {
          setState('busy')
          build().then(
            () => setState('idle'),
            () => setState('error'),
          )
        }}
        className="btn-secondary btn-sm"
      >
        <Icon name="file" className="h-4 w-4" />
        {state === 'busy' ? 'Đang tạo…' : label}
      </button>
      {state === 'error' && (
        <span role="alert" className="text-sm text-red-700">
          Không tạo được tệp mẫu. Hãy thử lại.
        </span>
      )}
    </div>
  )
}

// --- Từng loại ---------------------------------------------------------------------------------

function ConductGuide({ classId, className, period }: GuideProps) {
  const headers = ['Mã HS', 'Họ và tên', 'Xếp loại rèn luyện', 'Nhận xét']
  return (
    <>
      <ColumnTable
        columns={[
          ...STUDENT_COLUMNS,
          {
            name: 'Xếp loại rèn luyện',
            required: true,
            content: (
              <>
                Một trong bốn mức <strong>Tốt</strong>, <strong>Khá</strong>,{' '}
                <strong>Đạt</strong>, <strong>Chưa đạt</strong>. Viết tắt T, K, Đ, CĐ hoặc không
                dấu (Tot, Kha, Dat, Chua dat) cũng được. Để trống là lỗi.
              </>
            ),
            aliases: 'Mức rèn luyện, Rèn luyện, Kết quả rèn luyện, Xếp loại, Hạnh kiểm',
          },
          {
            name: 'Nhận xét',
            required: false,
            content:
              'Tối đa 500 ký tự. Có nội dung thì thay nhận xét cũ; để trống thì giữ nhận xét đang có.',
            aliases: 'Ghi chú, Nhận xét rèn luyện',
          },
        ]}
      />
      <Example
        headers={headers}
        rows={[
          ['HS26110701', 'Nguyễn Văn An', 'Tốt', 'Tích cực tham gia hoạt động của lớp.'],
          ['HS26110702', 'Trần Thị Bình', 'Khá', ''],
          ['HS26110703', 'Lê Minh Châu', 'Đạt', 'Cần đúng giờ hơn.'],
        ]}
      />
      <Rules
        items={[
          <>
            <strong>Mỗi tệp là một kỳ.</strong> Chọn đúng "Kỳ rèn luyện" ở trên (đang chọn:{' '}
            <strong>{PERIOD_LABELS[period]}</strong>) trước khi tải tệp. Học kỳ I, học kỳ II và cả
            năm là ba lần nhập riêng.
          </>,
          `Mã học sinh phải thuộc lớp ${className}. Không cần đủ cả lớp: em không có trong tệp giữ nguyên kết quả cũ.`,
          'Nhập lại tệp của cùng kỳ thì mức mới ghi đè mức cũ. Muốn sửa một vài em, dùng trang Rèn luyện của lớp (có lý do và lịch sử).',
          ...COMMON_RULES,
        ]}
      />
      <TemplateButton
        label={`Tải tệp mẫu có sẵn danh sách lớp ${className} (.csv)`}
        build={async () => {
          const students = await fetchClassStudents(classId)
          downloadCsv(
            `mau-ren-luyen-${slugClass(className)}-${period}.csv`,
            headers,
            students.map((s) => [s.student_code, s.full_name, '', '']),
          )
        }}
      />
    </>
  )
}

function AttendanceGuide({ classId, className }: GuideProps) {
  const headers = ['Mã HS', 'Họ và tên', 'Ngày', 'Trạng thái']
  return (
    <>
      <ColumnTable
        columns={[
          ...STUDENT_COLUMNS.map((c) =>
            c.name === 'Mã HS'
              ? { ...c, content: 'Mã học sinh trong lớp. Mỗi em mỗi ngày một dòng.' }
              : c,
          ),
          {
            name: 'Ngày',
            required: true,
            content: 'Ngày học, dạng dd/mm/yyyy (ví dụ 05/03/2027) hoặc yyyy-mm-dd.',
            aliases: 'Ngày học, Ngày điểm danh, Thời gian',
          },
          {
            name: 'Trạng thái',
            required: true,
            content: (
              <>
                <strong>Có mặt</strong>, <strong>Nghỉ có phép</strong> (P, CP),{' '}
                <strong>Nghỉ không phép</strong> (K, KP), <strong>Muộn</strong> (M),{' '}
                <strong>Vắng do nhà trường cử đi</strong> (Được cử đi, Cử đi: không tính buổi
                nghỉ). Có dấu hay không dấu đều được.
              </>
            ),
            aliases: 'Điểm danh, Tình trạng, Ký hiệu',
          },
        ]}
      />
      <Example
        headers={headers}
        rows={[
          ['HS26110701', 'Nguyễn Văn An', '05/03/2027', 'Có mặt'],
          ['HS26110702', 'Trần Thị Bình', '05/03/2027', 'Nghỉ có phép'],
          ['HS26110702', 'Trần Thị Bình', '06/03/2027', 'K'],
        ]}
      />
      <Rules
        items={[
          `Mã học sinh phải thuộc lớp ${className}. Cùng một em và cùng một ngày không được lặp lại.`,
          'Ngày phải nằm trong năm học của lớp. Một tệp có thể chứa nhiều ngày (ví dụ cả tháng); ngày đã có thì trạng thái mới ghi đè trạng thái cũ (lý do vắng đã ghi tay của ngày đó bị xoá vì tệp không có lý do).',
          'Muốn ghi lý do vắng (ốm, thi học sinh giỏi…) hoặc sửa một vài em, dùng trang Điểm danh của lớp.',
          ...COMMON_RULES,
        ]}
      />
      <TemplateButton
        label={`Tải tệp mẫu có sẵn danh sách lớp ${className} (.csv)`}
        build={async () => {
          const students = await fetchClassStudents(classId)
          downloadCsv(
            `mau-diem-danh-${slugClass(className)}.csv`,
            headers,
            students.map((s) => [s.student_code, s.full_name, '', '']),
          )
        }}
      />
    </>
  )
}

function AssessmentGuide({ classId, className, subjectId, subjectName, semester }: GuideProps) {
  const semesterName = semester === 2 ? 'học kỳ II' : 'học kỳ I'
  return (
    <>
      <ColumnTable
        columns={[
          ...STUDENT_COLUMNS,
          {
            name: 'ĐĐGtx 1, ĐĐGtx 2…',
            required: true,
            content: (
              <>
                Điểm thường xuyên, mỗi đầu điểm một cột. Số cột tuỳ số tiết của môn (tệp mẫu bên
                dưới có đúng số cột). Điểm từ 0 đến 10, tối đa <strong>1 chữ số thập phân</strong>,
                dấu phẩy hoặc chấm (7,5 hoặc 7.5).
              </>
            ),
            aliases: 'TX1, ĐGtx 1, KTTX 1, Điểm TX 1, Thường xuyên 1',
          },
          {
            name: 'ĐĐGgk',
            required: true,
            content: 'Điểm giữa kỳ, cùng quy tắc như trên.',
            aliases: 'GK, Giữa kỳ, Điểm giữa kỳ, Kiểm tra giữa kỳ',
          },
          {
            name: 'ĐĐGck',
            required: true,
            content: 'Điểm cuối kỳ, cùng quy tắc như trên.',
            aliases: 'CK, Cuối kỳ, Điểm cuối kỳ, Kiểm tra cuối kỳ',
          },
        ]}
      />
      <Example
        headers={['Mã HS', 'Họ và tên', 'ĐĐGtx 1', 'ĐĐGtx 2', 'ĐĐGtx 3', 'ĐĐGtx 4', 'ĐĐGgk', 'ĐĐGck']}
        rows={[
          ['HS26110701', 'Nguyễn Văn An', '8', '7,5', '9', '8', '7,8', '8,5'],
          ['HS26110702', 'Trần Thị Bình', '6,5', '7', '6', '7', '6,8', '7'],
        ]}
      />
      <Rules
        items={[
          <>
            <strong>Mỗi tệp là một môn, một học kỳ.</strong> Chọn đúng "Môn" và "Học kỳ" ở trên
            (đang chọn: <strong>{subjectName ?? 'chưa chọn'}</strong>, {semesterName}).
          </>,
          'Môn đánh giá bằng nhận xét (Giáo dục thể chất, Hoạt động trải nghiệm…): chỉ một cột "Nhận xét" ghi Đạt hoặc Chưa đạt (Đ, CĐ).',
          'Thiếu đầu điểm là lỗi, trừ khi bật "Cho phép nhập dở". Ô trống không bao giờ xoá điểm đã có. Cột ĐTB (nếu có) được bỏ qua: hệ thống tự tính.',
          'Không làm tròn hộ: 8,25 là lỗi.',
          ...COMMON_RULES,
        ]}
      />
      {subjectId !== null && (
        <TemplateButton
          label={`Tải tệp mẫu ${subjectName ?? ''} lớp ${className}, ${semesterName} (.csv)`}
          build={async () => {
            const scores = await fetchSubjectScores(classId, subjectId, semester === 2 ? 2 : 1)
            const isComment = scores.subject.assessment_type === 'comment'
            const tx = Array.from(
              { length: scores.subject.regular_required },
              (_, index) => `ĐĐGtx ${index + 1}`,
            )
            const headers = isComment
              ? ['Mã HS', 'Họ và tên', 'Nhận xét']
              : ['Mã HS', 'Họ và tên', ...tx, 'ĐĐGgk', 'ĐĐGck']
            downloadCsv(
              `mau-diem-${slugClass(className)}-mon${subjectId}-hk${semester}.csv`,
              headers,
              scores.rows.map((row) => [
                row.student_code,
                row.full_name,
                ...Array(headers.length - 2).fill(''),
              ]),
            )
          }}
        />
      )}
    </>
  )
}

function LessonGuide({ classId, className, subjectName }: GuideProps) {
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  const today = `${pad(now.getDate())}/${pad(now.getMonth() + 1)}`
  return (
    <>
      <p className="text-sm text-slate-700">
        Dùng khi điểm danh không có mạng: ghi trên Excel <strong>giống sổ giấy</strong> rồi tải lên
        sau. Mỗi học sinh một dòng, <strong>mỗi tiết đã dạy một cột</strong>; dạy xong tiết nào thì
        thêm một cột cho tiết đó.
      </p>
      <ColumnTable
        columns={[
          ...STUDENT_COLUMNS,
          {
            name: 'Một cột cho mỗi tiết',
            required: true,
            content: (
              <>
                Tiêu đề cột ghi <strong>ngày và tiết thứ mấy</strong>, ví dụ{' '}
                <strong>05/10 Tiết 2</strong> (cũng nhận "05/10/2026 - Tiết 2", "Tiết 2 (5/10)",
                "05/10 T2"). Năm có thể bỏ, hệ thống lấy theo năm học. Trong ô:{' '}
                <strong>để trống = có mặt</strong>, <strong>P</strong> = vắng có phép,{' '}
                <strong>K</strong> = vắng không phép, <strong>M</strong> = đi muộn (viết đầy đủ
                "Có phép", "Không phép", "Muộn" cũng được).
              </>
            ),
            aliases: 'Không cần ánh xạ: hệ thống tự nhận mọi cột có ngày và tiết.',
          },
        ]}
      />
      <Example
        headers={['Mã HS', 'Họ và tên', '05/10 Tiết 2', '07/10 Tiết 1', '12/10 Tiết 2']}
        rows={[
          ['HS26110701', 'Nguyễn Văn An', '', '', 'P'],
          ['HS26110702', 'Trần Thị Bình', 'K', 'M', ''],
          ['HS26110703', 'Lê Minh Châu', '', '', ''],
        ]}
      />
      <Rules
        items={[
          <>
            <strong>Mỗi tệp là một môn</strong> (đang chọn: <strong>{subjectName ?? 'chưa chọn'}</strong>
            ). Một tệp có thể chứa nhiều tiết, cả tháng hay cả học kỳ.
          </>,
          <>
            <strong>Bắt buộc có tiết thứ mấy</strong> (1 đến 10). Cột chỉ có ngày mà thiếu tiết, hai
            cột trùng một tiết, ngày ngoài năm học hoặc chưa tới, tiết đã được môn khác điểm danh:
            đều là lỗi và không ghi gì.
          </>,
          'Không nhận tệp chỉ có tổng số tiết vắng của từng em: cần ngày và tiết để đối chiếu với điểm danh ngày của giáo viên chủ nhiệm.',
          'Học sinh được trường cử đi (thi học sinh giỏi…): ghi P. Giáo viên chủ nhiệm xác nhận "cử đi" ở điểm danh ngày để em không bị tính buổi nghỉ.',
          'Tải lại tệp đã nhập: chỉ ô nào khác mới được ghi đè; em không có trong tệp giữ nguyên. Sổ theo tiết là sổ theo dõi của môn, không thay điểm danh ngày.',
          'Nên tải tệp mẫu từ trước (khi còn mạng) để có sẵn mã và họ tên cả lớp.',
          ...COMMON_RULES,
        ]}
      />
      <TemplateButton
        label={`Tải tệp mẫu có sẵn danh sách lớp ${className} (.csv)`}
        build={async () => {
          const students = await fetchClassStudents(classId)
          downloadCsv(
            `mau-diem-danh-tiet-${slugClass(className)}.csv`,
            ['Mã HS', 'Họ và tên', `${today} Tiết 1`],
            students.map((s) => [s.student_code, s.full_name, '']),
          )
        }}
      />
    </>
  )
}

const TITLES: Partial<Record<ImportKind, string>> = {
  lessons: 'Tệp điểm danh tiết cần có dạng nào?',
  conduct: 'Tệp rèn luyện cần có những cột nào?',
  attendance: 'Tệp điểm danh cần có những cột nào?',
  assessments: 'Tệp điểm cần có những cột nào?',
}

export function FormatGuide(props: GuideProps) {
  const title = TITLES[props.kind]
  if (title === undefined) return null // danh sách học sinh (Admin) có mô tả riêng
  return (
    <details open className="group rounded-2xl bg-slate-50 p-4 ring-1 ring-slate-200">
      <summary className="flex cursor-pointer list-none items-center gap-2 font-semibold text-slate-900">
        <Icon name="info" className="h-5 w-5 text-brand-700" />
        {title}
        <span className="ml-auto text-xs font-normal text-slate-500 group-open:hidden">
          Bấm để xem
        </span>
        <span className="ml-auto hidden text-xs font-normal text-slate-500 group-open:inline">
          Thu gọn
        </span>
      </summary>
      <div className="mt-4 space-y-4">
        {props.kind === 'conduct' && <ConductGuide {...props} />}
        {props.kind === 'attendance' && <AttendanceGuide {...props} />}
        {props.kind === 'assessments' && <AssessmentGuide {...props} />}
        {props.kind === 'lessons' && <LessonGuide {...props} />}
      </div>
    </details>
  )
}
