import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { imputationsApi } from '../services/api'

const STALE = 60 * 1000 // 1 min — operational data

export function useMyWeek(weekStart) {
  return useQuery({
    queryKey: ['my-week', weekStart],
    queryFn: () => imputationsApi.myWeek(weekStart ? { week_start: weekStart } : {}).then(r => r.data),
    staleTime: STALE,
  })
}

export function useImputations(params = {}) {
  return useQuery({
    queryKey: ['imputations', params],
    queryFn: () => imputationsApi.list(params).then(r => r.data),
    staleTime: STALE,
  })
}

export function useCreateImputation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data) => imputationsApi.create(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['my-week'] })
      qc.invalidateQueries({ queryKey: ['imputations'] })
    },
  })
}

export function useDeleteImputation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => imputationsApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['my-week'] })
      qc.invalidateQueries({ queryKey: ['imputations'] })
    },
  })
}

export function useUpdateImputation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => imputationsApi.update(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['my-week'] })
      qc.invalidateQueries({ queryKey: ['imputations'] })
    },
  })
}

export function useApproveImputation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => imputationsApi.approve(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['imputations'] }),
  })
}

export function useRejectImputation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => imputationsApi.reject(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['imputations'] }),
  })
}

export function useTimerCurrent() {
  return useQuery({
    queryKey: ['timer-current'],
    queryFn: () => imputationsApi.timerCurrent().then(r => r.data).catch(() => null),
    refetchInterval: 5000,
    staleTime: 0,
  })
}

export function useStartTimer() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data) => imputationsApi.timerStart(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['timer-current'] }),
  })
}

export function usePauseTimer() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => imputationsApi.timerPause(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['timer-current'] }),
  })
}

export function useResumeTimer() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => imputationsApi.timerResume(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['timer-current'] }),
  })
}

export function useStopTimer() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data) => imputationsApi.timerStop(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['timer-current'] })
      qc.invalidateQueries({ queryKey: ['my-week'] })
      qc.invalidateQueries({ queryKey: ['imputations'] })
    },
  })
}

export function useCancelTimer() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => imputationsApi.timerCancel(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['timer-current'] }),
  })
}
