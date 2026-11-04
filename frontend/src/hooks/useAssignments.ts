import { useQuery } from '@tanstack/react-query'
import { fetchAssignments } from '../api/auth'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/context'
import { useSelectedYear } from '../years/context'

// Lớp chủ nhiệm, lớp–môn được dạy (và các khối của BGH) trong năm học đang chọn (D-113).
export function useAssignments() {
  const { token } = useAuth()
  const { yearId } = useSelectedYear()
  return useQuery({
    // Token nằm trong khoá để dữ liệu của hai người dùng không bao giờ dùng chung một bộ nhớ đệm.
    queryKey: ['assignments', token, yearId],
    queryFn: ({ signal }) => fetchAssignments(yearId, signal),
    enabled: token !== null,
    // Lỗi 4xx (hết phiên, bị từ chối) không đổi khi thử lại; chỉ thử lại lỗi mạng và 5xx.
    retry: (failureCount, error) =>
      failureCount < 1 && !(error instanceof ApiError && error.status < 500),
  })
}
