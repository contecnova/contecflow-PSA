import { useState, useMemo } from 'react'
import type { CSSProperties } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { projectsApi, tasksApi } from '../services/api'
import type { ProjectStatus } from '../services/api'
import { Buscador, Badge, Button, EmptyState, useSort, SortableTH, Pulsable, Select, SelectorDeContexto } from '../components/ui'
import { SkeletonProjects } from '../components/ui/Skeletons'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { FolderOpen, Plus, LayoutGrid, List, Calendar, FileStack, GanttChartSquare } from 'lucide-react'
import GanttChart from '../components/GanttChart'
import { extractErr } from '../utils/helpers'
import { EtiquetaDeCatalogo, OpcionesDeCatalogo } from '../components/catalogos/Catalogo'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useAuth } from '../context/AuthContext'
import { useColVisibility } from '../components/ui/ColVisibility'
import { useAppT } from '../i18n/AppLangContext'
import { useTono } from '../hooks/useOrgSettings'
import { PROJ_COLS, PROJECT_STATUSES } from './proyectos/compartido'
import type { ProjectSummary, ProjectDetail } from './proyectos/compartido'
import { StatusDropdown, ProjectCard } from './proyectos/TarjetaDeProyecto'
import { ProjectFormModal } from './proyectos/FormularioDeProyecto'
import { ProjectDetailModal } from './proyectos/DetalleDeProyecto'
import { TemplatesTab } from './proyectos/PlantillasDeProyecto'
import { GanttWithDeps } from './proyectos/GanttConDependencias'
import './ProjectsPage.css'

// Troceada el 23-11-2026 (sin cambio de comportamiento): tipos y constantes en
// `proyectos/compartido.tsx`; tarjeta, formulario, ficha, plantillas y Gantt en `proyectos/`.
export default function ProjectsPage() {
  const traducir = useAppT()
  const tono = useTono()
  const t = useAppT()
  const { puede } = useAuth()
  const toast = useToast()
  const qc = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const search = searchParams.get('search') || ''
  const statusFilter = searchParams.get('status') || ''
  const typeFilter = searchParams.get('type') || ''
  const view = searchParams.get('view') || 'grid'
  const setParam = (k: string, v: string) => setSearchParams((p: URLSearchParams) => { const n = new URLSearchParams(p); v ? n.set(k, v) : n.delete(k); return n }, { replace: true })
  const setSearch = (v: string) => setParam('search', v)
  const setStatusFilter = (v: string) => setParam('status', v)
  const setTypeFilter = (v: string) => setParam('type', v)
  const setView = (v: string) => setParam('view', v)
  const [showCreate, setShowCreate] = useState(false)
  const [editTarget, setEditTarget] = useState<ProjectSummary | null>(null)
  const [selected, setSelected] = useState<ProjectSummary | null>(null)
  const [ganttMode, setGanttMode] = useState('portfolio')  // portfolio | project
  const projCols = useMemo(() => PROJ_COLS.map(c => ({ ...c, label: traducir(c.label) })), [traducir])
  const { visibleCols, colTemplate, ColToggle, visible: visCols } = useColVisibility(projCols, 'projects')

  const { data: projects = [], isLoading } = useQuery({
    queryKey: ['projects', search, statusFilter],
    // `statusFilter` sale de un select: texto que el servidor valida contra `ProjectStatus`.
    queryFn: () => projectsApi.list({ search: search || undefined, status: (statusFilter || undefined) as ProjectStatus }).then(r => r.data as ProjectSummary[]),
  })

  const { data: projectDetail } = useQuery({
    queryKey: ['project', selected?.id],
    queryFn: () => projectsApi.get(selected.id).then(r => r.data as ProjectDetail),
    enabled: !!selected,
  })

  // `ProjectOut` no trae tareas: el Gantt por proyecto las pide a `GET /tasks`.
  const ganttProjectId = view === 'gantt' && ganttMode === 'project' ? selected?.id : undefined
  const { data: ganttTasks = [] } = useQuery({
    queryKey: ['tasks', 'gantt', ganttProjectId],
    queryFn: () => tasksApi.list({ project_id: ganttProjectId }).then(r => r.data),
    enabled: !!ganttProjectId,
  })

  const { mutate: updateStatus } = useMutation({
    // `status` sale de un select con los valores de `ProjectStatus`.
    mutationFn: ({ id, status }: { id: string; status: string }) => projectsApi.update(id, { status: status as ProjectStatus }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['projects'] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const filtered = projects.filter(p => !typeFilter || p.project_type === typeFilter)
  const { sort: projSort, setSort: setProjSort, sortedData: sortedProjects } = useSort(filtered, 'name')

  const stats = {
    total: projects.length,
    active: projects.filter(p => p.status === 'active').length,
    atRisk: projects.filter(p => p.risk_level === 'high' || p.risk_level === 'critical').length,
    overBudget: projects.filter(p => tono('presupuesto', p.budget_used_pct) === 'danger').length,
  }

  return (
    <PageShell>
      <PageHeader
        icon={<FolderOpen size={18} />}
        title={t('nav.projects')}
        subtitle={t('projects.subtitle', { total: stats.total, active: stats.active, atRisk: stats.atRisk })}
        exportTargetSelector='[data-export-table="projects-list"]'
        exportFilePrefix='projects'
        actions={
          <div className="ds-row">
            <div className="ds-segmented" role="group" aria-label={traducir('proyectos_ui.vista')}>
              {[
                { v: 'grid',      label: traducir('proyectos_ui.vista_tarjetas'), icon: LayoutGrid },
                { v: 'list',      label: traducir('proyectos_ui.vista_lista'), icon: List },
                { v: 'gantt',     label: 'Gantt',     icon: Calendar },
                { v: 'templates', label: traducir('proyectos_ui.vista_plantillas'),icon: FileStack },
              ].map(({ v, label, icon: Icon }) => (
                <Pulsable aria-label={label} key={v} aria-pressed={view === v}
                  onClick={() => setView(v)} title={label}>
                  <Icon size={12} />
                </Pulsable>
              ))}
            </div>
            {puede('proyectos.gestionar') && (
              <Button onClick={() => setShowCreate(true)}>
                <Plus size={13} /> {traducir('projects.nuevo_proyecto')}
              </Button>
            )}
          </div>
        }
      />

      {/* Stats strip */}
      <div className="ds-grid-stats prj-text-2">
        {[
          { label: traducir('proyectos_ui.stat_total'), value: stats.total, color: 'var(--text-1)' },
          { label: traducir('proyectos_ui.stat_activos'), value: stats.active, color: 'var(--accent)' },
          { label: traducir('proyectos_ui.stat_en_riesgo'), value: stats.atRisk, color: 'var(--warning)' },
          { label: traducir('proyectos_ui.stat_sobre_presupuesto'), value: stats.overBudget, color: 'var(--danger)' },
        ].map(s => (
          <div key={s.label} className="ds-card prj-box-9">
            <div className="prj-text-2xl-strong prj-text-4" style={{ '--prj-text-4-color': s.color } as CSSProperties}>{s.value}</div>
            <div className="ds-eyebrow">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Toolbar */}
      <div className="ds-toolbar prj-text-2">
        <Buscador className="prj-box-10" value={search} onChange={setSearch} aria-label={traducir('projects.buscar_proyecto_por_nombre_o_codigo')} placeholder={traducir('projects.buscar_proyecto_por_nombre_o_codigo')} />
        <Select suelto placeholder={false} aria-label={traducir('proyectos_ui.filtro_estado')} value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
          className="prj-input-5">
          <option value="">{traducir('projects.todos_los_estados')}</option>
          {PROJECT_STATUSES.map(s => <option key={s.value} value={s.value}>{traducir(s.label)}</option>)}
        </Select>
        <Select suelto placeholder={false} aria-label={traducir('proyectos_ui.filtro_tipo')} value={typeFilter} onChange={e => setTypeFilter(e.target.value)} className="prj-input-5">
          <option value="">{traducir('projects.todos_los_tipos')}</option>
          <OpcionesDeCatalogo catalogo="project-types" />
        </Select>
      </div>

      {isLoading ? (
        <SkeletonProjects />
      ) : filtered.length === 0 && view !== 'templates' ? (
        <EmptyState icon="folder" title={traducir('projects.sin_proyectos')} description={traducir('proyectos_ui.sin_proyectos_desc')} ctaLabel={traducir('proyectos_ui.crear_proyecto')} onCta={() => setShowCreate(true)} />
      ) : view === 'grid' ? (
        <div className="ds-grid-cards">
          {sortedProjects.map(p => (
            <ProjectCard key={p.id} project={p} onClick={setSelected}
              onStatusChange={(id, status) => updateStatus({ id, status })} onEdit={setEditTarget} />
          ))}
        </div>
      ) : view === 'list' ? (
        <div data-export-table="projects-list" className="ds-card prj-box-11">
          <div className="prj-box-12">
          <div className="prj-grid-muted prj-box-13" style={{ '--prj-box-13-grid-template-columns': colTemplate } as CSSProperties}>
            {(visibleCols as typeof PROJ_COLS).map(c => (
              c.id === 'risk'
                ? <div className="prj-row-14" key={c.id}>
                    <SortableTH col={c.sortKey} sort={projSort} onSort={setProjSort}>{c.label}</SortableTH>
                    <ColToggle />
                  </div>
                : <SortableTH key={c.id} col={c.sortKey} sort={projSort} onSort={setProjSort}>{c.label}</SortableTH>
            ))}
          </div>
          {sortedProjects.map(p => (
            <div className="prj-grid-6 prj-box-14" key={p.id}
              style={{ '--prj-box-14-grid-template-columns': colTemplate } as CSSProperties}
              onPointerEnter={e => e.currentTarget.style.background = 'var(--surface-3)'}
              onPointerLeave={e => e.currentTarget.style.background = 'transparent'}
            >
              {visCols.includes('name') && (
                <Pulsable className="prj-btn-ghost-4" onClick={() => setSelected(p)}>
                  <div className="u-base-600">{p.name}</div>
                  <div className="u-text2-mono-xs">{p.code}</div>
                </Pulsable>
              )}
              {visCols.includes('type') && <span className="u-text2-sm"><EtiquetaDeCatalogo catalogo="project-types" clave={p.project_type} /></span>}
              {visCols.includes('pm') && <span className="u-sm">{p.pm_name || '—'}</span>}
              {visCols.includes('status') && <StatusDropdown project={p} onUpdate={status => updateStatus({ id: p.id, status })} />}
              {visCols.includes('budget') && <span className="prj-text-sm-mono" style={{ '--prj-text-sm-mono-color': tono('presupuesto', p.budget_used_pct ?? 0) === 'danger' ? 'var(--danger)' : 'var(--text-2)' } as CSSProperties}>{p.budget_used_pct?.toFixed(0) ?? 0}%</span>}
              {visCols.includes('progress') && <span className="u-text2-sm">{p.progress_pct?.toFixed(0) ?? 0}%</span>}
              {visCols.includes('risk') && <Badge label={p.risk_level} display={undefined} _color={undefined} />}
            </div>
          ))}
          </div>
        </div>
      ) : view === 'templates' ? (
        <TemplatesTab />
      ) : null}

      {/* ─── GANTT VIEW ─── */}
      {view === 'gantt' && (
        <div>
          <div className="prj-row-15">
            {[['portfolio', traducir('proyectos_ui.gantt_portfolio')], ['project', traducir('proyectos_ui.gantt_por_proyecto')]].map(([m, label]) => (
              <Pulsable className="prj-btn-xs-4" aria-pressed={ganttMode === m} key={m} onClick={() => setGanttMode(m)}
                style={{ '--prj-btn-xs-4-border': `1px solid ${ganttMode === m ? 'var(--accent)' : 'var(--surface-4)'}`, '--prj-btn-xs-4-background': ganttMode === m ? 'var(--accent-muted)' : 'transparent', '--prj-btn-xs-4-color': ganttMode === m ? 'var(--accent)' : 'var(--text-2)' } as CSSProperties}>
                {label}
              </Pulsable>
            ))}
            {ganttMode === 'project' && (
              <SelectorDeContexto><Select label={traducir('uikit.etiqueta_proyecto')} placeholder={false} value={selected?.id || ''} onChange={e => { const p = filtered.find(x => x.id === e.target.value); setSelected(p || null) }}>
                <option value="">{traducir('projects.selecciona_un_proyecto')}</option>
                {filtered.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
              </Select></SelectorDeContexto>
            )}
          </div>
          {ganttMode === 'portfolio' && (
            <GanttChart
              mode="portfolio"
              projects={filtered.map(p => ({
                id: p.id, code: p.code, name: p.name, status: p.status,
                start_date: p.start_date, end_date_planned: p.end_date_planned,
                progress_pct: p.progress_pct,
              }))}
            />
          )}
          {ganttMode === 'project' && selected && (
            <GanttWithDeps
              projectId={selected.id}
              tasks={ganttTasks.map(t => ({
                id: t.id, code: t.code, title: t.title,
                status: t.status, priority: t.priority,
                story_points: t.story_points,
                start_date: t.start_date || t.created_at?.slice(0,10),
                due_date: t.due_date,
                progress_pct: t.status === 'done' ? 100 : t.status === 'in_progress' ? 50 : 0,
              }))}
            />
          )}
          {ganttMode === 'project' && !selected && (
            <EmptyState icon={<GanttChartSquare size={28} />} title={traducir('projects.selecciona_un_proyecto_para_ver_su_gantt')} />
          )}
        </div>
      )}


      <ProjectDetailModal project={selected} detail={projectDetail} open={!!selected} onClose={() => setSelected(null)} onEdit={setEditTarget} />
      <ProjectFormModal open={showCreate} onClose={() => setShowCreate(false)} />
      {editTarget && <ProjectFormModal key={editTarget.id} open={!!editTarget} onClose={() => setEditTarget(null)} project={editTarget} />}
    </PageShell>
  )
}