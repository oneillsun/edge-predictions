from __future__ import annotations

from app.config import BACKEND_ROOT, resolve_sqlite_url


def test_resolve_sqlite_url_anchors_relative_path_to_backend_root() -> None:
    resolved = resolve_sqlite_url("sqlite:///./app.db")
    expected = (BACKEND_ROOT / "app.db").resolve().as_posix()
    assert resolved == f"sqlite:///{expected}"


def test_resolve_sqlite_url_leaves_absolute_path_unchanged() -> None:
    # Windows-style absolute path (drive letter) — a leading "/" alone isn't
    # absolute per pathlib on Windows, so this uses a real absolute example.
    absolute = "sqlite:///C:/tmp/somewhere/app.db"
    assert resolve_sqlite_url(absolute) == absolute


def test_resolve_sqlite_url_leaves_non_sqlite_url_unchanged() -> None:
    postgres_url = "postgresql://user:pass@localhost/dbname"
    assert resolve_sqlite_url(postgres_url) == postgres_url
