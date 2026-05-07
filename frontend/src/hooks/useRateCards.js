import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { rateCardsApi } from '../services/api'

const STALE = 2 * 60 * 1000

export function useRateCards() {
  return useQuery({
    queryKey: ['rate-cards'],
    queryFn: () => rateCardsApi.list().then(r => r.data),
    staleTime: STALE,
  })
}

export function useRateCard(id) {
  return useQuery({
    queryKey: ['rate-card', id],
    queryFn: () => rateCardsApi.get(id).then(r => r.data),
    enabled: !!id,
    staleTime: STALE,
  })
}

export function useEffectiveRate(params = {}) {
  return useQuery({
    queryKey: ['effective-rate', params],
    queryFn: () => rateCardsApi.effectiveRate(params).then(r => r.data),
    staleTime: STALE,
  })
}

export function useCreateRateCard() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data) => rateCardsApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['rate-cards'] }),
  })
}

export function useUpdateRateCard() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => rateCardsApi.update(id, data),
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: ['rate-cards'] })
      qc.invalidateQueries({ queryKey: ['rate-card', id] })
    },
  })
}

export function useDeleteRateCard() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => rateCardsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['rate-cards'] }),
  })
}

export function useDuplicateRateCard() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => rateCardsApi.duplicate(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['rate-cards'] }),
  })
}

export function useAddRateCardEntry() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => rateCardsApi.addEntry(id, data),
    onSuccess: (_, { id }) => qc.invalidateQueries({ queryKey: ['rate-card', id] }),
  })
}

export function useUpdateRateCardEntry() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, eid, data }) => rateCardsApi.updateEntry(id, eid, data),
    onSuccess: (_, { id }) => qc.invalidateQueries({ queryKey: ['rate-card', id] }),
  })
}

export function useDeleteRateCardEntry() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, eid }) => rateCardsApi.deleteEntry(id, eid),
    onSuccess: (_, { id }) => qc.invalidateQueries({ queryKey: ['rate-card', id] }),
  })
}
