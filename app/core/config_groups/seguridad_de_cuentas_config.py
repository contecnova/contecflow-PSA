"""
Políticas de cuenta (23-11-2026): contraseñas, MFA, sesiones, acceso, alertas y
recertificación. Cada valor es el respaldo de entorno de un ajuste POR EMPRESA
(grupo `account_security` del registro en vivo) que se edita en Configuración ›
Seguridad › Seguridad de cuentas. Documentado en docs/seguridad/politicas_de_cuenta.md,
con el valor recomendado de cada uno (NIST SP 800-63B, ISO 27001, CIS).

NOTE: This is a *mixin* — see `app.core.config_groups` package docstring.
"""
from pydantic import Field


class SeguridadDeCuentasSettingsMixin:
    # ── Contraseñas ──────────────────────────────────────────────────────────
    PASSWORD_MAX_LENGTH: int = Field(default=128, description="Password policy — maximum length (NIST: allow at least 64).")
    PASSWORD_BLOCK_COMMON: bool = Field(default=True, description="Password policy — reject common/breached passwords from the LOCAL list (nothing is sent to third parties).")
    PASSWORD_BLOCK_PERSONAL: bool = Field(default=True, description="Password policy — reject passwords containing the username, the e-mail local part or the name.")
    PASSWORD_HISTORY_COUNT: int = Field(default=5, description="Password policy — the last N passwords cannot be reused (bcrypt hashes kept). 0 = no history.")
    PASSWORD_MIN_AGE_HOURS: int = Field(default=0, description="Password policy — hours before a password can be changed again (stops cycling the history). 0 = off.")
    PASSWORD_EXPIRY_DAYS: int = Field(default=0, description="Password policy — days until a password expires and must be changed at sign-in. 0 = never (NIST recommendation).")
    PASSWORD_EXPIRY_WARNING_DAYS: int = Field(default=14, description="Password policy — warn this many days before the password expires.")
    TEMP_PASSWORD_EXPIRY_HOURS: int = Field(default=72, description="Password policy — hours a temporary password set by an administrator stays valid.")
    # ── Bloqueo ──────────────────────────────────────────────────────────────
    LOGIN_LOCKOUT_NOTIFY_USER: bool = Field(default=True, description="Account lockout — notify the user when their account gets locked.")
    # ── MFA ──────────────────────────────────────────────────────────────────
    MFA_REQUIRED_ROLES: str = Field(default="admin", description="MFA — base roles that must use a second factor (CSV). Empty = none (the company-wide switch still applies).")
    MFA_REQUIRED_FOR_SENSITIVE: bool = Field(default=True, description="MFA — required for anyone holding a sensitive capability (administration, costs, people, security).")
    MFA_ALLOWED_METHODS: str = Field(default="totp,webauthn", description="MFA — allowed second factors (CSV of totp, webauthn).")
    MFA_GRACE_DAYS: int = Field(default=7, description="MFA — days a user newly required to use MFA may still sign in without it.")
    MFA_REMEMBER_DEVICE_DAYS: int = Field(default=0, description="MFA — days a device may skip the MFA challenge after a successful one. 0 = off.")
    # ── Sesiones ─────────────────────────────────────────────────────────────
    SESSION_MAX_HOURS: int = Field(default=0, description="Sessions — absolute maximum length since sign-in (hours). 0 = no cap (NIST AAL2: 24).")
    SESSION_MAX_CONCURRENT: int = Field(default=0, description="Sessions — maximum concurrent sessions per user; the oldest is closed. 0 = unlimited.")
    # ── Acceso ───────────────────────────────────────────────────────────────
    ACCESS_IP_ALLOWLIST: str = Field(default="", description="Access — IPs/CIDRs allowed to sign in and use the API (CSV). Empty = any. The platform superadmin is exempt.")
    ACCESS_HOURS: str = Field(default="", description="Access — allowed time window HH:MM-HH:MM in the company time zone (may cross midnight). Empty = any time.")
    ACCESS_DAYS: str = Field(default="1,2,3,4,5,6,7", description="Access — allowed ISO weekdays (1 = Monday) when ACCESS_HOURS is set.")
    ACCESS_HOURS_EXEMPT_ROLES: str = Field(default="admin", description="Access — base roles exempt from the time window (CSV).")
    ACCESS_BLOCKED_COUNTRIES: str = Field(default="", description="Access — ISO-3166 alpha-2 countries blocked (CSV). Only acts when the country is known (trusted proxy header or GEOIP_LOOKUP_ENABLED).")
    # ── Cuentas, separación de funciones, alertas, recertificación ───────────
    ACCOUNT_INACTIVE_DISABLE_DAYS: int = Field(default=0, description="Accounts — the daily job deactivates accounts without sign-in for this many days. 0 = off.")
    SECURITY_SOD_TWO_ADMINS: bool = Field(default=False, description="Segregation of duties — security policy changes and MFA resets need a second administrator.")
    SECURITY_ALERT_FAILED_LOGINS: int = Field(default=20, description="Alerts — failed sign-ins in 15 minutes in the company that alert the administrators. 0 = off.")
    # Umbrales de las reglas del SOC (`security_observability`; ronda 2 auditoria 2026-11-22).
    SOC_FUERZA_BRUTA_VENTANA_MIN: int = Field(default=10, description="SOC — window (minutes) for failed sign-ins per IP.")
    SOC_FUERZA_BRUTA_FALLOS: int = Field(default=5, description="SOC — failed sign-ins per IP in the window that raise a brute-force detection.")
    SOC_CRED_STUFFING_USUARIOS: int = Field(default=3, description="SOC — distinct users targeted by one IP in the window that make it credential stuffing.")
    SOC_MFA_FALLOS: int = Field(default=3, description="SOC — MFA failures for one user in 15 minutes that raise an MFA spray detection.")
    SECURITY_ALERT_NEW_IP: bool = Field(default=True, description="Alerts — alert the administrators when a user signs in from an IP never seen for them.")
    ACCESS_REVIEW_INTERVAL_DAYS: int = Field(default=90, description="Access review — a campaign must be closed at least every this many days (compliance report). 0 = not required.")
