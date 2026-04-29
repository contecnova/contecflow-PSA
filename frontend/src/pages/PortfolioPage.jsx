/**
 * PortfolioPage — Gestión de carteras de proyectos
 * Vista RAG (Red/Amber/Green) de salud + EVM consolidado + hitos cruzados.
 */
import React, { useState } from 'react';
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api, { portfolioApi, projectsApi } from '../services/api';
import { useAppT } from '../i18n/AppLangContext'
import {
  Briefcase, Plus, ChevronRight, ChevronDown, X, Check,
  AlertTriangle, CheckCircle, Clock,
  DollarSign, BarChart2, Calendar
} from 'lucide-react';

// ── utils ──────────────────────────────────────────────────────────────────────
const _fmt  = n => n == null ? '—' : Number(n).toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fmtE = n => n == null ? '—' : `${Number(n).toLocaleString('es-ES', { maximumFractionDigits: 0 })} €`;
const fmtI = n => n == null ? '—' : Number(n).toLocaleString('es-ES', { minimumFractionDigits: 3, maximumFractionDigits: 3 });

const RAG = {
  green:  { color: 'var(--success)', label: 'En control',  Icon: CheckCircle },
  yellow: { color: 'var(--warning)', label: 'Atención',    Icon: AlertTriangle },
  red:    { color: 'var(--danger)',  label: 'En riesgo',   Icon: AlertTriangle },
  grey:   { color: 'var(--text-2)', label: 'Sin datos',   Icon: Clock },
};

// ── RAG pill ───────────────────────────────────────────────────────────────────
function RagPill({ rag }) {
  const r = RAG[rag] || RAG.grey;
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4,
      background: r.color + '22', color: r.color,
      borderRadius: 20, padding: '3px 10px', fontSize: 11, fontWeight: 600 }}>
      <r.Icon size={11} />
      {r.label}
    </span>
  );
}

// ── Create/edit portfolio modal ────────────────────────────────────────────────
function PortfolioModal({ initial, onClose, onSave }) {
  const [form, setForm] = useState(initial || { name: '', description: '', status: 'active', budget_total: '' });
  const set = k => e => setForm(f => ({ ...f, [k]: e.target.value }));
  const fs = { width: '100%', padding: '8px 10px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'var(--surface-2)', color: 'var(--text-1)', fontSize: 13, boxSizing: 'border-box' };
  const ls = { display: 'block', fontSize: 11, fontWeight: 600, color: 'var(--text-3)', marginBottom: 5 };

  return (
    <div role="presentation" style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onMouseDown={onClose}>
      <div role="presentation" style={{ background: 'var(--surface-1)', borderRadius: 14, padding: 28, width: 480, maxWidth: '95vw', boxShadow: '0 20px 60px rgba(0,0,0,0.4)' }} onMouseDown={e => e.stopPropagation()}>
        <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 20 }}>{initial ? 'Editar cartera' : 'Nueva cartera'}</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div><label style={ls}>Nombre *</label><input value={form.name} onChange={set('name')} style={fs} placeholder="Nombre de la cartera..." /></div>
          <div><label style={ls}>Descripción</label><textarea value={form.description || ''} onChange={set('description')} style={{ ...fs, resize: 'vertical', minHeight: 70 }} /></div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div><label style={ls}>Estado</label>
              <select value={form.status} onChange={set('status')} style={fs}>
                <option value="planning">Planificación</option>
                <option value="active">Activo</option>
                <option value="archived">Archivado</option>
              </select>
            </div>
            <div><label style={ls}>Presupuesto total (€)</label><input type="number" value={form.budget_total || ''} onChange={set('budget_total')} style={fs} placeholder="Ej: 500000" /></div>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div><label style={ls}>Fecha inicio</label><input type="date" value={form.start_date || ''} onChange={set('start_date')} style={fs} /></div>
            <div><label style={ls}>Fecha fin</label><input type="date" value={form.end_date || ''} onChange={set('end_date')} style={fs} /></div>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 10, marginTop: 22, justifyContent: 'flex-end' }}>
          <button onClick={onClose} style={{ padding: '8px 18px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--text-2)', cursor: 'pointer' }}>Cancelar</button>
          <button onClick={() => onSave(form)} disabled={!form.name} style={{ padding: '8px 18px', borderRadius: 8, border: 'none', background: 'var(--accent)', color: '#fff', cursor: 'pointer', fontWeight: 600 }}>
            {initial ? 'Guardar' : 'Crear cartera'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Add project to portfolio modal ─────────────────────────────────────────────
function AddProjectModal({ portfolioId, existingIds, onClose, onAdded }) {
  const [search, setSearch] = useState('');
  const qc = useQueryClient();

  const { data: allProjects = [] } = useQuery({
    queryKey: ['projects-for-portfolio'],
    queryFn: () => projectsApi.list().then(r => Array.isArray(r.data) ? r.data : r.data?.items || []),
  });

  const { mutate: addProject } = useMutation({
    mutationFn: pid => portfolioApi.addProject(portfolioId, pid),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['portfolio-dashboard', portfolioId] }); onAdded(); },
  });

  const available = allProjects.filter(p => !existingIds.includes(p.id) &&
    p.name.toLowerCase().includes(search.toLowerCase()));

  return (
    <div role="presentation" style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 1100, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onMouseDown={onClose}>
      <div role="presentation" style={{ background: 'var(--surface-1)', borderRadius: 14, padding: 24, width: 440, maxWidth: '95vw', maxHeight: '70vh', display: 'flex', flexDirection: 'column', boxShadow: '0 20px 60px rgba(0,0,0,0.4)' }} onMouseDown={e => e.stopPropagation()}>
        <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 14 }}>Añadir proyecto a la cartera</div>
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Buscar proyectos..."
          style={{ padding: '8px 12px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'var(--surface-2)', color: 'var(--text-1)', fontSize: 13, marginBottom: 12 }} />
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {available.map(p => (
            <button key={p.id} type="button" onClick={() => addProject(p.id)}
              style={{ padding: '10px 14px', borderRadius: 8, cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%', textAlign: 'left', background: 'transparent', border: 'none', fontFamily: 'inherit' }}
              onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-3)'}
              onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
              <div>
                <div style={{ fontWeight: 600, fontSize: 13 }}>{p.name}</div>
                <div style={{ fontSize: 11, color: 'var(--text-3)' }}>{p.status}</div>
              </div>
              <Plus size={14} color="var(--accent)" />
            </button>
          ))}
          {available.length === 0 && <div style={{ color: 'var(--text-3)', fontSize: 13, padding: '20px 0', textAlign: 'center' }}>Sin resultados</div>}
        </div>
        <button onClick={onClose} style={{ marginTop: 14, padding: '8px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--text-2)', cursor: 'pointer' }}>Cerrar</button>
      </div>
    </div>
  );
}

// ── Portfolio dashboard ────────────────────────────────────────────────────────
function PortfolioDashboard({ portfolioId, onClose }) {
  const qc = useQueryClient();
  const [showAddProject, setShowAddProject] = useState(false);
  const [expandedId, setExpandedId] = useState(null);

  const { data: dash, isLoading } = useQuery({
    queryKey: ['portfolio-dashboard', portfolioId],
    queryFn: () => portfolioApi.dashboard(portfolioId).then(r => r.data),
    enabled: !!portfolioId,
    refetchInterval: 60000,
  });

  const { mutate: removeProject } = useMutation({
    mutationFn: pid => portfolioApi.removeProject(portfolioId, pid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['portfolio-dashboard', portfolioId] }),
  });

  if (!portfolioId) return null;

  return (
    <div role="presentation" style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 1000, display: 'flex', alignItems: 'flex-start', justifyContent: 'center', paddingTop: 40, overflowY: 'auto' }} onMouseDown={onClose}>
      <div role="presentation" style={{ background: 'var(--surface-1)', borderRadius: 16, padding: 32, width: 900, maxWidth: '96vw', boxShadow: '0 24px 80px rgba(0,0,0,0.4)', marginBottom: 40 }} onMouseDown={e => e.stopPropagation()}>
        {isLoading && <div style={{ color: 'var(--text-3)' }}>Cargando dashboard…</div>}
        {dash && <>
          {/* Header */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 }}>
            <div>
              <div style={{ fontSize: 20, fontWeight: 700 }}>{dash.portfolio_name}</div>
              <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 3 }}>
                {dash.project_count} proyectos · {dash.status}
              </div>
            </div>
            <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
              <button onClick={() => setShowAddProject(true)}
                style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '7px 14px', borderRadius: 8, border: '1px solid var(--accent)', background: 'var(--accent)15', color: 'var(--accent)', cursor: 'pointer', fontSize: 13, fontWeight: 600 }}>
                <Plus size={13} /> Añadir proyecto
              </button>
              <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-3)' }}><X size={18} /></button>
            </div>
          </div>

          {/* KPIs */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginBottom: 24 }}>
            {[
              { label: 'Presupuesto total', value: fmtE(dash.budget_envelope), sub: `Gastado: ${fmtE(dash.budget_spent)}`, Icon: DollarSign, color: dash.budget_pct > 100 ? '#ef4444' : 'var(--text-1)' },
              { label: '% Gastado',   value: `${dash.budget_pct}%`, sub: dash.budget_pct > 90 ? '⚠ Cerca del límite' : 'Dentro de presupuesto', Icon: BarChart2, color: dash.budget_pct > 100 ? '#ef4444' : dash.budget_pct > 85 ? '#eab308' : '#22c55e' },
              { label: 'En riesgo',   value: dash.health_counts.red || 0, sub: `${dash.health_counts.yellow || 0} en atención`, Icon: AlertTriangle, color: dash.health_counts.red > 0 ? '#ef4444' : 'var(--text-1)' },
              { label: 'En control',  value: dash.health_counts.green || 0, sub: `${dash.project_count} total`, Icon: CheckCircle, color: '#22c55e' },
            ].map(({ label, value, sub, Icon, color }) => (
              <div key={label} style={{ background: 'var(--surface-2)', borderRadius: 12, padding: '14px 18px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div style={{ fontSize: 11, color: 'var(--text-3)' }}>{label}</div>
                  <Icon size={15} color="var(--accent)" />
                </div>
                <div style={{ fontSize: 22, fontWeight: 700, color, margin: '6px 0 2px' }}>{value}</div>
                <div style={{ fontSize: 11, color: 'var(--text-3)' }}>{sub}</div>
              </div>
            ))}
          </div>

          {/* Projects table */}
          <div style={{ background: 'var(--surface-2)', borderRadius: 12, overflow: 'hidden' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ background: 'var(--surface-3)' }}>
                  {['RAG', 'Proyecto', '% Hecho', 'CPI', 'SPI', 'Presupuesto', 'Gasto real', 'Próximo hito', ''].map(h => (
                    <th key={h} style={{ padding: '9px 14px', textAlign: 'left', fontSize: 11, color: 'var(--text-3)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {dash.projects.map((p, i) => {
                  const nextMs = p.milestones?.[0];
                  const isExpanded = expandedId === p.project_id;
                  return (
                    <React.Fragment key={p.project_id}>
                      <tr style={{ borderTop: i > 0 ? '1px solid var(--surface-3)' : 'none', cursor: 'pointer' }}
                        onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-3)'}
                        onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                        onClick={() => setExpandedId(isExpanded ? null : p.project_id)}
                        role="button"
                        tabIndex={0}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            setExpandedId(isExpanded ? null : p.project_id);
                          }
                        }}>
                        <td style={{ padding: '11px 14px' }}><RagPill rag={p.rag} /></td>
                        <td style={{ padding: '11px 14px', fontWeight: 600 }}>
                          <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                            {p.project_name}
                          </span>
                        </td>
                        <td style={{ padding: '11px 14px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <div style={{ width: 50, background: 'var(--surface-4)', borderRadius: 3, height: 5 }}>
                              <div style={{ width: `${p.pct_complete}%`, background: RAG[p.rag]?.color || '#6b7280', height: '100%', borderRadius: 3 }} />
                            </div>
                            <span style={{ fontSize: 11 }}>{p.pct_complete}%</span>
                          </div>
                        </td>
                        <td style={{ padding: '11px 14px', fontWeight: 600, color: p.cpi == null ? '#6b7280' : p.cpi >= 0.9 ? '#22c55e' : '#ef4444' }}>{fmtI(p.cpi)}</td>
                        <td style={{ padding: '11px 14px', fontWeight: 600, color: p.spi == null ? '#6b7280' : p.spi >= 0.9 ? '#22c55e' : '#ef4444' }}>{fmtI(p.spi)}</td>
                        <td style={{ padding: '11px 14px', color: 'var(--text-2)' }}>{fmtE(p.bac)}</td>
                        <td style={{ padding: '11px 14px', color: 'var(--text-2)' }}>{fmtE(p.ac)}</td>
                        <td style={{ padding: '11px 14px' }}>
                          {nextMs ? (
                            <span style={{ fontSize: 11, color: 'var(--text-2)' }}>
                              <Calendar size={10} style={{ marginRight: 4, verticalAlign: 'middle' }} />
                              {nextMs.title} · {nextMs.due_date}
                              {nextMs.is_completed && <Check size={10} color="#22c55e" style={{ marginLeft: 4 }} />}
                            </span>
                          ) : <span style={{ fontSize: 11, color: 'var(--text-3)' }}>—</span>}
                        </td>
                        <td style={{ padding: '11px 14px' }}>
                          <button onClick={ev => { ev.stopPropagation(); openConfirmGlobal({message:'¿Quitar del portfolio?',onConfirm:()=>removeProject(p.project_id),danger:true}) }}
                            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-3)' }}><X size={13} /></button>
                        </td>
                      </tr>
                      {isExpanded && (
                        <tr style={{ background: 'var(--surface-2)' }}>
                          <td colSpan={9} style={{ padding: '8px 28px 14px' }}>
                            <div style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 8 }}>Hitos próximos</div>
                            {p.milestones.length === 0
                              ? <span style={{ fontSize: 12, color: 'var(--text-3)' }}>Sin hitos próximos</span>
                              : p.milestones.map(m => (
                                <div key={m.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '5px 0', fontSize: 12 }}>
                                  {m.is_completed ? <Check size={12} color="#22c55e" /> : <Clock size={12} color="#eab308" />}
                                  <span>{m.title}</span>
                                  <span style={{ color: 'var(--text-3)' }}>{m.due_date}</span>
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
  const t = useAppT()
  const qc = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [editing, setEditing] = useState(null);
  const [selectedId, setSelectedId] = useState(null);

  const { data: portfolios = [], isLoading } = useQuery({
    queryKey: ['portfolios'],
    queryFn: () => portfolioApi.list().then(r => r.data),
  });

  const { mutate: createPortfolio } = useMutation({
    mutationFn: data => portfolioApi.create({ ...data, budget_total: data.budget_total ? Number(data.budget_total) : null }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['portfolios'] }); setShowCreate(false); },
  });

  const { mutate: updatePortfolio } = useMutation({
    mutationFn: ({ id, data }) => portfolioApi.update(id, { ...data, budget_total: data.budget_total ? Number(data.budget_total) : null }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['portfolios'] }); setEditing(null); },
  });

  const { mutate: deletePortfolio } = useMutation({
    mutationFn: id => portfolioApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['portfolios'] }),
  });

  return (
    <div style={{ padding: '24px 32px', maxWidth: 1100, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 28 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Briefcase size={22} color="var(--accent)" />
          <div>
            <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0 }}>{t('portfolio.title')}</h1>
            <p style={{ color: 'var(--text-3)', fontSize: 13, margin: '2px 0 0' }}>{t('portfolio.subtitle')}</p>
          </div>
        </div>
        <button onClick={() => setShowCreate(true)}
          style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '9px 18px', background: 'var(--accent)', border: 'none', borderRadius: 9, color: '#fff', cursor: 'pointer', fontWeight: 600, fontSize: 13 }}>
          <Plus size={14} /> {t('portfolio.new_portfolio')}
        </button>
      </div>

      {/* Portfolio cards */}
      {isLoading ? (
        <div style={{ color: 'var(--text-3)', textAlign: 'center', padding: 40 }}>Cargando…</div>
      ) : portfolios.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-3)' }}>
          <Briefcase size={40} style={{ marginBottom: 16, opacity: 0.3 }} />
          <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 8 }}>Sin carteras</div>
          <div style={{ fontSize: 13 }}>Crea tu primera cartera para agrupar proyectos y hacer seguimiento consolidado.</div>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 18 }}>
          {portfolios.map(p => (
            <div key={p.id} style={{
              background: 'var(--surface-2)', borderRadius: 14, padding: '20px 22px',
              cursor: 'pointer', transition: 'box-shadow 0.2s, transform 0.15s',
              border: '1px solid transparent',
            }}
              onMouseEnter={e => { e.currentTarget.style.boxShadow = '0 8px 30px rgba(0,0,0,0.2)'; e.currentTarget.style.borderColor = 'var(--accent)30'; }}
              onMouseLeave={e => { e.currentTarget.style.boxShadow = 'none'; e.currentTarget.style.borderColor = 'transparent'; }}
              onClick={() => setSelectedId(p.id)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  setSelectedId(p.id);
                }
              }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14 }}>
                <div>
                  <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 3 }}>{p.name}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-3)' }}>{p.project_count} proyectos · {p.status}</div>
                </div>
                <span style={{ fontSize: 10, fontWeight: 600, padding: '3px 10px', borderRadius: 20,
                  background: p.status === 'active' ? '#22c55e22' : p.status === 'planning' ? '#6366f122' : '#6b728022',
                  color:      p.status === 'active' ? '#22c55e'   : p.status === 'planning' ? '#6366f1'   : '#6b7280',
                }}>{p.status}</span>
              </div>

              {p.description && (
                <div style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 14, lineHeight: 1.5 }}>
                  {p.description.length > 100 ? p.description.slice(0, 100) + '…' : p.description}
                </div>
              )}

              {p.budget_total != null && (
                <div style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 10 }}>
                  <DollarSign size={11} style={{ marginRight: 4, verticalAlign: 'middle' }} />
                  Presupuesto: <strong style={{ color: 'var(--text-1)' }}>{Number(p.budget_total).toLocaleString('es-ES', { maximumFractionDigits: 0 })} €</strong>
                </div>
              )}

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 12 }}>
                <button onClick={ev => { ev.stopPropagation(); setEditing(p); }}
                  style={{ fontSize: 11, color: 'var(--accent)', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
                  Editar
                </button>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <button onClick={ev => { ev.stopPropagation(); openConfirmGlobal({message:`¿Eliminar cartera "${p.name}"?`,onConfirm:()=>deletePortfolio(p.id),danger:true}) }}
                    style={{ fontSize: 11, color: '#ef4444', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
                    Eliminar
                  </button>
                  <span style={{ fontSize: 12, color: 'var(--accent)', display: 'flex', alignItems: 'center', gap: 4 }}>
                    Ver dashboard <ChevronRight size={12} />
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
    </div>
  );
}
