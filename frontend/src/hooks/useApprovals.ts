import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { UseQueryResult, UseMutationResult } from '@tanstack/react-query'
// TODO type: services/api still JS.
import { approvalsApi } from '../services/api'
import { queryKeys } from '../constants/queryKeys'
import { POLL_RELAXED_MS, STALE_5_MIN_MS, STALE_DEFAULT_MS } from '../constants/timings'

const STALE = 2 * 60 * 1000

export interface ApprovalWorkflow {
  id: string
  name?: string
  status?: string
  [extra: string]: unknown
}

export interface ApprovalRequest {
  id: string
  status?: string
  [extra: string]: unknown
}

export interface ApprovalGroup {
  id: string
  name?: string
  [extra: string]: unknown
}

export type ApprovalsListParams = Record<string, unknown>
export type UpdateArgs<T> = { id: string; data: T }
export type DecideArgs = { id: string; data: Record<string, unknown> }

// ── Workflows ─────────────────────────────────────────────────────────────────

export function useApprovalWorkflows(params: ApprovalsListParams = {}): UseQueryResult<unknown> {
  return useQuery({
    // TODO #82: migrate to queryKeys — workflows.list(filters) not yet defined in factory
    queryKey: ['approval-workflows', params],
    queryFn: () => approvalsApi.listWorkflows(params).then((r: { data: unknown }) => r.data),
    staleTime: STALE,
  })
}

export function useApprovalWorkflow(id: string | undefined): UseQueryResult<unknown> {
  return useQuery({
    // TODO #82: migrate to queryKeys — workflow detail not yet defined in factory
    queryKey: ['approval-workflow', id],
    queryFn: () => approvalsApi.getWorkflow(id).then((r: { data: unknown }) => r.data),
    enabled: !!id,
    staleTime: STALE,
  })
}

export function useApprovalTemplates(): UseQueryResult<unknown> {
  return useQuery({
    // TODO #82: migrate to queryKeys — approval templates not yet defined in factory
    queryKey: ['approval-templates'],
    queryFn: () => approvalsApi.listTemplates().then((r: { data: unknown }) => r.data),
    staleTime: STALE_5_MIN_MS,
  })
}

export function useCreateApprovalWorkflow(): UseMutationResult<unknown, unknown, Partial<ApprovalWorkflow>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<ApprovalWorkflow>) => approvalsApi.createWorkflow(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.approvals.workflows() }),
  })
}

export function useUpdateApprovalWorkflow(): UseMutationResult<unknown, unknown, UpdateArgs<Partial<ApprovalWorkflow>>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: UpdateArgs<Partial<ApprovalWorkflow>>) => approvalsApi.updateWorkflow(id, data),
    onSuccess: (_: unknown, { id }: UpdateArgs<Partial<ApprovalWorkflow>>) => {
      qc.invalidateQueries({ queryKey: queryKeys.approvals.workflows() })
      qc.invalidateQueries({ queryKey: ['approval-workflow', id] })
    },
  })
}

export function useDeleteApprovalWorkflow(): UseMutationResult<unknown, unknown, string> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => approvalsApi.deleteWorkflow(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.approvals.workflows() }),
  })
}

export function usePublishApprovalWorkflow(): UseMutationResult<unknown, unknown, string> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => approvalsApi.publishWorkflow(id),
    onSuccess: (_: unknown, id: string) => qc.invalidateQueries({ queryKey: ['approval-workflow', id] }),
  })
}

// ── Requests ──────────────────────────────────────────────────────────────────

export function useApprovalRequests(params: ApprovalsListParams = {}): UseQueryResult<unknown> {
  return useQuery({
    // TODO #82: migrate to queryKeys — approval requests list not yet defined in factory
    queryKey: ['approval-requests', params],
    queryFn: () => approvalsApi.listRequests(params).then((r: { data: unknown }) => r.data),
    staleTime: STALE,
  })
}

export function usePendingApprovalRequests(): UseQueryResult<unknown> {
  return useQuery({
    queryKey: queryKeys.approvals.pending(),
    queryFn: () => approvalsApi.pendingMyAction().then((r: { data: unknown }) => r.data),
    staleTime: STALE_DEFAULT_MS,
    refetchInterval: POLL_RELAXED_MS,
  })
}

export function useApprovalStats(): UseQueryResult<unknown> {
  return useQuery({
    // TODO #82: migrate to queryKeys — approval stats not yet defined in factory
    queryKey: ['approval-stats'],
    queryFn: () => approvalsApi.stats().then((r: { data: unknown }) => r.data),
    staleTime: STALE,
  })
}

export function useCreateApprovalRequest(): UseMutationResult<unknown, unknown, Partial<ApprovalRequest>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<ApprovalRequest>) => approvalsApi.createRequest(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['approval-requests'] }),
  })
}

export function useApproveRequest(): UseMutationResult<unknown, unknown, DecideArgs> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: DecideArgs) => approvalsApi.decide(id, { ...data, decision: 'approve' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['approval-requests'] })
      qc.invalidateQueries({ queryKey: queryKeys.approvals.pending() })
    },
  })
}

export function useRejectRequest(): UseMutationResult<unknown, unknown, DecideArgs> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: DecideArgs) => approvalsApi.decide(id, { ...data, decision: 'reject' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['approval-requests'] })
      qc.invalidateQueries({ queryKey: queryKeys.approvals.pending() })
    },
  })
}

export function useCancelApprovalRequest(): UseMutationResult<unknown, unknown, string> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => approvalsApi.cancel(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['approval-requests'] }),
  })
}

// ── Groups ────────────────────────────────────────────────────────────────────

export function useApprovalGroups(): UseQueryResult<unknown> {
  return useQuery({
    // TODO #82: migrate to queryKeys — approval groups not yet defined in factory
    queryKey: ['approval-groups'],
    queryFn: () => approvalsApi.listGroups().then((r: { data: unknown }) => r.data),
    staleTime: STALE_5_MIN_MS,
  })
}

export function useCreateApprovalGroup(): UseMutationResult<unknown, unknown, Partial<ApprovalGroup>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<ApprovalGroup>) => approvalsApi.createGroup(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['approval-groups'] }),
  })
}

export function useUpdateApprovalGroup(): UseMutationResult<unknown, unknown, UpdateArgs<Partial<ApprovalGroup>>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: UpdateArgs<Partial<ApprovalGroup>>) => approvalsApi.updateGroup(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['approval-groups'] }),
  })
}

export function useDeleteApprovalGroup(): UseMutationResult<unknown, unknown, string> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => approvalsApi.deleteGroup(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['approval-groups'] }),
  })
}
