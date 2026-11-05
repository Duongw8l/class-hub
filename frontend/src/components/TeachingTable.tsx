import { Link } from 'react-router-dom'
import type { SubjectSupport } from '../api/analytics'
import type { TeachingItem } from '../api/auth'
import { useMySupport } from '../hooks/useAnalytics'
import { Panel } from './Panel'

// Số học sinh cần hỗ trợ của một lớp–môn (D-118), dẫn tới trang chi tiết.
function SupportCell({ item, found }: { item: TeachingItem; found: SubjectSupport | undefined }) {
  if (found === undefined) return <span className="text-slate-400">—</span>
  const { high, medium, low } = found.counts
  const total = high + medium + low
  if (total === 0) return <span className="text-slate-500">Không có</span>
  return (
    <Link
      to={`/support?item=${item.class_id}:${item.subject_id}`}
      aria-label={`${total} học sinh cần hỗ trợ môn ${item.subject_name} lớp ${item.class_name}`}
      className="inline-flex items-center gap-1.5"
    >
      {high > 0 && <span className="badge-high">{high} cao</span>}
      {medium > 0 && <span className="badge-medium">{medium} TB</span>}
      {low > 0 && <span className="badge-low">{low} thấp</span>}
    </Link>
  )
}

// Lớp và môn giáo viên đang dạy, mỗi dòng có lối tắt tới bảng điểm và nhập điểm, kèm số học sinh
// cần hỗ trợ trong môn đó.
export function TeachingTable({ items }: { items: TeachingItem[] }) {
  const support = useMySupport(null, items.length > 0)
  const find = (item: TeachingItem) =>
    support.data?.items.find(
      (s) => s.class_info.id === item.class_id && s.subject.id === item.subject_id,
    )
  return (
    <Panel
      id="lop-mon-dang-day"
      title="Lớp và môn đang dạy"
      actions={
        <Link to="/support" className="link text-sm">
          Học sinh cần hỗ trợ
        </Link>
      }
    >
      <div className="-mx-2 overflow-x-auto px-2">
        <table className="data-table min-w-max">
          <thead>
            <tr>
              <th scope="col" className="px-3 py-2.5 font-semibold">
                Lớp
              </th>
              <th scope="col" className="px-3 py-2.5 font-semibold">
                Môn
              </th>
              <th scope="col" className="px-3 py-2.5 font-semibold">
                Cần hỗ trợ
              </th>
              <th scope="col" className="px-3 py-2.5 text-right font-semibold">
                <span className="sr-only">Thao tác</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={`${item.class_id}-${item.subject_id}`}>
                <td className="px-3 py-2.5 font-medium">{item.class_name}</td>
                <td className="px-3 py-2.5">{item.subject_name}</td>
                <td className="px-3 py-2.5 text-sm">
                  {support.isPending ? (
                    <span className="text-slate-400">…</span>
                  ) : (
                    <SupportCell item={item} found={find(item)} />
                  )}
                </td>
                <td className="space-x-4 px-3 py-2.5 text-right">
                  <Link
                    to={`/classes/${item.class_id}/subjects/${item.subject_id}`}
                    aria-label={`Bảng điểm ${item.subject_name} lớp ${item.class_name}`}
                    className="link"
                  >
                    Bảng điểm
                  </Link>
                  <Link
                    to={`/classes/${item.class_id}/subjects/${item.subject_id}/lessons`}
                    aria-label={`Điểm danh tiết học ${item.subject_name} lớp ${item.class_name}`}
                    className="link"
                  >
                    Điểm danh tiết
                  </Link>
                  <Link
                    to={`/classes/${item.class_id}/import?kind=assessments&subject=${item.subject_id}`}
                    aria-label={`Nhập điểm ${item.subject_name} lớp ${item.class_name}`}
                    className="link"
                  >
                    Nhập điểm
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  )
}
