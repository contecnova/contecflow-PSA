import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { subcontractorsApi } from '../services/api'

const STALE = 2 * 60 * 1000

export function useSubcontractors(params = {}) {
  return useQuery({
    queryKey: ['subcontractors', params],
    queryFn: () => subcontractorsApi.list(params).then(r => r.data),
    staleTime: STALE,
  })
}

export function useAllSubcontractors() {
  return useQuery({
    queryKey: ['subcontractors'],
    queryFn: () => subcontractorsApi.list().then(r => r.data),
    staleTime: STALE,
  })
}

export function useCreateSubcontractor() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data) => subcontractorsApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['subcontractors'] }),
  })
}

export function useUpdateSubcontractor() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => subcontractorsApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['subcontractors'] }),
  })
}

export function useDeleteSubcontractor() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => subcontractorsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['subcontractors'] }),
  })
}
