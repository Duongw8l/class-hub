import { apiGet } from './client'

// Khớp backend/app/classes/schemas.py (SchoolYearOut), D-113.
export interface SchoolYear {
  id: number
  name: string
  start_date: string
  end_date: string
  is_current: boolean
}

export function fetchSchoolYears(signal?: AbortSignal): Promise<SchoolYear[]> {
  return apiGet<SchoolYear[]>('/school-years', signal)
}

// Thêm `school_year_id` vào đường dẫn khi đang xem một năm cụ thể; null là năm hiện hành (back-end
// tự chọn), nên không gửi gì.
export function withYear(path: string, yearId: number | null): string {
  if (yearId === null) return path
  return `${path}${path.includes('?') ? '&' : '?'}school_year_id=${yearId}`
}
