/**
 * Gantt de un proyecto con sus dependencias entre tareas (vista Gantt de la página).
 * Troceado de ProjectsPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import { useQuery } from '@tanstack/react-query'
import { taskDependenciesApi } from '../../services/api'
import GanttChart from '../../components/GanttChart'
import type { GanttTasks } from './compartido'

// Wrapper that fetches dependencies and passes them to GanttChart
export function GanttWithDeps({ projectId, tasks }: { projectId: string; tasks: GanttTasks }) {
  // Las del Gantt son /tasks/dependencies (predecessor/successor); /task-dependencies es
  // el grafo con metadatos ({nodes, edges}) y aquí daba siempre una lista vacía.
  const { data: deps = [] } = useQuery({
    queryKey: ['task-deps', projectId],
    queryFn: () => taskDependenciesApi.getByProject(projectId).then(r => r.data),
    enabled: !!projectId,
  })
  return <GanttChart mode="project" tasks={tasks} dependencies={deps} />
}
