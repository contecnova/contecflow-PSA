/**
 * React Query keys factory — audit #82.
 *
 * Convención: array de strings + parámetros, jerárquico.
 * Usar invalidateQueries con prefijo: queryClient.invalidateQueries(queryKeys.tasks.all())
 */
export const queryKeys = {
  // ── Auth / User ────────────────────────────────────────────────────
  auth: {
    all: () => ['auth'],
    me: () => ['auth', 'me'],
  },
  users: {
    all: () => ['users'],
    list: (filters) => ['users', 'list', filters || {}],
    detail: (id) => ['users', 'detail', id],
    settings: (id) => ['users', 'settings', id],
  },

  // ── Projects ─────────────────────────────────────────────────────────
  projects: {
    all: () => ['projects'],
    list: (filters) => ['projects', 'list', filters || {}],
    detail: (id) => ['projects', 'detail', id],
    milestones: (projectId) => ['projects', projectId, 'milestones'],
    tasks: (projectId) => ['projects', projectId, 'tasks'],
    members: (projectId) => ['projects', projectId, 'members'],
  },

  // ── Tasks ────────────────────────────────────────────────────────────
  tasks: {
    all: () => ['tasks'],
    list: (filters) => ['tasks', 'list', filters || {}],
    detail: (id) => ['tasks', 'detail', id],
    comments: (taskId) => ['tasks', taskId, 'comments'],
  },

  // ── Documents ────────────────────────────────────────────────────────
  documents: {
    all: () => ['documents'],
    list: (filters) => ['documents', 'list', filters || {}],
    detail: (id) => ['documents', 'detail', id],
    versions: (docId) => ['documents', docId, 'versions'],
  },

  // ── Alerts ───────────────────────────────────────────────────────────
  alerts: {
    all: () => ['alerts'],
    list: (filters) => ['alerts', 'list', filters || {}],
  },

  // ── Deliverables ─────────────────────────────────────────────────────
  deliverables: {
    all: () => ['deliverables'],
    list: () => ['deliverables', 'list'],
    byProject: (projectId) => ['deliverables', 'project', projectId],
  },

  // ── Sprints ──────────────────────────────────────────────────────────
  sprints: {
    all: () => ['sprints'],
    byProject: (projectId) => ['sprints', 'project', projectId],
    detail: (id) => ['sprints', 'detail', id],
    backlog: (projectId) => ['sprints', 'backlog', projectId],
  },

  // ── Clients ──────────────────────────────────────────────────────────
  clients: {
    all: () => ['clients'],
    list: () => ['clients', 'list'],
    detail: (id) => ['clients', 'detail', id],
  },

  // ── Approvals ────────────────────────────────────────────────────────
  approvals: {
    all: () => ['approvals'],
    pending: () => ['approvals', 'pending'],
    workflows: () => ['approvals', 'workflows'],
  },

  // ── Notifications ────────────────────────────────────────────────────
  notifications: {
    all: () => ['notifications'],
    list: () => ['notifications', 'list'],
    badges: () => ['notifications', 'badges'],
  },
}

// Opcional: helper para invalidaciones con queryClient
export const invalidateAll = (queryClient, group) => {
  return queryClient.invalidateQueries({ queryKey: queryKeys[group].all() })
}
