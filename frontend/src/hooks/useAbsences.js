import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { absencesApi } from '../services/api'

const STALE = 2 * 60 * 1000

export function useMyAbsences(params = {}) {
  return useQuery({
    queryKey: ['absences-my', params],
    queryFn: () => absencesApi.my(params).then(r => r.data?.items ?? r.data ?? []),
    staleTime: STALE,
  })
}

export function usePendingAbsences() {
  return useQuery({
    queryKey: ['absences-pending'],
    queryFn: () => absencesApi.pending().then(r => r.data?.items ?? r.data ?? []),
    staleTime: STALE,
  })
}

export function useTeamAbsences(params = {}) {
  return useQuery({
    queryKey: ['team-absences', params],
    queryFn: () => absencesApi.team(params).then(r => r.data),
    staleTime: STALE,
  })
}

export function useAbsenceCalendar(year, month) {
  return useQuery({
    queryKey: ['absence-calendar', year, month],
    queryFn: () => absencesApi.calendar({ year, month }).then(r => r.data),
    enabled: !!year && !!month,
    staleTime: STALE,
  })
}

export function useVacationPolicies() {
  return useQuery({
    queryKey: ['vacation-policies'],
    queryFn: () => absencesApi.policies().then(r => r.data),
    staleTime: STALE,
  })
}

export function useCreateAbsence() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data) => absencesApi.create(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['absences-my'] })
      qc.invalidateQueries({ queryKey: ['team-absences'] })
      qc.invalidateQueries({ queryKey: ['absence-calendar'] })
    },
  })
}

export function useApproveAbsence() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => absencesApi.approve(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['absences-pending'] })
      qc.invalidateQueries({ queryKey: ['team-absences'] })
    },
  })
}

export function useRejectAbsence() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => absencesApi.reject(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['absences-pending'] }),
  })
}

export function useDeleteAbsence() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => absencesApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['absences-my'] }),
  })
}
