import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { tasksApi } from '../services/api'

const STALE = 60 * 1000 // 1 min — operational data

export function useTasks(params = {}) {
  return useQuery({
    queryKey: ['tasks', params],
    queryFn: () => tasksApi.list(params).then(r => r.data),
    staleTime: STALE,
  })
}

export function useTask(id) {
  return useQuery({
    queryKey: ['task', id],
    queryFn: () => tasksApi.get(id).then(r => r.data),
    enabled: !!id,
    staleTime: STALE,
  })
}

export function useKanban(projectId) {
  return useQuery({
    queryKey: ['kanban', projectId],
    queryFn: () => tasksApi.kanban(projectId).then(r => r.data),
    enabled: !!projectId,
    staleTime: STALE,
  })
}

export function useTaskComments(taskId) {
  return useQuery({
    queryKey: ['task-comments', taskId],
    queryFn: () => tasksApi.comment(taskId, null).then(r => r.data).catch(() => []),
    enabled: !!taskId,
    staleTime: STALE,
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
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: ['tasks'] })
      qc.invalidateQueries({ queryKey: ['kanban'] })
      qc.invalidateQueries({ queryKey: ['task', id] })
    },
  })
}

export function useDeleteTask() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => tasksApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] })
      qc.invalidateQueries({ queryKey: ['kanban'] })
    },
  })
}

export function useBulkUpdateTasks() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data) => tasksApi.bulkUpdate(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] })
      qc.invalidateQueries({ queryKey: ['kanban'] })
    },
  })
}

export function useAddTaskComment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => tasksApi.comment(id, data),
    onSuccess: (_, { id }) => qc.invalidateQueries({ queryKey: ['task-comments', id] }),
  })
}

export function useTaskMovementLog(taskId) {
  return useQuery({
    queryKey: ['task-movement-log', taskId],
    queryFn: () => tasksApi.movementLog(taskId).then(r => r.data),
    enabled: !!taskId,
    staleTime: 0,
  })
}
