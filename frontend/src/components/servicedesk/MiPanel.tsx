/**
 * MiPanel — panel del service desk personalizable (mejoras de mercado 16-11-2026).
 *
 * Cada persona elige y ordena sus widgets por vista (operación, responsable,
 * dirección); sin panel propio ve el de la empresa y, si no, el de serie. Un
 * administrador puede guardar el suyo como el de la empresa. Los widgets salen
 * del catálogo del servidor (`/sd/dashboard/layout`), con datos reales.
 */
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowDown, ArrowUp, LayoutDashboard, Plus, Trash2 } from 'lucide-react'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { useAuth } from '../../context/AuthContext'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { Button, Section, Spinner, StatusBadge, Tabs } from '../ui'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import { puestoDelAgenteApi } from '../../services/api/serviceDeskMercado'
import type { RolDePanel } from '../../services/api/serviceDeskMercado'
import VistaDeDatos from './VistaDeDatos'
import './sdMercado.css'

/** Ruta y parámetros de cada widget (los mismos que declara el servidor). */
const ORIGEN: Record<string, { ruta: string; params?: Record<string, unknown> }> = {
  my_queue_prioritized: { ruta: '/sd/tickets/my-queue/prioritized', params: { page: 1, page_size: 5 } },
  sla_risk: { ruta: '/sd/predictive/stats' },
  major_incidents: { ruta: '/sd/major-incidents' },
  itil_metrics: { ruta: '/sd/metrics/itil' },
  agent_performance: { ruta: '/sd/metrics/agent-performance' },
  autonomous_agent: { ruta: '/sd/autonomous/stats' },
  cab_pending: { ruta: '/sd/changes/cab-dashboard', params: { page: 1, page_size: 5 } },
  my_approvals: { ruta: '/sd/approvals/mine' },
}

function Widget({ id, onAbrir }: { id: string; onAbrir: (ticketId: string) => void }) {
  const t = useAppT()
  const o = ORIGEN[id]
  const { data, isLoading, isError } = useQuery({ queryKey: ['sdm-widget', id], queryFn: () => puestoDelAgenteApi.get<unknown>(o.ruta, o.params), enabled: !!o, retry: false })
  return (
    <div className="ds-card sdm-card">
      <div className="sdm-card__head">{etiquetaCodigo(t, 'sd_mercado.widget', id)}</div>
      {isLoading ? <Spinner size={16} /> : isError ? <div className="u-text3-xs">{t('sd_mercado.error_carga')}</div>
        : id === 'my_queue_prioritized' && Array.isArray(data) ? (
          (data as { id: string; number: string; title: string; priority_score: number }[]).length === 0
            ? <div className="u-text3-xs">{t('sd_mercado.cola_vacia')}</div>
            : (data as { id: string; number: string; title: string; priority_score: number }[]).map(tk => (
              <button key={tk.id} type="button" className="u-btn-outline-sm sdm-wrap" onClick={() => onAbrir(tk.id)}>
                <span className="u-mono">{tk.number}</span> {tk.title} <StatusBadge caps={false}>{Math.round(tk.priority_score * 100)}</StatusBadge>
              </button>
            ))
        ) : <VistaDeDatos datos={Array.isArray(data) ? data.slice(0, 8) : data} />}
    </div>
  )
}

export default function MiPanel({ onAbrir }: { onAbrir: (ticketId: string) => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { user } = useAuth()
  const esAdmin = user?.role === 'admin'
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
      subtitle={data ? etiquetaCodigo(t, 'sd_mercado.origen_panel', data.layout.origin) : undefined}
      actions={<>
        {!editando && <Button size="sm" variant="secondary" onClick={() => setEditando(true)}>{t('sd_mercado.personalizar')}</Button>}
        {editando && data?.layout.origin === 'user' && <Button size="sm" variant="ghost" onClick={() => restablecer.mutate()}>{t('sd_mercado.restablecer')}</Button>}
      </>}>
      <Tabs variant="underline" size="sm" active={rol} onChange={id => setRol(id as RolDePanel)} ariaLabel={t('sd_mercado.panel_titulo')} items={(['operation', 'manager', 'executive'] as RolDePanel[]).map(r => ({ id: r, label: etiquetaCodigo(t, 'sd_mercado.vista_panel', r) }))} />
      <div className="u-mb-12" />
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
      ) : (
        <div className="sdm-widgets">{widgets.map(w => <Widget key={w} id={w} onAbrir={onAbrir} />)}</div>
      )}
    </Section>
  )
}
