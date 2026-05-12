import os
import requests


def main() -> None:
    base = "http://127.0.0.1:8000/api/v1"
    # Admin password viene de env var (idealmente DEFAULT_USER_PASSWORD del .env
    # local o SMOKE_ADMIN_PASS). Sin valores hardcoded.
    admin_pass = os.getenv("SMOKE_ADMIN_PASS") or os.getenv("DEFAULT_USER_PASSWORD")
    if not admin_pass:
        raise SystemExit(
            "SMOKE FAIL: configura SMOKE_ADMIN_PASS o DEFAULT_USER_PASSWORD en el entorno"
        )

    login = requests.post(
        f"{base}/auth/login",
        json={"username": "admin", "password": admin_pass},
        timeout=10,
    )
    if not login.ok:
        raise SystemExit(f"SMOKE FAIL: login admin devolvió {login.status_code}")
    token = login.json().get("access_token")
    if not token:
        raise SystemExit("SMOKE FAIL: respuesta sin access_token")

    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "ticket_type": "incident",
        "title": "Smoke ticket sin cliente",
        "description": "Validacion automatica",
        "priority": "p3_medium",
        "urgency": "medium",
        "impact": "user",
    }
    create = requests.post(
        f"{base}/sd/tickets",
        json=payload,
        headers=headers,
        timeout=15,
    )

    if create.status_code != 200:
        raise SystemExit(
            f"SMOKE FAIL: crear ticket sin cliente devolvio {create.status_code}: {create.text[:200]}"
        )

    body = create.json()
    print(f"SMOKE OK: login admin + ticket {body.get('number')} creado")


if __name__ == "__main__":
    main()
