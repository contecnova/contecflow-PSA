import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { approvalsApi } from '../services/api'
import { queryKeys } from '../constants/queryKeys'

const STALE = 2 * 60 * 1000

// ── Workflows ─────────────────────────────────────────────────────────────────

export function useApprovalWorkflows(params = {}) {
  return useQuery({
    // TODO #82: migrate to queryKeys — workflows.list(filters) not yet defined in factory
    queryKey: ['approval-workflows', params],
    queryFn: () => approvalsApi.listWorkflows(params).then(r => r.data),
    staleTime: STALE,
  })
}

export function useApprovalWorkflow(id) {
  return useQuery({
    // TODO #82: migrate to queryKeys — workflow detail not yet defined in factory
    queryKey: ['approval-workflow', id],
    queryFn: () => approvalsApi.getWorkflow(id).then(r => r.data),
    enabled: !!id,
    staleTime: STALE,
  })
}

export function useApprovalTemplates() {
  return useQuery({
    // TODO #82: migrate to queryKeys — approval templates not yet defined in factory
    queryKey: ['approval-templates'],
    queryFn: () => approvalsApi.listTemplates().then(r => r.data),
    staleTime: 5 * 60 * 1000,
  })
}

export function useCreateApprovalWorkflow() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data) => approvalsApi.createWorkflow(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.approvals.workflows() }),
  })
}

export function useUpdateApprovalWorkflow() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => approvalsApi.updateWorkflow(id, data),
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: queryKeys.approvals.workflows() })
      qc.invalidateQueries({ queryKey: ['approval-workflow', id] })
    },
  })
}

export function useDeleteApprovalWorkflow() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => approvalsApi.deleteWorkflow(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.approvals.workflows() }),
  })
}

export function usePublishApprovalWorkflow() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => approvalsApi.publishWorkflow(id),
    onSuccess: (_, id) => qc.invalidateQueries({ queryKey: ['approval-workflow', id] }),
  })
}

// ── Requests ──────────────────────────────────────────────────────────────────

export function useApprovalRequests(params = {}) {
  return useQuery({
    // TODO #82: migrate to queryKeys — approval requests list not yet defined in factory
    queryKey: ['approval-requests', params],
    queryFn: () => approvalsApi.listRequests(params).then(r => r.data),
    staleTime: STALE,
  })
}

export function usePendingApprovalRequests() {
  return useQuery({
    queryKey: queryKeys.approvals.pending(),
    queryFn: () => approvalsApi.pendingMyAction().then(r => r.data),
    staleTime: 60 * 1000,
    refetchInterval: 2 * 60 * 1000,
  })
}

export function useApprovalStats() {
  return useQuery({
    // TODO #82: migrate to queryKeys — approval stats not yet defined in factory
    queryKey: ['approval-stats'],
    queryFn: () => approvalsApi.stats().then(r => r.data),
    staleTime: STALE,
  })
}

export function useCreateApprovalRequest() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data) => approvalsApi.createRequest(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['approval-requests'] }),
  })
}

export function useApproveRequest() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => approvalsApi.decide(id, { ...data, decision: 'approve' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['approval-requests'] })
      qc.invalidateQueries({ queryKey: queryKeys.approvals.pending() })
    },
  })
}

export function useRejectRequest() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => approvalsApi.decide(id, { ...data, decision: 'reject' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['approval-requests'] })
      qc.invalidateQueries({ queryKey: queryKeys.approvals.pending() })
    },
  })
}

export function useCancelApprovalRequest() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => approvalsApi.cancel(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['approval-requests'] }),
  })
}

// ── Groups ────────────────────────────────────────────────────────────────────

export function useApprovalGroups() {
  return useQuery({
    // TODO #82: migrate to queryKeys — approval groups not yet defined in factory
    queryKey: ['approval-groups'],
    queryFn: () => approvalsApi.listGroups().then(r => r.data),
    staleTime: 5 * 60 * 1000,
  })
}

export function useCreateApprovalGroup() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data) => approvalsApi.createGroup(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['approval-groups'] }),
  })
}

export function useUpdateApprovalGroup() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => approvalsApi.updateGroup(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['approval-groups'] }),
  })
}

export function useDeleteApprovalGroup() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => approvalsApi.deleteGroup(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['approval-groups'] }),
  })
}
