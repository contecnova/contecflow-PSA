"""Seed CMDB relations between existing CIs.

18-11-2026: la URL y las credenciales salen del entorno, no del código:
`CONTECFLOW_API_URL` (por defecto http://localhost:8000/api/v1),
`SEED_ADMIN_USERNAME` (por defecto admin) y `SEED_ADMIN_PASSWORD` (obligatoria;
si falta, se usa `DEFAULT_USER_PASSWORD`; sin ninguna, el script sale).
"""
import json
import os
import sys
import urllib.request

BASE = os.environ.get("CONTECFLOW_API_URL", "http://localhost:8000/api/v1").rstrip("/")
_USUARIO = os.environ.get("SEED_ADMIN_USERNAME", "admin")
_CLAVE = os.environ.get("SEED_ADMIN_PASSWORD") or os.environ.get("DEFAULT_USER_PASSWORD")
if not _CLAVE:
    sys.exit("seed_cmdb_relations: define SEED_ADMIN_PASSWORD (o DEFAULT_USER_PASSWORD) en el entorno.")

login = urllib.request.urlopen(
    urllib.request.Request(
        f"{BASE}/auth/login",
        data=json.dumps({"username": _USUARIO, "password": _CLAVE}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
)
token = json.load(login)["access_token"]
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

def get(path):
    req = urllib.request.Request(f"{BASE}{path}", headers=headers)
    with urllib.request.urlopen(req) as r:
        return json.load(r)

def post(path, body):
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as r:
            return json.load(r), None
    except urllib.error.HTTPError as e:
        return None, e.read().decode()

# Fetch existing CIs
data = get("/sd/cmdb?limit=50")
items = data.get("items", data) if isinstance(data, dict) else data
ci_map = {ci["name"]: ci["id"] for ci in items}
print("CIs found:", list(ci_map.keys()))

# Define relations
relations = [
    ("Load Balancer",       "App Server A",        "connects_to"),
    ("Load Balancer",       "App Server B",        "connects_to"),
    ("App Server A",        "PostgreSQL Primary",  "depends_on"),
    ("App Server B",        "PostgreSQL Primary",  "depends_on"),
    ("PostgreSQL Primary",  "PostgreSQL Replica",  "depends_on"),
    ("App Server A",        "Redis Cache",         "depends_on"),
    ("CRM Service",         "Load Balancer",       "depends_on"),
    ("ITSM Service",        "Load Balancer",       "depends_on"),
]

for src_name, tgt_name, rel_type in relations:
    src = ci_map.get(src_name)
    tgt = ci_map.get(tgt_name)
    if not src or not tgt:
        print(f"  SKIP {src_name} -> {tgt_name}: CI not found")
        continue
    res, err = post("/sd/cmdb/relations", {
        "source_ci_id": src,
        "target_ci_id": tgt,
        "relation_type": rel_type,
    })
    if err:
        print(f"  ERR {src_name} -> {tgt_name}: {err}")
    else:
        print(f"  OK  {src_name} -> {tgt_name} ({rel_type}) -> {res.get('id','?')}")

print("\nVerifying 3D graph...")
graph = get("/sd/cmdb/3d-graph?max_nodes=50")
print(f"  nodes={graph['node_count']}  edges={graph['edge_count']}")
first = graph["nodes"][0] if graph["nodes"] else {}
print(f"  first node: name={first.get('name')} type={first.get('type')} layer={first.get('layer')}")
