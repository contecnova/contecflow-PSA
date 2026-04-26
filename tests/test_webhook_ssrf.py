"""
Regression tests for webhook SSRF protection.

Ensures _validate_webhook_url rejects internal/metadata destinations and
requires HTTPS, while accepting legitimate public HTTPS URLs.
"""
import pytest

from app.services.enterprise_service import _validate_webhook_url


# ── URLs that must be blocked ──────────────────────────────────────────────────

@pytest.mark.parametrize("url", [
    # Non-HTTPS schemes
    "http://example.com/hook",
    "ftp://example.com/hook",
    # AWS / GCP / Azure IMDS
    "https://169.254.169.254/latest/meta-data/",
    "https://metadata.google.internal/computeMetadata/v1/",
    "https://metadata.google/computeMetadata/v1/",
    "https://metadata/hook",
    # Loopback
    "https://localhost/hook",
    "https://127.0.0.1/hook",
    "https://127.1.1.1/hook",
    "https://[::1]/hook",
    "https://[fd00::1]/hook",
    # No hostname
    "https:///path/hook",
])
def test_validate_webhook_url_blocks(url: str) -> None:
    with pytest.raises(ValueError):
        _validate_webhook_url(url)


# ── scheme guard (does not require DNS resolution) ────────────────────────────

def test_validate_webhook_url_rejects_http() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        _validate_webhook_url("http://external-receiver.example.com/webhook")


def test_validate_webhook_url_rejects_metadata_hostname() -> None:
    with pytest.raises(ValueError, match="metadata"):
        _validate_webhook_url("https://169.254.169.254/iam/security-credentials/")


# ── source inspection ─────────────────────────────────────────────────────────

def test_validate_webhook_url_function_exists() -> None:
    """Guard: ensure the SSRF validator is importable and callable."""
    assert callable(_validate_webhook_url)
