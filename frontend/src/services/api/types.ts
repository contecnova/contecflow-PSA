/**
 * Shared DTO type aliases for the api/* modules.
 *
 * These are intentionally permissive — the goal is to surface intent
 * (params bag, payload body, ID type) without locking the migration
 * to brittle Pydantic-mirror types.
 *
 * Domain types live in `src/types/api.ts`; re-export them when adding
 * stronger typing to a specific endpoint group.
 */
import type { AxiosResponse } from 'axios'

/** Numeric or string ID — backend uses UUIDs (string) but some legacy endpoints use ints. */
export type Id = string | number

/** Generic query-string bag — values are passed through to axios `params`. */
export type Params = Record<string, unknown> | undefined

/** Generic JSON body — request/response payloads. */
export type JsonBody = Record<string, unknown>

/** Re-export AxiosResponse for callers. */
export type Response<T = unknown> = AxiosResponse<T>

/** Generic listing response that may be paginated or raw array. */
export type ListResponse<T = unknown> = AxiosResponse<T[] | { items: T[]; count?: number; total?: number }>

/** Helper alias for AxiosResponse<unknown>. */
export type UnknownResponse = AxiosResponse<unknown>
