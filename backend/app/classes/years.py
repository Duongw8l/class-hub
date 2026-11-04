"""Năm học đang xem (D-113). Mọi truy vấn "mọi lớp" (trang chủ, so sánh khối, cảnh báo toàn trường,
báo cáo khối, phạm vi trợ lý AI) lọc theo một năm học lấy từ đây.

`school_year_id` do giao diện gửi (ô chọn năm trên thanh trên cùng), không bao giờ do LLM điền.
Không gửi thì dùng năm hiện hành. Năm học không phải dữ liệu nhạy cảm: ai đăng nhập cũng xem được
danh sách năm; quyền xem lớp nào vẫn do authorize() quyết định theo lớp.
"""

from typing import Annotated

from fastapi import Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.classes.models import SchoolClass, SchoolYear

NOT_FOUND_MESSAGE = "Không có năm học này."

# Tham số truy vấn dùng chung của mọi endpoint xem theo năm học.
SchoolYearQuery = Annotated[
    int | None, Query(description="Năm học cần xem; bỏ trống là năm hiện hành")
]


class SchoolYearNotFound(Exception):
    """Không có năm học này, hoặc trường chưa có năm học nào."""


def school_year_not_found_handler(_request: Request, _exc: Exception) -> JSONResponse:
    """Đăng ký trong app/main.py: SchoolYearNotFound thành HTTP 404."""
    return JSONResponse(status_code=404, content={"detail": NOT_FOUND_MESSAGE})


def current_year(session: Session) -> SchoolYear | None:
    return session.scalar(select(SchoolYear).where(SchoolYear.is_current.is_(True)))


def resolve_year(session: Session, school_year_id: int | None) -> SchoolYear:
    """Năm được yêu cầu, hoặc năm hiện hành khi không gửi. Ném SchoolYearNotFound nếu không có."""
    year = (
        current_year(session) if school_year_id is None else session.get(SchoolYear, school_year_id)
    )
    if year is None:
        raise SchoolYearNotFound
    return year


def resolve_year_id(session: Session, school_year_id: int | None) -> int | None:
    """Như resolve_year nhưng trả None (không ném) khi trường chưa có năm học nào.

    Dùng cho các danh sách: chưa có năm học thì danh sách rỗng chứ không phải lỗi.
    """
    if school_year_id is not None:
        if session.get(SchoolYear, school_year_id) is None:
            raise SchoolYearNotFound
        return school_year_id
    year = current_year(session)
    return None if year is None else year.id


def year_of_class(session: Session, class_id: int) -> int | None:
    return session.scalar(select(SchoolClass.school_year_id).where(SchoolClass.id == class_id))


def list_years(session: Session) -> list[SchoolYear]:
    """Mọi năm học, mới nhất trước."""
    return list(
        session.scalars(select(SchoolYear).order_by(SchoolYear.start_date.desc(), SchoolYear.id))
    )
