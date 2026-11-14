/**
 * useUsers — Centralized hook for user data.
 * Use this everywhere a user list or user detail is needed.
 * Canonical query key: ['users']
 * All mutations invalidate this key so every module stays in sync.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { UseQueryResult, UseMutationResult } from '@tanstack/react-query'
// TODO type: services/api still JS.
import { usersApi } from '../services/api'
import type { UserCreatePayload, UserListItem, UserListParams as ParametrosDeUsuarios, UserUpdatePayload, UserWithRate } from '../services/api/users'
import { STALE_5_MIN_MS, STALE_REFERENCE_DATA_MS } from '../constants/timings'

export type UserListParams = ParametrosDeUsuarios
export type UpdateArgs<T> = { id: string; data: T }

// ── List ──────────────────────────────────────────────────────────────────────
export function useUsers(params: UserListParams = {}): UseQueryResult<UserListItem[]> {
  return useQuery({
    queryKey: ['users', params],
    queryFn: () => usersApi.list(params).then((r) => r.data),
    staleTime: STALE_REFERENCE_DATA_MS,
  })
}

// Convenience: all active users — used in assignee/member selectors across the app
export function useAllUsers(): UseQueryResult<UserListItem[]> {
  return useQuery({
    queryKey: ['users'],
    queryFn: () => usersApi.list({}).then((r) => r.data),
    staleTime: STALE_REFERENCE_DATA_MS,
  })
}

// ── Single ────────────────────────────────────────────────────────────────────
export function useUser(id: string | undefined): UseQueryResult<UserWithRate> {
  return useQuery({
    queryKey: ['user', id],
    // `id!` va respaldado por el `enabled` de la linea siguiente: react-query
    // no ejecuta `queryFn` mientras `enabled` sea falso, asi que aqui `id`
    // nunca es undefined. Sin esa garantia habria que cambiar la firma.
    queryFn: () => usersApi.get(id!).then((r) => r.data),
    enabled: !!id,
    staleTime: STALE_5_MIN_MS,
  })
}

// ── Mutations ─────────────────────────────────────────────────────────────────
export function useCreateUser(): UseMutationResult<unknown, unknown, UserCreatePayload> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: UserCreatePayload) => usersApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }),
  })
}

export function useUpdateUser(): UseMutationResult<unknown, unknown, UpdateArgs<UserUpdatePayload>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: UpdateArgs<UserUpdatePayload>) => usersApi.update(id, data),
    onSuccess: (_: unknown, { id }: UpdateArgs<UserUpdatePayload>) => {
      qc.invalidateQueries({ queryKey: ['users'] })
      qc.invalidateQueries({ queryKey: ['user', id] })
    },
  })
}

export function useDeactivateUser(): UseMutationResult<unknown, unknown, string> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => usersApi.deactivate(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }),
  })
}
