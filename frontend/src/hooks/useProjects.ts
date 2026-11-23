import { useQuery } from '@tanstack/react-query'
import type { UseQueryResult } from '@tanstack/react-query'
// TODO type: services/api still JS.
import { projectsApi } from '../services/api'
import type { MemberAddPayload, ProjectListItem } from '../services/api'
import { queryKeys } from '../constants/queryKeys'
import { STALE_REFERENCE_DATA_MS } from '../constants/timings'

/** Elemento de `GET /projects` (`ProjectListItem` de services/api/projects). */
export type Project = ProjectListItem

export type ProjectListParams = Record<string, unknown>
export type UpdateArgs<T> = { id: string; data: T }
export type AddMemberArgs = { id: string; data: MemberAddPayload }
export type RemoveMemberArgs = { id: string; memberId: string }

export function useProjects(params: ProjectListParams = {}): UseQueryResult<Project[]> {
  return useQuery<Project[]>({
    queryKey: queryKeys.projects.list(params),
    queryFn: () => projectsApi.list(params).then((r) => r.data),
    staleTime: STALE_REFERENCE_DATA_MS,
  })
}

// Convenience: all projects with no filter — used in selectors across the app
export function useAllProjects(): UseQueryResult<Project[]> {
  return useQuery<Project[]>({
    queryKey: queryKeys.projects.all(),
    queryFn: () => projectsApi.list({}).then((r) => r.data),
    staleTime: STALE_REFERENCE_DATA_MS,
  })
}

export function useProject(id: string | undefined): UseQueryResult<unknown> {
  return useQuery({
    queryKey: queryKeys.projects.detail(id),
    queryFn: () => projectsApi.get(id!).then((r) => r.data),
    enabled: !!id,
  })
}

