/**
 * useUsers — Centralized hook for user data.
 * Use this everywhere a user list or user detail is needed.
 * Canonical query key: ['users']
 * All mutations invalidate this key so every module stays in sync.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { usersApi } from '../services/api'

// ── List ──────────────────────────────────────────────────────────────────────
export function useUsers(params = {}) {
  return useQuery({
    queryKey: ['users', params],
    queryFn: () => usersApi.list(params).then(r => r.data),
    staleTime: 2 * 60 * 1000,
  })
}

// Convenience: all active users — used in assignee/member selectors across the app
export function useAllUsers() {
  return useQuery({
    queryKey: ['users'],
    queryFn: () => usersApi.list().then(r => r.data),
    staleTime: 2 * 60 * 1000,
  })
}

// ── Single ────────────────────────────────────────────────────────────────────
export function useUser(id) {
  return useQuery({
    queryKey: ['user', id],
    queryFn: () => usersApi.get(id).then(r => r.data),
    enabled: !!id,
    staleTime: 5 * 60 * 1000,
  })
}

// ── Mutations ─────────────────────────────────────────────────────────────────
export function useCreateUser() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data) => usersApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }),
  })
}

export function useUpdateUser() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => usersApi.update(id, data),
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: ['users'] })
      qc.invalidateQueries({ queryKey: ['user', id] })
    },
  })
}

export function useDeactivateUser() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => usersApi.deactivate(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }),
  })
}
