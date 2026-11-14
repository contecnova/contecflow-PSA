import { useQuery } from '@tanstack/react-query'
import type { UseQueryResult } from '@tanstack/react-query'
import { absencesApi } from '../services/api'
import type { Absence, CalendarioDeAusencias } from '../services/api/tipos-personas'

const STALE = 2 * 60 * 1000

export type { Absence }

export type AbsenceListParams = Record<string, unknown>
export type RejectArgs = { id: string; data: Partial<Absence> }

export function useMyAbsences(params: AbsenceListParams = {}): UseQueryResult<Absence[]> {
  return useQuery<Absence[]>({
    queryKey: ['absences-my', params],
    queryFn: () => absencesApi.my(params).then((r) => r.data),
    staleTime: STALE,
  })
}

export function usePendingAbsences(): UseQueryResult<Absence[]> {
  return useQuery<Absence[]>({
    queryKey: ['absences-pending'],
    queryFn: () => absencesApi.pending().then((r) => r.data),
    staleTime: STALE,
  })
}

export function useTeamAbsences(params: AbsenceListParams = {}): UseQueryResult<Absence[]> {
  return useQuery({
    queryKey: ['team-absences', params],
    queryFn: () => absencesApi.team(params).then((r) => r.data),
    staleTime: STALE,
  })
}

export function useAbsenceCalendar(year: number | string | undefined, month: number | string | undefined): UseQueryResult<CalendarioDeAusencias> {
  return useQuery({
    queryKey: ['absence-calendar', year, month],
    queryFn: () => absencesApi.calendar({ year, month }).then((r) => r.data),
    enabled: !!year && !!month,
    staleTime: STALE,
  })
}

