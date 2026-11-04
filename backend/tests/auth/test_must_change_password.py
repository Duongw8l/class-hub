"""Bắt đổi mật khẩu sau khi đăng nhập bằng mật khẩu tạm (D-114)."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.models import User
from data.seed.people import DEV_PASSWORD

pytestmark = pytest.mark.db

API = "/api/v1"
ADMIN = "admin@example.com"
TEACHER = "gv.van.11@example.com"
NEW_PASSWORD = "Mat-khau-rieng-2026"
Headers = Callable[[str], dict[str, str]]

# Mỗi vai trò có ít nhất một endpoint bị chặn khi còn mật khẩu tạm.
BLOCKED = [
    ("GET", f"{API}/me/assignments"),
    ("GET", f"{API}/school-years"),
    ("GET", f"{API}/alerts"),
    ("GET", f"{API}/admin/users"),
]


def user_of(session: Session, email: str) -> User:
    user = session.scalar(select(User).where(func.lower(User.email) == email.lower()))
    assert user is not None
    return user


def login(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def reset(client: TestClient, admin: dict[str, str], user_id: int) -> str:
    response = client.post(f"{API}/admin/users/{user_id}/reset-password", headers=admin)
    assert response.status_code == 200
    password: str = response.json()["temporary_password"]
    return password


def test_seeded_accounts_are_not_flagged(api_client: TestClient, auth_headers: Headers) -> None:
    response = api_client.get(f"{API}/auth/me", headers=auth_headers(TEACHER))
    assert response.status_code == 200
    assert response.json()["must_change_password"] is False


def test_unauthenticated_me_gets_401(api_client: TestClient) -> None:
    assert api_client.get(f"{API}/auth/me").status_code == 401


def test_created_account_must_change_password(
    api_client: TestClient, auth_headers: Headers, db_session: Session
) -> None:
    response = api_client.post(
        f"{API}/admin/users",
        headers=auth_headers(ADMIN),
        json={"email": "moi@example.com", "full_name": "Người Mới", "role": "teacher"},
    )
    assert response.status_code == 201
    password = response.json()["temporary_password"]
    login_response = api_client.post(
        f"{API}/auth/login", json={"email": "moi@example.com", "password": password}
    )
    assert login_response.json()["user"]["must_change_password"] is True
    assert user_of(db_session, "moi@example.com").must_change_password is True


@pytest.mark.parametrize(("method", "url"), BLOCKED)
def test_temporary_password_blocks_everything_but_me_and_change(
    api_client: TestClient, auth_headers: Headers, db_session: Session, method: str, url: str
) -> None:
    target = user_of(db_session, TEACHER)
    password = reset(api_client, auth_headers(ADMIN), target.id)
    headers = login(api_client, TEACHER, password)

    blocked = api_client.request(method, url, headers=headers)
    assert blocked.status_code == 403
    assert "mật khẩu tạm" in blocked.json()["detail"]

    me = api_client.get(f"{API}/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["must_change_password"] is True


def test_admin_with_temporary_password_is_blocked_too(
    api_client: TestClient, auth_headers: Headers, db_session: Session
) -> None:
    admin = user_of(db_session, ADMIN)
    password = reset(api_client, auth_headers(ADMIN), admin.id)
    headers = login(api_client, ADMIN, password)

    assert api_client.get(f"{API}/admin/users", headers=headers).status_code == 403


def test_changing_password_lifts_the_block(
    api_client: TestClient, auth_headers: Headers, db_session: Session
) -> None:
    target = user_of(db_session, TEACHER)
    password = reset(api_client, auth_headers(ADMIN), target.id)
    headers = login(api_client, TEACHER, password)

    changed = api_client.post(
        f"{API}/auth/change-password",
        headers=headers,
        json={"current_password": password, "new_password": NEW_PASSWORD},
    )
    assert changed.status_code == 200

    # Cùng token dùng tiếp được ngay; mật khẩu tạm không còn đăng nhập được.
    assert api_client.get(f"{API}/me/assignments", headers=headers).status_code == 200
    assert api_client.get(f"{API}/auth/me", headers=headers).json()["must_change_password"] is False
    db_session.expire_all()
    assert user_of(db_session, TEACHER).must_change_password is False
    relogin = api_client.post(f"{API}/auth/login", json={"email": TEACHER, "password": password})
    assert relogin.status_code == 401


def test_voluntary_change_keeps_the_flag_off(
    api_client: TestClient, auth_headers: Headers, db_session: Session
) -> None:
    headers = auth_headers(TEACHER)
    changed = api_client.post(
        f"{API}/auth/change-password",
        headers=headers,
        json={"current_password": DEV_PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert changed.status_code == 200
    db_session.expire_all()
    assert user_of(db_session, TEACHER).must_change_password is False


def test_imported_teachers_must_change_password(
    api_client: TestClient, auth_headers: Headers, db_session: Session
) -> None:
    headers = auth_headers(ADMIN)
    csv = "Họ và tên,Email\nNguyễn Văn Nhập,nhap.tu.tep@example.com\n".encode()
    preview = api_client.post(
        f"{API}/admin/users/import",
        headers=headers,
        files={"file": ("gv.csv", csv, "text/csv")},
    )
    assert preview.status_code == 200, preview.text
    job_id = preview.json()["job_id"]
    confirmed = api_client.post(f"{API}/admin/users/import/{job_id}/confirm", headers=headers)
    assert confirmed.status_code == 200, confirmed.text

    assert user_of(db_session, "nhap.tu.tep@example.com").must_change_password is True
