import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { UseQueryResult, UseMutationResult } from '@tanstack/react-query'
import { trainingApi } from '../services/api'
import type { Certificacion, Curso, Inscripcion } from '../services/api/tipos-personas'

const STALE = 2 * 60 * 1000

export type TrainingCourse = Curso
export type TrainingCert = Certificacion
export type TrainingEnrollment = Inscripcion

export type TrainingParams = Record<string, unknown>
export type UpdateArgs<T> = { id: string; data: T }

export function useTrainingCourses(params: TrainingParams = {}): UseQueryResult<TrainingCourse[]> {
  return useQuery<TrainingCourse[]>({
    queryKey: ['training-courses', params],
    queryFn: () => trainingApi.courses(params).then((r) => r.data),
    staleTime: STALE,
  })
}

export function useTrainingCerts(params: TrainingParams = {}): UseQueryResult<TrainingCert[]> {
  return useQuery<TrainingCert[]>({
    queryKey: ['training-certs', params],
    queryFn: () => trainingApi.certs(params).then((r) => r.data),
    staleTime: STALE,
  })
}

export function useTrainingEnrollments(params: TrainingParams = {}): UseQueryResult<TrainingEnrollment[]> {
  return useQuery<TrainingEnrollment[]>({
    queryKey: ['training-enrollments', params],
    queryFn: () => trainingApi.enrollments(params).then((r) => r.data),
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
