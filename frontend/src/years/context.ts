import { createContext, useContext } from 'react'
import type { SchoolYear } from '../api/years'

export interface YearContextValue {
  // Năm gửi lên back-end: null là năm hiện hành (back-end tự chọn).
  yearId: number | null
  setYearId: (id: number | null) => void
  years: SchoolYear[] // mới nhất trước; rỗng khi chưa tải hoặc chưa có năm học
  selected: SchoolYear | undefined // năm đang xem (năm hiện hành khi yearId là null)
  isPast: boolean // đang xem một năm không phải năm hiện hành
}

export const YearContext = createContext<YearContextValue>({
  yearId: null,
  setYearId: () => {},
  years: [],
  selected: undefined,
  isPast: false,
})

// Năm học đang xem (D-113), chọn ở thanh trên cùng và dùng chung cho mọi trang.
export function useSelectedYear(): YearContextValue {
  return useContext(YearContext)
}
