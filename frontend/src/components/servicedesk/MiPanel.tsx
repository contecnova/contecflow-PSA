/**
 * MiPanel — panel del service desk personalizable (mejoras de mercado 16-11-2026).
 *
 * Cada persona elige y ordena sus widgets por vista (operación, responsable,
 * dirección); sin panel propio ve el de la empresa y, si no, el de serie. Un
 * administrador puede guardar el suyo como el de la empresa. Los widgets salen
 * del catálogo del servidor (`/sd/dashboard/layout`), con datos reales.
 *
 * 19-11-2026 (rehecho como informe): cada widget tiene su render propio
 * (`WidgetsDelPanel.tsx`) en vez del volcado genérico `VistaDeDatos`, con su
 * ancho en una rejilla de 12 columnas (KPIs 4, tablas 8, métricas ITIL 12), y
 * las métricas ITIL comparan con los 30 días anteriores.
 */
import { useEffect, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle, ArrowDown, ArrowUp, BarChart3, Bot, ClipboardCheck, Flame, GitPullRequestArrow, LayoutDashboard,
  ListOrdered, Plus, ShieldAlert, Trash2, Users,
} from 'lucide-react'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { useAuth } from '../../context/AuthContext'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { Button, EmptyState, Section, Spinner, StatusBadge, Tabs } from '../ui'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import { puestoDelAgenteApi } from '../../services/api/serviceDeskMercado'
import type { RolDePanel } from '../../services/api/serviceDeskMercado'
import { STALE_DEFAULT_MS } from '../../constants/timings'
import {
  TAMANO_DE_WIDGET, WidgetAgenteAutonomo, WidgetCab, WidgetIncidentesMayores, WidgetMetricasItil, WidgetMiCola,
  WidgetMisAprobaciones, WidgetRendimiento, WidgetRiesgoSla, recuentoDeWidget,
} from './WidgetsDelPanel'
import type {
  AprobacionPendiente, EstadisticasDeRiesgo, EstadisticasDelAgente, IncidenteMayor, MetricasItil, PanelDelCab,
  RendimientoDeAgente, TicketDeCola,
} from './WidgetsDelPanel'
import './sdMercado.css'

/** Ruta y parámetros de cada widget (los mismos que declara el servidor). */
const ORIGEN: Record<string, { ruta: string; params?: Record<string, unknown> }> = {
  my_queue_prioritized: { ruta: '/sd/tickets/my-queue/prioritized', params: { page: 1, page_size: 8 } },
  sla_risk: { ruta: '/sd/predictive/stats' },
  major_incidents: { ruta: '/sd/major-incidents' },
  itil_metrics: { ruta: '/sd/metrics/itil' },
  agent_performance: { ruta: '/sd/metrics/agent-performance' },
  autonomous_agent: { ruta: '/sd/autonomous/stats' },
  cab_pending: { ruta: '/sd/changes/cab-dashboard', params: { page: 1, page_size: 6 } },
  my_approvals: { ruta: '/sd/approvals/mine' },
}

const ICONO: Record<string, ReactNode> = {
  my_queue_prioritized: <ListOrdered size={16} />,
  sla_risk: <ShieldAlert size={16} />,
  major_incidents: <Flame size={16} />,
  itil_metrics: <BarChart3 size={16} />,
  agent_performance: <Users size={16} />,
  autonomous_agent: <Bot size={16} />,
  cab_pending: <GitPullRequestArrow size={16} />,
  my_approvals: <ClipboardCheck size={16} />,
}

/** Fecha local `AAAA-MM-DD` de hace `dias` días. */
function haceDias(dias: number): string {
  const d = new Date()
  d.setDate(d.getDate() - dias)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

interface PropsDeMiPanel {
  onAbrir: (ticketId: string) => void
  /** Ir a otra pestaña del service desk (incidentes mayores, cambios, cola). */
  onIrA?: (pestana: string) => void
}

/** Cuerpo del widget según su id (cada uno con sus campos reales). */
function CuerpoDeWidget({ id, datos, previo, onAbrir, onIrA }: { id: string; datos: unknown; previo?: MetricasItil | null } & PropsDeMiPanel) {
  const comun = { onAbrir, onIrA }
  switch (id) {
    case 'my_queue_prioritized': return <WidgetMiCola datos={(datos as TicketDeCola[]) ?? []} {...comun} />
    case 'sla_risk': return <WidgetRiesgoSla datos={datos as EstadisticasDeRiesgo} {...comun} />
    case 'major_incidents': return <WidgetIncidentesMayores datos={(datos as IncidenteMayor[]) ?? []} {...comun} />
    case 'itil_metrics': return <WidgetMetricasItil datos={datos as MetricasItil} previo={previo} {...comun} />
    case 'agent_performance': return <WidgetRendimiento datos={(datos as RendimientoDeAgente[]) ?? []} {...comun} />
    case 'autonomous_agent': return <WidgetAgenteAutonomo datos={datos as EstadisticasDelAgente} {...comun} />
    case 'cab_pending': return <WidgetCab datos={(datos as PanelDelCab) ?? { total: 0, unscored: 0, items: [] }} {...comun} />
    case 'my_approvals': return <WidgetMisAprobaciones datos={(datos as AprobacionPendiente[]) ?? []} {...comun} />
    default: return null
  }
}

function Widget({ id, onAbrir, onIrA }: { id: string } & PropsDeMiPanel) {
  const t = useAppT()
  const o = ORIGEN[id]
  const { data, isLoading, isError } = useQuery({
    queryKey: ['sdm-widget', id], queryFn: () => puestoDelAgenteApi.get<unknown>(o.ruta, o.params),
    enabled: !!o, retry: false, staleTime: STALE_DEFAULT_MS,
  })
  // Tendencia de las métricas ITIL: los 30 días anteriores a los 30 que se ven.
  const previo = useQuery({
    queryKey: ['sdm-widget', id, 'previo'],
    queryFn: () => puestoDelAgenteApi.get<MetricasItil>('/sd/metrics/itil', { date_from: haceDias(60), date_to: haceDias(31) }),
    enabled: id === 'itil_metrics', retry: false, staleTime: STALE_DEFAULT_MS,
  })
  const tamano = TAMANO_DE_WIDGET[id] ?? 6
  const recuento = data != null ? recuentoDeWidget(id, data) : null
  return (
    <section className="ds-card sdp-widget" data-tamano={tamano} data-widget={id}
      style={{ '--sdp-span': tamano } as CSSProperties} aria-labelledby={`sdp-${id}`}>
      <header className="sdp-widget__cabecera">
        <h3 className="sdp-widget__titulo" id={`sdp-${id}`}>
          <span className="sdp-widget__icono" aria-hidden>{ICONO[id]}</span>
          {etiquetaCodigo(t, 'sd_mercado.widget', id)}
        </h3>
        {recuento && <div className="sdp-widget__acciones"><StatusBadge caps={false} kind={recuento.kind}>{recuento.n}</StatusBadge></div>}
      </header>
      <div className="sdp-widget__cuerpo">
        {!o ? null
          : isLoading ? <Spinner size={18} />
            : isError || data == null
              ? <EmptyState icon={<AlertTriangle size={28} />} title={t('sd_mercado.error_carga')} description={t('sd_mercado.panel.error_desc')} />
              : <CuerpoDeWidget id={id} datos={data} previo={previo.data ?? null} onAbrir={onAbrir} onIrA={onIrA} />}
      </div>
    </section>
  )
}

export default function MiPanel({ onAbrir, onIrA }: PropsDeMiPanel) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { puede } = useAuth()
  const esAdmin = puede('sd.administrar')
  const [rol, setRol] = useState<RolDePanel>('operation')
  const [editando, setEditando] = useState(false)
  const { data, isLoading } = useQuery({ queryKey: ['sdm-panel', rol], queryFn: () => puestoDelAgenteApi.panel(rol) })
  const [widgets, setWidgets] = useState<string[]>([])
  useEffect(() => { if (data) setWidgets(data.layout.widgets) }, [data])
  const err = (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  const guardar = useMutation({
    mutationFn: (scope: 'user' | 'org') => puestoDelAgenteApi.guardarPanel(rol, widgets, scope),
    onSuccess: () => { setEditando(false); qc.invalidateQueries({ queryKey: ['sdm-panel', rol] }); toast.success(t('sd_mercado.guardado')) },
    onError: err,
  })
  const restablecer = useMutation({
    mutationFn: () => puestoDelAgenteApi.restablecerPanel(rol),
    onSuccess: () => { setEditando(false); qc.invalidateQueries({ queryKey: ['sdm-panel', rol] }) },
    onError: err,
  })
  const disponibles = (data?.widgets ?? Object.keys(ORIGEN)).filter(w => !widgets.includes(w))
  const mover = (i: number, d: number) => { const n = [...widgets]; const [x] = n.splice(i, 1); n.splice(i + d, 0, x); setWidgets(n) }
  return (
    <Section title={<span className="u-row-center-6"><LayoutDashboard size={16} aria-hidden="true" />{t('sd_mercado.panel_titulo')}</span>}
      subtitle={data ? `${t(`sd_mercado.panel.desc_vista.${rol}`)} · ${etiquetaCodigo(t, 'sd_mercado.origen_panel', data.layout.origin)}` : undefined}
      actions={<>
        {!editando && <Button size="sm" variant="secondary" onClick={() => setEditando(true)}>{t('sd_mercado.personalizar')}</Button>}
        {editando && data?.layout.origin === 'user' && <Button size="sm" variant="ghost" onClick={() => restablecer.mutate()}>{t('sd_mercado.restablecer')}</Button>}
      </>}>
      <Tabs active={rol} onChange={id => setRol(id as RolDePanel)} ariaLabel={t('sd_mercado.panel_titulo')} items={(['operation', 'manager', 'executive'] as RolDePanel[]).map(r => ({ id: r, label: etiquetaCodigo(t, 'sd_mercado.vista_panel', r) }))} />
      {isLoading ? <Spinner /> : editando ? (
        <div className="u-stack-12">
          <ul className="sdm-list">
            {widgets.map((w, i) => (
              <li key={w} className="sdm-list__item">
                <span className="u-flex1">{etiquetaCodigo(t, 'sd_mercado.widget', w)}</span>
                <Button size="xs" variant="ghost" icon={<ArrowUp size={12} />} disabled={i === 0} onClick={() => mover(i, -1)}>{t('sd_mercado.subir')}</Button>
                <Button size="xs" variant="ghost" icon={<ArrowDown size={12} />} disabled={i === widgets.length - 1} onClick={() => mover(i, 1)}>{t('sd_mercado.bajar')}</Button>
                <Button size="xs" variant="ghost" icon={<Trash2 size={12} />} onClick={() => setWidgets(widgets.filter(x => x !== w))}>{t('sd_mercado.quitar')}</Button>
              </li>
            ))}
          </ul>
          {disponibles.length > 0 && <div className="u-wrap-6">{disponibles.map(w => (
            <Button key={w} size="xs" variant="secondary" icon={<Plus size={12} />} onClick={() => setWidgets([...widgets, w])}>{etiquetaCodigo(t, 'sd_mercado.widget', w)}</Button>
          ))}</div>}
          <div className="u-actions-8">
            <Button variant="secondary" onClick={() => { setEditando(false); if (data) setWidgets(data.layout.widgets) }}>{t('common.cancel')}</Button>
            {esAdmin && <Button variant="secondary" onClick={() => guardar.mutate('org')} disabled={widgets.length === 0}>{t('sd_mercado.guardar_empresa')}</Button>}
            <Button onClick={() => guardar.mutate('user')} loading={guardar.isPending} disabled={widgets.length === 0}>{t('sd_mercado.guardar_mio')}</Button>
          </div>
        </div>
      ) : widgets.length === 0 ? (
        <EmptyState icon={<LayoutDashboard size={28} />} title={t('sd_mercado.panel.vacio')} ctaLabel={t('sd_mercado.personalizar')} onCta={() => setEditando(true)} />
      ) : (
        <div className="sdp-rejilla">{widgets.map(w => <Widget key={w} id={w} onAbrir={onAbrir} onIrA={onIrA} />)}</div>
      )}
    </Section>
  )
}
