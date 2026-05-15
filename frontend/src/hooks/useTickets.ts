import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { UseQueryResult, UseMutationResult } from '@tanstack/react-query'
// TODO type: services/api still JS.
import { ticketsApi } from '../services/api'

const STALE = 60 * 1000  // 1 min — tickets change more frequently

export interface Ticket {
  id: string
  title?: string
  status?: string
  priority?: string
  [extra: string]: unknown
}

export type TicketListParams = Record<string, unknown>
export type UpdateArgs<T> = { id: string; data: T }
export type CloseArgs = { id: string; data: Record<string, unknown> }
export type CommentArgs = { id: string; data: Record<string, unknown> }
export type EscalateArgs = { id: string; level: string | number }
export type TimelogArgs = { id: string; data: Record<string, unknown> }
export type AiSuggestArgs = { id: string; data: Record<string, unknown> }

export function useTickets(params: TicketListParams = {}): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['sd-tickets', params],
    queryFn: () => ticketsApi.list(params).then((r: { data: unknown }) => r.data),
    staleTime: STALE,
  })
}

export function useTicket(id: string | undefined): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['sd-ticket', id],
    queryFn: () => ticketsApi.get(id).then((r: { data: unknown }) => r.data),
    enabled: !!id,
    staleTime: STALE,
  })
}

export function useCreateTicket(): UseMutationResult<unknown, unknown, Partial<Ticket>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<Ticket>) => ticketsApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sd-tickets'] }),
  })
}

export function useUpdateTicket(): UseMutationResult<unknown, unknown, UpdateArgs<Partial<Ticket>>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: UpdateArgs<Partial<Ticket>>) => ticketsApi.update(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sd-tickets'] })
      qc.invalidateQueries({ queryKey: ['sd-ticket'] })
    },
  })
}

export function useCloseTicket(): UseMutationResult<unknown, unknown, CloseArgs> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: CloseArgs) => ticketsApi.close(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sd-tickets'] }),
  })
}

export function useCommentTicket(): UseMutationResult<unknown, unknown, CommentArgs> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: CommentArgs) => ticketsApi.comment(id, data),
    onSuccess: (_: unknown, { id }: CommentArgs) => qc.invalidateQueries({ queryKey: ['sd-ticket', id] }),
  })
}

// NOTE: SD tickets do not have a hard-delete endpoint — use useCloseTicket to close them.

export function useTicketMyQueue(): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['sd-tickets-my-queue'],
    queryFn: () => ticketsApi.myQueue().then((r: { data: unknown }) => r.data),
    staleTime: STALE,
    refetchInterval: 60 * 1000,
  })
}

export function useEscalateTicket(): UseMutationResult<unknown, unknown, EscalateArgs> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, level }: EscalateArgs) => ticketsApi.escalate(id, level),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sd-tickets'] })
      qc.invalidateQueries({ queryKey: ['sd-ticket'] })
    },
  })
}

export function useTicketInternalComments(ticketId: string | undefined): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['sd-ticket-internal-comments', ticketId],
    queryFn: () => ticketsApi.internalComments(ticketId).then((r: { data: unknown }) => r.data),
    enabled: !!ticketId,
    staleTime: STALE,
  })
}

export function useAddTicketInternalComment(): UseMutationResult<unknown, unknown, CommentArgs> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: CommentArgs) => ticketsApi.createInternalComment(id, data),
    onSuccess: (_: unknown, { id }: CommentArgs) => qc.invalidateQueries({ queryKey: ['sd-ticket-internal-comments', id] }),
  })
}

export function useTicketTimelog(): UseMutationResult<unknown, unknown, TimelogArgs> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: TimelogArgs) => ticketsApi.timelog(id, data),
    onSuccess: (_: unknown, { id }: TimelogArgs) => qc.invalidateQueries({ queryKey: ['sd-ticket', id] }),
  })
}

export function useAiSuggestTicket(): UseMutationResult<unknown, unknown, AiSuggestArgs> {
  return useMutation({
    mutationFn: ({ id, data }: AiSuggestArgs) => ticketsApi.aiSuggest(id, data),
  })
}
