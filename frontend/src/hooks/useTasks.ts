import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { UseQueryResult, UseMutationResult } from '@tanstack/react-query'
// TODO type: services/api still JS.
import { tasksApi } from '../services/api'
import type { TaskCreatePayload, TaskUpdatePayload, TaskBulkUpdatePayload, TaskCommentPayload } from '../services/api/tasks'
import { queryKeys } from '../constants/queryKeys'

const STALE = 60 * 1000 // 1 min — operational data

export interface Task {
  id: string
  project_id?: string
  title?: string
  status?: string
  [extra: string]: unknown
}

export type TaskListParams = Record<string, unknown>
export type UpdateArgs<T> = { id: string; data: T }
export type CommentArgs = { id: string; data: Record<string, unknown> | null }
export type BulkUpdateArgs = Record<string, unknown>

function unwrapList<T>(r: { data?: { items?: T[] } | T[] | null }): T[] {
  const d = r?.data
  if (Array.isArray(d)) return d
  return d?.items ?? []
}

export function useTasks(params: TaskListParams = {}): UseQueryResult<Task[]> {
  return useQuery<Task[]>({
    queryKey: queryKeys.tasks.list(params),
    queryFn: () => tasksApi.list(params).then((r) => (r.data ?? []) as unknown as Task[]),
    staleTime: STALE,
  })
}

export function useTask(id: string | undefined): UseQueryResult<unknown> {
  return useQuery({
    queryKey: queryKeys.tasks.detail(id),
    queryFn: () => tasksApi.get(id).then((r: { data: unknown }) => r.data),
    enabled: !!id,
    staleTime: STALE,
  })
}

export function useKanban(projectId: string | undefined): UseQueryResult<unknown> {
  return useQuery({
    // TODO #82: migrate to queryKeys — kanban is task-derived per project but lacks a dedicated factory entry
    queryKey: ['kanban', projectId],
    queryFn: () => tasksApi.kanban(projectId).then((r: { data: unknown }) => r.data),
    enabled: !!projectId,
    staleTime: STALE,
  })
}

export function useTaskComments(taskId: string | undefined): UseQueryResult<unknown> {
  return useQuery({
    queryKey: queryKeys.tasks.comments(taskId),
    queryFn: () => tasksApi.comment(taskId, null).then((r: { data: unknown }) => r.data).catch(() => [] as unknown[]),
    enabled: !!taskId,
    staleTime: STALE,
  })
}

export function useCreateTask(): UseMutationResult<unknown, unknown, Partial<Task>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<Task>) => tasksApi.create(data as TaskCreatePayload),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.tasks.all() }),
  })
}

export function useUpdateTask(): UseMutationResult<unknown, unknown, UpdateArgs<Partial<Task>>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: UpdateArgs<Partial<Task>>) => tasksApi.update(id, data as TaskUpdatePayload),
    onSuccess: (_: unknown, { id }: UpdateArgs<Partial<Task>>) => {
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
    mutationFn: (data: BulkUpdateArgs) => tasksApi.bulkUpdate(data as unknown as TaskBulkUpdatePayload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.tasks.all() })
      qc.invalidateQueries({ queryKey: ['kanban'] })
    },
  })
}

export function useAddTaskComment(): UseMutationResult<unknown, unknown, CommentArgs> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: CommentArgs) => tasksApi.comment(id, data as unknown as TaskCommentPayload),
    onSuccess: (_: unknown, { id }: CommentArgs) => qc.invalidateQueries({ queryKey: queryKeys.tasks.comments(id) }),
  })
}

export function useTaskMovementLog(taskId: string | undefined): UseQueryResult<unknown[]> {
  return useQuery<unknown[]>({
    // TODO #82: migrate to queryKeys — movement log is task-derived but lacks a dedicated factory entry
    queryKey: ['task-movement-log', taskId],
    queryFn: () => tasksApi.movementLog(taskId).then((r: { data?: { items?: unknown[] } | unknown[] | null }) => {
      const d = r?.data
      if (Array.isArray(d)) return d
      return (d as { items?: unknown[] } | null)?.items ?? []
    }),
    enabled: !!taskId,
    staleTime: 0,
  })
}
