import { useState } from 'react'
import type { FormEvent } from 'react'
import type { SchoolYear } from '../../api/admin'
import { useCreateSchoolYear, useSetCurrentYear } from '../../hooks/useAdmin'
import { useSelectedYear } from '../../years/context'
import { ErrorAlert, SuccessNote } from './shared'

// Năm học kế tiếp năm mới nhất: tên "YYYY-YYYY" và ngày mặc định 05/9 – 31/5 (sửa được).
function nextYear(years: SchoolYear[]): { name: string; start: string; end: string } {
  const latest = years[0]
  const first = latest ? Number(latest.start_date.slice(0, 4)) + 1 : new Date().getFullYear()
  return { name: `${first}-${first + 1}`, start: `${first}-09-05`, end: `${first + 1}-05-31` }
}

function dateVi(iso: string): string {
  const [y, m, d] = iso.split('-')
  return `${d}/${m}/${y}`
}

// Các năm học của trường (D-113): xem từng năm, đặt năm hiện hành, tạo năm mới (có thể chép lớp và
// cho học sinh lên lớp từ năm trước). Năm cũ vẫn sửa được dữ liệu.
export function SchoolYearsPanel({ years }: { years: SchoolYear[] }) {
  const { selected, setYearId } = useSelectedYear()
  const makeCurrent = useSetCurrentYear()
  const create = useCreateSchoolYear()
  const suggestion = nextYear(years)
  const [name, setName] = useState(suggestion.name)
  const [start, setStart] = useState(suggestion.start)
  const [end, setEnd] = useState(suggestion.end)
  const [rollover, setRollover] = useState(true)
  const [current, setCurrent] = useState(false)
  const [done, setDone] = useState<string | null>(null)

  const valid = name.trim() !== '' && start !== '' && end !== '' && start < end

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!valid || create.isPending) return
    setDone(null)
    create.mutate(
      { name: name.trim(), start_date: start, end_date: end, rollover, make_current: current },
      {
        onSuccess: (result) => {
          setDone(
            rollover
              ? `Đã tạo năm học ${result.school_year.name}: ${result.classes_created} lớp, ` +
                  `${result.students_promoted} học sinh được lên lớp. Hãy gán GVCN và phân công cho các lớp mới.`
              : `Đã tạo năm học ${result.school_year.name} (chưa có lớp).`,
          )
          setYearId(result.school_year.is_current ? null : result.school_year.id)
        },
      },
    )
  }

  return (
    <div className="space-y-6">
      <div className="overflow-x-auto">
        <table className="data-table min-w-max">
          <thead>
            <tr>
              <th className="py-2 pr-4 font-medium">Năm học</th>
              <th className="px-3 py-2 font-medium">Thời gian</th>
              <th className="px-3 py-2 font-medium">Trạng thái</th>
              <th className="py-2 pl-3 font-medium">
                <span className="sr-only">Thao tác</span>
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 align-middle">
            {years.map((year) => {
              const viewing = selected?.id === year.id
              return (
                <tr key={year.id}>
                  <th scope="row" className="py-2 pr-4 text-left font-medium">
                    {year.name}
                    {viewing && (
                      <span className="ml-2 text-xs font-normal text-slate-500">(đang xem)</span>
                    )}
                  </th>
                  <td className="px-3 py-2 text-slate-600">
                    {dateVi(year.start_date)} – {dateVi(year.end_date)}
                  </td>
                  <td className="px-3 py-2">
                    {year.is_current ? (
                      <span className="badge-good">Năm hiện hành</span>
                    ) : (
                      <span className="text-slate-500">Năm khác</span>
                    )}
                  </td>
                  <td className="py-2 pl-3">
                    <span className="flex flex-wrap gap-2">
                      {!viewing && (
                        <button
                          type="button"
                          onClick={() => setYearId(year.is_current ? null : year.id)}
                          className="btn-secondary px-3 py-1.5"
                        >
                          Xem năm này
                        </button>
                      )}
                      {!year.is_current && (
                        <button
                          type="button"
                          disabled={makeCurrent.isPending}
                          onClick={() =>
                            makeCurrent.mutate(year.id, { onSuccess: () => setYearId(null) })
                          }
                          className="btn-secondary px-3 py-1.5"
                        >
                          Đặt làm năm hiện hành
                        </button>
                      )}
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {makeCurrent.isError && <ErrorAlert error={makeCurrent.error} />}
      <p className="text-sm text-slate-500">
        Năm hiện hành là năm mọi người thấy mặc định. Ai cũng chọn được năm khác ở ô "Năm học" trên
        thanh trên cùng để xem lại; dữ liệu năm cũ vẫn sửa được.
      </p>

      <form onSubmit={submit} className="card space-y-4 p-4">
        <h3 className="text-sm font-semibold text-slate-700">Tạo năm học mới</h3>
        <div className="grid gap-4 sm:grid-cols-3">
          <div>
            <label htmlFor="nam-moi-ten" className="label">
              Tên năm học
            </label>
            <input
              id="nam-moi-ten"
              type="text"
              value={name}
              maxLength={20}
              disabled={create.isPending}
              onChange={(event) => setName(event.target.value)}
              className="input mt-1"
            />
          </div>
          <div>
            <label htmlFor="nam-moi-bat-dau" className="label">
              Ngày bắt đầu
            </label>
            <input
              id="nam-moi-bat-dau"
              type="date"
              value={start}
              disabled={create.isPending}
              onChange={(event) => setStart(event.target.value)}
              className="input mt-1"
            />
          </div>
          <div>
            <label htmlFor="nam-moi-ket-thuc" className="label">
              Ngày kết thúc
            </label>
            <input
              id="nam-moi-ket-thuc"
              type="date"
              value={end}
              disabled={create.isPending}
              onChange={(event) => setEnd(event.target.value)}
              className="input mt-1"
            />
          </div>
        </div>
        <label className="flex items-start gap-2 text-sm text-slate-700">
          <input
            type="checkbox"
            checked={rollover}
            disabled={create.isPending || years.length === 0}
            onChange={(event) => setRollover(event.target.checked)}
            className="mt-0.5 h-4 w-4"
          />
          <span>
            Chép lớp từ năm trước và cho học sinh lên lớp
            <span className="block text-xs text-slate-500">
              Tạo sẵn các lớp cùng tên; học sinh 10Ax lên 11Ax, 11Ax lên 12Ax, khối 12 ra trường; khối
              10 mới để trống. GVCN và phân công để trống. Học sinh lưu ban: gỡ khỏi lớp mới rồi nhập
              vào đúng lớp.
            </span>
          </span>
        </label>
        <label className="flex items-center gap-2 text-sm text-slate-700">
          <input
            type="checkbox"
            checked={current}
            disabled={create.isPending}
            onChange={(event) => setCurrent(event.target.checked)}
            className="h-4 w-4"
          />
          Đặt làm năm hiện hành ngay
        </label>
        {start !== '' && end !== '' && start >= end && (
          <p className="text-sm text-red-700">Ngày bắt đầu phải trước ngày kết thúc.</p>
        )}
        <button type="submit" disabled={!valid || create.isPending} className="btn-primary">
          {create.isPending ? 'Đang tạo…' : 'Tạo năm học'}
        </button>
        {done && <SuccessNote>{done}</SuccessNote>}
        {create.isError && <ErrorAlert error={create.error} />}
      </form>
    </div>
  )
}
