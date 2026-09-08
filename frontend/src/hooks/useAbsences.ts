import { useQuery } from '@tanstack/react-query'
import type { UseQueryResult } from '@tanstack/react-query'
// TODO type: services/api still JS.
import { absencesApi } from '../services/api'

const STALE = 2 * 60 * 1000

export interface Absence {
  id: string
  user_id?: string
  status?: string
  start_date?: string
  end_date?: string
  [extra: string]: unknown
}

export type AbsenceListParams = Record<string, unknown>
export type RejectArgs = { id: string; data: Partial<Absence> }

function unwrapList<T>(r: { data?: { items?: T[] } | T[] | null }): T[] {
  const d = r?.data
  if (Array.isArray(d)) return d
  return d?.items ?? []
}

export function useMyAbsences(params: AbsenceListParams = {}): UseQueryResult<Absence[]> {
  return useQuery<Absence[]>({
    queryKey: ['absences-my', params],
    queryFn: () => absencesApi.my(params).then((r: { data?: { items?: Absence[] } | Absence[] | null }) => unwrapList<Absence>(r)),
    staleTime: STALE,
  })
}

export function usePendingAbsences(): UseQueryResult<Absence[]> {
  return useQuery<Absence[]>({
    queryKey: ['absences-pending'],
    queryFn: () => absencesApi.pending().then((r: { data?: { items?: Absence[] } | Absence[] | null }) => unwrapList<Absence>(r)),
    staleTime: STALE,
  })
}

export function useTeamAbsences(params: AbsenceListParams = {}): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['team-absences', params],
    queryFn: () => absencesApi.team(params).then((r: { data: unknown }) => r.data),
    staleTime: STALE,
  })
}

export function useAbsenceCalendar(year: number | string | undefined, month: number | string | undefined): UseQueryResult<unknown> {
  return useQuery({
    queryKey: ['absence-calendar', year, month],
    queryFn: () => absencesApi.calendar({ year, month }).then((r: { data: unknown }) => r.data),
    enabled: !!year && !!month,
    staleTime: STALE,
  })
}

