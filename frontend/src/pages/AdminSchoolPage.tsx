import { AdminGate } from '../components/admin/shared'
import { ClassForm } from '../components/admin/ClassForm'
import { ClassTable } from '../components/admin/ClassTable'
import { SchoolYearForm } from '../components/admin/SchoolYearForm'
import { SchoolYearsPanel } from '../components/admin/SchoolYearsPanel'
import { PageTitle, Panel } from '../components/Panel'
import { QueryState } from '../components/QueryState'
import { useSchool, useTeachers } from '../hooks/useAdmin'

// Năm học và các lớp (Admin, D-113): nhiều năm học, một năm hiện hành; trang xem và sửa lớp của năm
// đang chọn ở thanh trên cùng. Phân công giảng dạy và danh sách học sinh của từng lớp nằm ở trang
// quản trị lớp. Chỉ hiện số đếm, không có tên học sinh.
export default function AdminSchoolPage() {
  const school = useSchool()
  const teachers = useTeachers()

  return (
    <AdminGate>
      {() => (
        <>
          <PageTitle
            title="Năm học & lớp"
            subtitle="Mỗi năm học có lớp, GVCN và phân công riêng. Mỗi giáo viên chủ nhiệm một lớp trong một năm; giáo viên bộ môn được gán ở trang quản trị của từng lớp."
          />
          <QueryState query={school}>
            {(data) => {
              const year = data.school_year
              return (
                <>
                  {data.years.length > 0 && (
                    <Panel id="cac-nam-hoc" title="Các năm học">
                      <SchoolYearsPanel years={data.years} />
                    </Panel>
                  )}
                  <Panel
                    id="nam-hoc"
                    title={year ? `Năm học ${year.name}` : 'Năm học'}
                    description={year ? 'Sửa tên và ngày của năm đang xem.' : undefined}
                  >
                    <SchoolYearForm key={year?.id ?? 'moi'} year={year} />
                  </Panel>
                  {year && (
                    <>
                      <Panel id="cac-lop" title={`Các lớp năm ${year.name}`}>
                        <QueryState query={teachers}>
                          {(teacherList) => (
                            <ClassTable
                              classes={data.classes}
                              teachers={teacherList}
                              subjectCount={data.subject_count}
                            />
                          )}
                        </QueryState>
                      </Panel>
                      <Panel id="them-lop" title={`Thêm lớp vào năm ${year.name}`}>
                        <QueryState query={teachers}>
                          {(teacherList) => <ClassForm teachers={teacherList} yearId={year.id} />}
                        </QueryState>
                      </Panel>
                    </>
                  )}
                </>
              )
            }}
          </QueryState>
        </>
      )}
    </AdminGate>
  )
}
