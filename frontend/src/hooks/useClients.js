/**
 * useClients — Centralized hook for client data.
 * Use this everywhere a client list or client detail is needed.
 * Canonical query key: ['clients']
 * Any mutation that creates/updates/deletes a client invalidates this key,
 * ensuring all modules see up-to-date client data.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { clientsApi } from '../services/api'

// ── List ──────────────────────────────────────────────────────────────────────
export function useClients(params = {}) {
  return useQuery({
    queryKey: ['clients', params],
    queryFn: () => clientsApi.list(params).then(r => r.data),
    staleTime: 2 * 60 * 1000,
  })
}

// Convenience: all clients with no filter — used in selectors across the app
export function useAllClients() {
  return useQuery({
    queryKey: ['clients'],
    queryFn: () => clientsApi.list().then(r => r.data),
    staleTime: 2 * 60 * 1000,
  })
}

// ── Single ────────────────────────────────────────────────────────────────────
export function useClient(id) {
  return useQuery({
    queryKey: ['client', id],
    queryFn: () => clientsApi.get(id).then(r => r.data),
    enabled: !!id,
    staleTime: 5 * 60 * 1000,
  })
}

// ── Mutations ─────────────────────────────────────────────────────────────────
export function useCreateClient() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data) => clientsApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['clients'] }),
  })
}

export function useUpdateClient() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => clientsApi.update(id, data),
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: ['clients'] })
      qc.invalidateQueries({ queryKey: ['client', id] })
    },
  })
}

export function useDeleteClient() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => clientsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['clients'] }),
  })
}
