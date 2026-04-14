import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { problemsApi } from '../services/api'

const STALE = 2 * 60 * 1000

export function useProblems(params = {}) {
  return useQuery({
    queryKey: ['sd-problems', params],
    queryFn: () => problemsApi.list(params).then(r => r.data),
    staleTime: STALE,
  })
}

export function useAllProblems() {
  return useQuery({
    queryKey: ['sd-problems'],
    queryFn: () => problemsApi.list().then(r => r.data),
    staleTime: STALE,
  })
}

export function useCreateProblem() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data) => problemsApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sd-problems'] }),
  })
}

export function useUpdateProblem() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => problemsApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sd-problems'] }),
  })
}

export function useDeleteProblem() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => problemsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sd-problems'] }),
  })
}
