import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { imputationsApi } from '../services/api'

export function useMyWeek(weekStart) {
  return useQuery({
    queryKey: ['my-week', weekStart],
    queryFn: () => imputationsApi.myWeek(weekStart ? { week_start: weekStart } : {}).then(r => r.data),
  })
}

export function useImputations(params = {}) {
  return useQuery({
    queryKey: ['imputations', params],
    queryFn: () => imputationsApi.list(params).then(r => r.data),
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
