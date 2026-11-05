import type { EntryInput } from '../../api/attendance'

export type Draft = Record<number, EntryInput>

// Các em có lý do "Khác" mà chưa ghi chú: chặn lưu (back-end cũng kiểm).
export function draftProblems(draft: Draft): number[] {
  return Object.values(draft)
    .filter((entry) => entry.reason === 'other' && !(entry.note ?? '').trim())
    .map((entry) => entry.student_id)
}
