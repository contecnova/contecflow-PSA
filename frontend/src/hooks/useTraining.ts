import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { UseQueryResult, UseMutationResult } from '@tanstack/react-query'
// TODO type: services/api still JS.
import { trainingApi } from '../services/api'

const STALE = 2 * 60 * 1000

export interface TrainingCourse {
  id: string
  title?: string
  [extra: string]: unknown
}

export interface TrainingCert {
  id: string
  title?: string
  [extra: string]: unknown
}

export interface TrainingEnrollment {
  id: string
  user_id?: string
  course_id?: string
  [extra: string]: unknown
}

export type TrainingParams = Record<string, unknown>
export type UpdateArgs<T> = { id: string; data: T }

function unwrapList<T>(r: { data?: { items?: T[] } | T[] | null }): T[] {
  const d = r?.data
  if (Array.isArray(d)) return d
  return d?.items ?? []
}

export function useTrainingCourses(params: TrainingParams = {}): UseQueryResult<TrainingCourse[]> {
  return useQuery<TrainingCourse[]>({
    queryKey: ['training-courses', params],
    queryFn: () => trainingApi.courses(params).then((r: { data?: { items?: TrainingCourse[] } | TrainingCourse[] | null }) => unwrapList<TrainingCourse>(r)),
    staleTime: STALE,
  })
}

export function useTrainingCerts(params: TrainingParams = {}): UseQueryResult<TrainingCert[]> {
  return useQuery<TrainingCert[]>({
    queryKey: ['training-certs', params],
    queryFn: () => trainingApi.certs(params).then((r: { data?: { items?: TrainingCert[] } | TrainingCert[] | null }) => unwrapList<TrainingCert>(r)),
    staleTime: STALE,
  })
}

export function useTrainingEnrollments(params: TrainingParams = {}): UseQueryResult<TrainingEnrollment[]> {
  return useQuery<TrainingEnrollment[]>({
    queryKey: ['training-enrollments', params],
    queryFn: () => trainingApi.enrollments(params).then((r: { data?: { items?: TrainingEnrollment[] } | TrainingEnrollment[] | null }) => unwrapList<TrainingEnrollment>(r)),
    staleTime: STALE,
  })
}

export function useCreateCourse(): UseMutationResult<unknown, unknown, Partial<TrainingCourse>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<TrainingCourse>) => trainingApi.createCourse(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['training-courses'] }),
  })
}

export function useUpdateCourse(): UseMutationResult<unknown, unknown, UpdateArgs<Partial<TrainingCourse>>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: UpdateArgs<Partial<TrainingCourse>>) => trainingApi.updateCourse(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['training-courses'] }),
  })
}

export function useDeleteCourse(): UseMutationResult<unknown, unknown, string> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => trainingApi.deleteCourse(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['training-courses'] }),
  })
}

export function useCreateCert(): UseMutationResult<unknown, unknown, Partial<TrainingCert>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<TrainingCert>) => trainingApi.createCert(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['training-certs'] }),
  })
}

export function useUpdateCert(): UseMutationResult<unknown, unknown, UpdateArgs<Partial<TrainingCert>>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: UpdateArgs<Partial<TrainingCert>>) => trainingApi.updateCert(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['training-certs'] }),
  })
}

export function useDeleteCert(): UseMutationResult<unknown, unknown, string> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => trainingApi.deleteCert(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['training-certs'] }),
  })
}

export function useEnroll(): UseMutationResult<unknown, unknown, Partial<TrainingEnrollment>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<TrainingEnrollment>) => trainingApi.enroll(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['training-enrollments'] }),
  })
}
