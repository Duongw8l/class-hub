"""Schema phản hồi của ba endpoint Analytics.

Điểm là Decimal trong code; khi ra JSON là số thập phân (một chữ số), hiển thị dấu phẩy là việc của
giao diện. Giao diện không được tự tính lại mức hay ngưỡng: chỉ hiển thị những gì máy chủ trả.
"""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, PlainSerializer

from app.core.enums import AssessmentType, CommentResult
from app.warning.schemas import AlertCountsOut, ProfileAlertOut

Score = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]

# Kỳ xem: học kỳ I, học kỳ II hoặc cả năm.
Period = Literal["1", "2", "year"]


class ClassRefOut(BaseModel):
    id: int
    name: str
    grade_level: int


class SubjectStatOut(BaseModel):
    """Thống kê một môn của lớp (số mô tả để hiển thị, không phải số của Thông tư)."""

    subject_id: int
    name: str
    assessment_type: AssessmentType
    student_count: int  # số học sinh đã có điểm trung bình
    mean: Score | None  # trung bình lớp, làm tròn 1 chữ số
    below_pass: int  # số học sinh có ĐTB dưới ngưỡng đạt (5,0)
    below_fail: int  # số học sinh có ĐTB dưới 3,5
    comment_fail: int  # môn nhận xét: số học sinh Chưa đạt
    incomplete: int  # số học sinh chưa đủ dữ liệu


class AttentionOut(BaseModel):
    student_id: int
    student_code: str
    full_name: str
    absent_sessions: int  # số buổi nghỉ cả năm học
    # absent_over_limit, absent_notice, subject_below_fail, level_fail
    reasons: list[str]


class PromotionCountsOut(BaseModel):
    eligible: int
    not_eligible: int
    unknown: int


class MonthAbsenceOut(BaseModel):
    """Số buổi nghỉ trong một tháng (đi muộn không tính là nghỉ, D-028)."""

    month: str  # YYYY-MM
    excused: int
    unexcused: int
    total: int


class AbsenceLimitsOut(BaseModel):
    """Ngưỡng nghỉ lấy từ bảng settings, để giao diện vẽ vạch mà không ghi cứng số."""

    notice: int  # từ mức này bắt đầu nhắc (30)
    maximum: int  # nghỉ quá mức này thì không đủ điều kiện lên lớp (45)


class ThresholdsOut(BaseModel):
    """Ngưỡng điểm lấy từ bảng settings, để giao diện ghi chú đúng mà không ghi cứng số."""

    fail: Score  # dưới mức này là quá thấp (3,5)
    passing: Score  # mức đạt (5,0)
    fair: Score  # 6,5
    good: Score  # 8,0


class DashboardOut(BaseModel):
    class_info: ClassRefOut
    period: Period
    student_count: int
    # good, fair, pass, fail, incomplete (chưa đủ dữ liệu)
    learning_levels: dict[str, int]
    # good, fair, pass, fail, missing (chưa có dữ liệu)
    conduct_levels: dict[str, int]
    conduct_derived_count: int  # cả năm: số học sinh có rèn luyện được suy ra từ học kỳ II
    absent_notice_students: int  # nghỉ từ ngưỡng nhắc (30) buổi trong cả năm học
    absent_over_limit_students: int  # nghỉ quá số buổi tối đa (45)
    subjects: list[SubjectStatOut]
    attention: list[AttentionOut]
    promotion: PromotionCountsOut | None  # chỉ khi xem cả năm
    # Tổng số buổi nghỉ của cả lớp theo từng tháng của năm học (tháng không ai nghỉ ghi 0).
    absences_by_month: list[MonthAbsenceOut]
    absence_limits: AbsenceLimitsOut
    thresholds: ThresholdsOut
    # Số cảnh báo sớm hiện hành của lớp theo mức (Giai đoạn 6); luôn đủ ba khoá.
    alert_counts: AlertCountsOut


# --- Hồ sơ học sinh -----------------------------------------------------------------------------
# Hai schema riêng, không kế thừa nhau (D-044, D-066): GVBM nhận hồ sơ chỉ có các môn mình dạy,
# không có khoá chuyên cần, rèn luyện, phụ huynh, chứ không phải các khoá rỗng.


class ProfileStudentOut(BaseModel):
    id: int
    student_code: str
    full_name: str


class ProfileSemesterOut(BaseModel):
    semester: int
    tx: list[Score]  # các đầu điểm thường xuyên đã có
    tx_missing: int
    midterm: Score | None
    final: Score | None
    average: Score | None  # ĐTBmhk (tạm tính nếu complete = false); môn nhận xét: None
    comment_result: CommentResult | None
    complete: bool


class ProfileSubjectOut(BaseModel):
    subject_id: int
    name: str
    assessment_type: AssessmentType
    periods_per_year: int
    regular_required: int
    semesters: list[ProfileSemesterOut]  # học kỳ I rồi học kỳ II
    year_average: Score | None  # ĐTBmcn, khi đủ hai học kỳ
    year_comment_result: CommentResult | None  # môn nhận xét: kết quả cả năm (lấy theo học kỳ II)


class ProfileLearningOut(BaseModel):
    level: str | None  # good, fair, pass, fail; None: chưa đủ dữ liệu
    base_level: str | None  # mức trước khi điều chỉnh
    adjusted: bool
    incomplete_subjects: list[str]  # tên môn
    below_fail_subjects: list[str]  # môn điểm số dưới 3,5
    below_pass_subjects: list[str]  # môn điểm số dưới 5,0
    failed_comment_subjects: list[str]  # môn nhận xét Chưa đạt


class ProfileConductOut(BaseModel):
    level: str | None
    derived: bool  # cả năm được suy ra từ học kỳ II


class ProfileAttendanceOut(BaseModel):
    excused: int
    unexcused: int
    late: int
    absent_total: int  # nghỉ có phép + không phép, cả năm học
    school_duty: int  # vắng do nhà trường cử đi, không tính buổi nghỉ (D-120)
    limits: AbsenceLimitsOut
    by_month: list[MonthAbsenceOut]


class RetakeSubjectOut(BaseModel):
    subject_id: int
    name: str
    reason: str


class ProfilePromotionOut(BaseModel):
    eligible: bool | None  # None: chưa đủ dữ liệu để kết luận
    reasons: list[str]
    retake_subjects: list[RetakeSubjectOut]


class StudentProfileFullOut(BaseModel):
    """Hồ sơ đầy đủ cho GVCN của lớp và BGH."""

    scope: Literal["full"] = "full"
    class_info: ClassRefOut
    period: Period
    student: ProfileStudentOut
    guardian_name: str | None
    guardian_phone: str | None
    subjects: list[ProfileSubjectOut]
    learning: ProfileLearningOut
    conduct: ProfileConductOut
    attendance: ProfileAttendanceOut
    promotion: ProfilePromotionOut | None  # chỉ khi xem cả năm
    attention_reasons: list[str]  # cùng quy tắc với dashboard lớp
    thresholds: ThresholdsOut
    alert: ProfileAlertOut | None  # cảnh báo sớm hiện hành (None: chưa chạy cảnh báo)


class StudentProfileSubjectsOut(BaseModel):
    """Hồ sơ cho GVBM: chỉ các môn mình dạy ở lớp đó."""

    scope: Literal["subjects"] = "subjects"
    class_info: ClassRefOut
    student: ProfileStudentOut
    subjects: list[ProfileSubjectOut]
    thresholds: ThresholdsOut


# --- Bảng điểm một môn ------------------------------------------------------------------------


class SubjectOut(BaseModel):
    id: int
    name: str
    assessment_type: AssessmentType
    periods_per_year: int
    regular_required: int  # số đầu điểm thường xuyên mỗi học kỳ theo số tiết


class ScoreRowOut(BaseModel):
    student_id: int
    student_code: str
    full_name: str
    tx: list[Score]  # các đầu điểm thường xuyên đã có, theo thứ tự
    tx_missing: int  # số đầu điểm thường xuyên còn thiếu
    midterm: Score | None
    final: Score | None
    average: Score | None  # ĐTBmhk của học kỳ đang xem (tạm tính nếu complete = false)
    comment_result: CommentResult | None  # môn nhận xét
    complete: bool
    average_semester1: Score | None
    average_semester2: Score | None
    year_average: Score | None  # ĐTBmcn, khi đủ hai học kỳ


class DistributionOut(BaseModel):
    below_fail: int  # dưới 3,5
    fail_to_pass: int  # từ 3,5 đến dưới 5,0
    pass_to_fair: int  # từ 5,0 đến dưới 6,5
    fair_to_good: int  # từ 6,5 đến dưới 8,0
    at_least_good: int  # từ 8,0


class SubjectScoresOut(BaseModel):
    class_info: ClassRefOut
    subject: SubjectOut
    semester: int  # 1 hoặc 2
    thresholds: ThresholdsOut
    student_count: int
    mean: Score | None
    distribution: DistributionOut
    incomplete_count: int
    comment_fail_count: int
    rows: list[ScoreRowOut]


# --- Tổng quan khối -----------------------------------------------------------------------------


class ClassOverviewOut(BaseModel):
    class_id: int
    name: str
    student_count: int
    learning_levels: dict[str, int]
    conduct_levels: dict[str, int]
    absent_notice_students: int
    absent_over_limit_students: int
    below_fail_students: int  # số học sinh có ít nhất một môn dưới 3,5
    promotion: PromotionCountsOut | None = None  # chỉ khi xem cả năm


class ClassMeanOut(BaseModel):
    """Kết quả một môn của một lớp: ĐTB lớp (môn điểm số) hoặc số Đạt / Chưa đạt (môn nhận xét)."""

    class_id: int
    mean: Score | None  # môn điểm số; None với môn nhận xét hoặc chưa có điểm
    comment_pass: int  # môn nhận xét: số học sinh Đạt
    comment_fail: int  # môn nhận xét: số học sinh Chưa đạt


class GradeSubjectOut(BaseModel):
    """Một môn của khối (D-116): mọi môn có ít nhất một lớp học, kể cả môn lựa chọn và môn nhận
    xét. `class_means` chỉ có các lớp học môn đó."""

    subject_id: int
    name: str
    assessment_type: AssessmentType
    class_count: int  # số lớp trong khối học môn này
    class_means: list[ClassMeanOut]


class GradeOverviewOut(BaseModel):
    grade_level: int
    period: Period
    classes: list[ClassOverviewOut]
    subjects: list[GradeSubjectOut]  # môn điểm số trước, rồi môn nhận xét


# --- Học sinh cần hỗ trợ trong một môn (GVBM, D-118) --------------------------------------------

SupportLevel = Literal["high", "medium", "low"]


class SupportReasonOut(BaseModel):
    """Một lý do, chỉ từ điểm của chính môn đó. `message` đã có số liệu, viết sẵn tiếng Việt."""

    # average_below_fail, average_below_pass, comment_fail, level_drop, exam_below_pass,
    # missing_scores
    code: str
    level: SupportLevel
    message: str


class SupportStudentOut(BaseModel):
    student_id: int
    student_code: str
    full_name: str
    level: SupportLevel  # mức cao nhất trong các lý do
    reasons: list[SupportReasonOut]  # mức cao trước
    average: Score | None  # ĐTBmhk của học kỳ đang xem (môn điểm số)
    average_semester1: Score | None  # để so khi xem học kỳ II
    comment_result: CommentResult | None  # môn nhận xét


class StudentBriefOut(BaseModel):
    student_id: int
    student_code: str
    full_name: str
    average: Score | None


class SupportCountsOut(BaseModel):
    high: int
    medium: int
    low: int


class ComponentStatOut(BaseModel):
    """Một loại đầu điểm của cả lớp trong học kỳ (số mô tả để lên kế hoạch dạy học)."""

    count: int  # số điểm đã có (thường xuyên: số bài; giữa kỳ, cuối kỳ: số học sinh)
    mean: Score | None
    below_pass: int  # số điểm dưới mức đạt


class SubjectPlanStatsOut(BaseModel):
    """Thống kê giúp điều chỉnh kế hoạch dạy học của một lớp–môn trong một học kỳ."""

    regular: ComponentStatOut  # điểm thường xuyên
    midterm: ComponentStatOut
    final: ComponentStatOut
    support_group: int  # ĐTB dưới mức đạt: nhóm cần phụ đạo
    advanced_group: int  # ĐTB từ mức Tốt: nhóm có thể bồi dưỡng
    previous_mean: Score | None  # ĐTB lớp học kỳ I khi đang xem học kỳ II
    comment_pass: int
    comment_fail: int
    comment_missing: int


class SubjectSupportOut(BaseModel):
    class_info: ClassRefOut
    subject: SubjectOut
    semester: int
    thresholds: ThresholdsOut
    student_count: int
    mean: Score | None
    distribution: DistributionOut
    counts: SupportCountsOut
    students: list[SupportStudentOut]  # chỉ em có ít nhất một lý do; mức cao trước
    advanced_students: list[StudentBriefOut]  # ĐTB từ mức Tốt, cao trước
    stats: SubjectPlanStatsOut


class MySupportOut(BaseModel):
    """Mọi lớp–môn mà giáo viên đang dạy trong một năm học."""

    school_year_id: int | None
    items: list[SubjectSupportOut]
