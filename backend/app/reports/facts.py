"""Số liệu đưa cho LLM khi viết nhận xét và báo cáo (D-103; nguyên tắc 1 và 5).

Mọi con số đến từ hàm Analytics có sẵn (`build_student_profile`, `build_dashboard`,
`build_grade_overview`); file này chỉ chọn trường, đổi nhãn tiếng Việt và gom lại, không tính công
thức nào. Đầu ra là dict thuần JSON và KHÔNG có họ tên, mã học sinh thật, ngày sinh, thông tin phụ
huynh, cảnh báo sớm hay điều kiện lên lớp: `generation.py` gắn mã tạm `HS_01`... vào từng em.

Nhận xét môn không có điểm trung bình lớp (tránh so sánh với bạn). Báo cáo lớp bỏ danh sách "học
sinh cần quan tâm" (có tên); báo cáo khối so sánh các lớp, đúng mục đích của nó.
"""

from typing import Any

from sqlalchemy.orm import Session

from app.analytics import repository as repo
from app.analytics import service as analytics
from app.analytics.config import AnalyticsConfig
from app.analytics.schemas import Period
from app.core.enums import AssessmentType, CommentResult, ConductLevel, ReportType
from app.core.labels import label_vi
from app.warning import repository as warning_repo
from app.warning import service as warning_service

PERIOD_LABELS = {"1": "học kỳ I", "2": "học kỳ II", "year": "cả năm"}
BEST_SUBJECTS = 2  # số môn nổi bật nêu ở phần điểm mạnh

_LEVEL_LABELS = {
    **{level.value: label_vi(level) for level in ConductLevel},
    "incomplete": "chưa đủ dữ liệu",
    "missing": "chưa có dữ liệu",
}


def _level(value: str | None) -> str | None:
    return None if value is None else _LEVEL_LABELS.get(value, value)


def _levels(counts: dict[str, int]) -> dict[str, int]:
    return {_LEVEL_LABELS.get(key, key): value for key, value in counts.items()}


def _comment(value: str | None) -> str | None:
    return None if value is None else label_vi(CommentResult(value))


def _subject_summary(subject: dict[str, Any], period: Period) -> dict[str, Any]:
    """Một môn trong kỳ đang xét: điểm trung bình (môn tính điểm) hoặc Đạt / Chưa đạt."""
    if period == "year":
        average, result = subject["year_average"], subject["year_comment_result"]
    else:
        semester = next((s for s in subject["semesters"] if s["semester"] == int(period)), None)
        average = None if semester is None else semester["average"]
        result = None if semester is None else semester["comment_result"]
    item: dict[str, Any] = {"name": subject["name"]}
    if subject["assessment_type"] == "score":
        item["average"] = average
    else:
        item["result"] = _comment(result)
    if average is None and result is None:
        item["note"] = "chưa đủ dữ liệu"
    return item


def _best_subjects(subjects: list[dict[str, Any]], excluded: list[str]) -> list[str]:
    """Hai môn có điểm trung bình cao nhất, bỏ những môn Analytics đã xếp là dưới mức đạt.

    Đây là cách chọn để trình bày, không phải công thức Thông tư: cùng điểm thì xếp theo tên.
    """
    scored = [
        (s["average"], s["name"])
        for s in subjects
        if s.get("average") is not None and s["name"] not in excluded
    ]
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [name for _average, name in scored[:BEST_SUBJECTS]]


def student_facts(
    session: Session,
    class_info: repo.ClassInfo,
    student_id: int,
    report_type: ReportType,
    period: Period,
    config: AnalyticsConfig,
    *,
    subject_id: int | None = None,
) -> dict[str, Any] | None:
    """Số liệu một học sinh; None nếu em không thuộc lớp (hoặc lớp không học môn đó)."""
    if report_type is ReportType.SUBJECT_COMMENT:
        return _subject_comment_facts(session, class_info, student_id, period, config, subject_id)

    profile = analytics.build_student_profile(
        session, class_info, student_id, period, config, subject_ids=None
    )
    if profile is None or profile.scope != "full":
        return None
    data = profile.model_dump(mode="json")
    subjects = [_subject_summary(s, period) for s in data["subjects"]]
    learning, attendance = data["learning"], data["attendance"]
    return {
        "period": PERIOD_LABELS[period],
        "learning_level": _level(learning["level"]),
        "conduct_level": _level(data["conduct"]["level"]),
        "subjects": subjects,
        "best_subjects": _best_subjects(subjects, learning["below_pass_subjects"]),
        "below_pass_subjects": learning["below_pass_subjects"],
        "below_very_low_subjects": learning["below_fail_subjects"],
        "failed_comment_subjects": learning["failed_comment_subjects"],
        "incomplete_subjects": learning["incomplete_subjects"],
        # Số buổi nghỉ tính từ đầu năm học đến nay (đi muộn không tính là nghỉ).
        "attendance_since_start_of_year": {
            "absent_excused": attendance["excused"],
            "absent_unexcused": attendance["unexcused"],
            "late": attendance["late"],
            "absent_total": attendance["absent_total"],
            "warning_from": attendance["limits"]["notice"],
            "maximum_allowed": attendance["limits"]["maximum"],
        },
    }


def _subject_comment_facts(
    session: Session,
    class_info: repo.ClassInfo,
    student_id: int,
    period: Period,
    config: AnalyticsConfig,
    subject_id: int | None,
) -> dict[str, Any] | None:
    if subject_id is None or period == "year":
        return None
    profile = analytics.build_student_profile(
        session, class_info, student_id, period, config, subject_ids=frozenset({subject_id})
    )
    if profile is None or not profile.subjects:
        return None
    subject = profile.subjects[0].model_dump(mode="json")
    semester = next((s for s in subject["semesters"] if s["semester"] == int(period)), None)
    if semester is None:
        return None
    facts: dict[str, Any] = {
        "period": PERIOD_LABELS[period],
        "subject": subject["name"],
        "kind": "môn tính điểm" if subject["assessment_type"] == "score" else "môn nhận xét",
        "complete": semester["complete"],
    }
    if subject["assessment_type"] == "score":
        facts.update(
            regular_scores=semester["tx"],
            regular_scores_missing=semester["tx_missing"],
            midterm=semester["midterm"],
            final=semester["final"],
            average=semester["average"],
        )
    else:
        facts["result"] = _comment(semester["comment_result"])
    return facts


def class_facts(
    session: Session, class_info: repo.ClassInfo, period: Period, config: AnalyticsConfig
) -> dict[str, Any]:
    """Số liệu cả lớp: không có tên hay mã học sinh nào."""
    counts = warning_service.counts_out(
        warning_repo.current_counts(session, class_id=class_info.id)
    )
    data = analytics.build_dashboard(
        session, class_info, period, config, alert_counts=counts
    ).model_dump(mode="json")
    subjects = []
    for stat in data["subjects"]:
        if stat["assessment_type"] == "score":
            subjects.append(
                {
                    "name": stat["name"],
                    "mean": stat["mean"],
                    "below_pass": stat["below_pass"],
                    "below_very_low": stat["below_fail"],
                    "incomplete": stat["incomplete"],
                }
            )
        else:
            subjects.append(
                {
                    "name": stat["name"],
                    "comment_fail": stat["comment_fail"],
                    "incomplete": stat["incomplete"],
                }
            )
    facts: dict[str, Any] = {
        "class": data["class_info"]["name"],
        "grade": data["class_info"]["grade_level"],
        "period": PERIOD_LABELS[period],
        "student_count": data["student_count"],
        "learning_levels": _levels(data["learning_levels"]),
        "conduct_levels": _levels(data["conduct_levels"]),
        "students_absent_from_warning_level": data["absent_notice_students"],
        "students_absent_over_maximum": data["absent_over_limit_students"],
        "subjects": subjects,
        "early_warning_counts": data["alert_counts"],
    }
    if data["promotion"] is not None:
        facts["promotion_counts"] = data["promotion"]
    return facts


def grade_facts(
    session: Session,
    grade_level: int,
    period: Period,
    config: AnalyticsConfig,
    *,
    school_year_id: int,
) -> dict[str, Any]:
    """So sánh các lớp trong một khối của một năm học (D-113)."""
    classes = repo.classes_in_grade(session, grade_level, school_year_id=school_year_id)
    data = analytics.build_grade_overview(session, grade_level, classes, period, config).model_dump(
        mode="json"
    )
    name_of = {c["class_id"]: c["name"] for c in data["classes"]}
    return {
        "grade": data["grade_level"],
        "period": PERIOD_LABELS[period],
        "classes": [
            {
                "class": c["name"],
                "student_count": c["student_count"],
                "learning_levels": _levels(c["learning_levels"]),
                "conduct_levels": _levels(c["conduct_levels"]),
                "students_absent_from_warning_level": c["absent_notice_students"],
                "students_absent_over_maximum": c["absent_over_limit_students"],
                "students_with_a_very_low_subject": c["below_fail_students"],
            }
            for c in data["classes"]
        ],
        # Mọi môn điểm số của khối (D-116); lớp không học môn đó thì không có trong danh sách.
        "subject_means": [
            {
                "subject": s["name"],
                "class_means": [
                    {"class": name_of[m["class_id"]], "mean": m["mean"]} for m in s["class_means"]
                ],
            }
            for s in data["subjects"]
            if s["assessment_type"] == "score"
        ],
        # Môn đánh giá bằng nhận xét: số học sinh Đạt / Chưa đạt theo lớp.
        "comment_subjects": [
            {
                "subject": s["name"],
                "class_means": [
                    {
                        "class": name_of[m["class_id"]],
                        "pass": m["comment_pass"],
                        "fail": m["comment_fail"],
                    }
                    for m in s["class_means"]
                ],
            }
            for s in data["subjects"]
            if s["assessment_type"] == "comment"
        ],
    }


# Lý do cần hỗ trợ trong một môn (analytics/support.py) diễn đạt cho LLM, không kèm số ngưỡng.
_SUPPORT_REASONS = {
    "average_below_fail": "ĐTB môn dưới ngưỡng quá thấp",
    "average_below_pass": "ĐTB môn chưa tới mức đạt",
    "comment_fail": "kết quả môn Chưa đạt",
    "level_drop": "ĐTB học kỳ II tụt khoảng điểm so với học kỳ I",
    "exam_below_pass": "ĐTB đạt nhưng bài giữa kỳ hoặc cuối kỳ dưới mức đạt",
    "missing_scores": "còn thiếu đầu điểm so với lớp",
}


def teaching_plan_facts(
    session: Session,
    class_info: repo.ClassInfo,
    subject_id: int,
    semester: int,
    config: AnalyticsConfig,
) -> dict[str, Any] | None:
    """Số liệu một lớp–môn để gợi ý điều chỉnh kế hoạch dạy học (D-118). Chỉ số đếm và trung bình
    của cả lớp, không có tên hay mã học sinh nào."""
    subject = next(
        (s for s in repo.class_subjects(session, class_info.id) if s.id == subject_id), None
    )
    if subject is None:
        return None
    data = analytics.build_subject_support(session, class_info, subject, semester, config)
    stats = data.stats
    reasons: dict[str, int] = {}
    for student in data.students:
        for code in dict.fromkeys(r.code for r in student.reasons):
            label = _SUPPORT_REASONS.get(code, code)
            reasons[label] = reasons.get(label, 0) + 1
    facts: dict[str, Any] = {
        "class": class_info.name,
        "grade": class_info.grade_level,
        "subject": subject.name,
        "period": PERIOD_LABELS[str(semester)],
        "student_count": data.student_count,
        "students_needing_support": data.counts.model_dump(),
        "students_by_reason": reasons,
    }
    if subject.assessment_type is AssessmentType.SCORE:
        dist = data.distribution
        facts |= {
            "class_mean": data.mean,
            # Ngưỡng lấy từ settings (qua Analytics), để LLM nêu đúng số khi nhắc tới.
            "thresholds": {
                "very_low": data.thresholds.fail,
                "pass": data.thresholds.passing,
                "fair": data.thresholds.fair,
                "good": data.thresholds.good,
            },
            "students_by_score_band": {
                "below_very_low": dist.below_fail,
                "very_low_to_below_pass": dist.fail_to_pass,
                "pass_to_below_fair": dist.pass_to_fair,
                "fair_to_below_good": dist.fair_to_good,
                "from_good": dist.at_least_good,
            },
            "assessments": {
                name: {"count": c.count, "mean": c.mean, "below_pass": c.below_pass}
                for name, c in (
                    ("regular", stats.regular),
                    ("midterm", stats.midterm),
                    ("final", stats.final),
                )
            },
            "group_below_pass": stats.support_group,
            "group_from_good": stats.advanced_group,
        }
        if stats.previous_mean is not None:
            facts["class_mean_semester_1"] = stats.previous_mean
    else:
        facts["comment_results"] = {
            "pass": stats.comment_pass,
            "fail": stats.comment_fail,
            "not_yet_assessed": stats.comment_missing,
        }
    return facts
