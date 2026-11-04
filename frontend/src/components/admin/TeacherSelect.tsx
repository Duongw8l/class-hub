import type { Teacher, TeacherRef } from '../../api/admin'

interface TeacherSelectProps {
  id: string
  label: string
  teachers: Teacher[]
  value: number | null
  onChange: (teacherId: number | null) => void
  disabled?: boolean
  // Tên lớp đang sửa: giáo viên đang chủ nhiệm đúng lớp này không bị coi là "đã bận".
  currentClass?: string
  // Chọn GVCN thì loại giáo viên đang chủ nhiệm lớp khác; chọn người dạy thì không.
  homeroomOnly?: boolean
  emptyLabel: string
  hideLabel?: boolean
  // Giáo viên đang được chọn nhưng không còn trong danh sách (đã bị khoá): vẫn hiện để không bị trống.
  extra?: TeacherRef | null
  // Phân công một môn: giáo viên đúng môn lên đầu, giáo viên môn khác vẫn chọn được (dạy chéo môn).
  preferSubject?: { id: number; name: string }
}

// Ô chọn giáo viên. Mỗi dòng ghi kèm môn của giáo viên ("— Toán") để phân biệt hai người trùng tên.
// Với GVCN, giáo viên đang chủ nhiệm lớp khác bị tắt và ghi rõ lớp nào (mỗi giáo viên chỉ chủ nhiệm
// một lớp), tránh bấm rồi mới bị back-end từ chối.
export function TeacherSelect({
  id,
  label,
  teachers,
  value,
  onChange,
  disabled,
  currentClass,
  homeroomOnly = false,
  emptyLabel,
  hideLabel = false,
  extra = null,
  preferSubject,
}: TeacherSelectProps) {
  function option(teacher: Teacher) {
    const busy =
      homeroomOnly && teacher.homeroom_class !== null && teacher.homeroom_class !== currentClass
    return (
      <option key={teacher.id} value={teacher.id} disabled={busy && teacher.id !== value}>
        {teacher.full_name}
        {teacher.specialty ? ` — ${teacher.specialty}` : ''}
        {busy ? ` (đang chủ nhiệm ${teacher.homeroom_class})` : ''}
      </option>
    )
  }

  const matching = preferSubject
    ? teachers.filter((teacher) => teacher.specialty_subject_id === preferSubject.id)
    : []
  const others = preferSubject
    ? teachers.filter((teacher) => teacher.specialty_subject_id !== preferSubject.id)
    : teachers

  return (
    <div>
      <label htmlFor={id} className={hideLabel ? 'sr-only' : 'label'}>
        {label}
      </label>
      <select
        id={id}
        value={value ?? ''}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value === '' ? null : Number(event.target.value))}
        className={`input ${hideLabel ? '' : 'mt-1'}`}
      >
        <option value="">{emptyLabel}</option>
        {extra && !teachers.some((teacher) => teacher.id === extra.id) && (
          <option value={extra.id}>{extra.full_name} (đã bị khoá)</option>
        )}
        {preferSubject ? (
          <>
            {matching.length > 0 && (
              <optgroup label={`Giáo viên ${preferSubject.name}`}>{matching.map(option)}</optgroup>
            )}
            {others.length > 0 && (
              <optgroup label={matching.length > 0 ? 'Giáo viên khác' : 'Giáo viên'}>
                {others.map(option)}
              </optgroup>
            )}
          </>
        ) : (
          others.map(option)
        )}
      </select>
    </div>
  )
}
