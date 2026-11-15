/**
 * PortfolioPage — Gestión de carteras de proyectos
 * Vista RAG (Red/Amber/Green) de salud + EVM consolidado + hitos cruzados.
 */
import React, { useState } from 'react';
import type { CSSProperties} from 'react';
import PageShell from '../components/layout/PageShell'
import { useDialogo } from '../components/ui'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useToast } from '../context/ToastContext';
import { extractErr } from '../utils/helpers';
import { portfolioApi, projectsApi } from '../services/api'
import type { Cartera, PanelDeCartera } from '../services/api/tipos-analitica';
import { useAppT } from '../i18n/AppLangContext'
import {
  Briefcase, Plus, ChevronRight, ChevronDown, X, Check,
  AlertTriangle, CheckCircle, Clock,
  DollarSign, BarChart2, Calendar,
  type LucideIcon,
} from 'lucide-react';
import { alpha } from '../constants/theme'
import { localeActivo } from '../utils/helpers'
import DateInput from '../components/ui/DateInput'

import { useFormatoMoneda } from '../hooks/useFormatoMoneda'
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
const _fmt  = (n: number | string | null | undefined) => n == null ? '—' : Number(n).toLocaleString(localeActivo(), { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fmtI = (n: number | string | null | undefined) => n == null ? '—' : Number(n).toLocaleString(localeActivo(), { minimumFractionDigits: 3, maximumFractionDigits: 3 });

const RAG: Record<string, { color: string; label: string; Icon: LucideIcon }> = {
  green:  { color: 'var(--success)', label: 'portfolio_ui.rag_green',  Icon: CheckCircle },
  yellow: { color: 'var(--warning)', label: 'portfolio_ui.rag_yellow',    Icon: AlertTriangle },
  red:    { color: 'var(--danger)',  label: 'portfolio_ui.rag_red',   Icon: AlertTriangle },
  grey:   { color: 'var(--text-2)', label: 'portfolio_ui.rag_grey',   Icon: Clock },
};
const ESTADOS: Record<string, string> = {
  planning: 'portfolio_ui.estado_planning',
  active: 'portfolio_ui.estado_active',
  archived: 'portfolio_ui.estado_archived',
};

// ── RAG pill ───────────────────────────────────────────────────────────────────
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
    <span className="pf-row pf-box-4" style={{ '--pf-box-4-background': alpha(r.color, '22'), '--pf-box-4-color': r.color } as CSSProperties}>
      <r.Icon size={11} />
      {t(r.label)}
    </span>
  );
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
  const dialogRef = useDialogo<HTMLDivElement>(true, onClose);

  return (
    <div className="pf-row-2" role="presentation" onMouseDown={onClose}>
      <div className="pf-card" ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="portfolio-create-title" onMouseDown={e => e.stopPropagation()}>
        <div className="pf-text-lg-strong" id="portfolio-create-title">{initial ? t('portfolio_ui.editar_cartera') : t('portfolio_ui.nueva_cartera')}</div>
        <div className="u-stack-14">
          <div><label className="pf-ls" id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`}>{t('portfolio_ui.nombre_obligatorio')}</label><input className="pf-fs" id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.name} onChange={set('name')} placeholder={t('portfolio.nombre_de_la_cartera')} /></div>
          <div><label className="pf-ls" id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`}>{t('portfolio.descripcion')}</label><textarea className="pf-fs pf-input" id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.description || ''} onChange={set('description')} /></div>
          <div className="u-grid2-12">
            <div><label className="pf-ls" id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`}>{t('portfolio_ui.estado')}</label>
              <select className="pf-fs" id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.status} onChange={set('status')}>
                <option value="planning">{t('portfolio_ui.estado_planning')}</option>
                <option value="active">{t('portfolio_ui.estado_active')}</option>
                <option value="archived">{t('portfolio_ui.estado_archived')}</option>
              </select>
            </div>
            <div><label className="pf-ls" id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`}>{t('portfolio_ui.presupuesto_total_moneda', { moneda: fmtMoneda.simbolo })}</label><input className="pf-fs" id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} type="number" value={form.budget_total || ''} onChange={set('budget_total')} placeholder={t('portfolio_ui.ej_presupuesto')} /></div>
          </div>
          <div className="u-grid2-12">
            <div><label className="pf-ls" id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`}>{t('portfolio_ui.fecha_inicio')}</label><DateInput id={`${idCampo}-5`} value={form.start_date || ''} onChange={set('start_date')} className="pf-fs" /></div>
            <div><label className="pf-ls" id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`}>{t('portfolio_ui.fecha_fin')}</label><DateInput id={`${idCampo}-6`} value={form.end_date || ''} onChange={set('end_date')} className="pf-fs" /></div>
          </div>
        </div>
        <div className="pf-row-3">
          <button className="pf-btn-ghost" onClick={onClose}>{t('common.cancel')}</button>
          <button className="pf-btn" onClick={() => onSave(form)} disabled={!form.name}>
            {initial ? t('common.save') : t('portfolio_ui.crear_cartera')}
          </button>
        </div>
      </div>
    </div>
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
  const dialogRef = useDialogo<HTMLDivElement>(true, onClose);

  return (
    <div className="pf-row-4" role="presentation" onMouseDown={onClose}>
      <div className="pf-stack" ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="portfolio-add-project-title" onMouseDown={e => e.stopPropagation()}>
        <div className="pf-text-md-em-strong" id="portfolio-add-project-title">{t('portfolio.anadir_proyecto_a_la_cartera')}</div>
        <input className="pf-input-2" aria-label={t('portfolio_ui.buscar_proyectos')} value={search} onChange={e => setSearch(e.target.value)} placeholder={t('portfolio_ui.buscar_proyectos')} />
        <div className="pf-box">
          {available.map(p => (
            <button className="pf-btn-ghost-2" key={p.id} type="button" onClick={() => addProject(p.id)}>
              <div>
                <div className="u-base-600">{p.name}</div>
                <div className="u-text3-xs">{p.status}</div>
              </div>
              <Plus size={14} color="var(--accent)" />
            </button>
          ))}
          {available.length === 0 && <div className="pf-state-muted">{t('portfolio.sin_resultados')}</div>}
        </div>
        <button className="pf-btn-ghost-3" onClick={onClose}>{t('common.close')}</button>
      </div>
    </div>
  );
}

// ── Portfolio dashboard ────────────────────────────────────────────────────────
function PortfolioDashboard({ portfolioId, onClose }: { portfolioId: string | number; onClose: () => void }) {
  const fmtMoneda = useFormatoMoneda()
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
    <div className="pf-row-5" role="presentation" onMouseDown={onClose}>
      <div className="pf-card-2" ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="portfolio-dashboard-title" onMouseDown={e => e.stopPropagation()}>
        {isLoading && <div className="u-text3">{t('portfolio_ui.cargando_panel')}</div>}
        {dash && <>
          {/* Header */}
          <div className="pf-row-6">
            <div>
              <div className="pf-text-xl-strong" id="portfolio-dashboard-title">{dash.portfolio_name}</div>
              <div className="pf-text-muted-sm">
                {t('portfolio_ui.n_proyectos', { n: dash.project_count })} · {ESTADOS[dash.status] ? t(ESTADOS[dash.status]) : dash.status}
              </div>
            </div>
            <div className="u-row-center-10">
              <button className="pf-btn-accent-base" onClick={() => setShowAddProject(true)}>
                <Plus size={13} /> {t('portfolio.anadir_proyecto')}
              </button>
              <button className="pf-btn-2" onClick={onClose}><X size={18} /></button>
            </div>
          </div>

          {/* KPIs */}
          <div className="pf-grid">
            {[
              { label: t('portfolio_ui.presupuesto_total'), value: fmtMoneda(dash.budget_envelope, { decimales: 0 }), sub: t('portfolio_ui.gastado_importe', { importe: fmtMoneda(dash.budget_spent, { decimales: 0 }) }), Icon: DollarSign, color: dash.budget_pct > 100 ? 'var(--danger)' : 'var(--text-1)' },
              { label: t('portfolio_ui.pct_gastado'),   value: `${dash.budget_pct}%`, sub: dash.budget_pct > 90 ? t('portfolio_ui.cerca_limite') : t('portfolio_ui.dentro_presupuesto'), Icon: BarChart2, color: dash.budget_pct > 100 ? 'var(--danger)' : dash.budget_pct > 85 ? 'var(--warning)' : 'var(--success)' },
              { label: t('portfolio_ui.rag_red'),   value: dash.health_counts.red || 0, sub: t('portfolio_ui.n_en_atencion', { n: dash.health_counts.yellow || 0 }), Icon: AlertTriangle, color: dash.health_counts.red > 0 ? 'var(--danger)' : 'var(--text-1)' },
              { label: t('portfolio_ui.rag_green'),  value: dash.health_counts.green || 0, sub: t('portfolio_ui.n_total', { n: dash.project_count }), Icon: CheckCircle, color: 'var(--success)' },
            ].map(({ label, value, sub, Icon, color }) => (
              <div className="pf-card-3" key={label}>
                <div className="pf-row-7">
                  <div className="u-text3-xs">{label}</div>
                  <Icon size={15} color="var(--accent)" />
                </div>
                <div className="pf-text-xl-em-strong" style={{ '--pf-text-xl-em-strong-color': color } as CSSProperties}>{value}</div>
                <div className="u-text3-xs">{sub}</div>
              </div>
            ))}
          </div>

          {/* Projects table */}
          <div className="pf-card-4">
            <table className="pf-table">
              <thead>
                <tr className="pf-tr">
                  {['RAG', t('portfolio_ui.col_proyecto'), t('portfolio_ui.col_hecho'), 'CPI', 'SPI', t('portfolio_ui.col_presupuesto'), t('portfolio_ui.col_gasto_real'), t('portfolio_ui.col_proximo_hito'), ''].map(h => (
                    <th className="pf-th" key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {dash.projects.map((p, i) => {
                  const nextMs = p.milestones?.[0];
                  const isExpanded = expandedId === p.project_id;
                  return (
                    <React.Fragment key={p.project_id}>
                      <tr className="pf-tr-2" style={{ '--pf-tr-2-border-top': i > 0 ? '1px solid var(--surface-3)' : 'none' } as CSSProperties}
                        onClick={() => setExpandedId(isExpanded ? null : p.project_id)}
                        role="button"
                        tabIndex={0}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            setExpandedId(isExpanded ? null : p.project_id);
                          }
                        }}>
                        <td className="pf-td"><RagPill rag={p.rag} /></td>
                        <td className="pf-td-2">
                          <span className="u-row-center-6">
                            {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                            {p.project_name}
                          </span>
                        </td>
                        <td className="pf-td" aria-label={`${p.pct_complete}%`}>
                          <div className="u-row-center-8">
                            <div className="pf-card-5">
                              <div className="pf-box-2" style={{ '--pf-box-2-width': `${p.pct_complete}%`, '--pf-box-2-background': RAG[p.rag]?.color || 'var(--text-3)' } as CSSProperties} />
                            </div>
                            <span className="u-xs">{p.pct_complete}%</span>
                          </div>
                        </td>
                        <td className="pf-td-3" style={{ '--pf-td-3-color': p.cpi == null ? 'var(--text-3)' : p.cpi >= 0.9 ? 'var(--success)' : 'var(--danger)' } as CSSProperties}>{fmtI(p.cpi)}</td>
                        <td className="pf-td-4" style={{ '--pf-td-4-color': p.spi == null ? 'var(--text-3)' : p.spi >= 0.9 ? 'var(--success)' : 'var(--danger)' } as CSSProperties}>{fmtI(p.spi)}</td>
                        <td className="pf-td-muted">{fmtMoneda(p.bac, { decimales: 0 })}</td>
                        <td className="pf-td-muted">{fmtMoneda(p.ac, { decimales: 0 })}</td>
                        <td className="pf-td">
                          {nextMs ? (
                            <span className="u-text2-xs">
                              <Calendar size={10} className="pf-icono-previo" aria-hidden />
                              {nextMs.title} · {nextMs.due_date}
                              {nextMs.is_completed && <Check size={10} color="var(--success)" className="pf-icono-posterior" aria-hidden />}
                            </span>
                          ) : <span className="u-text3-xs">—</span>}
                        </td>
                        <td className="pf-td">
                          <button className="pf-btn-2" aria-label={t('portfolio_ui.quitar')} title={t('portfolio_ui.quitar')} onClick={ev => { ev.stopPropagation(); openConfirmGlobal({message:t('portfolio_ui.quitar_confirm'),onConfirm:()=>removeProject(p.project_id),danger:true}) }}><X size={13} /></button>
                        </td>
                      </tr>
                      {isExpanded && (
                        <tr className="pf-tr-3">
                          <td className="pf-td-5" colSpan={9}>
                            <div className="pf-text-muted-sm-2">{t('portfolio.hitos_proximos')}</div>
                            {p.milestones.length === 0
                              ? <span className="u-text3-sm">{t('portfolio.sin_hitos_proximos')}</span>
                              : p.milestones.map(m => (
                                <div className="pf-row-8" key={m.id}>
                                  {m.is_completed ? <Check size={12} color="var(--success)" /> : <Clock size={12} color="var(--warning)" />}
                                  <span>{m.title}</span>
                                  <span className="u-text3">{m.due_date}</span>
                                </div>
                              ))}
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>}
      </div>
      {showAddProject && dash && (
        <AddProjectModal
          portfolioId={portfolioId}
          existingIds={dash.projects.map(p => p.project_id)}
          onClose={() => setShowAddProject(false)}
          onAdded={() => setShowAddProject(false)}
        />
      )}
    </div>
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
    <PageShell className="pf-shell">
      {/* Header */}
      <div className="pf-row-9">
        <div className="u-row-center-12">
          <Briefcase size={22} color="var(--accent)" />
          <div>
            <h1 className="pf-title-xl-em-strong">{t('portfolio.title')}</h1>
            <p className="pf-text-muted-base">{t('portfolio.subtitle')}</p>
          </div>
        </div>
        <button className="pf-btn-base" onClick={() => setShowCreate(true)}>
          <Plus size={14} /> {t('portfolio.new_portfolio')}
        </button>
      </div>

      {/* Portfolio cards */}
      {isLoading ? (
        <div className="pf-state-muted-2">{t('common.loading')}</div>
      ) : portfolios.length === 0 ? (
        <div className="pf-state-muted-3">
          <Briefcase size={40} className="pf-vacio-icono" aria-hidden />
          <div className="pf-text-lg">{t('portfolio.sin_carteras')}</div>
          <div className="pf-text-base">{t('portfolio.crea_tu_primera_cartera_para_agrupar_proyectos')}</div>
        </div>
      ) : (
        <div className="pf-grid-2">
          {portfolios.map(p => (
            <div className="pf-card-6" key={p.id}
              onClick={() => setSelectedId(p.id)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  setSelectedId(p.id);
                }
              }}>
              <div className="pf-row-10">
                <div>
                  <div className="pf-text-md-em-strong-2">{p.name}</div>
                  <div className="u-text3-xs">{t('portfolio_ui.n_proyectos', { n: p.project_count })} · {ESTADOS[p.status] ? t(ESTADOS[p.status]) : p.status}</div>
                </div>
                <span className="pf-box-3" style={{ '--pf-box-3-background': p.status === 'active' ? alpha('var(--success)', '22') : p.status === 'planning' ? alpha('var(--accent)', '22') : alpha('var(--text-3)', '22'), '--pf-box-3-color': p.status === 'active' ? 'var(--success)' : p.status === 'planning' ? 'var(--accent)' : 'var(--text-3)' } as CSSProperties}>{ESTADOS[p.status] ? t(ESTADOS[p.status]) : p.status}</span>
              </div>

              {p.description && (
                <div className="pf-text-muted-sm-3">
                  {p.description.length > 100 ? p.description.slice(0, 100) + '…' : p.description}
                </div>
              )}

              {p.budget_total != null && (
                <div className="pf-text-muted-sm-4">
                  <DollarSign size={11} className="pf-icono-previo" aria-hidden />
                  {t('portfolio_ui.presupuesto_dos_puntos')} <strong className="u-text1">{fmtMoneda(p.budget_total, { decimales: 0 })}</strong>
                </div>
              )}

              <div className="pf-row-11">
                <button className="pf-btn-accent-xs" onClick={ev => { ev.stopPropagation(); setEditing(p); }}>
                  {t('common.edit')}
                </button>
                <div className="u-row-center-12">
                  <button className="pf-btn-danger-xs" onClick={ev => { ev.stopPropagation(); openConfirmGlobal({message:t('portfolio_ui.eliminar_confirm', { nombre: p.name }),onConfirm:()=>deletePortfolio(p.id),danger:true}) }}>
                    {t('common.delete')}
                  </button>
                  <span className="pf-row-accent">
                    {t('portfolio_ui.ver_panel')} <ChevronRight size={12} />
                  </span>
                </div>
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
