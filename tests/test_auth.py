from __future__ import annotations

from pathlib import Path

from aoe_linear_plugin.auth import resolve_token, token_file


def _key_file(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "api_key"
    path.write_text(content, encoding="utf-8")
    return path


def test_token_file_is_read_when_the_environment_has_none(tmp_path: Path) -> None:
    path = _key_file(tmp_path, "file-token\n")
    assert resolve_token({"LINEAR_API_KEY_FILE": str(path)}) == "file-token"


def test_environment_beats_the_token_file(tmp_path: Path) -> None:
    path = _key_file(tmp_path, "file-token\n")
    assert resolve_token({"LINEAR_API_KEY_FILE": str(path), "LINEAR_API_KEY": "env-token"}) == "env-token"
    assert resolve_token({"LINEAR_API_KEY_FILE": str(path), "LINEAR_TOKEN": "alias-token"}) == "alias-token"


def test_a_blank_environment_value_falls_through_to_the_file(tmp_path: Path) -> None:
    path = _key_file(tmp_path, "file-token\n")
    assert resolve_token({"LINEAR_API_KEY_FILE": str(path), "LINEAR_API_KEY": "   "}) == "file-token"


def test_a_blank_or_missing_file_resolves_to_no_token(tmp_path: Path) -> None:
    assert resolve_token({"LINEAR_API_KEY_FILE": str(_key_file(tmp_path, "\n \n"))}) is None
    assert resolve_token({"LINEAR_API_KEY_FILE": str(tmp_path / "absent")}) is None
    # A directory at that path is unreadable rather than fatal.
    assert resolve_token({"LINEAR_API_KEY_FILE": str(tmp_path)}) is None


def test_only_the_first_line_is_used_as_the_token(tmp_path: Path) -> None:
    path = _key_file(tmp_path, "  first-token  \nsecond line\n")
    assert resolve_token({"LINEAR_API_KEY_FILE": str(path)}) == "first-token"


def test_leading_blank_lines_are_skipped(tmp_path: Path) -> None:
    """A file that starts with a blank line still yields its token."""
    assert resolve_token({"LINEAR_API_KEY_FILE": str(_key_file(tmp_path, "\n  \ntok\n"))}) == "tok"


def test_a_valid_first_line_survives_undecodable_later_bytes(tmp_path: Path) -> None:
    """Undecodable bytes after the token are never read, so they cannot raise."""
    path = tmp_path / "api_key"
    path.write_bytes(b"file-token\n\xff\xfe\n")
    assert resolve_token({"LINEAR_API_KEY_FILE": str(path)}) == "file-token"


def test_an_undecodable_first_line_resolves_to_no_token(tmp_path: Path) -> None:
    """A UTF-16 or invalid-UTF-8 file is an absent token, not an exception."""
    path = tmp_path / "api_key"
    path.write_bytes("utf16-token\n".encode("utf-16"))
    assert resolve_token({"LINEAR_API_KEY_FILE": str(path)}) is None


def test_carriage_returns_also_end_the_first_line(tmp_path: Path) -> None:
    """A file saved with bare CR separators still yields just its token."""
    path = tmp_path / "api_key"
    path.write_bytes(b"file-token\rsecond line\r")
    assert resolve_token({"LINEAR_API_KEY_FILE": str(path)}) == "file-token"


def test_a_carriage_return_before_undecodable_bytes_keeps_the_token(tmp_path: Path) -> None:
    """The CR ends the line, so the undecodable bytes after it are never read."""
    path = tmp_path / "api_key"
    path.write_bytes(b"file-token\r\xff")
    assert resolve_token({"LINEAR_API_KEY_FILE": str(path)}) == "file-token"


def test_a_byte_order_mark_is_not_part_of_the_token(tmp_path: Path) -> None:
    """A key file edited on Windows must not carry U+FEFF into the header."""
    path = tmp_path / "api_key"
    path.write_bytes(b"\xef\xbb\xbffile-token\n")
    assert resolve_token({"LINEAR_API_KEY_FILE": str(path)}) == "file-token"


def test_reading_the_file_is_bounded(tmp_path: Path) -> None:
    """A path holding one huge line is read for its head, not to the end."""
    path = tmp_path / "api_key"
    path.write_bytes(b"a" * 10000)
    token = resolve_token({"LINEAR_API_KEY_FILE": str(path)})
    assert token is not None
    assert len(token) == 4096


def test_an_unresolvable_home_in_the_override_resolves_to_no_token() -> None:
    """expanduser() raises for a mistyped ``~user``; resolution must not."""
    assert resolve_token({"LINEAR_API_KEY_FILE": "~aoe-no-such-user-override/key"}) is None


def test_the_override_does_not_fall_through_to_the_default(monkeypatch, tmp_path: Path) -> None:
    """LINEAR_API_KEY_FILE selects a path; the default is not tried after it."""
    default = tmp_path / "default"
    default.write_text("home-token\n", encoding="utf-8")
    monkeypatch.setattr("aoe_linear_plugin.auth.DEFAULT_KEY_FILE", str(default))
    assert resolve_token({"LINEAR_API_KEY_FILE": str(tmp_path / "absent")}) is None
    assert resolve_token({}) == "home-token"


def test_the_default_file_lives_under_the_config_dir(monkeypatch, tmp_path: Path) -> None:
    """The documented default, which a daemon-started worker reads with no env at all."""
    monkeypatch.setattr("aoe_linear_plugin.auth.DEFAULT_KEY_FILE", "~/.config/linear/api_key")
    monkeypatch.setenv("HOME", str(tmp_path))
    default = tmp_path / ".config" / "linear" / "api_key"
    assert token_file({}) == default
    default.parent.mkdir(parents=True)
    default.write_text("home-token\n", encoding="utf-8")
    assert resolve_token({}) == "home-token"
