import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { tasksApi } from '../services/api'

export function useTasks(params = {}) {
  return useQuery({
    queryKey: ['tasks', params],
    queryFn: () => tasksApi.list(params).then(r => r.data),
  })
}

export function useKanban(projectId) {
  return useQuery({
    queryKey: ['kanban', projectId],
    queryFn: () => tasksApi.kanban(projectId).then(r => r.data),
    enabled: !!projectId,
  })
}

export function useCreateTask() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data) => tasksApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tasks'] }),
  })
}

export function useUpdateTask() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => tasksApi.update(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] })
      qc.invalidateQueries({ queryKey: ['kanban'] })
    },
  })
}
