/**
 * EVMPage — Earned Value Management
 * Vista de cartera con CPI, SPI, EAC, VAC, TCPI para todos los proyectos activos.
 * Drill-down por proyecto con métricas completas y gauge visual.
 */
import React, { useState } from 'react';
import type { ComponentType } from 'react';
import { useQuery } from '@tanstack/react-query';
import { projectsApi } from '../services/api';
import { TrendingUp, TrendingDown, AlertTriangle, CheckCircle, Clock, DollarSign, Target, BarChart2, ChevronRight } from 'lucide-react';
import PageHeader from '../components/layout/PageHeader';
import PageShell from '../components/layout/PageShell'
import { useAppT } from '../i18n/AppLangContext';
import { localeActivo } from '../utils/helpers';

type IdType = string | number
type HealthKey = 'green' | 'yellow' | 'red' | 'grey'

interface EvmData {
  project_id?: IdType
  project_name?: string
  start_date?: string
  planned_end?: string
  done_tasks?: number
  total_tasks?: number
  health?: HealthKey
  pct_complete?: number
  pct_time_elapsed?: number
  bac?: number
  pv?: number
  ev?: number
  ac?: number
  cpi?: number
  spi?: number
  tcpi?: number
  // Semáforo calculado en el servidor con los umbrales de Admin (EVM_INDEX_*).
  cpi_status?: HealthKey
  spi_status?: HealthKey
  tcpi_status?: HealthKey
  cv?: number
  sv?: number
  eac?: number
  etc?: number
  vac?: number
}

// ── helpers ─────────────────────────────────────────────────────────────────
const fmt = (n: number | null | undefined, dec = 2) => n == null ? '—' : Number(n).toLocaleString(localeActivo(), { minimumFractionDigits: dec, maximumFractionDigits: dec });
const fmtEur = (n: number | null | undefined) => n == null ? '—' : `${fmt(n, 0)} €`;
const fmtPct = (n: number | null | undefined) => n == null ? '—' : `${fmt(n, 1)} %`;
const fmtIdx = (n: number | null | undefined) => n == null ? '—' : fmt(n, 3);

const HEALTH_COLOR: Record<HealthKey, string> = { green: 'var(--success)', yellow: 'var(--warning)', red: 'var(--danger)', grey: 'var(--text-3)' };
const HEALTH_LABEL: Record<HealthKey, string> = { green: 'En control', yellow: 'Atención', red: 'En riesgo', grey: 'Sin datos' };
const HEALTH_ICON: Record<HealthKey, ComponentType<{ size?: number; color?: string }>>  = {
  green: CheckCircle as unknown as ComponentType<{ size?: number; color?: string }>,
  yellow: AlertTriangle as unknown as ComponentType<{ size?: number; color?: string }>,
  red: AlertTriangle as unknown as ComponentType<{ size?: number; color?: string }>,
  grey: Clock as unknown as ComponentType<{ size?: number; color?: string }>,
};

const COLOR_DE_ESTADO: Record<string, string> = { green: 'var(--success)', yellow: 'var(--warning)', red: 'var(--danger)', grey: 'var(--text-3)' };

// Revisión 2026-11: el color sale del estado que da el servidor; antes cada
// pantalla tenía sus umbrales y el de TCPI estaba al revés (más alto es peor).
function IndexBadge({ label, value, status, format = fmtIdx }: { label: string; value?: number | null; status?: string; format?: (n: number | null | undefined) => string }) {
  const color = value == null ? 'var(--text-3)' : status ? (COLOR_DE_ESTADO[status] ?? 'var(--text-1)') : 'var(--text-1)';
  return (
    <div style={{ background: 'var(--surface-2)', borderRadius: 10, padding: '12px 16px', minWidth: 120 }}>
      <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: "var(--text-xl-em)", fontWeight: 700, color }}>{format(value)}</div>
    </div>
  );
}

function VarianceBadge({ label, value }: { label: string; value?: number | null }) {
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

function ProgressBar({ pct, color = 'var(--accent)', label }: { pct?: number | null; color?: string; label?: string }) {
  return (
    <div>
      {label && <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginBottom: 4 }}>{label}</div>}
      <div style={{ background: 'var(--surface-3)', borderRadius: 4, height: 8, overflow: 'hidden' }}>
        <div style={{ width: `${Math.min(pct ?? 0, 100)}%`, background: color, height: '100%', transition: 'width 0.5s' }} />
      </div>
      <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginTop: 2 }}>{fmtPct(pct)}</div>
    </div>
  );
}

// ── Detail panel ─────────────────────────────────────────────────────────────
function EVMDetail({ projectId, onClose }: { projectId: IdType | null; onClose: () => void }) {
  const t = useAppT()
  const { data: dataRaw, isLoading, isError } = useQuery({
    queryKey: ['evm', projectId],
    queryFn: () => projectsApi.evm(String(projectId)).then(r => r.data),
    enabled: !!projectId,
  });
  const data = (dataRaw ?? null) as EvmData | null

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
        {isLoading && <div style={{ color: 'var(--text-3)' }}>{t('evm.calculando_metricas_evm')}</div>}
        {isError  && <div style={{ color: 'var(--danger)' }}>{t('evm.error_al_cargar_metricas')}</div>}
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
              color: HEALTH_COLOR[data.health ?? 'grey'], fontWeight: 600, fontSize: "var(--text-md)" }}>
              {React.createElement(HEALTH_ICON[data.health || 'grey'], { size: 16 })}
              {HEALTH_LABEL[data.health || 'grey']}
            </div>
          </div>

          {/* Progress */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 24 }}>
            <ProgressBar pct={data.pct_complete} label="Avance real" color={HEALTH_COLOR[data.health ?? 'grey']} />
            <ProgressBar pct={data.pct_time_elapsed} label="Tiempo transcurrido" color="var(--accent)" />
          </div>

          {/* Core values */}
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: 'var(--text-3)', marginBottom: 10, textTransform: 'uppercase', letterSpacing: 1 }}>Valores base</div>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              <IndexBadge label="BAC" value={data.bac} format={fmtEur} />
              <IndexBadge label="PV" value={data.pv} format={fmtEur} />
              <IndexBadge label="EV" value={data.ev} format={fmtEur} />
              <IndexBadge label="AC" value={data.ac} format={fmtEur} />
            </div>
          </div>

          {/* Indices */}
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: 'var(--text-3)', marginBottom: 10, textTransform: 'uppercase', letterSpacing: 1 }}>{t('evm.indices_de_rendimiento')}</div>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              <IndexBadge label="CPI" value={data.cpi} status={data.cpi_status} />
              <IndexBadge label="SPI" value={data.spi} status={data.spi_status} />
              <IndexBadge label="TCPI" value={data.tcpi} status={data.tcpi_status} />
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
            <div style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: 'var(--text-3)', marginBottom: 10, textTransform: 'uppercase', letterSpacing: 1 }}>{t('evm.prevision_final')}</div>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              <IndexBadge label="EAC" value={data.eac} format={fmtEur} />
              <IndexBadge label="ETC" value={data.etc} format={fmtEur} />
              <VarianceBadge label="VAC" value={data.vac} />
            </div>
          </div>

          {/* Legend */}
          <div style={{ marginTop: 24, padding: '12px 16px', background: 'var(--surface-2)', borderRadius: 10, fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>
            <strong>{t('evm.guia_rapida')}</strong> {t('evm.cpi_1_bajo_presupuesto_cpi_1_sobre')}
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
export default function EVMPage(): JSX.Element {
  const t = useAppT();
  const [selected, setSelected] = useState<IdType | null>(null);

  const { data: portfolioRaw = [], isLoading } = useQuery({
    queryKey: ['evm-portfolio'],
    queryFn: () => projectsApi.evmPortfolio().then(r => r.data),
    staleTime: 60000,
  });
  const portfolio = portfolioRaw as EvmData[]

  return (
    <PageShell>
      <PageHeader
        icon={<BarChart2 size={18} />}
        title={t('evm.title')}
        subtitle={t('evm.subtitle')}
      />

      {/* Summary KPIs */}
      {portfolio.length > 0 && (() => {
        // `flatMap` filtra y estrecha el tipo a la vez: un `filter(x => x != null)`
        // deja el array con el tipo de antes y TypeScript sigue viendo nulos.
        // Índices de la cartera: suma de EV entre suma de AC (o de PV), no la media de índices.
        const conAc = portfolio.filter(p => (p.ac || 0) > 0);
        const sumAc = conAc.reduce((s, p) => s + (p.ac || 0), 0);
        const avgCpi = sumAc > 0 ? conAc.reduce((s, p) => s + (p.ev || 0), 0) / sumAc : null;
        const conPv = portfolio.filter(p => (p.pv || 0) > 0);
        const sumPv = conPv.reduce((s, p) => s + (p.pv || 0), 0);
        const avgSpi = sumPv > 0 ? conPv.reduce((s, p) => s + (p.ev || 0), 0) / sumPv : null;
        const cpiRojos = portfolio.filter(p => p.cpi_status === 'red').length;
        const spiRojos = portfolio.filter(p => p.spi_status === 'red').length;
        const totalBac = portfolio.reduce((s, p) => s + (p.bac || 0), 0);
        const totalAc  = portfolio.reduce((s, p) => s + (p.ac || 0), 0);
        const reds     = portfolio.filter((p) => p.health === 'red').length;
        return (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(150px, 100%), 1fr))', gap: 14, marginBottom: 28 }}>
            {[
              { label: 'Proyectos activos', value: portfolio.length, sub: `${reds} en riesgo`, color: reds > 0 ? 'var(--danger)' : 'var(--text-1)', Icon: Target },
              { label: 'CPI de la cartera', value: fmtIdx(avgCpi), sub: `${cpiRojos} proyecto${cpiRojos === 1 ? '' : 's'} con CPI en rojo`, color: cpiRojos > 0 ? 'var(--danger)' : 'var(--text-1)', Icon: DollarSign },
              { label: 'SPI de la cartera', value: fmtIdx(avgSpi), sub: `${spiRojos} proyecto${spiRojos === 1 ? '' : 's'} con SPI en rojo`, color: spiRojos > 0 ? 'var(--danger)' : 'var(--text-1)', Icon: Clock },
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
        <div style={{ color: 'var(--text-3)', padding: 40, textAlign: 'center' }}>{t('evm.calculando_metricas_evm')}</div>
      ) : portfolio.length === 0 ? (
        <div style={{ color: 'var(--text-3)', padding: 40, textAlign: 'center' }}>{t('evm.sin_proyectos_activos_con_datos_suficientes')}</div>
      ) : (
        <div style={{ background: 'var(--surface-2)', borderRadius: 14, overflowX: 'auto' }}>
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
                const health = p.health || 'grey'
                const hc = HEALTH_COLOR[health];
                const HIcon = HEALTH_ICON[health];
                return (
                  <tr key={p.project_id}
                    onClick={() => p.project_id != null && setSelected(p.project_id)}
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
                          <div style={{ width: `${p.pct_complete ?? 0}%`, background: hc, height: '100%', borderRadius: 3 }} />
                        </div>
                        <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{p.pct_complete ?? 0}%</span>
                      </div>
                    </td>
                    <td style={{ padding: '12px 14px', color: 'var(--text-2)' }}>{fmtEur(p.bac)}</td>
                    <td style={{ padding: '12px 14px', color: 'var(--text-2)' }}>{fmtEur(p.ev)}</td>
                    <td style={{ padding: '12px 14px', color: 'var(--text-2)' }}>{fmtEur(p.ac)}</td>
                    <td style={{ padding: '12px 14px', fontWeight: 600, color: COLOR_DE_ESTADO[p.cpi_status ?? 'grey'] }}>
                      {fmtIdx(p.cpi)}
                    </td>
                    <td style={{ padding: '12px 14px', fontWeight: 600, color: COLOR_DE_ESTADO[p.spi_status ?? 'grey'] }}>
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
