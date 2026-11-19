/**
 * PortfolioPage — Gestión de carteras de proyectos
 * Vista RAG (Red/Amber/Green) de salud + EVM consolidado + hitos cruzados.
 *
 * 16-11-2026: pasada de diseño. Tenía cabecera propia (icono sin recuadro,
 * título menor, sin separador, ancho máximo centrado) y vacío con icono suelto
 * y título gris: ahora PageShell + PageHeader con el título del menú, KpiCard,
 * EmptyState, Button/Input/Select/Modal del kit y StatusBadge. Fechas con el
 * formateador de la app y estados de proyecto traducidos (antes, código crudo).
 */
import React, { useState } from 'react';
import type { CSSProperties } from 'react';
import PageShell from '../components/layout/PageShell'
import PageHeader from '../components/layout/PageHeader'
import { useDialogo, Button, Card, EmptyState, Input, KpiCard, Modal, Select, Spinner, Pulsable, TablaSimple } from '../components/ui'
import StatusBadge from '../components/ui/StatusBadge'
import type { StatusBadgeKind } from '../components/ui/StatusBadge'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useToast } from '../context/ToastContext';
import { extractErr, fmtDate, localeActivo } from '../utils/helpers';
import { portfolioApi, projectsApi } from '../services/api'
import type { Cartera, PanelDeCartera } from '../services/api/tipos-analitica';
import { useAppT } from '../i18n/AppLangContext'
import { etiquetaCodigo } from '../i18n/etiquetaCodigo'
import {
  Briefcase, Plus, ChevronRight, ChevronDown, X, Check,
  AlertTriangle, CheckCircle, Clock, Pencil, Trash2,
  DollarSign, BarChart2, Calendar, FolderSearch,
  type LucideIcon,
} from 'lucide-react';
import DateInput from '../components/ui/DateInput'

import { useFormatoMoneda } from '../hooks/useFormatoMoneda'
import { useTono } from '../hooks/useOrgSettings'
import { POLL_DEFAULT_MS } from '../constants/timings'
import './PortfolioPage.css'
type PortfolioStatus = 'planning' | 'active' | 'archived' | string
type RagLevel = 'green' | 'yellow' | 'red' | 'grey' | string

type PortfolioItem = Cartera

type PortfolioFormData = {
  name: string
  description: string
  status: PortfolioStatus
  budget_total: string | number | null
  start_date?: string
  end_date?: string
}

type ProjectItem = {
  id: string | number
  name: string
  status?: string
}

type PortfolioDashboardData = PanelDeCartera

// ── utils ──────────────────────────────────────────────────────────────────────
const fmtI = (n: number | string | null | undefined) => n == null ? '—' : Number(n).toLocaleString(localeActivo(), { minimumFractionDigits: 3, maximumFractionDigits: 3 });

const RAG: Record<string, { color: string; kind: StatusBadgeKind; label: string; Icon: LucideIcon }> = {
  green:  { color: 'var(--success)', kind: 'success', label: 'portfolio_ui.rag_green',  Icon: CheckCircle },
  yellow: { color: 'var(--warning)', kind: 'warning', label: 'portfolio_ui.rag_yellow', Icon: AlertTriangle },
  red:    { color: 'var(--danger)',  kind: 'danger',  label: 'portfolio_ui.rag_red',    Icon: AlertTriangle },
  grey:   { color: 'var(--text-3)',  kind: 'neutral', label: 'portfolio_ui.rag_grey',   Icon: Clock },
};
const ESTADOS: Record<string, { label: string; kind: StatusBadgeKind }> = {
  planning: { label: 'portfolio_ui.estado_planning', kind: 'accent' },
  active:   { label: 'portfolio_ui.estado_active',   kind: 'success' },
  archived: { label: 'portfolio_ui.estado_archived', kind: 'neutral' },
};

// Revisión 2026-11: una fecha vacía va como null (con '' la API da 422) y el
// presupuesto como número.
function aEnviar(data: PortfolioFormData) {
  return { ...data, budget_total: data.budget_total ? Number(data.budget_total) : null,
    start_date: data.start_date || null, end_date: data.end_date || null }
}

function RagPill({ rag }: { rag: RagLevel }) {
  const t = useAppT()
  const r = RAG[rag] || RAG.grey;
  return (
    <StatusBadge kind={r.kind} caps={false}>
      <r.Icon size={11} aria-hidden />
      {t(r.label)}
    </StatusBadge>
  );
}

function EstadoCartera({ status }: { status: string }) {
  const t = useAppT()
  const e = ESTADOS[status]
  return <StatusBadge kind={e?.kind ?? 'neutral'} caps={false}>{e ? t(e.label) : status}</StatusBadge>
}

// ── Create/edit portfolio modal ────────────────────────────────────────────────
function PortfolioModal({ initial, onClose, onSave }: { initial?: PortfolioItem | null; onClose: () => void; onSave: (data: PortfolioFormData) => void }) {
  const fmtMoneda = useFormatoMoneda()
  const idCampo = React.useId()
  const t = useAppT()
  const [form, setForm] = useState<PortfolioFormData>(initial
    ? {
      name: initial.name,
      description: initial.description || '',
      status: initial.status || 'active',
      budget_total: initial.budget_total ?? '',
      start_date: initial.start_date || '',
      end_date: initial.end_date || '',
    }
    : { name: '', description: '', status: 'active', budget_total: '', start_date: '', end_date: '' })
  const set = <K extends keyof PortfolioFormData>(k: K) => (e: { target: { value: string } }) => setForm(f => ({ ...f, [k]: e.target.value as PortfolioFormData[K] }));

  return (
    <Modal open onClose={onClose} title={initial ? t('portfolio_ui.editar_cartera') : t('portfolio_ui.nueva_cartera')}>
      <div className="u-stack-14">
        <Input label={t('portfolio_ui.nombre_obligatorio')} value={form.name} onChange={set('name')} placeholder={t('portfolio.nombre_de_la_cartera')} />
        <div className="ui-field">
          <label className="uiinde-estiloetiqueta" htmlFor={`${idCampo}-desc`}>{t('portfolio.descripcion')}</label>
          <textarea className="ds-input pf-textarea" id={`${idCampo}-desc`} rows={3} value={form.description || ''} onChange={set('description')} />
        </div>
        <div className="u-grid2-12">
          <Select label={t('portfolio_ui.estado')} value={String(form.status)} onChange={set('status')} options={[
            { value: 'planning', label: t('portfolio_ui.estado_planning') },
            { value: 'active', label: t('portfolio_ui.estado_active') },
            { value: 'archived', label: t('portfolio_ui.estado_archived') },
          ]} />
          <Input label={t('portfolio_ui.presupuesto_total_moneda', { moneda: fmtMoneda.simbolo })} type="number" value={form.budget_total ?? ''} onChange={set('budget_total')} placeholder={t('portfolio_ui.ej_presupuesto')} />
        </div>
        <div className="u-grid2-12">
          <div className="ui-field">
            <label className="uiinde-estiloetiqueta" htmlFor={`${idCampo}-ini`}>{t('portfolio_ui.fecha_inicio')}</label>
            <DateInput id={`${idCampo}-ini`} value={form.start_date || ''} onChange={set('start_date')} className="ds-input" />
          </div>
          <div className="ui-field">
            <label className="uiinde-estiloetiqueta" htmlFor={`${idCampo}-fin`}>{t('portfolio_ui.fecha_fin')}</label>
            <DateInput id={`${idCampo}-fin`} value={form.end_date || ''} onChange={set('end_date')} className="ds-input" />
          </div>
        </div>
      </div>
      <div className="pf-acciones-modal">
        <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
        <Button icon={initial ? <Check size={14} /> : <Plus size={14} />} onClick={() => onSave(form)} disabled={!form.name}>
          {initial ? t('common.save') : t('portfolio_ui.crear_cartera')}
        </Button>
      </div>
    </Modal>
  );
}

// ── Add project to portfolio modal ─────────────────────────────────────────────
function AddProjectModal({ portfolioId, existingIds, onClose, onAdded }: { portfolioId: string | number; existingIds: Array<string | number>; onClose: () => void; onAdded: () => void }) {
  const toast = useToast();
  const t = useAppT()
  const [search, setSearch] = useState('');
  const qc = useQueryClient();

  const { data: allProjects = [] } = useQuery<ProjectItem[]>({
    queryKey: ['projects-for-portfolio'],
    queryFn: () => projectsApi.list({}).then(r => r.data ?? []),
  });

  const { mutate: addProject } = useMutation({
    mutationFn: (pid: string | number) => portfolioApi.addProject(portfolioId, pid),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['portfolio-dashboard', portfolioId] }); onAdded(); },
    onError: (e: unknown) => toast.error(extractErr(e, t('portfolio_ui.error_anadir'))),
  });

  const available = allProjects.filter(p => !existingIds.includes(p.id) &&
    p.name.toLowerCase().includes(search.toLowerCase()));

  return (
    <Modal open onClose={onClose} title={t('portfolio.anadir_proyecto_a_la_cartera')}>
      <div className="u-stack-12">
        <Input aria-label={t('portfolio_ui.buscar_proyectos')} value={search} onChange={e => setSearch(e.target.value)} placeholder={t('portfolio_ui.buscar_proyectos')} />
        <div className="pf-lista-proyectos">
          {available.map(p => (
            <Pulsable className="pf-opcion-proyecto" key={p.id} onClick={() => addProject(p.id)}>
              <div className="u-min0">
                <div className="u-base-600">{p.name}</div>
                <div className="u-text3-xs">{etiquetaCodigo(t, 'estado', p.status)}</div>
              </div>
              <Plus size={14} className="pf-icono-accent" aria-hidden />
            </Pulsable>
          ))}
          {available.length === 0 && (
            <EmptyState icon={<FolderSearch size={28} />} title={t('portfolio.sin_resultados')} />
          )}
        </div>
        <div className="pf-acciones-modal">
          <Button variant="secondary" onClick={onClose}>{t('common.close')}</Button>
        </div>
      </div>
    </Modal>
  );
}

// ── Portfolio dashboard ────────────────────────────────────────────────────────
function PortfolioDashboard({ portfolioId, onClose }: { portfolioId: string | number; onClose: () => void }) {
  const fmtMoneda = useFormatoMoneda()
  const tono = useTono()
  const toast = useToast();
  const t = useAppT()
  const qc = useQueryClient();
  const [showAddProject, setShowAddProject] = useState(false);
  const [expandedId, setExpandedId] = useState<string | number | null>(null);

  const { data: dash, isLoading } = useQuery<PortfolioDashboardData>({
    queryKey: ['portfolio-dashboard', portfolioId],
    queryFn: () => portfolioApi.dashboard(portfolioId).then(r => r.data),
    enabled: !!portfolioId,
    refetchInterval: POLL_DEFAULT_MS,
  });

  const { mutate: removeProject } = useMutation({
    mutationFn: (pid: string | number) => portfolioApi.removeProject(portfolioId, pid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['portfolio-dashboard', portfolioId] }),
    onError: (e: unknown) => toast.error(extractErr(e, t('portfolio_ui.error_quitar'))),
  });
  // Con AddProjectModal abierto encima, cede Esc y foco a ese dialogo.
  const dialogRef = useDialogo<HTMLDivElement>(Boolean(portfolioId) && !(showAddProject && dash), onClose);

  if (!portfolioId) return null;

  return (
    <>
    <div className="pf-capa" role="presentation" onMouseDown={onClose}>
      <div className="pf-panel" ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="portfolio-dashboard-title" onMouseDown={e => e.stopPropagation()}>
        {isLoading && <div className="pf-cargando"><Spinner label={t('portfolio_ui.cargando_panel')} /></div>}
        {dash && <>
          {/* Header */}
          <div className="pf-panel-cabecera">
            <div className="u-min0">
              <h2 className="pf-panel-titulo" id="portfolio-dashboard-title">{dash.portfolio_name}</h2>
              <div className="pf-panel-sub">
                {t('portfolio_ui.n_proyectos', { n: dash.project_count })} · {ESTADOS[dash.status] ? t(ESTADOS[dash.status].label) : dash.status}
              </div>
            </div>
            <div className="u-row-center-8">
              <Button icon={<Plus size={14} />} onClick={() => setShowAddProject(true)}>
                {t('portfolio.anadir_proyecto')}
              </Button>
              <Pulsable className="pf-cerrar" aria-label={t('common.close')} onClick={onClose}><X size={16} aria-hidden /></Pulsable>
            </div>
          </div>

          {/* KPIs */}
          <div className="ds-grid-stats">
            <KpiCard icon={<DollarSign size={16} />} label={t('portfolio_ui.presupuesto_total')} value={fmtMoneda(dash.budget_envelope, { decimales: 0 })}
              sub={t('portfolio_ui.gastado_importe', { importe: fmtMoneda(dash.budget_spent, { decimales: 0 }) })} danger={dash.budget_pct > 100} />
            <KpiCard icon={<BarChart2 size={16} />} label={t('portfolio_ui.pct_gastado')} value={`${dash.budget_pct}%`}
              sub={tono('presupuesto', dash.budget_pct) === 'success' ? t('portfolio_ui.dentro_presupuesto') : t('portfolio_ui.cerca_limite')}
              danger={tono('presupuesto', dash.budget_pct) === 'danger'} warning={tono('presupuesto', dash.budget_pct) === 'warning'} />
            <KpiCard icon={<AlertTriangle size={16} />} label={t('portfolio_ui.rag_red')} value={dash.health_counts.red || 0}
              sub={t('portfolio_ui.n_en_atencion', { n: dash.health_counts.yellow || 0 })} danger={(dash.health_counts.red || 0) > 0} />
            <KpiCard icon={<CheckCircle size={16} />} label={t('portfolio_ui.rag_green')} value={dash.health_counts.green || 0}
              sub={t('portfolio_ui.n_total', { n: dash.project_count })} />
          </div>

          {/* Projects table */}
          {dash.projects.length === 0 ? (
            <EmptyState icon={<Briefcase size={28} />} title={t('portfolio.no_projects')}
              description={t('portfolio_ui.sin_proyectos_desc')} />
          ) : (
          <Card className="pf-tabla-card">
            <div className="pf-tabla-scroll">
            <TablaSimple claseTabla="pf-table">
              <thead>
                <tr>
                  {[t('portfolio_ui.col_salud'), t('portfolio_ui.col_proyecto'), t('portfolio_ui.col_hecho'), 'CPI', 'SPI', t('portfolio_ui.col_presupuesto'), t('portfolio_ui.col_gasto_real'), t('portfolio_ui.col_proximo_hito'), ''].map((h, i) => (
                    <th className="pf-th" key={i}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {dash.projects.map(p => {
                  const nextMs = p.milestones?.[0];
                  const isExpanded = expandedId === p.project_id;
                  return (
                    <React.Fragment key={p.project_id}>
                      <tr className="pf-fila"
                        onClick={() => setExpandedId(isExpanded ? null : p.project_id)}
                        role="button"
                        tabIndex={0}
                        aria-expanded={isExpanded}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            setExpandedId(isExpanded ? null : p.project_id);
                          }
                        }}>
                        <td className="pf-td"><RagPill rag={p.rag} /></td>
                        <td className="pf-td pf-td--nombre">
                          <span className="u-row-center-6">
                            {isExpanded ? <ChevronDown size={12} aria-hidden /> : <ChevronRight size={12} aria-hidden />}
                            {p.project_name}
                          </span>
                        </td>
                        <td className="pf-td" aria-label={`${p.pct_complete}%`}>
                          <div className="u-row-center-8">
                            <div className="pf-barra">
                              <div className="pf-barra__relleno" style={{ '--pf-ancho': `${p.pct_complete}%`, '--pf-color': RAG[p.rag]?.color || 'var(--text-3)' } as CSSProperties} />
                            </div>
                            <span className="u-xs">{p.pct_complete}%</span>
                          </div>
                        </td>
                        <td className="pf-td pf-td--indice" style={{ '--pf-color': p.cpi == null ? 'var(--text-3)' : p.cpi >= 0.9 ? 'var(--success)' : 'var(--danger)' } as CSSProperties}>{fmtI(p.cpi)}</td>
                        <td className="pf-td pf-td--indice" style={{ '--pf-color': p.spi == null ? 'var(--text-3)' : p.spi >= 0.9 ? 'var(--success)' : 'var(--danger)' } as CSSProperties}>{fmtI(p.spi)}</td>
                        <td className="pf-td pf-td--muted">{fmtMoneda(p.bac, { decimales: 0 })}</td>
                        <td className="pf-td pf-td--muted">{fmtMoneda(p.ac, { decimales: 0 })}</td>
                        <td className="pf-td">
                          {nextMs ? (
                            <span className="pf-hito">
                              <Calendar size={11} aria-hidden />
                              {nextMs.title} · {fmtDate(nextMs.due_date)}
                              {nextMs.is_completed && <Check size={11} className="pf-icono-ok" aria-hidden />}
                            </span>
                          ) : <span className="u-text3-xs">—</span>}
                        </td>
                        <td className="pf-td">
                          <Pulsable className="pf-quitar" aria-label={t('portfolio_ui.quitar')} title={t('portfolio_ui.quitar')} onClick={ev => { ev.stopPropagation(); openConfirmGlobal({message:t('portfolio_ui.quitar_confirm'),onConfirm:()=>removeProject(p.project_id),danger:true}) }}><X size={13} aria-hidden /></Pulsable>
                        </td>
                      </tr>
                      {isExpanded && (
                        <tr className="pf-fila-detalle">
                          <td className="pf-td-detalle" colSpan={9}>
                            <div className="ds-eyebrow pf-detalle-titulo">{t('portfolio.hitos_proximos')}</div>
                            {p.milestones.length === 0
                              ? <span className="u-text3-sm">{t('portfolio.sin_hitos_proximos')}</span>
                              : p.milestones.map(m => (
                                <div className="pf-hito-fila" key={m.id}>
                                  {m.is_completed ? <Check size={12} className="pf-icono-ok" aria-hidden /> : <Clock size={12} className="pf-icono-aviso" aria-hidden />}
                                  <span>{m.title}</span>
                                  <span className="u-text3">{fmtDate(m.due_date)}</span>
                                </div>
                              ))}
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </TablaSimple>
            </div>
          </Card>
          )}
        </>}
      </div>
    </div>
      {/* Fuera de la capa: un clic en su fondo no debe cerrar también el panel. */}
      {showAddProject && dash && (
        <AddProjectModal
          portfolioId={portfolioId}
          existingIds={dash.projects.map(p => p.project_id)}
          onClose={() => setShowAddProject(false)}
          onAdded={() => setShowAddProject(false)}
        />
      )}
    </>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function PortfolioPage() {
  const fmtMoneda = useFormatoMoneda()
  const toast = useToast();
  const t = useAppT()
  const qc = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [editing, setEditing] = useState<PortfolioItem | null>(null);
  const [selectedId, setSelectedId] = useState<string | number | null>(null);

  const { data: portfolios = [], isLoading } = useQuery<PortfolioItem[]>({
    queryKey: ['portfolios'],
    queryFn: () => portfolioApi.list().then(r => r.data),
  });

  const { mutate: createPortfolio } = useMutation({
    mutationFn: (data: PortfolioFormData) => portfolioApi.create(aEnviar(data)),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['portfolios'] }); setShowCreate(false); },
    onError: (e: unknown) => toast.error(extractErr(e, t('portfolio_ui.error_crear'))),
  });

  const { mutate: updatePortfolio } = useMutation({
    mutationFn: ({ id, data }: { id: string | number; data: PortfolioFormData }) => portfolioApi.update(id, aEnviar(data)),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['portfolios'] }); setEditing(null); },
    onError: (e: unknown) => toast.error(extractErr(e, t('portfolio_ui.error_guardar'))),
  });

  const { mutate: deletePortfolio } = useMutation({
    mutationFn: (id: string | number) => portfolioApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['portfolios'] }),
    onError: (e: unknown) => toast.error(extractErr(e, t('portfolio_ui.error_borrar'))),
  });

  return (
    <PageShell>
      <PageHeader
        icon={<Briefcase size={18} />}
        title={t('nav.portfolio')}
        subtitle={t('portfolio.subtitle')}
        actions={
          <Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>
            {t('portfolio.new_portfolio')}
          </Button>
        }
      />

      {/* Portfolio cards */}
      {isLoading ? (
        <div className="pf-cargando"><Spinner label={t('common.loading')} /></div>
      ) : portfolios.length === 0 ? (
        <EmptyState icon={<Briefcase size={28} />} title={t('portfolio.sin_carteras')}
          description={t('portfolio.crea_tu_primera_cartera_para_agrupar_proyectos')}
          ctaLabel={t('portfolio.new_portfolio')} onCta={() => setShowCreate(true)} />
      ) : (
        <div className="ds-grid-cards">
          {portfolios.map(p => (
            <div className="ds-card pf-tarjeta" key={p.id}
              onClick={() => setSelectedId(p.id)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  setSelectedId(p.id);
                }
              }}>
              <div className="pf-tarjeta__cabecera">
                <div className="u-min0">
                  <div className="pf-tarjeta__nombre">{p.name}</div>
                  <div className="u-text3-xs">{t('portfolio_ui.n_proyectos', { n: p.project_count })}</div>
                </div>
                <EstadoCartera status={p.status} />
              </div>

              {p.description && (
                <div className="pf-tarjeta__desc">{p.description}</div>
              )}

              {p.budget_total != null && (
                <div className="pf-tarjeta__dato">
                  <DollarSign size={12} aria-hidden />
                  {t('portfolio_ui.presupuesto_dos_puntos')} <strong className="u-text1">{fmtMoneda(p.budget_total, { decimales: 0 })}</strong>
                </div>
              )}

              <div className="pf-tarjeta__pie">
                <div className="u-row-center-6">
                  <Button variant="ghost" size="sm" icon={<Pencil size={13} />} onClick={ev => { ev.stopPropagation(); setEditing(p); }}>
                    {t('common.edit')}
                  </Button>
                  <Button variant="ghost" size="sm" icon={<Trash2 size={13} />} onClick={ev => { ev.stopPropagation(); openConfirmGlobal({message:t('portfolio_ui.eliminar_confirm', { nombre: p.name }),onConfirm:()=>deletePortfolio(p.id),danger:true}) }}>
                    {t('common.delete')}
                  </Button>
                </div>
                <span className="pf-ver-panel">
                  {t('portfolio_ui.ver_panel')} <ChevronRight size={13} aria-hidden />
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Modals */}
      {showCreate && <PortfolioModal onClose={() => setShowCreate(false)} onSave={data => createPortfolio(data)} />}
      {editing    && <PortfolioModal initial={editing} onClose={() => setEditing(null)} onSave={data => updatePortfolio({ id: editing.id, data })} />}
      {selectedId && <PortfolioDashboard portfolioId={selectedId} onClose={() => setSelectedId(null)} />}
    </PageShell>
  );
}
