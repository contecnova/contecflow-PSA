/**
 * React Query keys factory — audit #82.
 *
 * Convención: array de strings + parámetros, jerárquico.
 * Usar invalidateQueries con prefijo: queryClient.invalidateQueries(queryKeys.tasks.all())
 */
export type QueryKey = readonly unknown[]
export type QueryFilters = Record<string, unknown> | undefined

export const queryKeys = {
  // ── Auth / User ────────────────────────────────────────────────────
  auth: {
    all: (): QueryKey => ['auth'] as const,
    me: (): QueryKey => ['auth', 'me'] as const,
  },
  users: {
    all: (): QueryKey => ['users'] as const,
    list: (filters?: QueryFilters): QueryKey => ['users', 'list', filters || {}] as const,
    detail: (id: string | number | undefined): QueryKey => ['users', 'detail', id] as const,
    settings: (id: string | number | undefined): QueryKey => ['users', 'settings', id] as const,
  },

  // ── Projects ─────────────────────────────────────────────────────────
  projects: {
    all: (): QueryKey => ['projects'] as const,
    list: (filters?: QueryFilters): QueryKey => ['projects', 'list', filters || {}] as const,
    detail: (id: string | number | undefined): QueryKey => ['projects', 'detail', id] as const,
    milestones: (projectId: string | number | undefined): QueryKey => ['projects', projectId, 'milestones'] as const,
    tasks: (projectId: string | number | undefined): QueryKey => ['projects', projectId, 'tasks'] as const,
    members: (projectId: string | number | undefined): QueryKey => ['projects', projectId, 'members'] as const,
  },

  // ── Tasks ────────────────────────────────────────────────────────────
  tasks: {
    all: (): QueryKey => ['tasks'] as const,
    list: (filters?: QueryFilters): QueryKey => ['tasks', 'list', filters || {}] as const,
    detail: (id: string | number | undefined): QueryKey => ['tasks', 'detail', id] as const,
    comments: (taskId: string | number | undefined): QueryKey => ['tasks', taskId, 'comments'] as const,
  },

  // ── Documents ────────────────────────────────────────────────────────
  documents: {
    all: (): QueryKey => ['documents'] as const,
    list: (filters?: QueryFilters): QueryKey => ['documents', 'list', filters || {}] as const,
    detail: (id: string | number | undefined): QueryKey => ['documents', 'detail', id] as const,
    versions: (docId: string | number | undefined): QueryKey => ['documents', docId, 'versions'] as const,
  },

  // ── Alerts ───────────────────────────────────────────────────────────
  alerts: {
    all: (): QueryKey => ['alerts'] as const,
    list: (filters?: QueryFilters): QueryKey => ['alerts', 'list', filters || {}] as const,
  },

  // ── Deliverables ─────────────────────────────────────────────────────
  deliverables: {
    all: (): QueryKey => ['deliverables'] as const,
    list: (): QueryKey => ['deliverables', 'list'] as const,
    byProject: (projectId: string | number | undefined): QueryKey => ['deliverables', 'project', projectId] as const,
  },

  // ── Sprints ──────────────────────────────────────────────────────────
  sprints: {
    all: (): QueryKey => ['sprints'] as const,
    byProject: (projectId: string | number | undefined): QueryKey => ['sprints', 'project', projectId] as const,
    detail: (id: string | number | undefined): QueryKey => ['sprints', 'detail', id] as const,
    backlog: (projectId: string | number | undefined): QueryKey => ['sprints', 'backlog', projectId] as const,
  },

  // ── Clients ──────────────────────────────────────────────────────────
  clients: {
    all: (): QueryKey => ['clients'] as const,
    list: (): QueryKey => ['clients', 'list'] as const,
    detail: (id: string | number | undefined): QueryKey => ['clients', 'detail', id] as const,
  },

  // ── Approvals ────────────────────────────────────────────────────────
  approvals: {
    all: (): QueryKey => ['approvals'] as const,
    pending: (): QueryKey => ['approvals', 'pending'] as const,
    workflows: (): QueryKey => ['approvals', 'workflows'] as const,
  },

  // ── Notifications ────────────────────────────────────────────────────
  notifications: {
    all: (): QueryKey => ['notifications'] as const,
    list: (): QueryKey => ['notifications', 'list'] as const,
    badges: (): QueryKey => ['notifications', 'badges'] as const,
  },
} as const

export type QueryKeysFactory = typeof queryKeys
export type QueryKeysGroup = keyof QueryKeysFactory

interface InvalidateCapable {
  invalidateQueries: (args: { queryKey: QueryKey }) => unknown
}

// Opcional: helper para invalidaciones con queryClient
export const invalidateAll = (queryClient: InvalidateCapable, group: QueryKeysGroup) => {
  return queryClient.invalidateQueries({ queryKey: queryKeys[group].all() })
}
