import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import {
  fetchDashboard,
  fetchGradeOverview,
  fetchMySupport,
  fetchStudentProfile,
  fetchSubjectScores,
  fetchSubjectSupport,
} from '../api/analytics'
import type { Period } from '../api/analytics'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/context'
import { useSelectedYear } from '../years/context'

// Lỗi 4xx (hết phiên, không có quyền, không có dữ liệu) không đổi khi thử lại; chỉ thử lại lỗi mạng
// và 5xx (cùng quy tắc với useAssignments).
function retry(failureCount: number, error: Error): boolean {
  return failureCount < 1 && !(error instanceof ApiError && error.status < 500)
}

// Token nằm trong khoá bộ nhớ đệm để dữ liệu của hai người dùng không bao giờ dùng chung.
export function useDashboard(classId: number, period: Period) {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['dashboard', token, classId, period],
    queryFn: ({ signal }) => fetchDashboard(classId, period, signal),
    enabled: token !== null && Number.isInteger(classId),
    retry,
  })
}

export function useSubjectScores(classId: number, subjectId: number, semester: 1 | 2) {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['subject-scores', token, classId, subjectId, semester],
    queryFn: ({ signal }) => fetchSubjectScores(classId, subjectId, semester, signal),
    enabled: token !== null && Number.isInteger(classId) && Number.isInteger(subjectId),
    retry,
  })
}

export function useSubjectSupport(classId: number, subjectId: number, semester: 1 | 2 | null) {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['subject-support', token, classId, subjectId, semester],
    queryFn: ({ signal }) => fetchSubjectSupport(classId, subjectId, semester, signal),
    enabled: token !== null && Number.isInteger(classId) && Number.isInteger(subjectId),
    retry,
  })
}

// Mọi lớp–môn đang dạy trong năm đang chọn (D-118). `enabled` để chỉ giáo viên có phân công gọi.
export function useMySupport(semester: 1 | 2 | null, enabled = true) {
  const { token } = useAuth()
  const { yearId } = useSelectedYear()
  return useQuery({
    queryKey: ['my-support', token, semester, yearId],
    queryFn: ({ signal }) => fetchMySupport(semester, yearId, signal),
    enabled: token !== null && enabled,
    retry,
  })
}

export function useGradeOverview(level: number, period: Period) {
  const { token } = useAuth()
  const { yearId } = useSelectedYear() // so sánh các lớp của khối trong năm đang chọn (D-113)
  return useQuery({
    queryKey: ['grade-overview', token, level, period, yearId],
    queryFn: ({ signal }) => fetchGradeOverview(level, period, yearId, signal),
    enabled: token !== null && Number.isInteger(level),
    retry,
  })
}

export function useStudentProfile(classId: number, studentId: number, period: Period) {
  const { token } = useAuth()
  return useQuery({
    queryKey: ['student-profile', token, classId, studentId, period],
    queryFn: ({ signal }) => fetchStudentProfile(classId, studentId, period, signal),
    enabled: token !== null && Number.isInteger(classId) && Number.isInteger(studentId),
    retry,
  })
}

// Kỳ đang xem nằm trong `?semester=` của URL: chia sẻ được, nút Back hoạt động, tải lại trang không
// mất lựa chọn. Giá trị lạ trong URL rơi về mặc định.
export function usePeriod(allowed: readonly Period[], fallback: Period) {
  const [params, setParams] = useSearchParams()
  const raw = params.get('semester')
  const period = allowed.find((item) => item === raw) ?? fallback

  function setPeriod(next: Period) {
    setParams(
      (current) => {
        const copy = new URLSearchParams(current)
        copy.set('semester', next)
        return copy
      },
      { replace: true },
    )
  }
  return [period, setPeriod] as const
}
