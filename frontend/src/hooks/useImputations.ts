import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { UseQueryResult, UseMutationResult } from '@tanstack/react-query'
// TODO type: services/api still JS.
import { imputationsApi } from '../services/api'
import { POLL_FAST_MS, STALE_ALWAYS } from '../constants/timings'

const STALE = 60 * 1000 // 1 min — operational data

export interface Imputation {
  id: string
  user_id?: string
  hours?: number
  status?: string
  [extra: string]: unknown
}

export type ImputationListParams = Record<string, unknown>
export type UpdateArgs<T> = { id: string; data: T }

function unwrapList<T>(r: { data?: { items?: T[] } | T[] | null }): T[] {
  const d = r?.data
  if (Array.isArray(d)) return d
  return d?.items ?? []
}

export function useMyWeek(weekStart: string | undefined): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['my-week', weekStart],
    queryFn: () => imputationsApi.myWeek(weekStart ? { week_start: weekStart } : {}).then((r: { data: unknown }) => r.data),
    staleTime: STALE,
  })
}

export function useImputations(params: ImputationListParams = {}): UseQueryResult<Imputation[]> {
  return useQuery<Imputation[]>({
    queryKey: ['imputations', params],
    queryFn: () => imputationsApi.list(params).then((r: { data?: { items?: Imputation[] } | Imputation[] | null }) => unwrapList<Imputation>(r)),
    staleTime: STALE,
  })
}

export function useCreateImputation(): UseMutationResult<unknown, unknown, Partial<Imputation>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<Imputation>) => imputationsApi.create(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['my-week'] })
      qc.invalidateQueries({ queryKey: ['imputations'] })
    },
  })
}

export function useDeleteImputation(): UseMutationResult<unknown, unknown, string> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => imputationsApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['my-week'] })
      qc.invalidateQueries({ queryKey: ['imputations'] })
    },
  })
}

export function useUpdateImputation(): UseMutationResult<unknown, unknown, UpdateArgs<Partial<Imputation>>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: UpdateArgs<Partial<Imputation>>) => imputationsApi.update(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['my-week'] })
      qc.invalidateQueries({ queryKey: ['imputations'] })
    },
  })
}

export function useApproveImputation(): UseMutationResult<unknown, unknown, string> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => imputationsApi.approve(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['imputations'] }),
  })
}

export function useRejectImputation(): UseMutationResult<unknown, unknown, string> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => imputationsApi.reject(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['imputations'] }),
  })
}

export function useTimerCurrent(): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['timer-current'],
    queryFn: () => imputationsApi.timerCurrent().then((r: { data: unknown }) => r.data).catch(() => null),
    refetchInterval: POLL_FAST_MS,
    staleTime: STALE_ALWAYS,
  })
}

export function useStartTimer(): UseMutationResult<unknown, unknown, Record<string, unknown>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Record<string, unknown>) => imputationsApi.timerStart(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['timer-current'] }),
  })
}

export function usePauseTimer(): UseMutationResult<unknown, unknown, void> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => imputationsApi.timerPause(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['timer-current'] }),
  })
}

export function useResumeTimer(): UseMutationResult<unknown, unknown, void> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => imputationsApi.timerResume(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['timer-current'] }),
  })
}

export function useStopTimer(): UseMutationResult<unknown, unknown, Record<string, unknown>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Record<string, unknown>) => imputationsApi.timerStop(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['timer-current'] })
      qc.invalidateQueries({ queryKey: ['my-week'] })
      qc.invalidateQueries({ queryKey: ['imputations'] })
    },
  })
}

export function useCancelTimer(): UseMutationResult<unknown, unknown, void> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => imputationsApi.timerCancel(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['timer-current'] }),
  })
}
