/**
 * Ficha del proveedor → Paquetes de trabajo (outsourcing, 19-11-2026).
 *
 * Alcance: proyecto, fase, hito, entregable o tareas. Ciclo: planificado →
 * en curso → entregado → aceptado / rechazado (vuelve a empezar), o cancelado.
 * Aceptar exige la UAT superada si el paquete tiene sesión (lo comprueba el
 * backend) y deja el precio cerrado en la siguiente previsión. Externalizar
 * tareas las marca con `supplier_id` y el paquete (sin persona asignada).
 * Informes de avance y su revisión: `InformesDeProveedor` (también lo usa la
 * pestaña Servicios para los informes periódicos).
 *
 * Migración 191: sesión UAT elegible (las del proyecto, `useReferencias`);
 * informes con tipo (avance, periódico, parte de servicio, evidencia de SLA),
 * evidencias por enlace o fichero, y la marca de los que llegan del portal del
 * proveedor.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Briefcase, CheckCircle2, ClipboardCheck, FileBarChart, Globe, Link2, ListPlus, Paperclip, Pencil, Play, Plus, Send, X } from 'lucide-react'
import { Button, Card, Checkbox, EmptyState, Input, Modal, Select, Spinner, useErroresDeCampo, Textarea } from '../../components/ui'
import StatusBadge from '../../components/ui/StatusBadge'
import { usePersonasInternas } from '../../components/externos/FormularioDeExterno'
import { etiquetaDePersona } from '../../components/ui/MarcaExterno'
import { openConfirmGlobal, pedirTexto } from '../../context/ConfirmContext'
import { useToast } from '../../context/ToastContext'
import { useAppT } from '../../i18n/AppLangContext'
import { deliverablesApi, milestonesApi } from '../../services/api'
import { projectsApi } from '../../services/api/projects'
import { tasksApi } from '../../services/api/tasks'
import { proveedoresApi } from '../../services/api/proveedores'
import type { AdjuntoDeInforme, AlcanceDePaquete, InformeDeProveedor, InformeIn, PaqueteDeTrabajo, PaqueteIn, TipoDeInforme } from '../../services/api/tipos-proveedores'
import type { Subcontratista } from '../../services/api/tipos-alm'
import { useFormatoMoneda } from '../../hooks/useFormatoMoneda'
import { useOrgSettings } from '../../hooks/useOrgSettings'
import { extractErr, fmtDate, fmtNumber } from '../../utils/helpers'
import { sanitizeUrl } from '../../utils/security'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { ALCANCES, TIPOS_DE_INFORME_DE_SERVICIO, TONO_PAQUETE, numeroONull, pasosDePaquete, texto, textoONull } from './logica'
import { etiquetaDe, useProyectosActivos, usePermisosDeProveedores, useReferencias, useT } from './comunes'

function FormularioDePaquete({ sub, paquete, onClose }: { sub: Subcontratista; paquete: PaqueteDeTrabajo | null; onClose: () => void }) {
  const t = useT()
  const tApp = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const campos = useErroresDeCampo()
  const { currency, currencies } = useOrgSettings()
  const { personas } = usePersonasInternas()
  const proyectos = useProyectosActivos()
  const w = paquete
  const [f, setF] = useState({
    project_id: texto(w?.project_id), contract_id: texto(w?.contract_id), scope_type: (w?.scope_type || 'tasks') as AlcanceDePaquete,
    phase_id: texto(w?.phase_id), milestone_id: texto(w?.milestone_id), deliverable_id: texto(w?.deliverable_id),
    uat_session_id: texto(w?.uat_session_id),
    title: texto(w?.title), description: texto(w?.description), acceptance_criteria: texto(w?.acceptance_criteria),
    planned_start: texto(w?.planned_start), planned_end: texto(w?.planned_end), price: texto(w?.price),
    currency: w?.currency || sub.currency || currency, progress_pct: texto(w?.progress_pct), internal_owner_id: texto(w?.internal_owner_id),
  })
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => { campos.limpiar(k); setF(x => ({ ...x, [k]: e.target.value })) }
  const { data: contratos = [] } = useQuery({ queryKey: ['suppliers', 'contracts', sub.id], queryFn: () => proveedoresApi.contratos(sub.id).then(r => r.data) })
  const referencias = useReferencias({ projectId: f.project_id || null, subId: sub.id })
  const { data: proyecto } = useQuery({
    queryKey: ['project', f.project_id], queryFn: () => projectsApi.get(f.project_id).then(r => r.data),
    enabled: !!f.project_id && f.scope_type === 'phase',
  })
  const { data: hitos = [] } = useQuery({
    queryKey: ['milestones', f.project_id], queryFn: () => milestonesApi.list(f.project_id).then(r => r.data),
    enabled: !!f.project_id && f.scope_type === 'milestone',
  })
  const { data: entregables } = useQuery({
    queryKey: ['deliverables', f.project_id], queryFn: () => deliverablesApi.listByProject(f.project_id).then(r => r.data),
    enabled: !!f.project_id && f.scope_type === 'deliverable',
  })

  const guardar = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: () => {
      const d: PaqueteIn = {
        project_id: f.project_id, contract_id: f.contract_id || null, scope_type: f.scope_type,
        phase_id: f.scope_type === 'phase' ? (f.phase_id || null) : null,
        milestone_id: f.scope_type === 'milestone' ? (f.milestone_id || null) : null,
        deliverable_id: f.scope_type === 'deliverable' ? (f.deliverable_id || null) : null,
        uat_session_id: f.uat_session_id || null,
        title: f.title.trim(), description: textoONull(f.description), acceptance_criteria: textoONull(f.acceptance_criteria),
        planned_start: f.planned_start || null, planned_end: f.planned_end || null, price: numeroONull(f.price),
        currency: f.currency || null, progress_pct: numeroONull(f.progress_pct), internal_owner_id: f.internal_owner_id || null,
      }
      return w ? proveedoresApi.editarPaquete(w.id, d) : proveedoresApi.crearPaquete(sub.id, d)
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['suppliers'] }); toast.success(t('proveedores.paquete_guardado')); onClose() },
    onError: (e: unknown) => { if (!campos.recoger(e)) toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) },
  })

  const alcanceOk = f.scope_type === 'project' || f.scope_type === 'tasks'
    || (f.scope_type === 'phase' && !!f.phase_id) || (f.scope_type === 'milestone' && !!f.milestone_id) || (f.scope_type === 'deliverable' && !!f.deliverable_id)
  return (
    <Modal open title={w ? t('proveedores.editar_paquete') : t('proveedores.nuevo_paquete')} onClose={onClose} width={680}>
      <div className="u-stack-8">
        <div className="prv-rejilla">
          <Input className="prv-completo" label={t('proveedores.titulo')} required value={f.title} onChange={set('title')} error={campos.de('title')} />
          <Select label={t('subcontractors.col_proyecto')} required value={f.project_id} onChange={set('project_id')} error={campos.de('project_id')} placeholder={t('proveedores.elegir')}
            disabled={!!w} options={proyectos.map(p => ({ value: p.id, label: `${p.code} — ${p.name}` }))} />
          <Select label={t('proveedores.alcance')} value={f.scope_type} placeholder={false} onChange={set('scope_type')} error={campos.de('scope_type')}
            options={ALCANCES.map(a => ({ value: a, label: etiquetaDe(t, 'alcance_', a) }))} />
          {f.scope_type === 'phase' && (
            <Select className="prv-completo" label={t('proveedores.fase')} value={f.phase_id} onChange={set('phase_id')} error={campos.de('phase_id')} placeholder={t('proveedores.elegir')}
              options={(proyecto?.phases || []).map(p => ({ value: p.id, label: p.name }))} />
          )}
          {f.scope_type === 'milestone' && (
            <Select className="prv-completo" label={t('proveedores.hito')} value={f.milestone_id} onChange={set('milestone_id')} error={campos.de('milestone_id')} placeholder={t('proveedores.elegir')}
              options={hitos.map(h => ({ value: h.id, label: h.name }))} />
          )}
          {f.scope_type === 'deliverable' && (
            <Select className="prv-completo" label={t('proveedores.entregable')} value={f.deliverable_id} onChange={set('deliverable_id')} error={campos.de('deliverable_id')} placeholder={t('proveedores.elegir')}
              options={(entregables?.deliverables || []).map(d => ({ value: d.id, label: `${d.code} — ${d.name}` }))} />
          )}
          <Input label={t('proveedores.inicio_previsto')} type="date" value={f.planned_start} onChange={set('planned_start')} error={campos.de('planned_start')} />
          <Input label={t('proveedores.fin_previsto')} type="date" value={f.planned_end} onChange={set('planned_end')} error={campos.de('planned_end')} />
          <Input label={t('proveedores.precio_cerrado')} type="number" min={0} step="0.01" value={f.price} onChange={set('price')} error={campos.de('price')} />
          <Select label={t('subcontractors.moneda')} value={f.currency} placeholder={false} onChange={set('currency')}
            options={(currencies.includes(f.currency) ? currencies : [f.currency, ...currencies]).map(m => ({ value: m, label: m }))} />
          <Select label={t('proveedores.contrato')} value={f.contract_id} onChange={set('contract_id')} placeholder={t('proveedores.sin_contrato')}
            options={contratos.map(c => ({ value: c.id, label: c.title }))} />
          <Select label={t('proveedores.sesion_uat')} value={f.uat_session_id} onChange={set('uat_session_id')} error={campos.de('uat_session_id')}
            placeholder={t('proveedores.sin_sesion_uat')} hint={t('proveedores.sesion_uat_d')} disabled={!f.project_id}
            options={referencias.uat_sessions
              .filter(u => f.scope_type !== 'deliverable' || !f.deliverable_id || !u.deliverable_id || u.deliverable_id === f.deliverable_id)
              .map(u => ({ value: u.id, label: `${u.label} · ${etiquetaDe(t, 'uat_', String(u.status || ''))}` }))} />
          {w && <Input label={t('proveedores.avance_pct')} type="number" min={0} max={100} value={f.progress_pct} onChange={set('progress_pct')} error={campos.de('progress_pct')} />}
          <Select className="prv-completo" label={t('externos.responsable_interno')} value={f.internal_owner_id} onChange={set('internal_owner_id')} placeholder={t('externos.elegir_responsable')}
            options={personas.map(p => ({ value: p.id, label: etiquetaDePersona(tApp, p) }))} />
        </div>
        <Textarea label={t('subcontractors.descripcion')} id="prv-paquete-desc" value={f.description} onChange={set('description')} />
        <Textarea label={t('proveedores.criterios_aceptacion')} id="prv-paquete-criterios" value={f.acceptance_criteria} onChange={set('acceptance_criteria')} />
        <div className="u-actions-8">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => guardar.mutate()} loading={guardar.isPending} disabled={!f.title.trim() || !f.project_id || !alcanceOk || guardar.isPending}>{t('common.save')}</Button>
        </div>
      </div>
    </Modal>
  )
}

/** Elegir tareas del proyecto del paquete para externalizarlas. */
function ExternalizarTareas({ paquete, onClose }: { paquete: PaqueteDeTrabajo; onClose: () => void }) {
  const t = useT()
  const toast = useToast()
  const qc = useQueryClient()
  const [elegidas, setElegidas] = useState<string[]>([])
  const { data: tareas = [], isLoading } = useQuery({
    queryKey: ['tasks', 'externalizables', paquete.project_id],
    queryFn: () => tasksApi.list({ project_id: paquete.project_id, status: 'backlog,todo,in_progress,blocked,in_review' }).then(r => r.data),
  })
  const libres = tareas.filter(x => x.supplier_work_package_id !== paquete.id)
  const enviar = useMutation({
    mutationFn: () => proveedoresApi.tareasAlPaquete(paquete.id, elegidas),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['suppliers'] })
      qc.invalidateQueries({ queryKey: ['tasks'] })
      toast.success(t('proveedores.tareas_externalizadas', { n: elegidas.length }))
      onClose()
    },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  return (
    <Modal open title={t('proveedores.externalizar_tareas')} subtitle={paquete.title} onClose={onClose} width={560}>
      <div className="u-stack-8">
        <p className="u-text2-sm">{t('proveedores.externalizar_tareas_d')}</p>
        {isLoading ? <Spinner /> : libres.length === 0 ? <p className="u-text3-xs">{t('proveedores.sin_tareas_abiertas')}</p> : (
          <div className="prv-tareas-seleccion">
            {libres.map(x => (
              <Checkbox key={x.id} checked={elegidas.includes(x.id)}
                onChange={v => setElegidas(e => v ? [...e, x.id] : e.filter(i => i !== x.id))}
                label={`${x.code} — ${x.title}`}
                ayuda={x.assignee?.full_name ? t('proveedores.quita_asignado', { nombre: x.assignee.full_name }) : x.supplier_name || undefined} />
            ))}
          </div>
        )}
        <div className="u-actions-8">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => enviar.mutate()} disabled={!elegidas.length || enviar.isPending} loading={enviar.isPending}>{t('proveedores.externalizar_n', { n: elegidas.length })}</Button>
        </div>
      </div>
    </Modal>
  )
}

/** Alta de informe de avance (paquete) o periódico (servicio). */
export function FormularioDeInforme({ sub, paqueteId, servicioId, onClose }: { sub: Subcontratista; paqueteId?: string | null; servicioId?: string | null; onClose: () => void }) {
  const t = useT()
  const toast = useToast()
  const qc = useQueryClient()
  const campos = useErroresDeCampo()
  const [f, setF] = useState({ period_start: '', period_end: '', progress_pct: '', summary: '', risks: '', report_type: (servicioId ? 'periodic' : 'progress') as TipoDeInforme, enlace: '' })
  const [ficheros, setFicheros] = useState<File[]>([])
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => { campos.limpiar(k); setF(x => ({ ...x, [k]: e.target.value })) }
  const guardar = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: async () => {
      const d: InformeIn = {
        work_package_id: paqueteId || null, service_id: servicioId || null, report_type: f.report_type, period_start: f.period_start || null,
        period_end: f.period_end || null, progress_pct: numeroONull(f.progress_pct), summary: f.summary.trim(), risks: textoONull(f.risks),
        attachments: f.enlace.trim() ? [{ url: f.enlace.trim() }] : null,
      }
      const r = await proveedoresApi.crearInforme(sub.id, d)
      for (const fichero of ficheros) await proveedoresApi.adjuntarAlInforme(r.data.id, fichero)
      return r
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['suppliers'] }); toast.success(t('proveedores.informe_registrado')); onClose() },
    onError: (e: unknown) => { qc.invalidateQueries({ queryKey: ['suppliers'] }); if (!campos.recoger(e)) toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) },
  })
  return (
    <Modal open title={t('proveedores.nuevo_informe')} onClose={onClose} width={560}>
      <div className="u-stack-8">
        {servicioId && (
          <Select label={t('proveedores.tipo_de_informe')} value={f.report_type} placeholder={false} onChange={set('report_type')}
            options={TIPOS_DE_INFORME_DE_SERVICIO.map(x => ({ value: x, label: etiquetaDe(t, 'informe_tipo_', x) }))} />
        )}
        <div className="prv-rejilla--3 prv-rejilla">
          <Input label={t('proveedores.desde')} type="date" value={f.period_start} onChange={set('period_start')} error={campos.de('period_start')} />
          <Input label={t('proveedores.hasta')} type="date" value={f.period_end} onChange={set('period_end')} error={campos.de('period_end')} />
          {paqueteId && <Input label={t('proveedores.avance_pct')} type="number" min={0} max={100} value={f.progress_pct} onChange={set('progress_pct')} error={campos.de('progress_pct')} />}
        </div>
        <div className="ui-field">
          <Textarea label={<>{t('proveedores.resumen')}*</>} id="prv-informe-resumen" value={f.summary} onChange={set('summary')} />
          {campos.de('summary') && <div className="u-field-error" role="alert">{campos.de('summary')}</div>}
        </div>
        <Textarea label={t('proveedores.riesgos')} id="prv-informe-riesgos" value={f.risks} onChange={set('risks')} />
        <Input label={t('proveedores.evidencia_enlace')} value={f.enlace} onChange={set('enlace')} placeholder="https://" error={campos.de('attachments')} />
        <div className="ui-field">
          <label htmlFor="prv-informe-ficheros" className="uiinde-estiloetiqueta">{t('proveedores.evidencias')}</label>
          <input id="prv-informe-ficheros" type="file" multiple className="ds-input" onChange={e => setFicheros(Array.from(e.target.files || []))} />
        </div>
        <div className="u-actions-8">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => guardar.mutate()} disabled={!f.summary.trim() || guardar.isPending} loading={guardar.isPending}>{t('proveedores.registrar_informe')}</Button>
        </div>
      </div>
    </Modal>
  )
}

/**
 * Evidencias de un informe: enlaces y ficheros (enlace firmado y auditado al abrir).
 * `abrir` decide la ruta: la ficha (`/suppliers/...`) o el portal (`/supplier-portal/...`).
 */
export function AdjuntosDeInforme({ informe, abrir }: { informe: InformeDeProveedor; abrir: (rid: string, docId: string) => Promise<{ data: { url: string } }> }) {
  const t = useT()
  const toast = useToast()
  const adjuntos: AdjuntoDeInforme[] = informe.attachments || []
  if (!adjuntos.length) return null
  const abrirFichero = async (a: AdjuntoDeInforme) => {
    try {
      const r = await abrir(informe.id, a.document_id || '')
      window.open(r.data.url, '_blank', 'noopener,noreferrer')
    } catch (e) {
      toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
    }
  }
  return (
    <div className="prv-insignias">
      {adjuntos.map((a, i) => a.kind === 'link' ? (
        <a key={i} href={sanitizeUrl(a.url)} target="_blank" rel="noopener noreferrer" className="u-text2-sm"><Link2 size={12} aria-hidden /> {a.name}</a>
      ) : (
        <Button key={i} size="xs" variant="ghost" icon={<Paperclip size={12} />} onClick={() => abrirFichero(a)} title={t('proveedores.abrir_evidencia')}>{a.name}</Button>
      ))}
    </div>
  )
}

/** Informes del proveedor (de paquetes o de servicios) con su revisión. */
export function InformesDeProveedor({ sub, de, nombres }: { sub: Subcontratista; de: 'work_package' | 'service'; nombres: Record<string, string> }) {
  const t = useT()
  const toast = useToast()
  const qc = useQueryClient()
  const { gestionar } = usePermisosDeProveedores()
  const { data: informes = [] } = useQuery({
    queryKey: ['suppliers', 'reports', sub.id],
    queryFn: () => proveedoresApi.informes(sub.id).then(r => r.data),
  })
  const revisar = useMutation({
    mutationFn: ({ id, notas }: { id: string; notas: string | null }) => proveedoresApi.revisarInforme(id, notas),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['suppliers'] }); toast.success(t('proveedores.informe_revisado')) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const lista = informes.filter(r => (de === 'service' ? !!r.service_id : !!r.work_package_id))
  if (!lista.length) return null
  return (
    <div className="u-stack-8 prv-mt">
      <div className="prv-bloque-titulo"><FileBarChart size={16} aria-hidden />{t('proveedores.informes')}</div>
      {lista.map(r => (
        <Card key={r.id} className="sub-item">
          <div className="prv-cabecera-item">
            <div className="u-min0">
              <div className="u-row-center-8">
                <strong>{nombres[(de === 'service' ? r.service_id : r.work_package_id) || ''] || '—'}</strong>
                <StatusBadge kind={r.status === 'reviewed' ? 'success' : 'warning'} caps={false}>{etiquetaDe(t, 'informe_estado_', r.status)}</StatusBadge>
                <StatusBadge kind="neutral" caps={false}>{etiquetaDe(t, 'informe_tipo_', r.report_type || 'progress')}</StatusBadge>
                {r.submitted_via === 'portal' && <StatusBadge kind="info" caps={false}><Globe size={11} aria-hidden /> {t('proveedores.desde_el_portal')}</StatusBadge>}
                {r.progress_pct != null && <span className="u-text2-sm">{fmtNumber(r.progress_pct, 0)}%</span>}
              </div>
              <div className="prv-sub">{(r.period_start || r.period_end) ? `${fmtDate(r.period_start)} – ${fmtDate(r.period_end)} · ` : ''}{r.summary}</div>
              {r.risks && <div className="u-text3-xs">{t('proveedores.riesgos')}: {r.risks}</div>}
              {r.review_notes && <div className="u-text3-xs">{t('proveedores.notas_revision')}: {r.review_notes}</div>}
              <AdjuntosDeInforme informe={r} abrir={proveedoresApi.abrirAdjunto} />
            </div>
            {gestionar && r.status === 'submitted' && (
              <Button size="xs" variant="secondary" icon={<ClipboardCheck size={13} />}
                onClick={async () => {
                  const notas = await pedirTexto({ message: t('proveedores.revisar_informe'), label: t('proveedores.notas_revision'), multiline: true })
                  if (notas !== null) revisar.mutate({ id: r.id, notas })
                }}>{t('proveedores.revisar')}</Button>
            )}
          </div>
        </Card>
      ))}
    </div>
  )
}

const ICONO_DEL_PASO = { start: <Play size={13} />, deliver: <Send size={13} />, accept: <CheckCircle2 size={13} />, reject: <X size={13} />, cancel: <X size={13} /> }

export default function PestanaPaquetes({ sub }: { sub: Subcontratista }) {
  const t = useT()
  const toast = useToast()
  const qc = useQueryClient()
  const fmtMoneda = useFormatoMoneda()
  const { gestionar } = usePermisosDeProveedores()
  const [editando, setEditando] = useState<PaqueteDeTrabajo | null | 'nuevo'>(null)
  const [tareas, setTareas] = useState<PaqueteDeTrabajo | null>(null)
  const [informe, setInforme] = useState<PaqueteDeTrabajo | null>(null)
  const { data: paquetes = [], isLoading } = useQuery({
    queryKey: ['suppliers', 'work-packages', sub.id],
    queryFn: () => proveedoresApi.paquetes(sub.id).then(r => r.data),
  })
  const alFallar = (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  const refrescar = () => { qc.invalidateQueries({ queryKey: ['suppliers'] }); qc.invalidateQueries({ queryKey: ['tasks'] }) }
  const paso = useMutation({
    mutationFn: ({ id, p }: { id: string; p: 'start' | 'deliver' | 'accept' | 'cancel' }) => proveedoresApi.pasoDePaquete(id, p),
    onSuccess: (_r, v) => { refrescar(); toast.success(t(`proveedores.paquete_paso_${v.p}`)) },
    onError: alFallar,
  })
  const rechazar = useMutation({
    mutationFn: ({ id, motivo }: { id: string; motivo: string }) => proveedoresApi.rechazarPaquete(id, motivo),
    onSuccess: () => { refrescar(); toast.success(t('proveedores.paquete_paso_reject')) },
    onError: alFallar,
  })
  const ejecutar = async (w: PaqueteDeTrabajo, p: 'start' | 'deliver' | 'accept' | 'reject' | 'cancel') => {
    if (p === 'reject') {
      const motivo = await pedirTexto({ message: t('proveedores.rechazar_paquete', { titulo: w.title }), label: t('proveedores.motivo'), required: true, multiline: true, danger: true })
      if (motivo) rechazar.mutate({ id: w.id, motivo })
      return
    }
    if (p === 'cancel') {
      openConfirmGlobal({ message: t('proveedores.cancelar_paquete_confirmar', { titulo: w.title }), danger: true, onConfirm: () => paso.mutate({ id: w.id, p }) })
      return
    }
    paso.mutate({ id: w.id, p })
  }
  const nombres = Object.fromEntries(paquetes.map(w => [w.id, w.title]))

  if (isLoading) return <Spinner />
  return (
    <div>
      {gestionar && (
        <div className="sub-toolbar-end">
          <Button size="sm" icon={<Plus size={14} />} onClick={() => setEditando('nuevo')}>{t('proveedores.nuevo_paquete')}</Button>
        </div>
      )}
      {paquetes.length === 0 ? (
        <EmptyState icon={<Briefcase size={28} />} title={t('proveedores.sin_paquetes')} description={t('proveedores.sin_paquetes_d')} />
      ) : (
        <div className="u-stack-8">
          {paquetes.map(w => (
            <Card key={w.id} className="sub-item">
              <div className="prv-cabecera-item">
                <div className="u-min0">
                  <div className="u-row-center-8">
                    <span className="prv-titulo-item">{w.title}</span>
                    <StatusBadge kind={TONO_PAQUETE[w.status] || 'neutral'} caps={false}>{etiquetaDe(t, 'paquete_estado_', w.status)}</StatusBadge>
                    <StatusBadge kind="neutral" caps={false}>{etiquetaDe(t, 'alcance_', w.scope_type)}</StatusBadge>
                  </div>
                  <div className="prv-sub">
                    {[
                      w.project_name,
                      (w.planned_start || w.planned_end) && `${fmtDate(w.planned_start)} – ${fmtDate(w.planned_end)}`,
                      w.price != null && fmtMoneda(w.price, { moneda: w.currency }),
                      w.progress_pct != null && t('proveedores.avance_n', { pct: fmtNumber(w.progress_pct, 0) }),
                      w.task_count != null && t('proveedores.n_tareas', { n: w.task_count }),
                      w.accepted_at && t('proveedores.aceptado_el', { fecha: fmtDate(w.accepted_at) }),
                      w.rejections > 0 && t('proveedores.n_rechazos', { n: w.rejections }),
                    ].filter(Boolean).join(' · ')}
                  </div>
                  {w.status === 'rejected' && w.rejection_reason && <div className="prv-aviso prv-aviso--peligro prv-mt">{w.rejection_reason}</div>}
                </div>
                {gestionar && (
                  <div className="prv-barra-acciones">
                    {pasosDePaquete(w.status).map(p => (
                      <Button key={p} size="xs" variant={p === 'accept' ? 'primary' : p === 'reject' || p === 'cancel' ? 'ghost' : 'secondary'}
                        className={p === 'reject' || p === 'cancel' ? 'sub-borrar' : undefined} icon={ICONO_DEL_PASO[p]} onClick={() => ejecutar(w, p)}>
                        {t(`proveedores.paso_${p}`)}
                      </Button>
                    ))}
                    {w.status !== 'accepted' && w.status !== 'cancelled' && (
                      <Button size="xs" variant="secondary" icon={<ListPlus size={13} />} onClick={() => setTareas(w)}>{t('proveedores.externalizar_tareas')}</Button>
                    )}
                    <Button size="xs" variant="secondary" icon={<FileBarChart size={13} />} onClick={() => setInforme(w)}>{t('proveedores.informe')}</Button>
                    <Button size="xs" variant="secondary" icon={<Pencil size={13} />} onClick={() => setEditando(w)}>{t('subcontractors.edit')}</Button>
                  </div>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}
      <InformesDeProveedor sub={sub} de="work_package" nombres={nombres} />
      {editando && <FormularioDePaquete sub={sub} paquete={editando === 'nuevo' ? null : editando} onClose={() => setEditando(null)} />}
      {tareas && <ExternalizarTareas paquete={tareas} onClose={() => setTareas(null)} />}
      {informe && <FormularioDeInforme sub={sub} paqueteId={informe.id} onClose={() => setInforme(null)} />}
    </div>
  )
}
