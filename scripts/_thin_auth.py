"""Thin auth.py router — replace all helper function bodies with _svc delegation."""
import ast, re as _re

with open("app/api/v1/endpoints/auth.py", encoding="utf-8") as f:
    src = f.read()

count = 0

# ── 1. Add service import after "router = APIRouter()" ───────────────────────
old_router = "logger = logging.getLogger(__name__)\n\nrouter = APIRouter()"
new_router = "logger = logging.getLogger(__name__)\n\nrouter = APIRouter()\nimport app.services.auth_service as _svc"
if old_router in src:
    src = src.replace(old_router, new_router, 1); count += 1; print("Added _svc import")
else:
    print("WARNING: router pattern not found")

# ── 2. Replace each helper function body ─────────────────────────────────────

replacements = [
    # (name, pattern, replacement)
    (
        "_soc_svc",
        r'def _soc_svc\(db, user\) -> "SecurityEventService \| None":.*?return None\n',
        'def _soc_svc(db, user):\n    return _svc.soc_svc(db, user)\n',
    ),
    (
        "_client_ip",
        r'def _client_ip\(request: Request\) -> str:\n    return extract_client_ip\(request\)\n',
        'def _client_ip(request: Request) -> str:\n    return _svc.client_ip(request)\n',
    ),
    (
        "_mfa_challenge_query",
        r'def _mfa_challenge_query\(db: Session\):.*?return q\n',
        'def _mfa_challenge_query(db: Session):\n    return _svc.mfa_challenge_query(db)\n',
    ),
    (
        "_issue_mfa_challenge",
        r'def _issue_mfa_challenge\(db: Session, user: User\) -> str:.*?return token\n',
        'def _issue_mfa_challenge(db: Session, user: User) -> str:\n    return _svc.issue_mfa_challenge(db, user)\n',
    ),
    (
        "_read_mfa_challenge",
        r'def _read_mfa_challenge\(db: Session, challenge_token: str\) -> tuple\[dict, MFAChallenge\]:.*?return challenge_data, row\n',
        'def _read_mfa_challenge(db: Session, challenge_token: str):\n    return _svc.read_mfa_challenge(db, challenge_token)\n',
    ),
    (
        "_consume_mfa_challenge",
        r'def _consume_mfa_challenge\(row: MFAChallenge\) -> None:\n    row\.consumed_at = datetime\.now\(timezone\.utc\)\n',
        'def _consume_mfa_challenge(row: MFAChallenge) -> None:\n    return _svc.consume_mfa_challenge(row)\n',
    ),
    (
        "_resolve_sso_role",
        r'def _resolve_sso_role\(default_role: str\):.*?return UserRole\.employee\n',
        'def _resolve_sso_role(default_role: str):\n    return _svc.resolve_sso_role(default_role)\n',
    ),
    (
        "_resolve_sso_organization_id",
        r'def _resolve_sso_organization_id\(db: Session, config, email: str\) -> str:.*?\"La confi.*?\",\n    \)\n',
        'def _resolve_sso_organization_id(db: Session, config, email: str):\n    return _svc.resolve_sso_organization_id(db, config, email)\n',
    ),
    (
        "_validate_https_discovery_url",
        r'def _validate_https_discovery_url\(discovery_url: str\) -> str:.*?return discovery_url\n',
        'def _validate_https_discovery_url(discovery_url: str) -> str:\n    return _svc.validate_https_discovery_url(discovery_url)\n',
    ),
]

for name, pattern, replacement in replacements:
    m = _re.search(pattern, src, _re.DOTALL)
    if m:
        src = src[:m.start()] + replacement + src[m.end():]
        count += 1; print(f"Replaced {name}")
    else:
        print(f"WARNING: {name} not found")

# ── 3. Replace SSO state / Redis block (constants + functions) ────────────────
# Replace everything from "# ── SSO state store..." section up to the first @router
# i.e. the section containing constants + _get_sso_redis + _register_sso_state + etc.
old_block_start = "# ── SSO state store (CSRF protection: one-time use + 10-min TTL) ──────────────"
old_block_end = "\n_LOGIN_FAIL_PREFIX = \"clarive:login:fail:\"\n_LOGIN_LOCK_PREFIX = \"clarive:login:lock:\"\n_login_fail_fallback: dict[str, dict[str, float]] = {}\n_PASSWORD_RESET_TTL_SECONDS = 30 * 60\n_PASSWORD_RESET_REQUEST_WINDOW_SECONDS = 15 * 60\n_PASSWORD_RESET_REQUEST_MAX_PER_WINDOW = 5\n_password_reset_req_fallback: dict[str, dict[str, float]] = {}\n"

idx_start = src.find(old_block_start)
idx_end = src.find(old_block_end)
if idx_start >= 0 and idx_end >= 0:
    idx_end_full = idx_end + len(old_block_end)
    replacement_block = (
        "# ── SSO state / rate-limiting (delegated to auth_service) ──────────────────────\n"
        "_SSO_STATE_TTL = _svc.SSO_STATE_TTL\n"
        "_SSO_KEY_PREFIX = _svc.SSO_KEY_PREFIX\n"
        "_LOGIN_FAIL_PREFIX = _svc.LOGIN_FAIL_PREFIX\n"
        "_LOGIN_LOCK_PREFIX = _svc.LOGIN_LOCK_PREFIX\n"
        "_PASSWORD_RESET_TTL_SECONDS = _svc.PASSWORD_RESET_TTL_SECONDS\n"
        "_PASSWORD_RESET_REQUEST_WINDOW_SECONDS = _svc.PASSWORD_RESET_REQUEST_WINDOW_SECONDS\n"
        "_PASSWORD_RESET_REQUEST_MAX_PER_WINDOW = _svc.PASSWORD_RESET_REQUEST_MAX_PER_WINDOW\n"
    )
    src = src[:idx_start] + replacement_block + src[idx_end_full:]
    count += 1; print("Replaced SSO constants block")
else:
    print(f"WARNING: SSO constants block not found (start={idx_start}, end={idx_end})")

# ── 4. Replace remaining helper functions that follow ─────────────────────────
remaining = [
    (
        "_get_sso_redis",
        r'def _get_sso_redis\(\):.*?return _redis_client\n',
        'def _get_sso_redis():\n    return _svc.get_sso_redis()\n',
    ),
    (
        "_register_sso_state",
        r'def _register_sso_state\(state_raw: str\) -> None:.*?_sso_states_fallback\[state_raw\] = now \+ _SSO_STATE_TTL\n',
        'def _register_sso_state(state_raw: str) -> None:\n    return _svc.register_sso_state(state_raw)\n',
    ),
    (
        "_consume_sso_state",
        r'def _consume_sso_state\(state_raw: str\) -> bool:.*?return expiry is not None and time\.time\(\) < expiry\n',
        'def _consume_sso_state(state_raw: str) -> bool:\n    return _svc.consume_sso_state(state_raw)\n',
    ),
    (
        "_login_bucket",
        r'def _login_bucket\(username: str, request: Request\) -> str:\n    ip = request\.client\.host.*?\n    return f".*?\n',
        'def _login_bucket(username: str, request: Request) -> str:\n    return _svc.login_bucket(username, request)\n',
    ),
    (
        "_login_lock_ttl",
        r'def _login_lock_ttl\(bucket: str\) -> int:.*?return 0\n',
        'def _login_lock_ttl(bucket: str) -> int:\n    return _svc.login_lock_ttl(bucket)\n',
    ),
    (
        "_register_login_failure",
        r'def _register_login_failure\(bucket: str\) -> int:.*?_login_fail_fallback\[bucket\] = state\n    return 0\n',
        'def _register_login_failure(bucket: str) -> int:\n    return _svc.register_login_failure(bucket)\n',
    ),
    (
        "_clear_login_failure",
        r'def _clear_login_failure\(bucket: str\) -> None:.*?_login_fail_fallback\.pop\(bucket, None\)\n',
        'def _clear_login_failure(bucket: str) -> None:\n    return _svc.clear_login_failure(bucket)\n',
    ),
    (
        "_password_reset_bucket",
        r'def _password_reset_bucket\(identifier: str, request: Request\) -> str:\n    ip = request\.client\.host.*?\n    return f".*?\n',
        'def _password_reset_bucket(identifier: str, request: Request) -> str:\n    return _svc.password_reset_bucket(identifier, request)\n',
    ),
    (
        "_register_password_reset_request",
        r'def _register_password_reset_request\(bucket: str\) -> int:.*?return 0\n',
        'def _register_password_reset_request(bucket: str) -> int:\n    return _svc.register_password_reset_request(bucket)\n',
    ),
    (
        "_b64url_encode",
        r'def _b64url_encode\(data: bytes\) -> str:\n    return base64\.urlsafe_b64encode\(data\)\.decode\(\)\.rstrip\("="\)\n',
        'def _b64url_encode(data: bytes) -> str:\n    return _svc.b64url_encode(data)\n',
    ),
    (
        "_b64url_decode",
        r'def _b64url_decode\(data: str\) -> bytes:\n    padding = "=" \* \(\(4 - len\(data\) % 4\) % 4\)\n    return base64\.urlsafe_b64decode\(data \+ padding\)\n',
        'def _b64url_decode(data: str) -> bytes:\n    return _svc.b64url_decode(data)\n',
    ),
    (
        "_create_ephemeral_token",
        r'def _create_ephemeral_token\(token_type: str, subject: str, challenge: str, ttl_seconds: int = 300\) -> str:.*?return jose_jwt\.encode\(payload, key, algorithm="HS256", headers=\{"kid": kid\}\)\n',
        'def _create_ephemeral_token(token_type: str, subject: str, challenge: str, ttl_seconds: int = 300) -> str:\n    return _svc.create_ephemeral_token(token_type, subject, challenge, ttl_seconds)\n',
    ),
    (
        "_read_ephemeral_token",
        r'def _read_ephemeral_token\(token: str, expected_type: str\) -> dict:.*?return payload\n',
        'def _read_ephemeral_token(token: str, expected_type: str) -> dict:\n    return _svc.read_ephemeral_token(token, expected_type)\n',
    ),
    (
        "_COOKIE_OPTS + _set_auth_cookies",
        r'# Cookie settings.*?_COOKIE_OPTS = \{.*?\}\n\n\ndef _set_auth_cookies\(response: Response, access_token: str, refresh_token: str\) -> None:.*?}\n    \)\n',
        '# Cookie settings\n_COOKIE_OPTS = _svc.COOKIE_OPTS\n\n\ndef _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:\n    return _svc.set_auth_cookies(response, access_token, refresh_token)\n',
    ),
    (
        "_current_refresh_jti",
        r'def _current_refresh_jti\(request: Request\) -> Optional\[str\]:.*?return token_data\.get\("jti"\)\n',
        'def _current_refresh_jti(request: Request) -> Optional[str]:\n    return _svc.current_refresh_jti(request)\n',
    ),
    (
        "_issue_password_reset_token",
        r'def _issue_password_reset_token\(user: User\) -> str:.*?return _create_ephemeral_token\(.*?\)\n',
        'def _issue_password_reset_token(user: User) -> str:\n    return _svc.issue_password_reset_token(user)\n',
    ),
    (
        "_send_password_reset_email",
        r'def _send_password_reset_email\(recipient: str, reset_link: str\) -> None:.*?logger\.info\("Password reset link for %s: %s", recipient, reset_link\)\n',
        'def _send_password_reset_email(recipient: str, reset_link: str) -> None:\n    return _svc.send_password_reset_email(recipient, reset_link)\n',
    ),
]

for name, pattern, replacement in remaining:
    m = _re.search(pattern, src, _re.DOTALL)
    if m:
        src = src[:m.start()] + replacement + src[m.end():]
        count += 1; print(f"Replaced {name}")
    else:
        print(f"WARNING: {name} not found")

with open("app/api/v1/endpoints/auth.py", "w", encoding="utf-8") as f:
    f.write(src)

print(f"\nTotal: {count} replacements")
try:
    ast.parse(src)
    print("Syntax OK")
except SyntaxError as e:
    print(f"SYNTAX ERROR: {e}")
