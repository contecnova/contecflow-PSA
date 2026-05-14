import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi } from '../services/api'
import { queryKeys } from '../constants/queryKeys'

export function useProjects(params = {}) {
  return useQuery({
    queryKey: queryKeys.projects.list(params),
    queryFn: () => projectsApi.list(params).then(r => r.data?.items ?? r.data ?? []),
    staleTime: 2 * 60 * 1000,
  })
}

// Convenience: all projects with no filter — used in selectors across the app
export function useAllProjects() {
  return useQuery({
    queryKey: queryKeys.projects.all(),
    queryFn: () => projectsApi.list().then(r => r.data?.items ?? r.data ?? []),
    staleTime: 2 * 60 * 1000,
  })
}

export function useProject(id) {
  return useQuery({
    queryKey: queryKeys.projects.detail(id),
    queryFn: () => projectsApi.get(id).then(r => r.data),
    enabled: !!id,
  })
}

export function useCreateProject() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data) => projectsApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.projects.all() }),
  })
}

export function useUpdateProject() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => projectsApi.update(id, data),
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: queryKeys.projects.all() })
      qc.invalidateQueries({ queryKey: queryKeys.projects.detail(id) })
    },
  })
}

export function useDeleteProject() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => projectsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.projects.all() }),
  })
}

export function useProjectTeam(projectId) {
  return useQuery({
    // TODO #82: migrate to queryKeys — team is project-derived but lacks a dedicated factory entry
    queryKey: ['project-team', projectId],
    queryFn: () => projectsApi.team(projectId).then(r => r.data),
    enabled: !!projectId,
    staleTime: 2 * 60 * 1000,
  })
}

export function useProjectMembers(projectId) {
  return useQuery({
    queryKey: queryKeys.projects.members(projectId),
    queryFn: () => projectsApi.members(projectId).then(r => r.data),
    enabled: !!projectId,
    staleTime: 2 * 60 * 1000,
  })
}

export function useProjectEVM(projectId) {
  return useQuery({
    // TODO #82: migrate to queryKeys — EVM is project-derived but lacks a dedicated factory entry
    queryKey: ['project-evm', projectId],
    queryFn: () => projectsApi.evm(projectId).then(r => r.data),
    enabled: !!projectId,
    staleTime: 2 * 60 * 1000,
  })
}

export function useProjectEVMPortfolio() {
  return useQuery({
    // TODO #82: migrate to queryKeys — EVM portfolio lacks a dedicated factory entry
    queryKey: ['project-evm-portfolio'],
    queryFn: () => projectsApi.evmPortfolio().then(r => r.data),
    staleTime: 2 * 60 * 1000,
  })
}

export function useAddProjectMember() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => projectsApi.addMember(id, data),
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: queryKeys.projects.members(id) })
      qc.invalidateQueries({ queryKey: ['project-team', id] })
    },
  })
}

export function useRemoveProjectMember() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, memberId }) => projectsApi.removeMember(id, memberId),
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: queryKeys.projects.members(id) })
      qc.invalidateQueries({ queryKey: ['project-team', id] })
    },
  })
}
