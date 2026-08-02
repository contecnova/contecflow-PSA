# Circular import policy

Audit #110 — inventory and architectural recommendations.

## TL;DR

Three modules previously deferred imports inside functions with comments such
as "imported lazily to avoid circular imports". A grep-based investigation
(see methodology below) showed that none of the three had a real cycle. The
deferred imports have been hoisted to module level.

There are **no remaining lazy imports in the audited services for the sole
purpose of breaking import cycles.** Any future deferred imports should be
documented inline with the full cycle path and a refactor plan.

> ⚠️ Alcance real de esa afirmación (revisado en la auditoría 2026-07,
> `docs/AUDIT_2026_07_FULL.md` §2.1). El «TL;DR» de arriba se refiere **solo a los
> tres módulos auditados en el audit #110**, no al backend completo. A día de hoy
> hay **~200 imports diferidos dentro de funciones** marcados `# noqa: PLC0415`, y
> los símbolos más diferidos son **módulos internos**, no dependencias opcionales:
> `AppSetting` (18), `HTTPException` (12), `settings` (11), `ITSMChangeRequest` (6),
> `CMDBAgentRegistration` (5), `User` (4), `Project` (3).
>
> Diferir `app.models.*` y `app.core.config.settings` dentro de funciones es el
> patrón clásico de evitar ciclos, y **ninguno de los ~200 documenta la ruta del
> ciclo**, que es justo lo que esta política exige en el párrafo anterior.
>
> Es decir: la política es correcta, pero no se está cumpliendo fuera de los tres
> módulos originales. Pendiente: mapear el grafo de imports y extraer un módulo de
> tipos/contratos que rompa los ciclos de verdad, o justificar inline cada
> deferral que se quede.

## Investigation methodology

For each suspected lazy import we ran:

```sh
# Does any module import the deferred symbol back?
grep -rn "from <importing_module>\|import <importing_module>" app/
```

We then read the imports of every module reached transitively, looking for
a path back to the module that contains the lazy import. A cycle exists iff
such a path is found.

## Audited cases

### 1. `app/core/abac_middleware.py` — RESOLVED

Previously deferred inside `dispatch()`:

- `from app.db.session import SessionLocal`
- `from app.core.abac_enforce import enforce_abac`
- `from fastapi import HTTPException`

**Cycle analysis:**

- `app.db.session` imports only `sqlalchemy` and `app.core.config`.
- `app.core.abac_enforce` imports `app.models.user` and
  `app.services.abac`.
- `app.services.abac` imports `app.models.abac`, `app.models.user`,
  `sqlalchemy`, `fastapi`.
- None of the above imports `app.core.abac_middleware`.
- `app.core.abac_middleware` is referenced from exactly one place,
  `app/main.py:424`, well after the entire model/service graph has loaded.

**Verdict:** No cycle. Imports were hoisted to the top of the module.

### 2. `app/services/ai_governance.py` — RESOLVED

Previously deferred inside `_load_policies()` and `_audit()`:

- `from app.models.ai_governance import AIGuardrailPolicyModel`
- `from app.models.ai_governance import AIGuardrailAuditLog`

**Cycle analysis:**

The same symbols were already imported eagerly at the top of the module
(`lines 24-25` before refactor). The deferred imports were strictly
redundant. `app.models.ai_governance` imports only `app.db.base` and
`sqlalchemy`; nothing in `app.models.*` imports
`app.services.ai_governance`.

**Verdict:** No cycle. Redundant lazy `import` statements were removed; the
module-level imports are used directly.

### 3. `app/services/grc_service.py` — RESOLVED

Previously used a `_models()` helper that returned a tuple of model classes
so every consumer could destructure it instead of importing the symbols
directly.

**Cycle analysis:**

The same model classes were already imported eagerly at the top of the
module (`line 14` before refactor). `app.models.billing_reports` imports
only `app.db.base` and `sqlalchemy`; nothing in `app.models.*` or
`app.db.*` imports `app.services.grc_service`.

**Verdict:** No cycle. The `_models()` indirection has been removed and
every function references the top-level imports directly.

## Remaining acceptable deferred imports

The codebase still contains some lazy imports that are intentional and
**not** related to circular-import avoidance. They should not be hoisted:

- `tiktoken` in `ai_governance._estimate_tokens` — optional runtime
  dependency; falls back to a heuristic if missing.
- `time as _time` in `ai_governance._load_policies` — local alias scoped to
  the function (cosmetic).
- `_json` aliases in `grc_service.serialize_*` — same (cosmetic).

These have nothing to do with circular imports and the local form keeps the
module top tidy.

## Architectural recommendation for future cycles

If a real circular import appears in the future (you will know because the
process fails at import time, not because somebody added a defensive
comment), prefer these refactors in order:

1. **Move the shared interface to a leaf module.** Most cycles happen
   because a "service" module imports a "router" module or vice versa. Put
   the shared dataclass / Protocol / DB model in a leaf module that both
   sides can import without referencing each other.

2. **Invert the dependency with a registry / event bus.** If module A
   needs to call a function from module B, but B already imports A, B can
   register a callback into a neutral registry that A reads. We already
   use this pattern for ABAC (`app/core/abac_registry.py`) — every router
   registers its `(prefix, resource_type, action)` triple at import time
   and the middleware reads the registry without importing any router.

3. **Use a Protocol / abstract type.** Define the contract in a third
   module that both A and B import. The implementation injects itself at
   runtime.

4. **As a last resort, keep the lazy import** but document inline:
   - the exact cycle path (`A -> B -> C -> A`),
   - why the cycle exists (what business need ties the two ends),
   - what refactor would remove it,
   - a TODO with a reference to a tracking issue.

A bare comment like `# avoid circular imports` is not acceptable — it
hides whether the cycle is real and prevents future cleanups.

## How to verify there is no cycle

```sh
# 1. Fail-fast import of the application graph.
source venv/bin/activate
python -c "from app.main import app; print('OK')"

# 2. Optional: visualize the import graph for a suspected module.
python -m pydeps app/services/ai_governance.py --max-bacon 3 --no-show
```

If `step 1` fails with `ImportError: cannot import name X (most likely due
to a circular import)`, the cycle is real and one of the refactors above is
required.
