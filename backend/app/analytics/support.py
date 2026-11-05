"""Học sinh cần hỗ trợ trong MỘT môn và thống kê để điều chỉnh kế hoạch dạy học (D-118).

Hàm thuần: đầu vào là bảng điểm môn đã tính (`build_subject_scores`) và cấu hình từ `settings`;
không đọc DB, không ghi cứng ngưỡng. Chỉ dùng điểm của chính môn đó (giáo viên bộ môn không thấy
chuyên cần, rèn luyện hay môn khác, D-066), nên khác với cảnh báo sớm của GVCN (D-071).

Lý do và mức:
- `average_below_fail` (cao): ĐTB môn dưới ngưỡng quá thấp (3,5).
- `average_below_pass` (trung bình): ĐTB từ 3,5 đến dưới mức đạt (5,0).
- `comment_fail` (trung bình): môn nhận xét, kết quả Chưa đạt.
- `level_drop` (trung bình): xem học kỳ II, ĐTB rơi xuống khoảng điểm thấp hơn học kỳ I (các khoảng
  chia bởi bốn ngưỡng 3,5 / 5,0 / 6,5 / 8,0).
- `exam_below_pass` (thấp): ĐTB đạt nhưng điểm giữa kỳ hoặc cuối kỳ dưới mức đạt.
- `missing_scores` (thấp): thiếu đầu điểm mà phần lớn lớp đã có (so với chính lớp đó, để đầu học kỳ
  khi cả lớp chưa kiểm tra thì không ai bị đánh dấu).
"""

from collections.abc import Iterable
from decimal import Decimal

from app.analytics.config import AnalyticsConfig
from app.analytics.schemas import (
    ComponentStatOut,
    ScoreRowOut,
    StudentBriefOut,
    SubjectPlanStatsOut,
    SubjectScoresOut,
    SubjectSupportOut,
    SupportCountsOut,
    SupportLevel,
    SupportReasonOut,
    SupportStudentOut,
)
from app.analytics.scores import round_score
from app.core.enums import AssessmentType, CommentResult

LEVEL_ORDER: dict[SupportLevel, int] = {"high": 0, "medium": 1, "low": 2}
SEMESTER_LABELS = {1: "học kỳ I", 2: "học kỳ II"}


def score_vn(value: Decimal) -> str:
    """6.5 thành "6,5" để đặt trong câu lý do."""
    return f"{value:.1f}".replace(".", ",")


def _band(value: Decimal, config: AnalyticsConfig) -> int:
    """Khoảng điểm 0 (dưới 3,5) đến 4 (từ 8,0); dùng để biết ĐTB có tụt khoảng hay không."""
    thresholds = (
        config.score_threshold_fail,
        config.score_threshold_pass,
        config.score_threshold_fair,
        config.score_threshold_good,
    )
    return sum(1 for threshold in thresholds if value >= threshold)


def _mean(values: Iterable[Decimal]) -> Decimal | None:
    items = list(values)
    return round_score(sum(items, Decimal(0)) / len(items)) if items else None


class _ClassPresence:
    """Đầu điểm mà lớp đã có, để chỉ đánh dấu em thiếu khi các bạn đã có."""

    def __init__(self, rows: list[ScoreRowOut]) -> None:
        self.max_regular = max((len(r.tx) for r in rows), default=0)
        self.has_midterm = any(r.midterm is not None for r in rows)
        self.has_final = any(r.final is not None for r in rows)
        self.has_comment = any(r.comment_result is not None for r in rows)


def _average_reasons(
    row: ScoreRowOut, semester: int, config: AnalyticsConfig
) -> list[SupportReasonOut]:
    reasons: list[SupportReasonOut] = []
    label = SEMESTER_LABELS[semester]
    average = row.average
    if average is not None:
        note = "" if row.complete else " (tạm tính, còn thiếu đầu điểm)"
        if average < config.score_threshold_fail:
            reasons.append(
                SupportReasonOut(
                    code="average_below_fail",
                    level="high",
                    message=f"ĐTB môn {label} là {score_vn(average)}{note}, dưới "
                    f"{score_vn(config.score_threshold_fail)}.",
                )
            )
        elif average < config.score_threshold_pass:
            reasons.append(
                SupportReasonOut(
                    code="average_below_pass",
                    level="medium",
                    message=f"ĐTB môn {label} là {score_vn(average)}{note}, chưa tới mức đạt "
                    f"{score_vn(config.score_threshold_pass)}.",
                )
            )
    first = row.average_semester1
    if (
        semester == 2
        and average is not None
        and first is not None
        and _band(average, config) < _band(first, config)
    ):
        reasons.append(
            SupportReasonOut(
                code="level_drop",
                level="medium",
                message=f"ĐTB giảm từ {score_vn(first)} (học kỳ I) xuống {score_vn(average)} "
                "(học kỳ II), sang khoảng điểm thấp hơn.",
            )
        )
    if average is not None and average >= config.score_threshold_pass:
        low = [
            f"{name} {score_vn(value)}"
            for name, value in (("giữa kỳ", row.midterm), ("cuối kỳ", row.final))
            if value is not None and value < config.score_threshold_pass
        ]
        if low:
            reasons.append(
                SupportReasonOut(
                    code="exam_below_pass",
                    level="low",
                    message=f"ĐTB đạt nhưng điểm {' và '.join(low)} dưới "
                    f"{score_vn(config.score_threshold_pass)}.",
                )
            )
    return reasons


def _missing_reason(row: ScoreRowOut, presence: _ClassPresence) -> SupportReasonOut | None:
    parts: list[str] = []
    gap = presence.max_regular - len(row.tx)
    if gap > 0:
        parts.append(f"{gap} đầu điểm thường xuyên")
    if presence.has_midterm and row.midterm is None:
        parts.append("điểm giữa kỳ")
    if presence.has_final and row.final is None:
        parts.append("điểm cuối kỳ")
    if not parts:
        return None
    return SupportReasonOut(
        code="missing_scores",
        level="low",
        message=f"Còn thiếu {', '.join(parts)} mà các bạn trong lớp đã có "
        "(có thể cần kiểm tra bù).",
    )


def student_reasons(
    row: ScoreRowOut,
    *,
    semester: int,
    assessment_type: AssessmentType,
    presence: _ClassPresence,
    config: AnalyticsConfig,
) -> list[SupportReasonOut]:
    """Mọi lý do của một em trong môn, mức cao trước. Rỗng: em không cần hỗ trợ thêm."""
    reasons: list[SupportReasonOut] = []
    if assessment_type is AssessmentType.SCORE:
        reasons += _average_reasons(row, semester, config)
        missing = _missing_reason(row, presence)
        if missing is not None:
            reasons.append(missing)
    elif row.comment_result is CommentResult.FAIL:
        reasons.append(
            SupportReasonOut(
                code="comment_fail",
                level="medium",
                message=f"Kết quả môn {SEMESTER_LABELS[semester]}: Chưa đạt.",
            )
        )
    elif row.comment_result is None and presence.has_comment:
        reasons.append(
            SupportReasonOut(
                code="missing_scores",
                level="low",
                message="Chưa có kết quả đánh giá mà các bạn trong lớp đã có.",
            )
        )
    return sorted(reasons, key=lambda reason: LEVEL_ORDER[reason.level])


def _component(values: list[Decimal], config: AnalyticsConfig) -> ComponentStatOut:
    return ComponentStatOut(
        count=len(values),
        mean=_mean(values),
        below_pass=sum(1 for v in values if v < config.score_threshold_pass),
    )


def plan_stats(scores: SubjectScoresOut, config: AnalyticsConfig) -> SubjectPlanStatsOut:
    rows = scores.rows
    averages = [r.average for r in rows if r.average is not None]
    previous = (
        _mean(r.average_semester1 for r in rows if r.average_semester1 is not None)
        if scores.semester == 2
        else None
    )
    is_score = scores.subject.assessment_type is AssessmentType.SCORE
    return SubjectPlanStatsOut(
        regular=_component([score for r in rows for score in r.tx], config),
        midterm=_component([r.midterm for r in rows if r.midterm is not None], config),
        final=_component([r.final for r in rows if r.final is not None], config),
        support_group=sum(1 for a in averages if a < config.score_threshold_pass),
        advanced_group=sum(1 for a in averages if a >= config.score_threshold_good),
        previous_mean=previous if is_score else None,
        comment_pass=sum(1 for r in rows if r.comment_result is CommentResult.PASS),
        comment_fail=sum(1 for r in rows if r.comment_result is CommentResult.FAIL),
        comment_missing=0 if is_score else sum(1 for r in rows if r.comment_result is None),
    )


def build_support(scores: SubjectScoresOut, config: AnalyticsConfig) -> SubjectSupportOut:
    presence = _ClassPresence(scores.rows)
    students: list[SupportStudentOut] = []
    for row in scores.rows:
        reasons = student_reasons(
            row,
            semester=scores.semester,
            assessment_type=scores.subject.assessment_type,
            presence=presence,
            config=config,
        )
        if not reasons:
            continue
        students.append(
            SupportStudentOut(
                student_id=row.student_id,
                student_code=row.student_code,
                full_name=row.full_name,
                level=reasons[0].level,
                reasons=reasons,
                average=row.average,
                average_semester1=row.average_semester1,
                comment_result=row.comment_result,
            )
        )
    # Mức cao trước; cùng mức thì ĐTB thấp trước (môn nhận xét giữ thứ tự danh sách lớp).
    students.sort(
        key=lambda s: (
            LEVEL_ORDER[s.level],
            s.average if s.average is not None else Decimal(99),
        )
    )
    advanced = sorted(
        (
            StudentBriefOut(
                student_id=r.student_id,
                student_code=r.student_code,
                full_name=r.full_name,
                average=r.average,
            )
            for r in scores.rows
            if r.average is not None and r.average >= config.score_threshold_good
        ),
        key=lambda s: -(s.average or Decimal(0)),
    )
    return SubjectSupportOut(
        class_info=scores.class_info,
        subject=scores.subject,
        semester=scores.semester,
        thresholds=scores.thresholds,
        student_count=scores.student_count,
        mean=scores.mean,
        distribution=scores.distribution,
        counts=SupportCountsOut(
            high=sum(1 for s in students if s.level == "high"),
            medium=sum(1 for s in students if s.level == "medium"),
            low=sum(1 for s in students if s.level == "low"),
        ),
        students=students,
        advanced_students=advanced,
        stats=plan_stats(scores, config),
    )
