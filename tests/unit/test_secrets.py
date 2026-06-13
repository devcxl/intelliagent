from __future__ import annotations

from src.core.secrets import redact_secrets


def test_redact_sk_key():
    result = redact_secrets("sk-abc123def456")
    assert "[REDACTED]" in result
    assert "sk-abc123def456" not in result


def test_redact_bearer_token():
    result = redact_secrets("Authorization: Bearer abc123.def456.ghi789")
    assert "[REDACTED]" in result
    assert "abc123.def456.ghi789" not in result


def test_redact_password_retains_key():
    result = redact_secrets("password = hunter2")
    assert "password = [REDACTED]" in result
    assert "hunter2" not in result


def test_redact_api_key_retains_key():
    result = redact_secrets('"api_key": "sk-abc123"')
    assert "api_key" in result
    assert "[REDACTED]" in result
    assert "sk-abc123" not in result


def test_redact_url_credentials():
    result = redact_secrets("https://user:pass123@example.com/path")
    assert "user:[REDACTED]@example.com" in result
    assert "pass123" not in result


def test_redact_url_credentials_http():
    result = redact_secrets("http://admin:secret@localhost:8080")
    assert "admin:[REDACTED]@localhost" in result
    assert "secret" not in result


def test_redact_bearer_preserves_prefix():
    """Bearer 有捕获组，保留前缀。"""
    result = redact_secrets("Bearer abc123.def456")
    assert result == "Bearer [REDACTED]"


def test_redact_sk_preserves_no_prefix():
    """sk- 无捕获组，整体替换为 [REDACTED]。"""
    result = redact_secrets("sk-abc123")
    assert result == "[REDACTED]"


def test_redact_mixed_content():
    result = redact_secrets(
        "password=admin123 api_key=sk-abc Bearer token https://u:p@host"
    )
    assert "admin123" not in result
    assert "sk-abc" not in result
    assert "https://u:p" not in result
    assert "[REDACTED]" in result
    # 验证 password 保留了键名
    assert "password=" in result or "password =" in result


def test_redact_no_secrets_unchanged():
    result = redact_secrets("hello world, this is normal text")
    assert result == "hello world, this is normal text"


def test_redact_empty_string():
    assert redact_secrets("") == ""
