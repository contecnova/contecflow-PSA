/**
 * AgenteAutonomoPanel — el agente autónomo y sus playbooks en pantalla
 * (mejoras de mercado 16-11-2026).
 *
 * Configuración por empresa (encendido, modo sugerir/ejecutar, umbrales,
 * playbooks de serie apagados), playbooks propios, estadísticas y el registro
 * de lo que hizo o propuso, con «Aplicar» y «Descartar» para las propuestas.
 * Lo que cambia la configuración es de administrador; el resto lo ve el equipo.
 *
 * 16-11-2026 (pasada de diseño): pestañas normales (eran subrayadas), vacío
 * con icono y el tipo de guía con su nombre (salía el código).
 */
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bot, Check, Play, Plus, Trash2, X } from 'lucide-react'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { useAuth } from '../../context/AuthContext'
import { confirmar } from '../../context/ConfirmContext'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { Button, Checkbox, EmptyState, GrupoDeOpciones, KpiCard, Modal, Section, Select, Spinner, StatusBadge, Switch, Tabs, useErroresDeCampo } from '../ui'
import type { StatusBadgeKind } from '../ui/StatusBadge'
import Pagination from '../ui/Pagination'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import { fmtDate } from '../../utils/helpers'
import { agenteAutonomoApi } from '../../services/api/serviceDeskMercado'
import type { ConfigDelAgente, PasoDePlaybook, Playbook } from '../../services/api/serviceDeskMercado'
import './sdMercado.css'

const TAMANO = 25
const ESTADO_KIND: Record<string, StatusBadgeKind> = {
  success: 'success', applied: 'success', suggested: 'warning', discarded: 'neutral', skipped: 'neutral', failed: 'danger',
}
const TIPOS_DE_PASO: PasoDePlaybook['type'][] = ['comment', 'notify', 'escalate', 'resolve']
const PRIORIDADES = ['p1_critical', 'p2_high', 'p3_medium', 'p4_low']

export default function AgenteAutonomoPanel() {
  const t = useAppT()
  const [vista, setVista] = useState('registro')
  const { user } = useAuth()
  const esAdmin = user?.role === 'admin'
  return (
    <Section title={<span className="u-row-center-6"><Bot size={16} aria-hidden="true" />{t('sd_mercado.agente_titulo')}</span>}
      subtitle={t('sd_mercado.agente_desc')}>
      <Tabs active={vista} onChange={setVista} ariaLabel={t('sd_mercado.agente_titulo')} items={[
        { id: 'registro', label: t('sd_mercado.agente_registro') },
        { id: 'playbooks', label: t('sd_mercado.agente_playbooks') },
        { id: 'config', label: t('sd_mercado.agente_config') },
      ]} />
      {vista === 'registro' && <Registro />}
      {vista === 'playbooks' && <Playbooks esAdmin={esAdmin} />}
      {vista === 'config' && <Configuracion esAdmin={esAdmin} />}
    </Section>
  )
}

function Registro() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [page, setPage] = useState(1)
  const [estado, setEstado] = useState('')
  const stats = useQuery({ queryKey: ['sdm-agente-stats'], queryFn: agenteAutonomoApi.estadisticas })
  const log = useQuery({
    queryKey: ['sdm-agente-log', page, estado],
    queryFn: () => agenteAutonomoApi.registro({ page, page_size: TAMANO, status: estado || undefined }),
  })
  const refrescar = () => { qc.invalidateQueries({ queryKey: ['sdm-agente-log'] }); qc.invalidateQueries({ queryKey: ['sdm-agente-stats'] }) }
  const decidir = useMutation({
    mutationFn: ({ id, aplicar }: { id: string; aplicar: boolean }) => aplicar ? agenteAutonomoApi.aplicar(id) : agenteAutonomoApi.descartar(id),
    onSuccess: (_d, v) => { toast.success(t(v.aplicar ? 'sd_mercado.propuesta_aplicada' : 'sd_mercado.propuesta_descartada')); refrescar() },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const s = stats.data
  const items = log.data?.items ?? []
  const total = log.data?.meta?.total ?? items.length
  return (
    <div className="u-stack-12">
      {s && (
        <div className="ds-grid-stats">
          <KpiCard label={t('sd_mercado.kpi_total')} value={s.total_executions} />
          <KpiCard label={t('sd_mercado.kpi_hechas')} value={s.success + s.applied} accent />
          <KpiCard label={t('sd_mercado.kpi_pendientes')} value={s.suggested} warning={s.suggested > 0} />
          <KpiCard label={t('sd_mercado.kpi_tasa')} value={`${s.success_rate_pct} %`} />
        </div>
      )}
      <div className="u-row-8">
        <label className="sdm-field"><span>{t('sd_mercado.filtrar_estado')}</span>
          <Select suelto placeholder={false} value={estado} onChange={e => { setEstado(e.target.value); setPage(1) }}>
            <option value="">{t('sd_mercado.todos')}</option>
            {Object.keys(ESTADO_KIND).map(k => <option key={k} value={k}>{etiquetaCodigo(t, 'sd_mercado.ejec', k)}</option>)}
          </Select>
        </label>
      </div>
      {log.isLoading ? <Spinner /> : items.length === 0 ? <EmptyState icon={<Bot size={28} />} title={t('sd_mercado.registro_vacio')} description={t('sd_mercado.agente_desc')} /> : (
        <ul className="sdm-list">
          {items.map(e => (
            <li key={e.id} className="sdm-list__item">
              <div className="u-flex1-min0 u-stack-6">
                <div className="u-wrap-8">
                  <span className="u-mono u-600">{e.ticket_number || e.ticket_id}</span>
                  <StatusBadge kind={ESTADO_KIND[e.status] || 'neutral'} caps={false}>{etiquetaCodigo(t, 'sd_mercado.ejec', e.status)}</StatusBadge>
                  {e.mode && <StatusBadge kind="info" caps={false}>{etiquetaCodigo(t, 'sd_mercado.modo', e.mode)}</StatusBadge>}
                  <span className="u-text2-xs">{etiquetaCodigo(t, 'sd_mercado.pb', e.playbook_type)}</span>
                  {e.confidence_score != null && <span className="u-text2-xs">{t('sd_mercado.confianza')}: {Math.round(e.confidence_score * 100)} %</span>}
                  <span className="u-text3-xs">{e.executed_at ? fmtDate(e.executed_at) : ''}</span>
                </div>
                {e.actions?.length > 0 && (
                  <ol className="sdm-steps">
                    {e.actions.map((a, i) => (
                      <li key={i} className="u-text2-xs sdm-wrap">
                        <span className="u-600">{etiquetaCodigo(t, 'sd_mercado.paso', a.type)}</span>
                        {a.status ? ` · ${etiquetaCodigo(t, 'sd_mercado.paso_estado', a.status)}` : ''}
                        {a.content ? ` — ${a.content.slice(0, 300)}` : ''}
                      </li>
                    ))}
                  </ol>
                )}
              </div>
              {e.status === 'suggested' && (
                <div className="u-actions-8">
                  <Button size="xs" variant="secondary" icon={<X size={12} />} onClick={() => decidir.mutate({ id: e.id, aplicar: false })} disabled={decidir.isPending}>{t('sd_mercado.descartar')}</Button>
                  <Button size="xs" icon={<Check size={12} />} onClick={async () => {
                    if (await confirmar({ message: t('sd_mercado.aplicar_confirmar', { n: e.ticket_number || '' }) })) decidir.mutate({ id: e.id, aplicar: true })
                  }} disabled={decidir.isPending}>{t('sd_mercado.aplicar')}</Button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      <Pagination page={page} totalPages={Math.max(1, Math.ceil(total / TAMANO))} onChange={setPage} total={total} pageSize={TAMANO} />
    </div>
  )
}

function Configuracion({ esAdmin }: { esAdmin: boolean }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({ queryKey: ['sdm-agente-config'], queryFn: agenteAutonomoApi.config })
  const [form, setForm] = useState<ConfigDelAgente | null>(null)
  useEffect(() => { if (data) setForm(data) }, [data])
  const guardar = useMutation({
    mutationFn: (f: ConfigDelAgente) => agenteAutonomoApi.guardarConfig({
      enabled: f.enabled, mode: f.mode, resolve_threshold: f.resolve_threshold, suggest_threshold: f.suggest_threshold,
      disabled_playbooks: f.disabled_playbooks,
    }),
    onSuccess: d => { setForm(d); qc.invalidateQueries({ queryKey: ['sdm-agente-config'] }); qc.invalidateQueries({ queryKey: ['sdm-agente-playbooks'] }); toast.success(t('sd_mercado.guardado')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const pasar = useMutation({
    mutationFn: agenteAutonomoApi.pasarAhora,
    onSuccess: r => { toast.success(t('sd_mercado.pasada_hecha', { n: r.evaluated ?? 0 })); qc.invalidateQueries({ queryKey: ['sdm-agente-log'] }) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  if (isLoading || !form) return <Spinner />
  const set = (p: Partial<ConfigDelAgente>) => setForm({ ...form, ...p })
  return (
    <div className="u-stack-12">
      {!esAdmin && <div className="u-text3-xs">{t('sd_mercado.solo_admin')}</div>}
      {/* 16-11-2026: casillas y radios como tarjetas del kit (ds-opcion), no
          fieldsets con el borde del navegador. */}
      <div className="ds-opciones">
        <Switch checked={!!form.enabled} disabled={!esAdmin} onChange={v => set({ enabled: v })} label={t('sd_mercado.agente_encendido')} />
      </div>
      <GrupoDeOpciones name="sdm-modo" leyenda={t('sd_mercado.modo_titulo')} disabled={!esAdmin} valor={form.mode}
        onChange={m => set({ mode: m as typeof form.mode })}
        opciones={form.modes.map(m => ({ valor: m, titulo: etiquetaCodigo(t, 'sd_mercado.modo', m), ayuda: t(`sd_mercado.modo_desc_${m}`) }))} />
      <div className="sdm-form">
        <label className="sdm-field"><span>{t('sd_mercado.umbral_resolver')}</span>
          <input className="ds-input" type="number" min={0} max={1} step={0.05} disabled={!esAdmin} value={form.resolve_threshold ?? ''}
            onChange={e => set({ resolve_threshold: e.target.value === '' ? null : Number(e.target.value) })} /></label>
        <label className="sdm-field"><span>{t('sd_mercado.umbral_sugerir')}</span>
          <input className="ds-input" type="number" min={0} max={1} step={0.05} disabled={!esAdmin} value={form.suggest_threshold ?? ''}
            onChange={e => set({ suggest_threshold: e.target.value === '' ? null : Number(e.target.value) })} /></label>
      </div>
      <GrupoDeOpciones tipo="checkbox" leyenda={t('sd_mercado.de_serie_titulo')} disabled={!esAdmin}
        valor={form.builtin_playbooks.filter(id => !form.disabled_playbooks.includes(id))}
        onChange={activos => set({ disabled_playbooks: [...form.disabled_playbooks.filter(x => !form.builtin_playbooks.includes(x)), ...form.builtin_playbooks.filter(id => !activos.includes(id))] })}
        opciones={form.builtin_playbooks.map(id => ({ valor: id, titulo: etiquetaCodigo(t, 'sd_mercado.pb', id) }))} />
      {esAdmin && (
        <div className="u-actions-8">
          <Button variant="secondary" icon={<Play size={14} />} onClick={() => pasar.mutate()} loading={pasar.isPending} disabled={!data?.enabled}>{t('sd_mercado.pasar_ahora')}</Button>
          <Button onClick={() => guardar.mutate(form)} loading={guardar.isPending}>{t('common.save')}</Button>
        </div>
      )}
    </div>
  )
}

function Playbooks({ esAdmin }: { esAdmin: boolean }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [editando, setEditando] = useState<Playbook | 'nuevo' | null>(null)
  const { data = [], isLoading } = useQuery({ queryKey: ['sdm-agente-playbooks'], queryFn: agenteAutonomoApi.playbooks })
  const borrar = useMutation({
    mutationFn: agenteAutonomoApi.borrarPlaybook,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sdm-agente-playbooks'] }); toast.success(t('sd_mercado.playbook_desactivado')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  if (isLoading) return <Spinner />
  return (
    <div className="u-stack-12">
      {esAdmin && <div className="u-row-end"><Button icon={<Plus size={14} />} onClick={() => setEditando('nuevo')}>{t('sd_mercado.playbook_nuevo')}</Button></div>}
      <ul className="sdm-list">
        {data.map(p => (
          <li key={p.id} className="sdm-list__item">
            <div className="u-flex1-min0 u-stack-6">
              <div className="u-wrap-8">
                <span className="u-text1-sm-600">{p.source === 'builtin' ? etiquetaCodigo(t, 'sd_mercado.pb', p.id, p.name) : p.name}</span>
                <StatusBadge kind={p.source === 'builtin' ? 'neutral' : 'accent'} caps={false}>{t(p.source === 'builtin' ? 'sd_mercado.de_serie' : 'sd_mercado.propio')}</StatusBadge>
                <StatusBadge kind={p.enabled ? 'success' : 'neutral'} caps={false}>{t(p.enabled ? 'sd_mercado.activo' : 'sd_mercado.apagado')}</StatusBadge>
                {p.conditions.auto_resolve && <StatusBadge kind="warning" caps={false}>{t('sd_mercado.puede_resolver')}</StatusBadge>}
              </div>
              <div className="u-text3-xs sdm-wrap">{t('sd_mercado.palabras')}: {(p.conditions.trigger_keywords || []).join(', ') || '—'} · {t('sd_mercado.hasta_prioridad')}: {etiquetaCodigo(t, 'estado', p.conditions.max_priority || 'p3_medium')}</div>
              <div className="u-text3-xs">{t('sd_mercado.n_pasos', { n: p.steps.length })}</div>
            </div>
            {esAdmin && p.source === 'custom' && (
              <div className="u-actions-8">
                <Button size="xs" variant="secondary" onClick={() => setEditando(p)}>{t('sd_mercado.editar')}</Button>
                <Button size="xs" variant="ghost" icon={<Trash2 size={12} />} onClick={async () => {
                  if (await confirmar({ message: t('sd_mercado.playbook_desactivar_confirmar', { n: p.name }), danger: true })) borrar.mutate(p.id)
                }}>{t('sd_mercado.desactivar')}</Button>
              </div>
            )}
          </li>
        ))}
      </ul>
      {editando && <PlaybookModal inicial={editando === 'nuevo' ? null : editando} onClose={() => setEditando(null)}
        onSaved={() => { setEditando(null); qc.invalidateQueries({ queryKey: ['sdm-agente-playbooks'] }); toast.success(t('sd_mercado.guardado')) }} />}
    </div>
  )
}

function PlaybookModal({ inicial, onClose, onSaved }: { inicial: Playbook | null; onClose: () => void; onSaved: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const [nombre, setNombre] = useState(inicial?.name ?? '')
  const [descripcion, setDescripcion] = useState(inicial?.description ?? '')
  const [palabras, setPalabras] = useState((inicial?.conditions.trigger_keywords ?? []).join(', '))
  const [categorias, setCategorias] = useState((inicial?.conditions.trigger_categories ?? []).join(', '))
  const [maxPrioridad, setMaxPrioridad] = useState(inicial?.conditions.max_priority ?? 'p3_medium')
  const [resolver, setResolver] = useState(Boolean(inicial?.conditions.auto_resolve))
  const [pasos, setPasos] = useState<PasoDePlaybook[]>(inicial?.steps ?? [{ type: 'comment', content: '' }])
  const lista = (s: string) => s.split(',').map(x => x.trim()).filter(Boolean)
  const campos = useErroresDeCampo()
  const msg = (k: string) => campos.de(k) ? <div className="u-field-error">{campos.de(k)}</div> : null
  const guardar = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: () => {
      const datos = {
        name: nombre.trim(), description: descripcion.trim() || undefined,
        steps: pasos.map(p => ({ type: p.type, content: p.content })),
        conditions: { trigger_keywords: lista(palabras), trigger_categories: lista(categorias), max_priority: maxPrioridad, auto_resolve: resolver },
      }
      return inicial ? agenteAutonomoApi.editarPlaybook(inicial.id, datos) : agenteAutonomoApi.crearPlaybook(datos)
    },
    onSuccess: onSaved,
    onError: (e: unknown) => { campos.recoger(e); toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) },
  })
  return (
    <Modal open size="lg" onClose={onClose} title={inicial ? t('sd_mercado.playbook_editar') : t('sd_mercado.playbook_nuevo')}>
      <div className="u-stack-12">
        <div className="sdm-form">
          <label className="sdm-field"><span>{t('sd_mercado.nombre')}</span><input className="ds-input" value={nombre} onChange={e => setNombre(e.target.value)} /></label>
          <label className="sdm-field"><span>{t('sd_mercado.hasta_prioridad')}</span>
            <Select suelto placeholder={false} value={maxPrioridad} onChange={e => setMaxPrioridad(e.target.value)}>
              {PRIORIDADES.map(p => <option key={p} value={p}>{etiquetaCodigo(t, 'estado', p)}</option>)}
            </Select></label>
        </div>
        <label className="sdm-field"><span>{t('sd_mercado.descripcion')}</span><input className="ds-input" value={descripcion} onChange={e => setDescripcion(e.target.value)} /></label>
        <label className="sdm-field"><span>{t('sd_mercado.palabras_hint')}</span><input className="ds-input" value={palabras} onChange={e => setPalabras(e.target.value)} /></label>
        <label className="sdm-field"><span>{t('sd_mercado.categorias_hint')}</span><input className="ds-input" value={categorias} onChange={e => setCategorias(e.target.value)} /></label>
        <Checkbox className="u-row-center-8" checked={!!resolver} onChange={setResolver} label={t('sd_mercado.puede_resolver')} />
        <div className="ds-eyebrow">{t('sd_mercado.pasos')}</div>
        <div className="sdm-steps">
          {pasos.map((p, i) => (
            <div key={i} className="sdm-step">
              <Select suelto placeholder={false} aria-label={t('sd_mercado.tipo_paso')} value={p.type}
                onChange={e => setPasos(pasos.map((x, j) => j === i ? { ...x, type: e.target.value as PasoDePlaybook['type'] } : x))}>
                {TIPOS_DE_PASO.map(tp => <option key={tp} value={tp}>{etiquetaCodigo(t, 'sd_mercado.paso', tp)}</option>)}
              </Select>{msg('type')}
              <textarea className="ds-input" rows={2} aria-label={t('sd_mercado.contenido_paso')} value={p.content}
                onChange={e => setPasos(pasos.map((x, j) => j === i ? { ...x, content: e.target.value } : x))} />{msg('content')}
              <Button size="xs" variant="ghost" icon={<Trash2 size={12} />} onClick={() => setPasos(pasos.filter((_, j) => j !== i))}>{t('sd_mercado.quitar')}</Button>
            </div>
          ))}
        </div>
        <div><Button size="sm" variant="secondary" icon={<Plus size={12} />} onClick={() => setPasos([...pasos, { type: 'comment', content: '' }])}>{t('sd_mercado.anadir_paso')}</Button></div>
        <div className="u-actions-10">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => guardar.mutate()} loading={guardar.isPending} disabled={nombre.trim().length < 2 || pasos.length === 0}>{t('common.save')}</Button>
        </div>
      </div>
    </Modal>
  )
}
