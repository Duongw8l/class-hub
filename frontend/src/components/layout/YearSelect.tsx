import { useLocation, useNavigate } from 'react-router-dom'
import { useSelectedYear } from '../../years/context'

// Ô chọn năm học trên thanh trên cùng (D-113): áp dụng cho mọi trang. Chỉ hiện khi trường có từ hai
// năm học trở lên. Đang mở một lớp (lớp thuộc một năm cụ thể) mà đổi năm thì về trang chủ.
export function YearSelect() {
  const { years, selected, setYearId } = useSelectedYear()
  const { pathname } = useLocation()
  const navigate = useNavigate()

  if (years.length < 2 || selected === undefined) return null

  return (
    <div className="flex items-center gap-2">
      <label htmlFor="chon-nam-hoc" className="hidden text-sm text-slate-500 sm:block">
        Năm học
      </label>
      <select
        id="chon-nam-hoc"
        value={selected.id}
        onChange={(event) => {
          const year = years.find((item) => item.id === Number(event.target.value))
          if (!year) return
          setYearId(year.is_current ? null : year.id)
          if (pathname.startsWith('/classes/') || pathname.startsWith('/admin/classes/')) {
            navigate('/')
          }
        }}
        className="input w-auto py-1.5 text-sm"
      >
        {years.map((year) => (
          <option key={year.id} value={year.id}>
            {year.name}
            {year.is_current ? ' (hiện hành)' : ''}
          </option>
        ))}
      </select>
    </div>
  )
}

// Dải báo khi đang xem một năm không phải năm hiện hành, kèm nút quay về.
export function PastYearNotice() {
  const { isPast, selected, years, setYearId } = useSelectedYear()
  const { pathname } = useLocation()
  const navigate = useNavigate()
  if (!isPast || selected === undefined) return null
  const current = years.find((year) => year.is_current)
  return (
    <div
      role="status"
      className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-900 ring-1 ring-amber-200"
    >
      <span>
        Bạn đang xem năm học <strong>{selected.name}</strong>
        {current ? `, không phải năm hiện hành (${current.name}).` : '.'}
      </span>
      <button
        type="button"
        onClick={() => {
          setYearId(null)
          if (pathname.startsWith('/classes/') || pathname.startsWith('/admin/classes/')) {
            navigate('/')
          }
        }}
        className="btn-secondary px-3 py-1.5"
      >
        Về năm hiện hành
      </button>
    </div>
  )
}
