"""Nạp bộ `diem-30-lop/` vào DB đang chạy, qua đúng API của hệ thống (kiểm tra, quyền, nhật ký).

Chỉ dữ liệu giả lập (nguyên tắc 7). Các bước:
1. Năm học 2026-2027 (tạo nếu chưa có, đặt làm năm hiện hành).
2. 30 lớp 10A1…12A10 trong năm đó, GVCN theo kế hoạch của `12-lop.xlsx` (`build_12_lop.build_plan`).
3. Nhập danh sách học sinh từng lớp (Admin).
4. Phân công giáo viên bộ môn theo cùng kế hoạch. Giáo viên trong kế hoạch bị khoá hoặc không có
   thì thay bằng giáo viên đang hoạt động cùng môn, ít lớp nhất.
5. Mỗi tệp điểm: giáo viên được phân công xem trước rồi xác nhận. Có dòng lỗi thì dừng.

Cần các tài khoản giáo viên của `12-lop.xlsx` (@thpt-demo.local) đã được nhập. Chạy lại được: lớp
đã có học sinh thì bỏ qua bước nhập danh sách; điểm trùng thì chỉ ghi đè bằng cùng giá trị.

Chạy trong container backend (cần data/samples đã chép vào /data/samples):
    PYTHONPATH=/app:/ python /data/samples/load_diem_30_lop.py
"""

import re
import sys
from collections import Counter
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.models import User
from app.auth.tokens import create_access_token
from app.classes.models import ClassStudent, SchoolClass, SchoolYear, Subject
from app.core.db import get_engine
from app.core.enums import UserRole
from app.main import app
from data.samples.build_12_lop import build_plan
from data.samples.build_diem_30_lop import (
    CLASSES_PER_GRADE,
    GRADES,
    OUTPUT,
    YEAR_NAME,
    class_subjects,
    slug,
)

API = "/api/v1"
ADMIN_EMAIL = "admin@example.com"
YEAR = {"name": YEAR_NAME, "start_date": "2026-09-05", "end_date": "2027-05-31"}


def headers(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id)[0]}"}


def check(response: Any, what: str) -> Any:
    if response.status_code >= 400:
        raise SystemExit(f"Lỗi khi {what}: {response.status_code} {response.text[:500]}")
    return response.json()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    client = TestClient(app)
    engine = get_engine()
    with Session(engine) as session:
        users = {u.email.lower(): u for u in session.scalars(select(User))}
        subjects = {slug(s.name): s for s in session.scalars(select(Subject))}
        year = session.scalar(select(SchoolYear).where(SchoolYear.name == YEAR_NAME))
    admin = users[ADMIN_EMAIL]
    admin_headers = headers(admin.id)

    # 1. Năm học.
    if year is None:
        created = check(
            client.post(
                f"{API}/admin/school-years",
                headers=admin_headers,
                json={**YEAR, "make_current": True},
            ),
            "tạo năm học",
        )
        year_id = created["school_year"]["id"]
        print(f"Đã tạo năm học {YEAR_NAME} (năm hiện hành).")
    else:
        year_id = year.id
        if not year.is_current:
            check(
                client.post(f"{API}/admin/school-years/{year_id}/current", headers=admin_headers),
                "đặt năm hiện hành",
            )
        print(f"Dùng năm học {YEAR_NAME} có sẵn.")

    _, plan, homerooms = build_plan()
    load: Counter[int] = Counter()  # số lớp–môn đã giao cho mỗi giáo viên (để chọn người thay)
    replaced: list[str] = []

    def teacher_for(class_name: str, subject_name: str) -> User:
        planned = users.get(plan[(class_name, subject_name)].email.lower())
        if planned is not None and planned.is_active and planned.role is UserRole.TEACHER:
            return planned
        subject_id = subjects[slug(subject_name)].id
        pool = [
            u
            for u in users.values()
            if u.is_active and u.role is UserRole.TEACHER and u.specialty_subject_id == subject_id
        ]
        if not pool:
            raise SystemExit(f"Không có giáo viên {subject_name} nào đang hoạt động.")
        chosen = min(pool, key=lambda u: (load[u.id], u.email))
        replaced.append(f"{class_name} {subject_name}: {chosen.email}")
        return chosen

    files = 0
    for grade in GRADES:
        for index in range(1, CLASSES_PER_GRADE + 1):
            name = f"{grade}A{index}"
            with Session(engine) as session:
                school_class = session.scalar(
                    select(SchoolClass).where(
                        SchoolClass.school_year_id == year_id, SchoolClass.name == name
                    )
                )
                members = (
                    session.scalar(
                        select(func.count())
                        .select_from(ClassStudent)
                        .where(ClassStudent.class_id == school_class.id)
                    )
                    if school_class
                    else 0
                )

            # 2. Lớp và GVCN.
            if school_class is None:
                homeroom = users.get(homerooms[name].email.lower())
                body: dict[str, Any] = {
                    "grade_level": grade,
                    "name": name,
                    "school_year_id": year_id,
                }
                if homeroom is not None and homeroom.is_active:
                    body["homeroom_teacher_id"] = homeroom.id
                class_id = check(
                    client.post(f"{API}/admin/classes", headers=admin_headers, json=body),
                    f"tạo lớp {name}",
                )["id"]
            else:
                class_id = school_class.id

            # 3. Danh sách học sinh.
            if not members:
                roster = OUTPUT / "danh-sach-hoc-sinh" / f"{name}.xlsx"
                preview = check(
                    client.post(
                        f"{API}/classes/{class_id}/import/roster",
                        headers=admin_headers,
                        files={
                            "file": (roster.name, roster.read_bytes(), "application/octet-stream")
                        },
                    ),
                    f"xem trước danh sách {name}",
                )
                if preview["summary"]["error_rows"]:
                    raise SystemExit(f"Danh sách {name} có dòng lỗi.")
                check(
                    client.post(
                        f"{API}/imports/{preview['job_id']}/confirm", headers=admin_headers
                    ),
                    f"nhập danh sách {name}",
                )

            # 4–5. Phân công và điểm.
            for subject in class_subjects(index):
                teacher = teacher_for(name, subject.name)
                load[teacher.id] += 1
                subject_id = subjects[slug(subject.name)].id
                check(
                    client.put(
                        f"{API}/admin/classes/{class_id}/assignments/{subject_id}",
                        headers=admin_headers,
                        json={"teacher_id": teacher.id},
                    ),
                    f"phân công {name} {subject.name}",
                )
                teacher_headers = headers(teacher.id)
                for semester in (1, 2):
                    path = OUTPUT / "diem" / name / f"{slug(subject.name)}-hk{semester}.xlsx"
                    assert re.fullmatch(r".+-hk[12]", path.stem)
                    preview = check(
                        client.post(
                            f"{API}/classes/{class_id}/import/assessments",
                            headers=teacher_headers,
                            files={
                                "file": (path.name, path.read_bytes(), "application/octet-stream")
                            },
                            data={"subject_id": str(subject_id), "semester": str(semester)},
                        ),
                        f"xem trước {path.name} lớp {name}",
                    )
                    if preview["summary"]["error_rows"]:
                        raise SystemExit(f"{name}/{path.name} có dòng lỗi.")
                    check(
                        client.post(
                            f"{API}/imports/{preview['job_id']}/confirm", headers=teacher_headers
                        ),
                        f"nhập {path.name} lớp {name}",
                    )
                    files += 1
            print(f"{name}: xong ({files} tệp điểm tới giờ).", flush=True)

    print(f"Hoàn tất: 30 lớp, {files} tệp điểm.")
    if replaced:
        print("Giáo viên thay cho người trong kế hoạch bị khoá hoặc không có:")
        for line in replaced:
            print(f"  - {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
