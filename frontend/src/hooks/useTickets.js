import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ticketsApi } from '../services/api'

const STALE = 60 * 1000  // 1 min — tickets change more frequently

export function useTickets(params = {}) {
  return useQuery({
    queryKey: ['sd-tickets', params],
    queryFn: () => ticketsApi.list(params).then(r => r.data),
    staleTime: STALE,
  })
}

export function useTicket(id) {
  return useQuery({
    queryKey: ['sd-ticket', id],
    queryFn: () => ticketsApi.get(id).then(r => r.data),
    enabled: !!id,
    staleTime: STALE,
  })
}

export function useCreateTicket() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data) => ticketsApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sd-tickets'] }),
  })
}

export function useUpdateTicket() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => ticketsApi.update(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sd-tickets'] })
      qc.invalidateQueries({ queryKey: ['sd-ticket'] })
    },
  })
}

export function useCloseTicket() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => ticketsApi.close(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sd-tickets'] }),
  })
}

export function useCommentTicket() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => ticketsApi.comment(id, data),
    onSuccess: (_, { id }) => qc.invalidateQueries({ queryKey: ['sd-ticket', id] }),
  })
}
