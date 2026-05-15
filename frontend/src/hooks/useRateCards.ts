import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { UseQueryResult, UseMutationResult } from '@tanstack/react-query'
// TODO type: services/api still JS.
import { rateCardsApi } from '../services/api'

const STALE = 2 * 60 * 1000

export interface RateCard {
  id: string
  name?: string
  currency?: string
  [extra: string]: unknown
}

export type RateParams = Record<string, unknown>
export type UpdateArgs<T> = { id: string; data: T }
export type DuplicateArgs = { id: string; data: Record<string, unknown> }
export type EntryArgs = { id: string; data: Record<string, unknown> }
export type EntryUpdateArgs = { id: string; eid: string; data: Record<string, unknown> }
export type EntryDeleteArgs = { id: string; eid: string }

function unwrapList<T>(r: { data?: { items?: T[] } | T[] | null }): T[] {
  const d = r?.data
  if (Array.isArray(d)) return d
  return d?.items ?? []
}

export function useRateCards(): UseQueryResult<RateCard[]> {
  return useQuery<RateCard[]>({
    queryKey: ['rate-cards'],
    queryFn: () => rateCardsApi.list().then((r: { data?: { items?: RateCard[] } | RateCard[] | null }) => unwrapList<RateCard>(r)),
    staleTime: STALE,
  })
}

export function useRateCard(id: string | undefined): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['rate-card', id],
    queryFn: () => rateCardsApi.get(id).then((r: { data: unknown }) => r.data),
    enabled: !!id,
    staleTime: STALE,
  })
}

export function useEffectiveRate(params: RateParams = {}): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['effective-rate', params],
    queryFn: () => rateCardsApi.effectiveRate(params).then((r: { data: unknown }) => r.data),
    staleTime: STALE,
  })
}

export function useCreateRateCard(): UseMutationResult<unknown, unknown, Partial<RateCard>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<RateCard>) => rateCardsApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['rate-cards'] }),
  })
}

export function useUpdateRateCard(): UseMutationResult<unknown, unknown, UpdateArgs<Partial<RateCard>>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: UpdateArgs<Partial<RateCard>>) => rateCardsApi.update(id, data),
    onSuccess: (_: unknown, { id }: UpdateArgs<Partial<RateCard>>) => {
      qc.invalidateQueries({ queryKey: ['rate-cards'] })
      qc.invalidateQueries({ queryKey: ['rate-card', id] })
    },
  })
}

export function useDeleteRateCard(): UseMutationResult<unknown, unknown, string> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => rateCardsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['rate-cards'] }),
  })
}

export function useDuplicateRateCard(): UseMutationResult<unknown, unknown, DuplicateArgs> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: DuplicateArgs) => rateCardsApi.duplicate(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['rate-cards'] }),
  })
}

export function useAddRateCardEntry(): UseMutationResult<unknown, unknown, EntryArgs> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: EntryArgs) => rateCardsApi.addEntry(id, data),
    onSuccess: (_: unknown, { id }: EntryArgs) => qc.invalidateQueries({ queryKey: ['rate-card', id] }),
  })
}

export function useUpdateRateCardEntry(): UseMutationResult<unknown, unknown, EntryUpdateArgs> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, eid, data }: EntryUpdateArgs) => rateCardsApi.updateEntry(id, eid, data),
    onSuccess: (_: unknown, { id }: EntryUpdateArgs) => qc.invalidateQueries({ queryKey: ['rate-card', id] }),
  })
}

export function useDeleteRateCardEntry(): UseMutationResult<unknown, unknown, EntryDeleteArgs> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, eid }: EntryDeleteArgs) => rateCardsApi.deleteEntry(id, eid),
    onSuccess: (_: unknown, { id }: EntryDeleteArgs) => qc.invalidateQueries({ queryKey: ['rate-card', id] }),
  })
}
