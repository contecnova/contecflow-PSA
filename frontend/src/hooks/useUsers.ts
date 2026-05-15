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

export interface User {
  id: string
  name?: string
  email?: string
  role?: string
  is_active?: boolean
  [extra: string]: unknown
}

export type UserListParams = Record<string, unknown>
export type UpdateArgs<T> = { id: string; data: T }

// ── List ──────────────────────────────────────────────────────────────────────
export function useUsers(params: UserListParams = {}): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['users', params],
    queryFn: () => usersApi.list(params).then((r: { data: unknown }) => r.data),
    staleTime: 2 * 60 * 1000,
  })
}

// Convenience: all active users — used in assignee/member selectors across the app
export function useAllUsers(): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['users'],
    queryFn: () => usersApi.list().then((r: { data: unknown }) => r.data),
    staleTime: 2 * 60 * 1000,
  })
}

// ── Single ────────────────────────────────────────────────────────────────────
export function useUser(id: string | undefined): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['user', id],
    queryFn: () => usersApi.get(id).then((r: { data: unknown }) => r.data),
    enabled: !!id,
    staleTime: 5 * 60 * 1000,
  })
}

// ── Mutations ─────────────────────────────────────────────────────────────────
export function useCreateUser(): UseMutationResult<unknown, unknown, Partial<User>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<User>) => usersApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }),
  })
}

export function useUpdateUser(): UseMutationResult<unknown, unknown, UpdateArgs<Partial<User>>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: UpdateArgs<Partial<User>>) => usersApi.update(id, data),
    onSuccess: (_: unknown, { id }: UpdateArgs<Partial<User>>) => {
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
