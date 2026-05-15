/**
 * useClients — Centralized hook for client data.
 * Use this everywhere a client list or client detail is needed.
 * Canonical query key: ['clients']
 * Any mutation that creates/updates/deletes a client invalidates this key,
 * ensuring all modules see up-to-date client data.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { UseQueryResult, UseMutationResult } from '@tanstack/react-query'
// TODO type: services/api still JS.
import { clientsApi } from '../services/api'

export interface Client {
  id: string
  name?: string
  status?: string
  [extra: string]: unknown
}

export type ClientListParams = Record<string, unknown>
export type UpdateArgs<T> = { id: string; data: T }

function unwrapList<T>(r: { data?: { items?: T[] } | T[] | null }): T[] {
  const d = r?.data
  if (Array.isArray(d)) return d
  return d?.items ?? []
}

// ── List ──────────────────────────────────────────────────────────────────────
export function useClients(params: ClientListParams = {}): UseQueryResult<Client[]> {
  return useQuery<Client[]>({
    queryKey: ['clients', params],
    queryFn: () => clientsApi.list(params).then((r: { data?: { items?: Client[] } | Client[] | null }) => unwrapList<Client>(r)),
    staleTime: 2 * 60 * 1000,
  })
}

// Convenience: all clients with no filter — used in selectors across the app
export function useAllClients(): UseQueryResult<Client[]> {
  return useQuery<Client[]>({
    queryKey: ['clients'],
    queryFn: () => clientsApi.list().then((r: { data?: { items?: Client[] } | Client[] | null }) => unwrapList<Client>(r)),
    staleTime: 2 * 60 * 1000,
  })
}

// ── Single ────────────────────────────────────────────────────────────────────
export function useClient(id: string | undefined): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['client', id],
    queryFn: () => clientsApi.get(id).then((r: { data: unknown }) => r.data),
    enabled: !!id,
    staleTime: 5 * 60 * 1000,
  })
}

// ── Mutations ─────────────────────────────────────────────────────────────────
export function useCreateClient(): UseMutationResult<unknown, unknown, Partial<Client>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<Client>) => clientsApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['clients'] }),
  })
}

export function useUpdateClient(): UseMutationResult<unknown, unknown, UpdateArgs<Partial<Client>>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: UpdateArgs<Partial<Client>>) => clientsApi.update(id, data),
    onSuccess: (_: unknown, { id }: UpdateArgs<Partial<Client>>) => {
      qc.invalidateQueries({ queryKey: ['clients'] })
      qc.invalidateQueries({ queryKey: ['client', id] })
    },
  })
}

export function useDeleteClient(): UseMutationResult<unknown, unknown, string> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => clientsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['clients'] }),
  })
}
