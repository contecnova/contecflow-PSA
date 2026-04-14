import requests


def main() -> None:
    base = "http://127.0.0.1:8000/api/v1"
    password_candidates = ["clarive2024!", "admin123", "Clarive2024!"]

    token = None
    used_password = None
    for pwd in password_candidates:
        login = requests.post(
            f"{base}/auth/login",
            json={"username": "admin", "password": pwd},
            timeout=10,
        )
        if login.ok:
            token = login.json().get("access_token")
            used_password = pwd
            break

    if not token:
        raise SystemExit("SMOKE FAIL: no se pudo autenticar admin con contrasenas conocidas")

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
    print(f"SMOKE OK: login admin ({used_password}) + ticket {body.get('number')} creado")


if __name__ == "__main__":
    main()
