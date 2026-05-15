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

## Recommended next batches

Each batch should remain reviewable in a single PR (~30 files).

### Batch B: Remaining hooks (~17 files)
`useAbsences`, `useAnalytics`, `useApprovals`, `useClients`, `useDocCollab`, `useExpenses`, `useForecasts`, `useImputations`, `useInvalidate`, `useLicenses`, `useNotificationBadges`, `usePipeline`, `useProjects`, `useRateCards`, `useSprints`, `useSwipeGesture`, `useTasks`, `useTickets`, `useTraining`, `useUsers`, `useUserPreferences`, `hooks/index.js`.
**Risk:** low. Same pattern as Batch A. `useNotificationBadges` and `useUserPreferences` touch `AuthContext` — needs context typing first or temporary `as any`.

### Batch C: Services + axios client (~6 files)
`services/api.js` (1856 LOC), `services/settingsApi.js`, `services/collaborationApi.js`, `services/biOfflineDb.js`, `services/offlineQueue.js`, `services/offlineSync.js` (745 LOC).
**Risk:** medium. Big files. `api.js` should be split into one file per resource (e.g. `services/api/clients.ts`) during migration. Once `api` exports are typed, remove all `// TODO type: services/api still JS` markers and tighten every hook's return type.
**Blocker:** axios `AxiosResponse<T>` typing — currently every hook treats response as `{ data: unknown }`. After this batch, hooks can return real domain types instead of `unknown`.

### Batch D: Constants + small contexts (~10 files)
`constants/queryKeys.js`, `constants/api.js`, `constants/errors.js`, `constants/theme.js`, `constants/business_config.json`, `constants/constants.json`, `context/ConfirmContext.jsx`, plus a few `i18n/*.js` helpers.
**Risk:** low. `queryKeys` is consumed everywhere — once typed, every hook's `queryKey` parameter can use `as const` tuples and enable cache key inference.

### Batch E: Charts + simple components (~30 files)
Leaf components in `src/charts/`, `src/components/ui/`, `src/components/feedback/`, etc. — anything with minimal props or no children.
**Risk:** medium. Most react components need `React.FC<Props>` or explicit `Props` interface; complex prop drilling can wait.

### Batch F: Features + portal components (~40 files)
`src/features/*`, `src/components/portal/*`, `src/components/layout/*`. Many touch ChatRealtimeContext + i18n.
**Risk:** medium-high — coordinate with the chat realtime work.

### Batch G: Pages + AuthContext + ChatRealtimeContext (~80 files)
The large surface. Should be done last because:
- Pages import many hooks (now typed) but also many components (not yet typed).
- `AuthContext.jsx` (207 LOC) and `ChatRealtimeContext.jsx` (261 LOC) are central — type them carefully in a dedicated PR.
- Coordinate with Wave B (i18n) so we don't fight over the same files.

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
