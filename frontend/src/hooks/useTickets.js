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

// NOTE: SD tickets do not have a hard-delete endpoint — use useCloseTicket to close them.

export function useTicketMyQueue() {
  return useQuery({
    queryKey: ['sd-tickets-my-queue'],
    queryFn: () => ticketsApi.myQueue().then(r => r.data),
    staleTime: STALE,
    refetchInterval: 60 * 1000,
  })
}

export function useEscalateTicket() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, level }) => ticketsApi.escalate(id, level),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sd-tickets'] })
      qc.invalidateQueries({ queryKey: ['sd-ticket'] })
    },
  })
}

export function useTicketInternalComments(ticketId) {
  return useQuery({
    queryKey: ['sd-ticket-internal-comments', ticketId],
    queryFn: () => ticketsApi.internalComments(ticketId).then(r => r.data),
    enabled: !!ticketId,
    staleTime: STALE,
  })
}

export function useAddTicketInternalComment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => ticketsApi.createInternalComment(id, data),
    onSuccess: (_, { id }) => qc.invalidateQueries({ queryKey: ['sd-ticket-internal-comments', id] }),
  })
}

export function useTicketTimelog() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => ticketsApi.timelog(id, data),
    onSuccess: (_, { id }) => qc.invalidateQueries({ queryKey: ['sd-ticket', id] }),
  })
}

export function useAiSuggestTicket() {
  return useMutation({
    mutationFn: ({ id, data }) => ticketsApi.aiSuggest(id, data),
  })
}
