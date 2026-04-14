import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { contractsApi } from '../services/api'

const STALE = 2 * 60 * 1000

export function useContracts(params = {}) {
  return useQuery({
    queryKey: ['contracts', params],
    queryFn: () => contractsApi.list(params).then(r => r.data),
    staleTime: STALE,
  })
}

export function useAllContracts() {
  return useQuery({
    queryKey: ['contracts'],
    queryFn: () => contractsApi.list().then(r => r.data),
    staleTime: STALE,
  })
}

export function useContract(id) {
  return useQuery({
    queryKey: ['contracts', id],
    queryFn: () => contractsApi.get(id).then(r => r.data),
    enabled: !!id,
    staleTime: STALE,
  })
}

export function useCreateContract() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data) => contractsApi.create(data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['contracts'] }); qc.invalidateQueries({ queryKey: ['clients'] }) },
  })
}

export function useUpdateContract() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => contractsApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['contracts'] }),
  })
}

export function useDeleteContract() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => contractsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['contracts'] }),
  })
}
