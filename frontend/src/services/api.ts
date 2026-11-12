// Audit #C10 — services/api.ts is now a thin shim.
//
// The original 1,890-LOC god-file has been moved verbatim to
// `services/api/_core.ts`. The public surface (`from '.../services/api'`)
// re-exports the `services/api/` barrel, which in turn re-exports `_core`
// plus any new strictly-typed slices (`auth.ts`, `users.ts`, …).
//
// Why a shim instead of deleting this file:
//   • TS/Vite bundler resolution prefers `api.ts` (file) over `api/index.ts`
//     (folder) when both exist. Keeping the file makes the redirect explicit
//     and removes ambiguity for tooling and code-search.
//   • Zero changes required in the ~200 existing imports. Migration of each
//     domain happens independently in `services/api/<domain>.ts`.

export * from './api/index'
export { default } from './api/index'
