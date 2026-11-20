/**
 * InformesDeCmdb — informe propio de cada resultado de la CMDB (19-11-2026).
 *
 * Antes `CmdbMercado` pintaba todo con `VistaDeDatos` (volcado genérico de
 * claves y valores). Ahora cada respuesta tiene su render con los campos
 * reales del servidor (`app/api/v1/endpoints/service_desk/cmdb.py` y
 * `app/services/cmdb/models.py`):
 *
 *  - ejecuciones de un proveedor de descubrimiento → tabla + gráfico;
 *  - salud de la reconciliación → indicador, KPIs y barras por proveedor;
 *  - candidatos a duplicado → tabla conserva/duplicado con la confianza;
 *  - deriva de configuración → KPIs, barras por proveedor y tabla con cambios;
 *  - radio de impacto de un CI → KPIs y barras por criticidad (también lo usa
 *    el análisis del cambio);
 *  - retirada de un CI → KPIs, CIs y activos afectados y recomendaciones.
 *
 * Los renders son puros (reciben `datos`); las peticiones las hace quien los usa.
 */
import { Activity, AlertTriangle, Boxes, CheckCircle2, Copy, GitCompare, Layers, Package, Radar, ShieldAlert, Users } from 'lucide-react'
import { Bar, BarChart, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useAppT } from '../../i18n/AppLangContext'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import { EmptyState, KpiCard, StatusBadge, TablaSimple } from '../ui'
import type { StatusBadgeKind } from '../ui'
import { BarRow, GaugeCard, typePalette } from '../dashboard/DashKit'
import { useTono } from '../../hooks/useOrgSettings'
import { colorDeTono } from '../../utils/umbrales'
import { fmtDate, fmtDateTime, fmtNumber, fmtRelative } from '../../utils/helpers'
import { useChartTheme } from '../../charts/useChartTheme'
import { LEYENDA_XS, tooltipDelTemaConBorde } from '../../constants/estilosGrafico'
import { Barra, fmtMinutos } from '../servicedesk/WidgetsDelPanel'
import { COLOR_DE_NIVEL, NIVELES, Nivel, Subtitulo, codigo, listaDe, minutosEntre } from '../servicedesk/InformesComunes'
import '../servicedesk/sdMercado.css'

/* ── Tipos (campos reales de cada endpoint) ──────────────────────────────── */

/** `/sd/cmdb/discovery/providers/{id}/jobs` (`_serialize_discovery_job`). */
export interface EjecucionDeDescubrimiento {
  id: string; status: string | null; started_at: string | null; finished_at: string | null
  cis_created: number | null; cis_updated: number | null; cis_deactivated: number | null
  error_message: string | null; triggered_by: string | null
}
/** `/sd/cmdb/discovery/reconciliation-health`. */
export interface SaludDeReconciliacion {
  total_discovered: number; active_discovered: number; stale_discovered: number
  duplicate_external_ids: number; reconciliation_score: number
  by_provider: Record<string, { total: number; active: number; retired: number }>
}
interface CiResumido { name: string | null; hostname: string | null; ip_address: string | null }
/** Un candidato de `/sd/cmdb/discovery/reconciliation-candidates`. */
export interface CandidatoADuplicado { provider: string | null; confidence: number; keeper: CiResumido; duplicate: CiResumido }
/** `/sd/cmdb/discovery/drift-report`. */
export interface InformeDeDeriva {
  total_drifted: number
  items: {
    ci_id: string; name: string; ci_type: string | null; environment: string | null; provider: string | null
    drift_detected_at: string | null; last_discovered_at: string | null; ip_address: string | null; hostname: string | null
    recent_changelog: { field: string | null; old_value: string | null; new_value: string | null; summary: string | null; created_at: string | null }[]
  }[]
}
/** `/sd/cmdb/{ci}/blast-radius` (`get_blast_radius_summary`). */
export interface RadioDeImpacto {
  impacted_count: number; truncated: boolean; criticality_breakdown: Record<string, number>
  estimated_affected_users: number; highest_criticality: string; max_depth: number
}
/** `/sd/cmdb/{ci}/deprecation-impact` (`get_ci_deprecation_impact_payload`). */
export interface ImpactoDeRetirada {
  ci: { code: string | null; name: string; ci_type: string | null; status: string | null; criticality: string | null }
  summary: {
    risk_level: string; impacted_ci_count: number; impacted_asset_count: number; direct_impacted_ci_count: number
    max_depth: number; truncated: boolean; highest_criticality: string | null
    assets_by_status: Record<string, number>; assets_by_type: Record<string, number>
  }
  impacted_cis: { ci_id: string; ci_name: string; ci_type: string | null; criticality: string | null; relation: string | null; depth: number }[]
  impacted_assets: { id: string; asset_tag: string | null; name: string; type: string | null; status: string | null; assigned_to_name: string | null; ci_name: string | null }[]
}

/* ── Utilidades ───────────────────────────────────────────────────────────── */

const KIND_EJECUCION: Record<string, StatusBadgeKind> = { ok: 'success', error: 'danger', running: 'info' }
const n0 = (v: number | null | undefined) => v ?? 0

/** Nombre traducido de un proveedor de descubrimiento («unknown» incluido). */
function useProveedor() {
  const t = useAppT()
  return (p: string | null | undefined) => (!p || p === 'unknown')
    ? t('sd_informes.proveedor_desconocido')
    : etiquetaCodigo(t, 'sd_mercado.proveedor', p)
}

/* ── 1. Ejecuciones de un proveedor ──────────────────────────────────────── */

export function InformeEjecuciones({ datos }: { datos: unknown }) {
  const t = useAppT()
  const { tokens } = useChartTheme()
  const filas = listaDe<EjecucionDeDescubrimiento>(datos)
  if (filas.length === 0) return <EmptyState icon={<Activity size={28} />} title={t('sd_informes.ejecuciones_vacio')} description={t('sd_informes.ejecuciones_vacio_desc')} />
  // Gráfico en orden cronológico (la lista llega de la más reciente a la más antigua).
  const grafico = [...filas].reverse().map(j => ({
    cuando: fmtDate(j.started_at), creados: n0(j.cis_created), actualizados: n0(j.cis_updated), desactivados: n0(j.cis_deactivated),
  }))
  return (
    <div className="u-stack-12">
      {grafico.length > 1 && (
        <div className="sdp-grafico" role="img" aria-label={t('sd_informes.ejecuciones_grafico')}>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={grafico} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
              <XAxis dataKey="cuando" tick={{ fill: tokens.text3, fontSize: 11 }} />
              <YAxis allowDecimals={false} width={36} tick={{ fill: tokens.text3, fontSize: 11 }} />
              <Tooltip contentStyle={tooltipDelTemaConBorde(tokens)} />
              <Legend wrapperStyle={LEYENDA_XS} />
              <Bar dataKey="creados" name={t('sd_informes.cis_creados')} stackId="a" fill={tokens.success} />
              <Bar dataKey="actualizados" name={t('sd_informes.cis_actualizados')} stackId="a" fill={tokens.accent} />
              <Bar dataKey="desactivados" name={t('sd_informes.cis_desactivados')} stackId="a" fill={tokens.text3} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
      <TablaSimple densidad="compacta" etiqueta={t('sd_informes.ejecuciones')} claseTabla="sdp-tabla">
        <thead>
          <tr>
            <th>{t('sd_informes.col_inicio')}</th>
            <th>{t('sd_informes.col_estado')}</th>
            <th>{t('sd_informes.col_origen')}</th>
            <th className="sdp-num">{t('sd_informes.col_duracion')}</th>
            <th className="sdp-num">{t('sd_informes.cis_creados')}</th>
            <th className="sdp-num">{t('sd_informes.cis_actualizados')}</th>
            <th className="sdp-num">{t('sd_informes.cis_desactivados')}</th>
          </tr>
        </thead>
        <tbody>
          {filas.map(j => (
            <tr key={j.id}>
              <td title={fmtDateTime(j.started_at)}>
                <div>{fmtDateTime(j.started_at)}</div>
                {j.error_message && <div className="u-text3-xs sdp-wrap">{j.error_message}</div>}
              </td>
              <td><StatusBadge caps={false} dot kind={KIND_EJECUCION[j.status ?? ''] ?? 'neutral'}>{etiquetaCodigo(t, 'sd_mercado.ejecucion', j.status)}</StatusBadge></td>
              <td>{etiquetaCodigo(t, 'sd_informes.disparo', j.triggered_by)}</td>
              <td className="sdp-num">{fmtMinutos(minutosEntre(j.started_at, j.finished_at))}</td>
              <td className="sdp-num">{n0(j.cis_created)}</td>
              <td className="sdp-num">{n0(j.cis_updated)}</td>
              <td className="sdp-num">{n0(j.cis_deactivated)}</td>
            </tr>
          ))}
        </tbody>
      </TablaSimple>
    </div>
  )
}

/* ── 2. Salud de la reconciliación ───────────────────────────────────────── */

export function InformeSaludReconciliacion({ datos }: { datos: SaludDeReconciliacion }) {
  const t = useAppT()
  const tono = useTono()
  const proveedor = useProveedor()
  if (!datos.total_discovered) return <EmptyState icon={<Radar size={28} />} title={t('sd_informes.salud_vacia')} description={t('sd_informes.salud_vacia_desc')} />
  // La puntuación es salud (más es mejor): el semáforo es el de riesgo sobre lo que falta.
  const tonoSalud = tono('riesgo', 100 - datos.reconciliation_score)
  const proveedores = Object.entries(datos.by_provider ?? {}).sort((a, b) => b[1].total - a[1].total)
  return (
    <div className="sdp-columnas">
      <div className="u-stack-12">
        <GaugeCard label={t('sd_informes.puntuacion_reconciliacion')} value={datos.reconciliation_score} suffix="" color={colorDeTono(tonoSalud)}
          sub={t('sd_informes.puntuacion_reconciliacion_desc')} />
        <div className="sdp-kpis">
          <KpiCard icon={<Boxes size={16} />} label={t('sd_informes.descubiertos')} value={datos.total_discovered}
            sub={t('sd_informes.n_activos', { n: datos.active_discovered })} />
          <KpiCard icon={<Layers size={16} />} label={t('sd_informes.retirados')} value={datos.stale_discovered} warning={datos.stale_discovered > 0} />
          <KpiCard icon={<Copy size={16} />} label={t('sd_informes.ids_duplicados')} value={datos.duplicate_external_ids}
            danger={datos.duplicate_external_ids > 0} sub={t('sd_informes.ids_duplicados_desc')} />
        </div>
      </div>
      {proveedores.length > 0 && (
        <div>
          <Subtitulo>{t('sd_informes.por_proveedor')}</Subtitulo>
          {proveedores.map(([p, c], i) => (
            <BarRow key={p} label={proveedor(p)} count={c.total} total={datos.total_discovered} color={typePalette[i % typePalette.length]}
              displayValue={c.retired ? t('sd_informes.n_con_retirados', { n: c.total, r: c.retired }) : c.total} />
          ))}
        </div>
      )}
    </div>
  )
}

/* ── 3. Candidatos a duplicado ───────────────────────────────────────────── */

function CiEnFila({ ci }: { ci: CiResumido }) {
  const sub = [ci.hostname, ci.ip_address].filter(Boolean).join(' · ')
  return (
    <span className="sdp-enlace__cuerpo">
      <span className="sdp-enlace__titulo"><span className="sdp-wrap">{ci.name || '—'}</span></span>
      {sub && <span className="sdp-enlace__sub u-mono">{sub}</span>}
    </span>
  )
}

export function InformeCandidatos({ datos }: { datos: CandidatoADuplicado[] }) {
  const t = useAppT()
  const tono = useTono()
  const proveedor = useProveedor()
  return (
    <div className="u-stack-10">
      <TablaSimple densidad="compacta" etiqueta={t('sd_informes.candidatos')} claseTabla="sdp-tabla">
        <thead>
          <tr>
            <th>{t('sd_informes.col_se_conserva')}</th>
            <th>{t('sd_informes.col_duplicado')}</th>
            <th>{t('sd_informes.col_proveedor')}</th>
            <th>{t('sd_informes.col_confianza')}</th>
          </tr>
        </thead>
        <tbody>
          {datos.map((c, i) => {
            const pct = Math.round((c.confidence ?? 0) * 100)
            return (
              <tr key={i}>
                <td><CiEnFila ci={c.keeper} /></td>
                <td><CiEnFila ci={c.duplicate} /></td>
                <td>{proveedor(c.provider)}</td>
                <td><Barra pct={pct} color={colorDeTono(tono('riesgo', pct))} etiqueta={t('sd_informes.confianza_aria', { pct })} /></td>
              </tr>
            )
          })}
        </tbody>
      </TablaSimple>
      <p className="u-hint">{t('sd_informes.candidatos_ayuda')}</p>
    </div>
  )
}

/* ── 4. Deriva de configuración ──────────────────────────────────────────── */

export function InformeDeriva({ datos }: { datos: InformeDeDeriva }) {
  const t = useAppT()
  const proveedor = useProveedor()
  const items = datos.items ?? []
  if (items.length === 0) return <EmptyState icon={<CheckCircle2 size={28} />} title={t('sd_informes.deriva_vacia')} description={t('sd_informes.deriva_vacia_desc')} />
  const porProveedor = new Map<string, number>()
  for (const it of items) porProveedor.set(it.provider || 'unknown', (porProveedor.get(it.provider || 'unknown') ?? 0) + 1)
  const cambios = items.reduce((s, it) => s + (it.recent_changelog?.length ?? 0), 0)
  return (
    <div className="u-stack-14">
      <div className="sdp-columnas">
        <div className="sdp-kpis">
          <KpiCard icon={<GitCompare size={16} />} label={t('sd_informes.cis_con_deriva')} value={datos.total_drifted ?? items.length} warning />
          <KpiCard icon={<Activity size={16} />} label={t('sd_informes.cambios_registrados')} value={cambios} sub={t('sd_informes.cambios_registrados_desc')} />
        </div>
        <div>
          <Subtitulo>{t('sd_informes.por_proveedor')}</Subtitulo>
          {[...porProveedor.entries()].sort((a, b) => b[1] - a[1]).map(([p, n], i) => (
            <BarRow key={p} label={proveedor(p)} count={n} total={items.length} color={typePalette[i % typePalette.length]} />
          ))}
        </div>
      </div>
      <TablaSimple densidad="compacta" etiqueta={t('sd_mercado.deriva')} claseTabla="sdp-tabla">
        <thead>
          <tr>
            <th>{t('sd_informes.col_ci')}</th>
            <th>{t('sd_informes.col_clase')}</th>
            <th>{t('sd_informes.col_entorno')}</th>
            <th>{t('sd_informes.col_proveedor')}</th>
            <th>{t('sd_informes.col_deriva')}</th>
            <th>{t('sd_informes.col_ultimos_cambios')}</th>
          </tr>
        </thead>
        <tbody>
          {items.map(it => (
            <tr key={it.ci_id}>
              <td><CiEnFila ci={{ name: it.name, hostname: it.hostname, ip_address: it.ip_address }} /></td>
              <td>{it.ci_type ? etiquetaCodigo(t, 'sd_mercado.clase_base', codigo(it.ci_type)) : '—'}</td>
              <td>{it.environment ? etiquetaCodigo(t, 'sd_informes.entorno', it.environment) : '—'}</td>
              <td>{proveedor(it.provider)}</td>
              <td title={fmtDateTime(it.drift_detected_at)}>{fmtRelative(it.drift_detected_at)}</td>
              <td>
                {(it.recent_changelog ?? []).length === 0 ? <span className="u-text3-sm">—</span> : (
                  <ul className="sdp-lista">
                    {it.recent_changelog.slice(0, 3).map((c, i) => (
                      <li key={i} title={fmtDateTime(c.created_at)}>
                        <span className="sdp-wrap">
                          {c.field ? <span className="u-mono">{c.field}</span> : null}
                          {c.field && (c.old_value != null || c.new_value != null) ? ': ' : ''}
                          {(c.old_value != null || c.new_value != null)
                            ? t('sd_informes.de_a', { antes: c.old_value ?? '—', despues: c.new_value ?? '—' })
                            : (c.summary ?? '')}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </TablaSimple>
    </div>
  )
}

/* ── 5. Radio de impacto de un CI ────────────────────────────────────────── */

export function InformeRadioDeImpacto({ datos }: { datos: RadioDeImpacto }) {
  const t = useAppT()
  const desglose = datos.criticality_breakdown ?? {}
  const total = datos.impacted_count ?? 0
  return (
    <div className="u-stack-12">
      <div className="sdp-kpis">
        <KpiCard icon={<Boxes size={16} />} label={t('sd_informes.cis_afectados')} value={total}
          sub={t('sd_informes.hasta_n_saltos', { n: datos.max_depth })} warning={total > 0} />
        <KpiCard icon={<Users size={16} />} label={t('sd_informes.usuarios_estimados')} value={fmtNumber(datos.estimated_affected_users ?? 0, 0)}
          sub={t('sd_informes.usuarios_estimados_desc')} />
      </div>
      {total === 0 ? <p className="u-hint">{t('sd_informes.radio_sin_dependientes')}</p> : (
        <div>
          <Subtitulo><span className="u-row-center-8">{t('sd_informes.por_criticidad')} <Nivel nivel={datos.highest_criticality} /></span></Subtitulo>
          {NIVELES.map(n => (
            <BarRow key={n} label={etiquetaCodigo(t, 'sd_informes.nivel', n)} count={desglose[n] ?? 0} total={total} color={COLOR_DE_NIVEL[n]} />
          ))}
        </div>
      )}
      {datos.truncated && <p className="u-hint">{t('sd_informes.recortado')}</p>}
    </div>
  )
}

/* ── 6. Si se retira el CI ───────────────────────────────────────────────── */

const MAX_FILAS = 12

export function InformeRetirada({ datos }: { datos: ImpactoDeRetirada }) {
  const t = useAppT()
  const r = datos.summary
  const cis = [...(datos.impacted_cis ?? [])].sort((a, b) => a.depth - b.depth)
  const activos = datos.impacted_assets ?? []
  const porEstado = Object.entries(r.assets_by_status ?? {}).sort((a, b) => b[1] - a[1])
  // Recomendaciones con las mismas reglas que el servidor, en el idioma activo.
  const recomendaciones = ['sd_informes.rec_reemplazo', 'sd_informes.rec_ventana']
  if ((r.assets_by_status?.in_use ?? 0) > 0) recomendaciones.push('sd_informes.rec_usuarios')
  if (r.impacted_ci_count > 0) recomendaciones.push('sd_informes.rec_regresion')
  return (
    <div className="u-stack-14">
      <div className="u-wrap-8">
        {datos.ci.code && <span className="u-mono u-text3-xs">{datos.ci.code}</span>}
        <span className="u-text1-sm-600">{datos.ci.name}</span>
        {datos.ci.ci_type && <StatusBadge caps={false}>{etiquetaCodigo(t, 'sd_mercado.clase_base', codigo(datos.ci.ci_type))}</StatusBadge>}
        {datos.ci.status && <StatusBadge caps={false} kind="neutral">{etiquetaCodigo(t, 'sd_informes.estado_ci', codigo(datos.ci.status))}</StatusBadge>}
      </div>
      <div className="sdp-kpis">
        <KpiCard icon={<ShieldAlert size={16} />} label={t('sd_informes.riesgo_retirada')} value={<Nivel nivel={r.risk_level} />} />
        <KpiCard icon={<Boxes size={16} />} label={t('sd_informes.cis_afectados')} value={r.impacted_ci_count}
          sub={t('sd_informes.n_directos', { n: r.direct_impacted_ci_count })} />
        <KpiCard icon={<Package size={16} />} label={t('sd_informes.activos_afectados')} value={r.impacted_asset_count}
          warning={r.impacted_asset_count > 0} />
      </div>
      {porEstado.length > 0 && (
        <div>
          <Subtitulo>{t('sd_informes.activos_por_estado')}</Subtitulo>
          {porEstado.map(([st, n], i) => (
            <BarRow key={st} label={etiquetaCodigo(t, 'sd_informes.estado_activo', st)} count={n} total={r.impacted_asset_count || 1} color={typePalette[i % typePalette.length]} />
          ))}
        </div>
      )}
      {cis.length > 0 && (
        <div>
          <Subtitulo>{t('sd_informes.cis_afectados')}</Subtitulo>
          <TablaSimple densidad="compacta" etiqueta={t('sd_informes.cis_afectados')} claseTabla="sdp-tabla">
            <thead>
              <tr>
                <th>{t('sd_informes.col_ci')}</th>
                <th>{t('sd_informes.col_clase')}</th>
                <th>{t('sd_informes.col_criticidad')}</th>
                <th>{t('sd_informes.col_relacion')}</th>
                <th className="sdp-num">{t('sd_informes.col_saltos')}</th>
              </tr>
            </thead>
            <tbody>
              {cis.slice(0, MAX_FILAS).map(c => (
                <tr key={c.ci_id}>
                  <td className="sdp-wrap">{c.ci_name}</td>
                  <td>{c.ci_type ? etiquetaCodigo(t, 'sd_mercado.clase_base', codigo(c.ci_type)) : '—'}</td>
                  <td><Nivel nivel={c.criticality} /></td>
                  <td>{c.relation ? etiquetaCodigo(t, 'sd_informes.relacion', c.relation) : '—'}</td>
                  <td className="sdp-num">{c.depth}</td>
                </tr>
              ))}
            </tbody>
          </TablaSimple>
          {cis.length > MAX_FILAS && <p className="u-hint">{t('sd_informes.y_mas', { n: cis.length - MAX_FILAS })}</p>}
        </div>
      )}
      {activos.length > 0 && (
        <div>
          <Subtitulo>{t('sd_informes.activos_afectados')}</Subtitulo>
          <TablaSimple densidad="compacta" etiqueta={t('sd_informes.activos_afectados')} claseTabla="sdp-tabla">
            <thead>
              <tr>
                <th>{t('sd_informes.col_activo')}</th>
                <th>{t('sd_informes.col_tipo')}</th>
                <th>{t('sd_informes.col_estado')}</th>
                <th>{t('sd_informes.col_asignado')}</th>
                <th>{t('sd_informes.col_ci')}</th>
              </tr>
            </thead>
            <tbody>
              {activos.slice(0, MAX_FILAS).map(a => (
                <tr key={a.id}>
                  <td>
                    <span className="sdp-enlace__titulo">
                      {a.asset_tag && <span className="u-mono sdp-enlace__numero">{a.asset_tag}</span>}
                      <span className="sdp-wrap">{a.name}</span>
                    </span>
                  </td>
                  <td>{a.type ? etiquetaCodigo(t, 'almint.tipo_equipo', a.type) : '—'}</td>
                  <td><StatusBadge caps={false} kind={a.status === 'in_use' ? 'warning' : 'neutral'}>{etiquetaCodigo(t, 'sd_informes.estado_activo', a.status)}</StatusBadge></td>
                  <td>{a.assigned_to_name ?? <span className="u-text3-sm">{t('sd_informes.sin_asignar')}</span>}</td>
                  <td className="sdp-wrap">{a.ci_name ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </TablaSimple>
          {activos.length > MAX_FILAS && <p className="u-hint">{t('sd_informes.y_mas', { n: activos.length - MAX_FILAS })}</p>}
        </div>
      )}
      <div>
        <Subtitulo><span className="u-row-center-8"><AlertTriangle size={14} aria-hidden="true" />{t('sd_informes.recomendaciones')}</span></Subtitulo>
        <ul className="sdp-lista">
          {recomendaciones.map(k => <li key={k}><span className="sdp-wrap">{t(k)}</span></li>)}
        </ul>
      </div>
      {r.truncated && <p className="u-hint">{t('sd_informes.recortado')}</p>}
    </div>
  )
}
