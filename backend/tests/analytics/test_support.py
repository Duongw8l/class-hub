"""Học sinh cần hỗ trợ trong một môn (D-118): hàm thuần, số liệu tính tay.

Ngưỡng mặc định của settings: 3,5 / 5,0 / 6,5 / 8,0.
"""

from decimal import Decimal

from app.analytics.config import AnalyticsConfig
from app.analytics.schemas import (
    ClassRefOut,
    DistributionOut,
    ScoreRowOut,
    SubjectOut,
    SubjectScoresOut,
    ThresholdsOut,
)
from app.analytics.support import build_support
from app.core.enums import AssessmentType, CommentResult

D = Decimal


def row(
    student_id: int,
    *,
    tx: list[str] = (),  # type: ignore[assignment]
    midterm: str | None = None,
    final: str | None = None,
    average: str | None = None,
    first: str | None = None,
    complete: bool = True,
    comment: CommentResult | None = None,
) -> ScoreRowOut:
    return ScoreRowOut(
        student_id=student_id,
        student_code=f"HS{student_id:03d}",
        full_name=f"Học sinh {student_id}",
        tx=[D(v) for v in tx],
        tx_missing=0,
        midterm=None if midterm is None else D(midterm),
        final=None if final is None else D(final),
        average=None if average is None else D(average),
        comment_result=comment,
        complete=complete,
        average_semester1=None if first is None else D(first),
        average_semester2=None,
        year_average=None,
    )


def scores(
    rows: list[ScoreRowOut],
    *,
    semester: int = 1,
    kind: AssessmentType = AssessmentType.SCORE,
) -> SubjectScoresOut:
    return SubjectScoresOut(
        class_info=ClassRefOut(id=1, name="11A2", grade_level=11),
        subject=SubjectOut(
            id=1, name="Toán", assessment_type=kind, periods_per_year=105, regular_required=4
        ),
        semester=semester,
        thresholds=ThresholdsOut(fail=D("3.5"), passing=D("5"), fair=D("6.5"), good=D("8")),
        student_count=len(rows),
        mean=None,
        distribution=DistributionOut(
            below_fail=0, fail_to_pass=0, pass_to_fair=0, fair_to_good=0, at_least_good=0
        ),
        incomplete_count=0,
        comment_fail_count=0,
        rows=rows,
    )


def codes(result: object, student_id: int) -> list[str]:
    student = next(s for s in result.students if s.student_id == student_id)  # type: ignore[attr-defined]
    return [r.code for r in student.reasons]


def test_average_bands_give_high_and_medium(config: AnalyticsConfig) -> None:
    result = build_support(
        scores(
            [
                row(1, tx=["3", "3"], midterm="3", final="3", average="3.0"),
                row(2, tx=["5", "4"], midterm="4", final="5", average="4.6"),
                row(3, tx=["5", "5"], midterm="5", final="5", average="5.0"),  # đúng mức đạt
            ]
        ),
        config,
    )

    assert codes(result, 1) == ["average_below_fail"]
    assert codes(result, 2) == ["average_below_pass"]
    assert [s.student_id for s in result.students] == [1, 2]  # em 3 không cần hỗ trợ
    assert result.students[0].level == "high" and result.students[1].level == "medium"
    assert result.counts.model_dump() == {"high": 1, "medium": 1, "low": 0}
    assert result.students[0].reasons[0].message == "ĐTB môn học kỳ I là 3,0, dưới 3,5."


def test_level_drop_only_in_semester_two_and_only_across_a_threshold(
    config: AnalyticsConfig,
) -> None:
    rows = [
        row(1, tx=["7"], midterm="6", final="6", average="6.3", first="6.7"),  # 6,7 → 6,3: qua 6,5
        row(2, tx=["7"], midterm="7", final="7", average="7.0", first="7.9"),  # cùng khoảng
    ]
    second = build_support(scores(rows, semester=2), config)
    first = build_support(scores(rows, semester=1), config)

    assert codes(second, 1) == ["level_drop"]
    assert second.students[0].reasons[0].message == (
        "ĐTB giảm từ 6,7 (học kỳ I) xuống 6,3 (học kỳ II), sang khoảng điểm thấp hơn."
    )
    assert [s.student_id for s in second.students] == [1]
    assert first.students == []


def test_exam_below_pass_when_the_average_still_passes(config: AnalyticsConfig) -> None:
    result = build_support(
        scores([row(1, tx=["8", "8"], midterm="4.5", final="7", average="6.6")]), config
    )
    [student] = result.students
    assert student.level == "low"
    assert student.reasons[0].message == "ĐTB đạt nhưng điểm giữa kỳ 4,5 dưới 5,0."


def test_missing_scores_compare_with_the_class_not_with_the_full_requirement(
    config: AnalyticsConfig,
) -> None:
    rows = [
        row(1, tx=["7", "7", "7"], midterm="7", average="7.0"),
        row(2, tx=["7"], average="7.0", complete=False),  # thiếu 2 TX và giữa kỳ so với lớp
    ]
    result = build_support(scores(rows), config)

    # Chưa ai có điểm cuối kỳ nên không ai bị đánh dấu thiếu cuối kỳ.
    assert codes(result, 2) == ["missing_scores"]
    assert result.students[0].reasons[0].message == (
        "Còn thiếu 2 đầu điểm thường xuyên, điểm giữa kỳ mà các bạn trong lớp đã có "
        "(có thể cần kiểm tra bù)."
    )
    assert [s.student_id for s in result.students] == [2]


def test_comment_subject_uses_the_comment_result(config: AnalyticsConfig) -> None:
    rows = [
        row(1, comment=CommentResult.PASS),
        row(2, comment=CommentResult.FAIL),
        row(3),
    ]
    result = build_support(scores(rows, kind=AssessmentType.COMMENT), config)

    assert codes(result, 2) == ["comment_fail"] and codes(result, 3) == ["missing_scores"]
    assert result.stats.comment_pass == 1 and result.stats.comment_fail == 1
    assert result.stats.comment_missing == 1


def test_plan_stats_by_assessment_and_groups(config: AnalyticsConfig) -> None:
    rows = [
        row(1, tx=["4", "6"], midterm="4", final="5", average="4.8", first="5.5"),
        row(2, tx=["8", "9"], midterm="8", final="9", average="8.6", first="8.0"),
        row(3, tx=["7"], midterm="6", average="6.5", first="7.0"),
    ]
    result = build_support(scores(rows, semester=2), config)
    stats = result.stats

    # TX: 4, 6, 8, 9, 7 → 34/5 = 6,8; một điểm dưới 5,0.
    assert (stats.regular.count, stats.regular.mean, stats.regular.below_pass) == (5, D("6.8"), 1)
    # Giữa kỳ: 4, 8, 6 → 6,0; cuối kỳ: 5, 9 → 7,0.
    assert (stats.midterm.count, stats.midterm.mean, stats.midterm.below_pass) == (3, D("6.0"), 1)
    assert (stats.final.count, stats.final.mean, stats.final.below_pass) == (2, D("7.0"), 0)
    assert stats.support_group == 1 and stats.advanced_group == 1
    # ĐTB lớp học kỳ I: (5,5 + 8,0 + 7,0) / 3 = 6,83… → 6,8.
    assert stats.previous_mean == D("6.8")
    assert [s.student_id for s in result.advanced_students] == [2]


def test_students_are_sorted_by_level_then_lowest_average(config: AnalyticsConfig) -> None:
    rows = [
        row(1, tx=["4"], midterm="4", final="5", average="4.9"),
        row(2, tx=["3"], midterm="3", final="3", average="3.2"),
        row(3, tx=["4"], midterm="4", final="4", average="4.0"),
    ]
    result = build_support(scores(rows), config)
    assert [s.student_id for s in result.students] == [2, 3, 1]
