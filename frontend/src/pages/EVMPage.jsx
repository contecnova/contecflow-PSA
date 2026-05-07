/**
 * EVMPage — Earned Value Management
 * Vista de cartera con CPI, SPI, EAC, VAC, TCPI para todos los proyectos activos.
 * Drill-down por proyecto con métricas completas y gauge visual.
 */
import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { projectsApi } from '../services/api';
import { TrendingUp, TrendingDown, AlertTriangle, CheckCircle, Clock, DollarSign, Target, BarChart2, ChevronRight } from 'lucide-react';
import PageHeader from '../components/layout/PageHeader';
import PageShell from '../components/layout/PageShell'
import { useAppT } from '../i18n/AppLangContext';

// ── helpers ─────────────────────────────────────────────────────────────────
const fmt = (n, dec = 2) => n == null ? '—' : Number(n).toLocaleString('es-ES', { minimumFractionDigits: dec, maximumFractionDigits: dec });
const fmtEur = (n) => n == null ? '—' : `${fmt(n, 0)} €`;
const fmtPct = (n) => n == null ? '—' : `${fmt(n, 1)} %`;
const fmtIdx = (n) => n == null ? '—' : fmt(n, 3);

const HEALTH_COLOR = { green: 'var(--success)', yellow: 'var(--warning)', red: 'var(--danger)', grey: 'var(--text-3)' };
const HEALTH_LABEL = { green: 'En control', yellow: 'Atención', red: 'En riesgo', grey: 'Sin datos' };
const HEALTH_ICON  = { green: CheckCircle, yellow: AlertTriangle, red: AlertTriangle, grey: Clock };

function IndexBadge({ label, value, good, format = fmtIdx }) {
  const color = value == null ? 'var(--text-3)' : value >= (good || 0.9) ? 'var(--success)' : value >= 0.8 ? 'var(--warning)' : 'var(--danger)';
  return (
    <div style={{ background: 'var(--surface-2)', borderRadius: 10, padding: '12px 16px', minWidth: 120 }}>
      <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: "var(--text-xl-em)", fontWeight: 700, color }}>{format(value)}</div>
    </div>
  );
}

function VarianceBadge({ label, value }) {
  const pos = value == null ? null : value >= 0;
  const color = pos == null ? 'var(--text-3)' : pos ? 'var(--success)' : 'var(--danger)';
  const Icon  = pos == null ? null : pos ? TrendingUp : TrendingDown;
  return (
    <div style={{ background: 'var(--surface-2)', borderRadius: 10, padding: '12px 16px', minWidth: 120 }}>
      <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginBottom: 4 }}>{label}</div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, color }}>
        {Icon && <Icon size={14} />}
        <span style={{ fontSize: "var(--text-lg-em)", fontWeight: 700 }}>{fmtEur(value)}</span>
      </div>
    </div>
  );
}

function ProgressBar({ pct, color = 'var(--accent)', label }) {
  return (
    <div>
      {label && <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginBottom: 4 }}>{label}</div>}
      <div style={{ background: 'var(--surface-3)', borderRadius: 4, height: 8, overflow: 'hidden' }}>
        <div style={{ width: `${Math.min(pct, 100)}%`, background: color, height: '100%', transition: 'width 0.5s' }} />
      </div>
      <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginTop: 2 }}>{fmtPct(pct)}</div>
    </div>
  );
}

// ── Detail panel ─────────────────────────────────────────────────────────────
function EVMDetail({ projectId, onClose }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['evm', projectId],
    queryFn: () => projectsApi.evm(projectId).then(r => r.data),
    enabled: !!projectId,
  });

  if (!projectId) return null;

  return (
    <div role="presentation" style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 1000,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }} onMouseDown={onClose}>
      <div role="dialog" aria-modal="true" aria-labelledby="evm-dialog-title" style={{
        background: 'var(--surface-1)', borderRadius: 16, padding: 32,
        width: 700, maxWidth: '95vw', maxHeight: '90vh', overflowY: 'auto',
        boxShadow: '0 24px 80px rgba(0,0,0,0.4)',
      }} onMouseDown={e => e.stopPropagation()}>
        {isLoading && <div style={{ color: 'var(--text-3)' }}>Calculando métricas EVM…</div>}
        {isError  && <div style={{ color: 'var(--danger)' }}>Error al cargar métricas</div>}
        {data && <>
          {/* Header */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 }}>
            <div>
              <div id="evm-dialog-title" style={{ fontSize: "var(--text-xl)", fontWeight: 700 }}>{data.project_name}</div>
              <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)', marginTop: 4 }}>
                {data.start_date} → {data.planned_end || 'Sin fecha fin'}
                {' · '}{data.done_tasks}/{data.total_tasks} tareas completadas
              </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8,
              color: HEALTH_COLOR[data.health], fontWeight: 600, fontSize: "var(--text-md)" }}>
              {React.createElement(HEALTH_ICON[data.health], { size: 16 })}
              {HEALTH_LABEL[data.health]}
            </div>
          </div>

          {/* Progress */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 24 }}>
            <ProgressBar pct={data.pct_complete} label="Avance real" color={HEALTH_COLOR[data.health]} />
            <ProgressBar pct={data.pct_time_elapsed} label="Tiempo transcurrido" color="var(--accent)" />
          </div>

          {/* Core values */}
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: 'var(--text-3)', marginBottom: 10, textTransform: 'uppercase', letterSpacing: 1 }}>Valores base</div>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              <IndexBadge label="BAC" value={data.bac} good={Infinity} format={fmtEur} />
              <IndexBadge label="PV" value={data.pv} good={Infinity} format={fmtEur} />
              <IndexBadge label="EV" value={data.ev} good={Infinity} format={fmtEur} />
              <IndexBadge label="AC" value={data.ac} good={Infinity} format={fmtEur} />
            </div>
          </div>

          {/* Indices */}
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: 'var(--text-3)', marginBottom: 10, textTransform: 'uppercase', letterSpacing: 1 }}>Índices de rendimiento</div>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              <IndexBadge label="CPI" value={data.cpi} />
              <IndexBadge label="SPI" value={data.spi} />
              <IndexBadge label="TCPI" value={data.tcpi} good={1.1} />
            </div>
          </div>

          {/* Variances */}
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: 'var(--text-3)', marginBottom: 10, textTransform: 'uppercase', letterSpacing: 1 }}>Varianzas</div>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              <VarianceBadge label="CV" value={data.cv} />
              <VarianceBadge label="SV" value={data.sv} />
            </div>
          </div>

          {/* Forecast */}
          <div>
            <div style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: 'var(--text-3)', marginBottom: 10, textTransform: 'uppercase', letterSpacing: 1 }}>Previsión final</div>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              <IndexBadge label="EAC" value={data.eac} good={Infinity} format={fmtEur} />
              <IndexBadge label="ETC" value={data.etc} good={Infinity} format={fmtEur} />
              <VarianceBadge label="VAC" value={data.vac} />
            </div>
          </div>

          {/* Legend */}
          <div style={{ marginTop: 24, padding: '12px 16px', background: 'var(--surface-2)', borderRadius: 10, fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>
            <strong>Guía rápida:</strong> CPI &gt; 1 = bajo presupuesto · CPI &lt; 1 = sobre presupuesto · SPI &gt; 1 = adelantado · SPI &lt; 1 = retrasado · TCPI &gt; 1.1 = metas difíciles de alcanzar
          </div>

          <button onClick={onClose} style={{
            marginTop: 20, padding: '9px 20px', background: 'var(--surface-3)', border: 'none',
            borderRadius: 8, color: 'var(--text-1)', cursor: 'pointer', width: '100%',
          }}>Cerrar</button>
        </>}
      </div>
    </div>
  );
}

// ── Portfolio table ───────────────────────────────────────────────────────────
export default function EVMPage() {
  const t = useAppT();
  const [selected, setSelected] = useState(null);

  const { data: portfolio = [], isLoading } = useQuery({
    queryKey: ['evm-portfolio'],
    queryFn: () => projectsApi.evmPortfolio().then(r => r.data),
    staleTime: 60000,
  });

  return (
    <PageShell>
      <PageHeader
        icon={<BarChart2 size={18} />}
        title={t('evm.title')}
        subtitle={t('evm.subtitle')}
      />

      {/* Summary KPIs */}
      {portfolio.length > 0 && (() => {
        const withCpi = portfolio.filter(p => p.cpi != null);
        const avgCpi  = withCpi.length ? withCpi.reduce((s, p) => s + p.cpi, 0) / withCpi.length : null;
        const withSpi = portfolio.filter(p => p.spi != null);
        const avgSpi  = withSpi.length ? withSpi.reduce((s, p) => s + p.spi, 0) / withSpi.length : null;
        const totalBac = portfolio.reduce((s, p) => s + (p.bac || 0), 0);
        const totalAc  = portfolio.reduce((s, p) => s + (p.ac || 0), 0);
        const reds     = portfolio.filter(p => p.health === 'red').length;
        return (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginBottom: 28 }}>
            {[
              { label: 'Proyectos activos', value: portfolio.length, sub: `${reds} en riesgo`, color: reds > 0 ? 'var(--danger)' : 'var(--text-1)', Icon: Target },
              { label: 'CPI medio cartera', value: fmtIdx(avgCpi), sub: avgCpi >= 0.9 ? 'Bajo presupuesto ✓' : 'Sobre presupuesto ✗', color: avgCpi == null ? 'var(--text-2)' : avgCpi >= 0.9 ? 'var(--success)' : 'var(--danger)', Icon: DollarSign },
              { label: 'SPI medio cartera', value: fmtIdx(avgSpi), sub: avgSpi >= 0.9 ? 'En plazo ✓' : 'Retrasado ✗', color: avgSpi == null ? 'var(--text-2)' : avgSpi >= 0.9 ? 'var(--success)' : 'var(--danger)', Icon: Clock },
              { label: 'Presupuesto total', value: fmtEur(totalBac), sub: `Gastado: ${fmtEur(totalAc)}`, color: 'var(--text-1)', Icon: BarChart2 },
            ].map(({ label, value, sub, color, Icon }) => (
              <div key={label} style={{ background: 'var(--surface-2)', borderRadius: 12, padding: '16px 20px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)' }}>{label}</div>
                  <Icon size={16} color="var(--accent)" />
                </div>
                <div style={{ fontSize: "var(--text-2xl)", fontWeight: 700, color, margin: '6px 0 2px' }}>{value}</div>
                <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>{sub}</div>
              </div>
            ))}
          </div>
        );
      })()}

      {/* Portfolio table */}
      {isLoading ? (
        <div style={{ color: 'var(--text-3)', padding: 40, textAlign: 'center' }}>Calculando métricas EVM…</div>
      ) : portfolio.length === 0 ? (
        <div style={{ color: 'var(--text-3)', padding: 40, textAlign: 'center' }}>Sin proyectos activos con datos suficientes</div>
      ) : (
        <div style={{ background: 'var(--surface-2)', borderRadius: 14, overflow: 'hidden' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: "var(--text-base)" }}>
            <thead>
              <tr style={{ background: 'var(--surface-3)' }}>
                {['Estado', 'Proyecto', '% Hecho', 'BAC', 'EV', 'AC', 'CPI', 'SPI', 'EAC', ''].map(h => (
                  <th key={h} style={{ padding: '10px 14px', textAlign: h === '' ? 'center' : 'left', fontWeight: 600, fontSize: "var(--text-xs)", color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: 0.5 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {portfolio.map((p, i) => {
                const hc = HEALTH_COLOR[p.health];
                const HIcon = HEALTH_ICON[p.health];
                return (
                  <tr key={p.project_id}
                    onClick={() => setSelected(p.project_id)}
                    style={{ borderTop: i > 0 ? '1px solid var(--surface-3)' : 'none', cursor: 'pointer', transition: 'background 0.15s' }}
                    onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-3)'}
                    onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                  >
                    <td style={{ padding: '12px 14px' }}>
                      <HIcon size={14} color={hc} />
                    </td>
                    <td style={{ padding: '12px 14px', fontWeight: 600 }}>{p.project_name}</td>
                    <td style={{ padding: '12px 14px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <div style={{ width: 60, background: 'var(--surface-4)', borderRadius: 3, height: 6 }}>
                          <div style={{ width: `${p.pct_complete}%`, background: hc, height: '100%', borderRadius: 3 }} />
                        </div>
                        <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{p.pct_complete}%</span>
                      </div>
                    </td>
                    <td style={{ padding: '12px 14px', color: 'var(--text-2)' }}>{fmtEur(p.bac)}</td>
                    <td style={{ padding: '12px 14px', color: 'var(--text-2)' }}>{fmtEur(p.ev)}</td>
                    <td style={{ padding: '12px 14px', color: 'var(--text-2)' }}>{fmtEur(p.ac)}</td>
                    <td style={{ padding: '12px 14px', fontWeight: 600, color: p.cpi == null ? 'var(--text-3)' : p.cpi >= 0.9 ? 'var(--success)' : 'var(--danger)' }}>
                      {fmtIdx(p.cpi)}
                    </td>
                    <td style={{ padding: '12px 14px', fontWeight: 600, color: p.spi == null ? 'var(--text-3)' : p.spi >= 0.9 ? 'var(--success)' : 'var(--danger)' }}>
                      {fmtIdx(p.spi)}
                    </td>
                    <td style={{ padding: '12px 14px', color: 'var(--text-2)' }}>{fmtEur(p.eac)}</td>
                    <td style={{ padding: '12px 14px', textAlign: 'center' }}>
                      <ChevronRight size={14} color="var(--text-3)" />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Detail modal */}
      <EVMDetail projectId={selected} onClose={() => setSelected(null)} />
    </PageShell>
  );
}
