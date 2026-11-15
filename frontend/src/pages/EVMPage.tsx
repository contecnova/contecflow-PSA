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
import { useDialogo } from '../components/ui';
import { useAppT } from '../i18n/AppLangContext';
import { localeActivo } from '../utils/helpers';

import { useFormatoMoneda } from '../hooks/useFormatoMoneda'
import { STALE_DEFAULT_MS } from '../constants/timings'
import './EVMPage.css'
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
const fmtPct = (n: number | null | undefined) => n == null ? '—' : `${fmt(n, 1)} %`;
const fmtIdx = (n: number | null | undefined) => n == null ? '—' : fmt(n, 3);

const HEALTH_COLOR: Record<HealthKey, string> = { green: 'var(--success)', yellow: 'var(--warning)', red: 'var(--danger)', grey: 'var(--text-3)' };
const HEALTH_LABEL: Record<HealthKey, string> = { green: 'pagina_evm.en_control', yellow: 'pagina_evm.atencion', red: 'pagina_evm.en_riesgo_2', grey: 'pagina_evm.sin_datos' };
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
    <div className="evm-card">
      <div className="evm-box">{label}</div>
      <div className="evm-box-2" style={{ color }}>{format(value)}</div>
    </div>
  );
}

function VarianceBadge({ label, value }: { label: string; value?: number | null }) {
  const fmtMoneda = useFormatoMoneda()
  const pos = value == null ? null : value >= 0;
  const color = pos == null ? 'var(--text-3)' : pos ? 'var(--success)' : 'var(--danger)';
  const Icon  = pos == null ? null : pos ? TrendingUp : TrendingDown;
  return (
    <div className="evm-card">
      <div className="evm-box">{label}</div>
      <div className="u-row-center-6" style={{ color }}>
        {Icon && <Icon size={14} />}
        <span className="evm-label">{fmtMoneda(value, { decimales: 0 })}</span>
      </div>
    </div>
  );
}

function ProgressBar({ pct, color = 'var(--accent)', label }: { pct?: number | null; color?: string; label?: string }) {
  return (
    <div>
      {label && <div className="evm-box">{label}</div>}
      <div className="evm-card-2">
        <div className="evm-box-3" style={{ width: `${Math.min(pct ?? 0, 100)}%`, background: color }} />
      </div>
      <div className="u-text2-xs-mt2">{fmtPct(pct)}</div>
    </div>
  );
}

// ── Detail panel ─────────────────────────────────────────────────────────────
function EVMDetail({ projectId, onClose }: { projectId: IdType | null; onClose: () => void }) {
  const fmtMoneda = useFormatoMoneda()
  const fmtEurDetalle = (n: number | null | undefined) => fmtMoneda(n, { decimales: 0 })
  const t = useAppT()
  const { data: dataRaw, isLoading, isError } = useQuery({
    queryKey: ['evm', projectId],
    queryFn: () => projectsApi.evm(String(projectId)).then(r => r.data),
    enabled: !!projectId,
  });
  const data = (dataRaw ?? null) as EvmData | null
  const dialogRef = useDialogo<HTMLDivElement>(Boolean(projectId), onClose);

  if (!projectId) return null;

  return (
    <div role="presentation" className="evm-overlay" onMouseDown={onClose}>
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="evm-dialog-title" className="evm-dialog" onMouseDown={e => e.stopPropagation()}>
        {isLoading && <div className="u-text3">{t('evm.calculando_metricas_evm')}</div>}
        {isError  && <div className="u-danger">{t('evm.error_al_cargar_metricas')}</div>}
        {data && <>
          {/* Header */}
          <div className="evm-row-2">
            <div>
              <div id="evm-dialog-title" className="evm-box-4">{data.project_name}</div>
              <div className="evm-box-5">
                {data.start_date} → {data.planned_end || t('pagina_evm.sin_fecha_fin')}
                {' · '}{data.done_tasks}/{data.total_tasks}{' '}{t('pagina_evm.tareas_completadas')}
              </div>
            </div>
            <div className="evm-row-3" style={{ color: HEALTH_COLOR[data.health ?? 'grey'] }}>
              {React.createElement(HEALTH_ICON[data.health || 'grey'], { size: 16 })}
              {t(HEALTH_LABEL[data.health || 'grey'])}
            </div>
          </div>

          {/* Progress */}
          <div className="evm-grid">
            <ProgressBar pct={data.pct_complete} label={t('pagina_evm.avance_real')} color={HEALTH_COLOR[data.health ?? 'grey']} />
            <ProgressBar pct={data.pct_time_elapsed} label={t('pagina_evm.tiempo_transcurrido')} color="var(--accent)" />
          </div>

          {/* Core values */}
          <div className="u-mb-16">
            <div className="evm-box-6">{t('pagina_evm.valores_base')}</div>
            <div className="evm-row-4">
              <IndexBadge label="BAC" value={data.bac} format={fmtEurDetalle} />
              <IndexBadge label="PV" value={data.pv} format={fmtEurDetalle} />
              <IndexBadge label="EV" value={data.ev} format={fmtEurDetalle} />
              <IndexBadge label="AC" value={data.ac} format={fmtEurDetalle} />
            </div>
          </div>

          {/* Indices */}
          <div className="u-mb-16">
            <div className="evm-box-6">{t('evm.indices_de_rendimiento')}</div>
            <div className="evm-row-4">
              <IndexBadge label="CPI" value={data.cpi} status={data.cpi_status} />
              <IndexBadge label="SPI" value={data.spi} status={data.spi_status} />
              <IndexBadge label="TCPI" value={data.tcpi} status={data.tcpi_status} />
            </div>
          </div>

          {/* Variances */}
          <div className="u-mb-16">
            <div className="evm-box-6">{t('pagina_evm.varianzas')}</div>
            <div className="evm-row-4">
              <VarianceBadge label="CV" value={data.cv} />
              <VarianceBadge label="SV" value={data.sv} />
            </div>
          </div>

          {/* Forecast */}
          <div>
            <div className="evm-box-6">{t('evm.prevision_final')}</div>
            <div className="evm-row-4">
              <IndexBadge label="EAC" value={data.eac} format={fmtEurDetalle} />
              <IndexBadge label="ETC" value={data.etc} format={fmtEurDetalle} />
              <VarianceBadge label="VAC" value={data.vac} />
            </div>
          </div>

          {/* Legend */}
          <div className="evm-card-4">
            <strong>{t('evm.guia_rapida')}</strong> {t('evm.cpi_1_bajo_presupuesto_cpi_1_sobre')}
          </div>

          <button onClick={onClose} className="evm-btn">{t('pagina_evm.cerrar')}</button>
        </>}
      </div>
    </div>
  );
}

// ── Portfolio table ───────────────────────────────────────────────────────────
export default function EVMPage(): JSX.Element {
  const fmtMoneda = useFormatoMoneda()
  const t = useAppT();
  const [selected, setSelected] = useState<IdType | null>(null);

  const { data: portfolioRaw = [], isLoading } = useQuery({
    queryKey: ['evm-portfolio'],
    queryFn: () => projectsApi.evmPortfolio().then(r => r.data),
    staleTime: STALE_DEFAULT_MS,
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
          <div className="evm-grid-2">
            {[
              { label: t('pagina_evm.proyectos_activos'), value: portfolio.length, sub: t('pagina_evm.en_riesgo', { reds }), color: reds > 0 ? 'var(--danger)' : 'var(--text-1)', Icon: Target },
              { label: t('pagina_evm.cpi_de_la_cartera'), value: fmtIdx(avgCpi), sub: t(cpiRojos === 1 ? 'pagina_evm.proyectos_cpi_rojo_uno' : 'pagina_evm.proyectos_cpi_rojo_otros', { n: cpiRojos }), color: cpiRojos > 0 ? 'var(--danger)' : 'var(--text-1)', Icon: DollarSign },
              { label: t('pagina_evm.spi_de_la_cartera'), value: fmtIdx(avgSpi), sub: t(spiRojos === 1 ? 'pagina_evm.proyectos_spi_rojo_uno' : 'pagina_evm.proyectos_spi_rojo_otros', { n: spiRojos }), color: spiRojos > 0 ? 'var(--danger)' : 'var(--text-1)', Icon: Clock },
              { label: t('pagina_evm.presupuesto_total'), value: fmtMoneda(totalBac, { decimales: 0 }), sub: t('pagina_evm.gastado', { v1: fmtMoneda(totalAc, { decimales: 0 }) }), color: 'var(--text-1)', Icon: BarChart2 },
            ].map(({ label, value, sub, color, Icon }) => (
              <div key={label} className="evm-card-5">
                <div className="evm-row-5">
                  <div className="u-text3-sm">{label}</div>
                  <Icon size={16} color="var(--accent)" />
                </div>
                <div className="evm-box-7" style={{ color }}>{value}</div>
                <div className="u-text3-xs">{sub}</div>
              </div>
            ))}
          </div>
        );
      })()}

      {/* Portfolio table */}
      {isLoading ? (
        <div className="evm-box-8">{t('evm.calculando_metricas_evm')}</div>
      ) : portfolio.length === 0 ? (
        <div className="evm-box-8">{t('evm.sin_proyectos_activos_con_datos_suficientes')}</div>
      ) : (
        <div className="evm-card-6">
          <table className="evm-table">
            <thead>
              <tr className="evm-row-6">
                {[t('pagina_evm.estado'), t('pagina_evm.proyecto'), t('pagina_evm.hecho'), 'BAC', 'EV', 'AC', 'CPI', 'SPI', 'EAC', ''].map(h => (
                  <th key={h} className={`evm-th ${h === '' ? 'evmpage-sx1' : 'evmpage-sx2'}`}>{h}</th>
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
                    className={`evm-row-7 ${i > 0 ? 'evmpage-sx3' : 'evmpage-sx4'}`}
                    onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-3)'}
                    onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                  >
                    <td className="evm-td">
                      <HIcon size={14} color={hc} />
                    </td>
                    <td className="evm-td-2">{p.project_name}</td>
                    <td className="evm-td" aria-label={`${p.pct_complete ?? 0}%`}>
                      <div className="u-row-center-8">
                        <div className="evm-card-7">
                          <div className="evm-box-9" style={{ width: `${p.pct_complete ?? 0}%`, background: hc }} />
                        </div>
                        <span className="u-text2-xs">{p.pct_complete ?? 0}%</span>
                      </div>
                    </td>
                    <td className="evm-td-3">{fmtMoneda(p.bac, { decimales: 0 })}</td>
                    <td className="evm-td-3">{fmtMoneda(p.ev, { decimales: 0 })}</td>
                    <td className="evm-td-3">{fmtMoneda(p.ac, { decimales: 0 })}</td>
                    <td className="evm-td-2" style={{ color: COLOR_DE_ESTADO[p.cpi_status ?? 'grey'] }}>
                      {fmtIdx(p.cpi)}
                    </td>
                    <td className="evm-td-2" style={{ color: COLOR_DE_ESTADO[p.spi_status ?? 'grey'] }}>
                      {fmtIdx(p.spi)}
                    </td>
                    <td className="evm-td-3">{fmtMoneda(p.eac, { decimales: 0 })}</td>
                    <td className="evm-td-4">
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
