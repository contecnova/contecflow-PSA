import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { UseQueryResult, UseMutationResult } from '@tanstack/react-query'
// TODO type: services/api still JS.
import { projectsApi } from '../services/api'
import type { MemberAddPayload, ProjectCreatePayload, ProjectListItem, ProjectUpdatePayload } from '../services/api'
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

export function useCreateProject(): UseMutationResult<unknown, unknown, ProjectCreatePayload> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: ProjectCreatePayload) => projectsApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.projects.all() }),
  })
}

export function useUpdateProject(): UseMutationResult<unknown, unknown, UpdateArgs<ProjectUpdatePayload>> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: UpdateArgs<ProjectUpdatePayload>) => projectsApi.update(id, data),
    onSuccess: (_: unknown, { id }: UpdateArgs<ProjectUpdatePayload>) => {
      qc.invalidateQueries({ queryKey: queryKeys.projects.all() })
      qc.invalidateQueries({ queryKey: queryKeys.projects.detail(id) })
    },
  })
}

export function useDeleteProject(): UseMutationResult<unknown, unknown, string> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => projectsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.projects.all() }),
  })
}

export function useProjectTeam(projectId: string | undefined): UseQueryResult<unknown> {
  return useQuery({
    // TODO #82: migrate to queryKeys — team is project-derived but lacks a dedicated factory entry
    queryKey: ['project-team', projectId],
    queryFn: () => projectsApi.team(projectId!).then((r) => r.data),
    enabled: !!projectId,
    staleTime: STALE_REFERENCE_DATA_MS,
  })
}

export function useProjectMembers(projectId: string | undefined): UseQueryResult<unknown> {
  return useQuery({
    queryKey: queryKeys.projects.members(projectId),
    queryFn: () => projectsApi.members(projectId!).then((r) => r.data),
    enabled: !!projectId,
    staleTime: STALE_REFERENCE_DATA_MS,
  })
}

export function useProjectEVM(projectId: string | undefined): UseQueryResult<unknown> {
  return useQuery({
    // TODO #82: migrate to queryKeys — EVM is project-derived but lacks a dedicated factory entry
    queryKey: ['project-evm', projectId],
    queryFn: () => projectsApi.evm(projectId!).then((r) => r.data),
    enabled: !!projectId,
    staleTime: STALE_REFERENCE_DATA_MS,
  })
}

export function useProjectEVMPortfolio(): UseQueryResult<unknown> {
  return useQuery({
    // TODO #82: migrate to queryKeys — EVM portfolio lacks a dedicated factory entry
    queryKey: ['project-evm-portfolio'],
    queryFn: () => projectsApi.evmPortfolio().then((r) => r.data),
    staleTime: STALE_REFERENCE_DATA_MS,
  })
}

export function useAddProjectMember(): UseMutationResult<unknown, unknown, AddMemberArgs> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: AddMemberArgs) => projectsApi.addMember(id, data),
    onSuccess: (_: unknown, { id }: AddMemberArgs) => {
      qc.invalidateQueries({ queryKey: queryKeys.projects.members(id) })
      qc.invalidateQueries({ queryKey: ['project-team', id] })
    },
  })
}

export function useRemoveProjectMember(): UseMutationResult<unknown, unknown, RemoveMemberArgs> {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, memberId }: RemoveMemberArgs) => projectsApi.removeMember(id, memberId),
    onSuccess: (_: unknown, { id }: RemoveMemberArgs) => {
      qc.invalidateQueries({ queryKey: queryKeys.projects.members(id) })
      qc.invalidateQueries({ queryKey: ['project-team', id] })
    },
  })
}
