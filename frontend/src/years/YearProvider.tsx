import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { fetchSchoolYears } from '../api/years'
import { useAuth } from '../auth/context'
import { YearContext } from './context'

const STORAGE_KEY = 'nam-hoc-dang-xem'

function readStored(): number | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const value = raw === null ? NaN : Number(raw)
    return Number.isInteger(value) ? value : null
  } catch {
    return null
  }
}

// Giữ năm học đang xem (lưu trong trình duyệt để tải lại trang không mất). Năm đã lưu mà không còn
// trong danh sách (bị xoá, hoặc người dùng khác trên cùng máy) thì quay về năm hiện hành.
export function YearProvider({ children }: { children: ReactNode }) {
  const { token } = useAuth()
  const [stored, setStored] = useState<number | null>(readStored)
  const query = useQuery({
    queryKey: ['school-years', token],
    queryFn: ({ signal }) => fetchSchoolYears(signal),
    enabled: token !== null,
    staleTime: 5 * 60 * 1000,
  })

  const value = useMemo(() => {
    const years = query.data ?? []
    const current = years.find((year) => year.is_current)
    const chosen = stored === null ? undefined : years.find((year) => year.id === stored)
    // Chưa tải xong danh sách thì vẫn giữ lựa chọn đã lưu để khỏi tải dữ liệu hai lần.
    const yearId = query.data === undefined ? stored : chosen && !chosen.is_current ? chosen.id : null
    const selected = chosen ?? current
    return {
      yearId,
      setYearId: (id: number | null) => {
        setStored(id)
        try {
          if (id === null) localStorage.removeItem(STORAGE_KEY)
          else localStorage.setItem(STORAGE_KEY, String(id))
        } catch {
          // Trình duyệt chặn localStorage: vẫn đổi năm trong phiên này.
        }
      },
      years,
      selected,
      isPast: selected !== undefined && !selected.is_current,
    }
  }, [query.data, stored])

  return <YearContext.Provider value={value}>{children}</YearContext.Provider>
}
