import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { epicsApi } from '../services/api'

const STALE = 2 * 60 * 1000

export function useEpics(projectId) {
  return useQuery({
    queryKey: ['epics', projectId],
    queryFn: () => epicsApi.list(projectId).then(r => r.data),
    enabled: !!projectId,
    staleTime: STALE,
  })
}

export function useAllEpics() {
  return useQuery({
    queryKey: ['epics'],
    queryFn: () => epicsApi.list().then(r => r.data),
    staleTime: STALE,
  })
}

export function useCreateEpic() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data) => epicsApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['epics'] }),
  })
}

export function useUpdateEpic() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => epicsApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['epics'] }),
  })
}

export function useDeleteEpic() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => epicsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['epics'] }),
  })
}
