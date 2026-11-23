/**
 * Tarjeta de proyecto (vista de tarjetas) y desplegable de estado.
 * Troceado de ProjectsPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import { Badge, LoadBar, Pulsable } from '../../components/ui'
import ProjectRiskBadge from '../../components/ui/ProjectRiskBadge'
import { Pencil, ArrowRight, ChevronDown } from 'lucide-react'
import { EtiquetaDeCatalogo } from '../../components/catalogos/Catalogo'
import { useAppT } from '../../i18n/AppLangContext'
import { alpha } from '../../constants/theme'
import { useTono } from '../../hooks/useOrgSettings'
import { PROJECT_STATUSES } from './compartido'
import type { ProjectSummary } from './compartido'

export function StatusDropdown({ project, onUpdate }: { project: Pick<ProjectSummary, 'status'>; onUpdate: (s: string) => void }) {
  const traducir = useAppT()
  const [open, setOpen] = useState(false)
  const cfg: Record<string, { color: string }> = {
    planning:  { color: 'var(--text-2)' },
    active:    { color: 'var(--accent)' },
    paused:    { color: 'var(--warning)' },
    closed:    { color: 'var(--success)' },
    on_hold:   { color: 'var(--warning)' },
    completed: { color: 'var(--success)' },
    cancelled: { color: 'var(--text-3)' },
    archived:  { color: 'var(--text-3)' },
  }
  const c = cfg[project.status] || cfg.planning
  const etiqueta = PROJECT_STATUSES.find(s => s.value === project.status)

  return (
    <div className="prj-box">
      <Pulsable className="prj-btn-xs" aria-haspopup="listbox" aria-expanded={open} aria-label={traducir('proyectos_ui.cambiar_estado')}
        onClick={e => { e.stopPropagation(); setOpen(o => !o) }}
        style={{ '--prj-btn-xs-border': `1px solid ${alpha(c.color, '40')}`, '--prj-btn-xs-background': alpha(c.color, '15'), '--prj-btn-xs-color': c.color } as CSSProperties}
      >
        {etiqueta ? traducir(etiqueta.label) : project.status} <ChevronDown size={11} aria-hidden />
      </Pulsable>
      {open && (
        <>
          <div className="prj-box-2" role="presentation" onMouseDown={e => { e.stopPropagation(); setOpen(false) }} />
          <div className="prj-card-2">
            {PROJECT_STATUSES.map(s => (
              <Pulsable className="prj-btn-base" key={s.value} onClick={e => { e.stopPropagation(); onUpdate(s.value); setOpen(false) }}
                style={{ '--prj-btn-base-background': project.status === s.value ? 'var(--accent-muted)' : 'transparent', '--prj-btn-base-color': project.status === s.value ? 'var(--accent)' : 'var(--text-1)' } as CSSProperties}
              >
                {traducir(s.label)}
              </Pulsable>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

export function ProjectCard({ project, onClick, onStatusChange, onEdit }: { project: ProjectSummary; onClick: (p: ProjectSummary) => void; onStatusChange: (id: string, s: string) => void; onEdit: (p: ProjectSummary) => void }) {
  const traducir = useAppT()
  const tono = useTono()
  return (
    <div className="ds-card prj-tarjeta"
    >
      <div className="prj-row">
        <Pulsable className="prj-btn-ghost" onClick={() => onClick(project)}>
          <div className="ds-muted prj-text-xs-mono">{project.code}</div>
          <div className="prj-box-3">{project.name}</div>
          {project.pm_name && <div className="ds-muted prj-text">{traducir('proyectos_ui.pm_nombre', { nombre: project.pm_name })}</div>}
          {project.department && <div className="ds-muted">{traducir('proyectos_ui.depto_nombre', { nombre: project.department })}</div>}
          {project.client_name && <div className="ds-muted">{traducir('proyectos_ui.cliente_nombre', { nombre: project.client_name })}</div>}
        </Pulsable>
        <div className="prj-stack">
          <StatusDropdown project={project} onUpdate={status => onStatusChange(project.id, status)} />
          <Badge label={project.risk_level} display={undefined} _color={undefined} />
          <ProjectRiskBadge projectId={project.id} hasData={(project.task_count ?? project.team_size ?? 1) > 0} />
        </div>
      </div>

      <Pulsable className="prj-btn-ghost-2" onClick={() => onClick(project)}>
        <div className="prj-row-muted">
          <span><EtiquetaDeCatalogo catalogo="project-types" clave={project.project_type} /></span>
          <span>{traducir('proyectos_ui.pct_completado', { n: project.progress_pct?.toFixed(0) ?? 0 })}</span>
        </div>
        <LoadBar value={project.progress_pct ?? 0} label={undefined} />
      </Pulsable>

      <div className="prj-row-2">
        <Pulsable className="prj-btn-ghost-3" onClick={() => onClick(project)}>
          <span className="ds-muted">{traducir('proyectos_ui.equipo')} <span className="u-text1">{project.team_size}</span></span>
          {project.budget_amount && (
            <span className="prj-text-mono" style={{ '--prj-text-mono-color': tono('presupuesto', project.budget_used_pct) === 'danger' ? 'var(--danger)' : 'var(--text-2)' } as CSSProperties}>
              {traducir('proyectos_ui.pct_presupuesto', { n: project.budget_used_pct?.toFixed(0) ?? 0 })}
            </span>
          )}
        </Pulsable>
        <div className="u-row-6">
          <Link to={`/projects/${project.id}`} onClick={e => e.stopPropagation()} className="prj-enlace-ver">
            {traducir('proyectos_ui.ver')} <ArrowRight size={11} />
          </Link>
          <Pulsable className="prj-btn-ghost-xs" onClick={e => { e.stopPropagation(); onEdit(project) }}>
            <Pencil size={11} /> {traducir('common.edit')}
          </Pulsable>
        </div>
      </div>
    </div>
  )
}
