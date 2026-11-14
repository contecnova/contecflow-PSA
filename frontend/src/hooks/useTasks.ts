import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { UseQueryResult, UseMutationResult } from '@tanstack/react-query'
// TODO type: services/api still JS.
import { tasksApi } from '../services/api'
import type { TaskCreatePayload, TaskUpdatePayload, TaskBulkUpdatePayload, TaskCommentPayload, TaskListItem } from '../services/api/tasks'
import { queryKeys } from '../constants/queryKeys'
import { STALE_ALWAYS } from '../constants/timings'

const STALE = 60 * 1000 // 1 min — operational data

/** Elemento de `GET /tasks` (`TaskListItem` de services/api/tasks). */
export type Task = TaskListItem

export type TaskListParams = Record<string, unknown>
export type UpdateArgs<T> = { id: string; data: T }
export type CommentArgs = { id: string; data: TaskCommentPayload }
export type BulkUpdateArgs = TaskBulkUpdatePayload

export function useTasks(params: TaskListParams = {}): UseQueryResult<Task[]> {
  return useQuery<Task[]>({
    queryKey: queryKeys.tasks.list(params),
    queryFn: () => tasksApi.list(params).then((r) => r.data),
    staleTime: STALE,
  })
}

export function useTask(id: string | undefined): UseQueryResult<unknown> {
  return useQuery({
    queryKey: queryKeys.tasks.detail(id),
    // `!` respaldado por el `enabled` de abajo: react-query no ejecuta
    // `queryFn` mientras `enabled` sea falso, asi que aqui el id nunca
    // es undefined. Sin esa garantia habria que cambiar la firma.
    queryFn: () => tasksApi.get(id!).then((r: { data: unknown }) => r.data),
    enabled: !!id,
    staleTime: STALE,
  })
}

export function useKanban(projectId: string | undefined): UseQueryResult<unknown> {
  return useQuery({
    // TODO #82: migrate to queryKeys — kanban is task-derived per project but lacks a dedicated factory entry
    queryKey: ['kanban', projectId],
    // `!` respaldado por el `enabled` de abajo: react-query no ejecuta
    // `queryFn` mientras `enabled` sea falso, asi que aqui el id nunca
    // es undefined. Sin esa garantia habria que cambiar la firma.
    queryFn: () => tasksApi.kanban(projectId!).then((r: { data: unknown }) => r.data),
    enabled: !!projectId,
    staleTime: STALE,
  })
}


export function useCreateTask(): UseMutationResult<unknown, unknown, TaskCreatePayload> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: TaskCreatePayload) => tasksApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.tasks.all() }),
  })
}

export function useUpdateTask(): UseMutationResult<unknown, unknown, UpdateArgs<TaskUpdatePayload>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: UpdateArgs<TaskUpdatePayload>) => tasksApi.update(id, data),
    onSuccess: (_: unknown, { id }: UpdateArgs<TaskUpdatePayload>) => {
      qc.invalidateQueries({ queryKey: queryKeys.tasks.all() })
      qc.invalidateQueries({ queryKey: ['kanban'] })
      qc.invalidateQueries({ queryKey: queryKeys.tasks.detail(id) })
    },
  })
}

export function useDeleteTask(): UseMutationResult<unknown, unknown, string> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => tasksApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.tasks.all() })
      qc.invalidateQueries({ queryKey: ['kanban'] })
    },
  })
}

export function useBulkUpdateTasks(): UseMutationResult<unknown, unknown, BulkUpdateArgs> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: BulkUpdateArgs) => tasksApi.bulkUpdate(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.tasks.all() })
      qc.invalidateQueries({ queryKey: ['kanban'] })
    },
  })
}

export function useAddTaskComment(): UseMutationResult<unknown, unknown, CommentArgs> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: CommentArgs) => tasksApi.comment(id, data),
    onSuccess: (_: unknown, { id }: CommentArgs) => qc.invalidateQueries({ queryKey: queryKeys.tasks.comments(id) }),
  })
}

export function useTaskMovementLog(taskId: string | undefined): UseQueryResult<unknown[]> {
  return useQuery<unknown[]>({
    // TODO #82: migrate to queryKeys — movement log is task-derived but lacks a dedicated factory entry
    queryKey: ['task-movement-log', taskId],
    // `!` respaldado por el `enabled` de abajo: react-query no ejecuta
    // `queryFn` mientras `enabled` sea falso, asi que aqui el id nunca
    // es undefined. Sin esa garantia habria que cambiar la firma.
    queryFn: () => tasksApi.movementLog(taskId!).then((r: { data?: { items?: unknown[] } | unknown[] | null }) => {
      const d = r?.data
      if (Array.isArray(d)) return d
      return (d as { items?: unknown[] } | null)?.items ?? []
    }),
    enabled: !!taskId,
    staleTime: STALE_ALWAYS,
  })
}
