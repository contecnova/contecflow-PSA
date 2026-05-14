import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { trainingApi } from '../services/api'

const STALE = 2 * 60 * 1000

export function useTrainingCourses(params = {}) {
  return useQuery({
    queryKey: ['training-courses', params],
    queryFn: () => trainingApi.courses(params).then(r => r.data?.items ?? r.data ?? []),
    staleTime: STALE,
  })
}

export function useTrainingCerts(params = {}) {
  return useQuery({
    queryKey: ['training-certs', params],
    queryFn: () => trainingApi.certs(params).then(r => r.data?.items ?? r.data ?? []),
    staleTime: STALE,
  })
}

export function useTrainingEnrollments(params = {}) {
  return useQuery({
    queryKey: ['training-enrollments', params],
    queryFn: () => trainingApi.enrollments(params).then(r => r.data?.items ?? r.data ?? []),
    staleTime: STALE,
  })
}

export function useCreateCourse() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data) => trainingApi.createCourse(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['training-courses'] }),
  })
}

export function useUpdateCourse() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => trainingApi.updateCourse(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['training-courses'] }),
  })
}

export function useDeleteCourse() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => trainingApi.deleteCourse(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['training-courses'] }),
  })
}

export function useCreateCert() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data) => trainingApi.createCert(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['training-certs'] }),
  })
}

export function useUpdateCert() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => trainingApi.updateCert(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['training-certs'] }),
  })
}

export function useDeleteCert() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => trainingApi.deleteCert(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['training-certs'] }),
  })
}

export function useEnroll() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data) => trainingApi.enroll(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['training-enrollments'] }),
  })
}
