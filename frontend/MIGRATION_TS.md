# TypeScript Migration — Audit #115

Gradual JS → TS migration of the Contecflow PSA frontend.
`tsconfig.json` runs with `allowJs: true` so JS and TS files coexist seamlessly during the migration.

## Current state (post-pilot)

- TS/TSX files: **34** (8 pre-existing + 26 migrated in this pilot)
- JS/JSX files remaining: **~311**
- `strict: true`, `noImplicitAny: false` (relax to allow gradual hardening), `noFallthroughCasesInSwitch: true`
- Vitest `test.include` updated to accept `.test.{js,jsx,ts,tsx}` so migrated tests keep running
- API service (`services/api.js`) still JS — every typed hook imports it with a `// TODO type:` marker

## Pilot batch (this PR)

Renames done with plain `mv` because `git mv` is sandbox-blocked; git detects them as renames via content similarity.

### utils (6 + 1 test)
| File | Type highlights |
|---|---|
| `src/utils/wsUtils.ts` | `resolveWsBase(): string`; `import.meta.env` cast to `string \| undefined` |
| `src/utils/security.ts` | `sanitizeUrl(url: string \| null \| undefined): string`; `isSafeUrl(): boolean` |
| `src/utils/formValidation.ts` | Generic `validateSchema<T>(schema: ZodSchema<T>, values: unknown): ValidationResult<T>`; exports `FieldErrors` type |
| `src/utils/logger.ts` | `LogLevel` union, `Logger` interface, `window.CONTECFLOW_LOG_LEVEL` declared via global augmentation |
| `src/utils/collabPush.ts` | Discriminated union `CollabPushResult`, `CollabPushFailureReason` |
| `src/utils/helpers.ts` | `DateInput`, `Maybe<T>`, `RiskLevel` types; `fmtCurrency`, `fmtNumber`, `extractErr` typed; status/role label maps typed `Record<string, string>` |
| `src/utils/helpers.test.ts` | No type annotations needed — test code reuses typed exports |

### hooks (19)
All React Query hooks now declare `UseQueryResult<T>` / `UseMutationResult<TData, TError, TVariables>` return types and parameter types. `Partial<T>` is used for create/update payloads. The `api` service remains JS, so its `.then((r: { data: T }) => r.data)` callsites are explicitly typed to surface intent.

| File | Type highlights |
|---|---|
| `src/hooks/useMediaQuery.ts` | `(query: string, defaultValue?: boolean) => boolean` |
| `src/hooks/useOnlineStatus.ts` | `() => boolean` |
| `src/hooks/useOrgSettings.ts` | `OrgSettings` interface (currency, timezone, capacity, etc.) |
| `src/hooks/useFormValidation.ts` | Generic `useFormValidation<T>(schema: ZodSchema<T>)` returning `UseFormValidationResult<T>` |
| `src/hooks/useAlerts.ts` | `AlertItem` interface, list unwrapping typed |
| `src/hooks/useProblems.ts` | `ProblemRecord`, `UpdateArgs<T>` |
| `src/hooks/useSubcontractors.ts` | `Subcontractor` |
| `src/hooks/useVendors.ts` | `Vendor` |
| `src/hooks/useDashboard.ts` | `DashboardParams` |
| `src/hooks/useDeliverables.ts` | `Deliverable` |
| `src/hooks/useEpics.ts` | `Epic` |
| `src/hooks/useAssets.ts` | `Asset` |
| `src/hooks/useContracts.ts` | `Contract`, internal `unwrapList<T>` helper |
| `src/hooks/useMilestones.ts` | `Milestone`, `CreateMilestoneArgs` |
| `src/hooks/useOKRs.ts` | `OKR`, `UpdateKRArgs` |
| `src/hooks/useRisks.ts` | `Risk` |
| `src/hooks/useCountUp.ts` | `CountUpTarget = number \| string`; properly typed `requestAnimationFrame` ref |
| `src/hooks/useChanges.ts` | `ChangeRequest`, `ApproveArgs` |
| `src/hooks/useIdleTimeout.ts` | `UseIdleTimeoutOptions`, `UseIdleTimeoutResult`; timer refs typed `ReturnType<typeof setTimeout> \| null` |

### Tooling
- `frontend/vite.config.js`: vitest `test.include` widened to `src/**/*.test.{js,jsx,ts,tsx}` so `helpers.test.ts` runs.

## Final state (2026-05-15)

All batches **closed**. Coverage: **380/380 .ts/.tsx, 0 .js/.jsx**.

| Batch | Scope | Status |
|---|---|---|
| A (pilot) | utils + 19 hooks | ✅ b410398 |
| B | remaining hooks + hooks/index | ✅ 00f13ce |
| C | services + axios client | ⚠️ deferred — see "Open type-debt" below |
| D | constants + small contexts | ✅ 00f13ce |
| E | charts + leaf UI + components/ui | ✅ 00f13ce + 9664589 |
| F | features + portal + layout aggregators | ✅ 00f13ce + 9664589 + 9d7a3cd |
| G | pages + AuthContext + ChatRealtimeContext + tests + entrypoints | ✅ 00f13ce + 9664589 |
| polish | type-quality on top 38 layout/bi/servicedesk/dashboard files | ✅ 9d7a3cd |

## Open type-debt

The migration closes the file-extension goal (100% .ts/.tsx). The
following type-quality items remain as future polish — none block
correctness because `tsconfig.json` runs `allowJs: true` and
`noImplicitAny: false`:

1. **`services/api.ts` (1856 LOC).** Canonical, working, but a single
   file. An incomplete split attempt under `services/api/*.ts` was
   reverted in 2da391e because no caller imported from it and the
   re-export coverage was only 26%. Future: split `api.ts` into
   per-resource modules under `services/api/` AND migrate every caller
   in lockstep so the file can be deleted.
2. **`AxiosResponse<T>` propagation.** Hooks still treat responses as
   `{ data: unknown }` because `api.ts` exports loose shapes. Resolved
   when the split above completes.
3. **`// TODO type:` markers across ~140 files** (mostly pages and
   components that got mechanical rename + minimal Props/useState
   typing). Grep `// TODO type:` for the canonical list.
4. **i18n `t()` keys are stringly-typed.** Optional improvement via
   `i18next-resources-for-ts` codegen.
5. **`useLocation().state` is `unknown` in many pages.** Should be
   addressed per-page when each page's domain types stabilize.

## Known type-debt blockers

1. **`services/api.js` (axios client).** All hooks treat responses as `unknown`. Until typed, every `useQuery<DomainType>` is technically `useQuery<unknown>` at runtime. **Resolution: Batch C.**
2. **`react-i18next` types.** `useTranslation()` returns `t(key: string)` with `string` return; without typed resource JSONs, all i18n keys are stringly-typed. Consider `i18next-resources-for-ts` later. **Not a blocker for hooks/utils.**
3. **`react-router` types.** `useParams<{ id: string }>()` is fine, but pages also use `useLocation().state` which is `unknown`. **Address per-page during Batch G.**
4. **`AuthContext`.** Untyped `useAuth()` exposes `user`, `loading`, `hasRole(...roles)`. Should be typed in Batch D or as part of Batch G prerequisites; many hooks consume it.
5. **`@tanstack/react-query` v5 strict types.** `useQuery` requires explicit generics or returns `unknown`. We already opted into explicit types — keep doing so.
6. **`zod` peer.** Already a runtime dep, no extra install needed; `ZodSchema<T>` import works out of the box.
7. **`window.CONTECFLOW_LOG_LEVEL` and similar globals.** Use `declare global { interface Window {...} }` blocks inside each file that needs them (logger.ts has the example).

## Migration playbook (for future batches)

1. `mv file.js file.ts` (or `.jsx` → `.tsx`). Importers without extensions keep working.
2. Replace function params: `function foo(x)` → `function foo(x: Type)`.
3. Type `useState`: `useState<Type>(initial)`.
4. Type external responses: import the domain type from `src/types/api.ts` (extend it when needed) or write a local interface near the hook.
5. For shapes still unknown, use `unknown` (never `any`) and resolve in the next batch. Mark with `// TODO type: <reason>`.
6. Run `npx tsc --noEmit` from `frontend/` to surface type errors before committing.
7. Run `npx vitest run` to make sure tests still pass.
