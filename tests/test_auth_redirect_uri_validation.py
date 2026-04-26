from app.api.v1.routers.auth_sso import _is_allowed_redirect_uri


def test_redirect_uri_allows_exact_origin_with_path_and_query():
    allowed = ["http://localhost:3000", "https://app.example.com"]

    assert _is_allowed_redirect_uri("http://localhost:3000/auth/callback?next=/", allowed)


def test_redirect_uri_rejects_prefix_bypass_domain():
    allowed = ["http://localhost:3000"]

    assert not _is_allowed_redirect_uri("http://localhost:3000.evil.com/callback", allowed)


def test_redirect_uri_rejects_port_mismatch():
    allowed = ["https://app.example.com"]

    assert not _is_allowed_redirect_uri("https://app.example.com:444/callback", allowed)
