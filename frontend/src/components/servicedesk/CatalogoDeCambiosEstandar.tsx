/**
 * Sección «Cambios estándar» de Configuración (`/settings/sd-cambios-estandar`, 23-11-2026).
 *
 * Auditoría 2026-11-22 (A-SD19): un cambio solo es estándar si referencia un
 * modelo de este catálogo aprobado por el CAB, vigente (revisión periódica sin
 * vencer) y cuyo alcance cubre el cambio. Aquí se proponen, editan, aprueban,
 * suspenden, reactivan y dan de baja los modelos; cada acción queda en la
 * auditoría (`sd_standard_change_model`). Se ven el uso y la tasa de fallo: por
 * encima de `SD_STANDARD_CHANGE_MAX_FAILURE_PCT` el modelo se suspende solo.
 *
 * API: `/sd/standard-changes` (`sd.gestionar`). Aprobar exige ser del CAB o
 * administrador y no haber propuesto el modelo (lo comprueba el servidor).
 */
import { useState } from 'react'
import type { ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Pause, Pencil, Plus, RotateCcw, Trash2 } from 'lucide-react'
import { Button, Checkbox, EmptyState, IconButton, Input, Modal, Select, Spinner, StatusBadge, TablaSimple, Textarea } from '../ui'
import type { StatusBadgeKind } from '../ui/StatusBadge'
import { useToast } from '../../context/ToastContext'
import { confirmar } from '../../context/ConfirmContext'
import { useAppT } from '../../i18n/AppLangContext'
import { extractErr, fmtDateTime } from '../../utils/helpers'
import { cmdbApi } from '../../services/api'
import { cambiosEstandarApi } from '../../services/api/cambiosEstandar'
import type { EstadoDeModeloEstandar, ModeloDeCambioEstandar, ModeloDeCambioEstandarIn, RiesgoDeCambio } from '../../services/api/cambiosEstandar'
import './CatalogoDeCambiosEstandar.css'

const RIESGOS: RiesgoDeCambio[] = ['low', 'medium', 'high', 'critical']
/** `CIType` (app/models/service_desk/_enums.py). */
const TIPOS_DE_CI = ['application', 'server', 'database', 'network', 'service', 'module', 'integration',
  'virtual_machine', 'container', 'cloud', 'endpoint', 'storage', 'other'] as const
const TONO: Record<EstadoDeModeloEstandar, StatusBadgeKind> = {
  proposed: 'warning', approved: 'success', suspended: 'danger', retired: 'neutral',
}
const CLAVE_QUERY = ['sd-standard-changes', 'catalogo']

const VACIO: ModeloDeCambioEstandarIn = {
  name: '', description: '', procedure: '', rollback_plan: '', test_plan: '', max_risk: 'low',
  applies_to_ci_ids: [], applies_to_ci_types: [], applies_to_service_ids: [], review_interval_days: null,
}

/** Botón de icono de la fila, con su texto accesible. */
function Accion({ icono, texto, onClick }: { icono: ReactNode; texto: string; onClick: () => void }) {
  return <IconButton ariaLabel={texto} title={texto} onClick={onClick}>{icono}</IconButton>
}

function alternar(lista: string[] | undefined, valor: string, marcado: boolean): string[] {
  const base = (lista ?? []).filter(v => v !== valor)
  return marcado ? [...base, valor] : base
}

function FormularioDeModelo({ inicial, onClose }: { inicial: ModeloDeCambioEstandar | null; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [form, setForm] = useState<ModeloDeCambioEstandarIn>(inicial ? {
    name: inicial.name, description: inicial.description ?? '', procedure: inicial.procedure,
    rollback_plan: inicial.rollback_plan ?? '', test_plan: inicial.test_plan ?? '', max_risk: inicial.max_risk,
    applies_to_ci_ids: inicial.applies_to_ci_ids, applies_to_ci_types: inicial.applies_to_ci_types,
    applies_to_service_ids: inicial.applies_to_service_ids, review_interval_days: inicial.review_interval_days,
  } : VACIO)
  const [buscar, setBuscar] = useState('')
  const { data: cis = [] } = useQuery({
    queryKey: ['sd-cmdb', 'cambios-estandar'],
    queryFn: () => cmdbApi.sdList({ page_size: 500 }).then(r => r.data),
  })
  const servicios = cis.filter(c => c.ci_type === 'service')
  const otros = cis.filter(c => c.ci_type !== 'service' && (!buscar || `${c.code} ${c.name}`.toLowerCase().includes(buscar.toLowerCase()))).slice(0, 50)

  const { mutate, isPending } = useMutation({
    mutationFn: () => (inicial ? cambiosEstandarApi.editar(inicial.id, form) : cambiosEstandarApi.proponer(form)),
    onSuccess: (m) => {
      toast.success(t(m.status === 'proposed' && inicial?.status === 'approved' ? 'cambios_estandar.vuelve_al_cab' : 'cambios_estandar.guardado'))
      qc.invalidateQueries({ queryKey: ['sd-standard-changes'] })
      onClose()
    },
    onError: (e) => toast.error(extractErr(e, t('cambios_estandar.error'))),
  })
  const set = <K extends keyof ModeloDeCambioEstandarIn>(k: K, v: ModeloDeCambioEstandarIn[K]) => setForm(f => ({ ...f, [k]: v }))

  return (
    <Modal open title={t(inicial ? 'cambios_estandar.editar' : 'cambios_estandar.proponer')} onClose={onClose} size="lg">
      <div className="u-stack-12">
        {inicial?.status === 'approved' && <div className="u-text3-xs">{t('cambios_estandar.aviso_edicion')}</div>}
        <Input label={t('cambios_estandar.nombre')} required value={form.name} onChange={e => set('name', e.target.value)} maxLength={200} />
        <Textarea label={t('cambios_estandar.descripcion')} value={form.description ?? ''} onChange={e => set('description', e.target.value)} rows={2} />
        <Textarea label={t('cambios_estandar.procedimiento')} hint={t('cambios_estandar.procedimiento_ayuda')} required value={form.procedure} onChange={e => set('procedure', e.target.value)} rows={5} />
        <div className="cce-dos">
          <Textarea label={t('cambios_estandar.vuelta_atras')} value={form.rollback_plan ?? ''} onChange={e => set('rollback_plan', e.target.value)} rows={3} />
          <Textarea label={t('cambios_estandar.prueba')} value={form.test_plan ?? ''} onChange={e => set('test_plan', e.target.value)} rows={3} />
        </div>
        <div className="cce-dos">
          <Select label={t('cambios_estandar.riesgo_maximo')} placeholder={false} value={form.max_risk} onChange={e => set('max_risk', e.target.value as RiesgoDeCambio)}>
            {RIESGOS.map(r => <option key={r} value={r}>{t(`changemanagement.risk_${r}`)}</option>)}
          </Select>
          <Input label={t('cambios_estandar.revision_dias')} hint={t('cambios_estandar.revision_dias_ayuda')} type="number" min={1} max={3650}
            value={form.review_interval_days ?? ''} onChange={e => set('review_interval_days', e.target.value ? Number(e.target.value) : null)} />
        </div>
        {/* Bloque mixto (casillas + buscador): grupo con título, no fieldset (regla del kit). */}
        <section className="cce-alcance" role="group" aria-labelledby="cce-alcance-titulo">
          <div id="cce-alcance-titulo" className="cce-subtitulo">{t('cambios_estandar.alcance')}</div>
          <div className="u-text3-xs">{t('cambios_estandar.alcance_ayuda')}</div>
          <div className="cce-casillas">
            {TIPOS_DE_CI.map(tipo => (
              <Checkbox key={tipo} label={tipo} checked={(form.applies_to_ci_types ?? []).includes(tipo)}
                onChange={m => set('applies_to_ci_types', alternar(form.applies_to_ci_types, tipo, m))} />
            ))}
          </div>
          {servicios.length > 0 && (
            <>
              <div className="cce-subtitulo">{t('cambios_estandar.servicios')}</div>
              <div className="cce-casillas">
                {servicios.map(c => (
                  <Checkbox key={c.id} label={`${c.code} · ${c.name}`} checked={(form.applies_to_service_ids ?? []).includes(c.id)}
                    onChange={m => set('applies_to_service_ids', alternar(form.applies_to_service_ids, c.id, m))} />
                ))}
              </div>
            </>
          )}
          <div className="cce-subtitulo">{t('cambios_estandar.cis')}</div>
          <Input aria-label={t('cambios_estandar.buscar_ci')} placeholder={t('cambios_estandar.buscar_ci')} value={buscar} onChange={e => setBuscar(e.target.value)} />
          <div className="cce-casillas cce-casillas--lista">
            {otros.map(c => (
              <Checkbox key={c.id} label={`${c.code} · ${c.name}`} checked={(form.applies_to_ci_ids ?? []).includes(c.id)}
                onChange={m => set('applies_to_ci_ids', alternar(form.applies_to_ci_ids, c.id, m))} />
            ))}
          </div>
        </section>
        <div className="u-actions-8">
          <Button variant="secondary" onClick={onClose}>{t('cambios_estandar.cancelar')}</Button>
          <Button onClick={() => mutate()} loading={isPending} disabled={isPending || form.name.trim().length < 3 || form.procedure.trim().length < 3}>
            {t(inicial ? 'cambios_estandar.guardar' : 'cambios_estandar.proponer')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export default function CatalogoDeCambiosEstandar() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [editando, setEditando] = useState<ModeloDeCambioEstandar | null | 'nuevo'>(null)
  const [suspendiendo, setSuspendiendo] = useState<ModeloDeCambioEstandar | null>(null)
  const [motivo, setMotivo] = useState('')
  const [verBajas, setVerBajas] = useState(false)

  const { data: modelos = [], isLoading } = useQuery({
    queryKey: [...CLAVE_QUERY, verBajas],
    queryFn: () => cambiosEstandarApi.listar({ incluir_bajas: verBajas }),
  })
  const accion = useMutation({
    mutationFn: (fn: () => Promise<ModeloDeCambioEstandar>) => fn(),
    onSuccess: () => {
      toast.success(t('cambios_estandar.guardado'))
      qc.invalidateQueries({ queryKey: ['sd-standard-changes'] })
      setSuspendiendo(null); setMotivo('')
    },
    onError: (e) => toast.error(extractErr(e, t('cambios_estandar.error'))),
  })

  if (isLoading) return <Spinner />
  return (
    <div className="u-stack-16">
      <div className="cce-barra">
        <Checkbox label={t('cambios_estandar.ver_bajas')} checked={verBajas} onChange={setVerBajas} />
        <Button icon={<Plus size={14} />} onClick={() => setEditando('nuevo')}>{t('cambios_estandar.proponer')}</Button>
      </div>
      {modelos.length === 0 ? (
        <EmptyState title={t('cambios_estandar.vacio')} description={t('cambios_estandar.vacio_d')} />
      ) : (
        <TablaSimple>
          <thead>
            <tr>
              <th>{t('cambios_estandar.nombre')}</th>
              <th>{t('cambios_estandar.estado')}</th>
              <th>{t('cambios_estandar.riesgo_maximo')}</th>
              <th>{t('cambios_estandar.aprobado_por')}</th>
              <th>{t('cambios_estandar.proxima_revision')}</th>
              <th>{t('cambios_estandar.usos')}</th>
              <th>{t('cambios_estandar.tasa_fallo')}</th>
              <th>{t('cambios_estandar.acciones')}</th>
            </tr>
          </thead>
          <tbody>
            {modelos.map(m => (
              <tr key={m.id}>
                <td>
                  <div>{m.name}</div>
                  {m.suspended_reason && <div className="u-text3-xs">{m.suspended_reason}</div>}
                </td>
                <td>
                  <StatusBadge kind={TONO[m.status]}>{t(`cambios_estandar.estado_${m.status}`)}</StatusBadge>
                  {m.caducado && <div className="u-text3-xs">{t('cambios_estandar.caducado')}</div>}
                </td>
                <td>{t(`changemanagement.risk_${m.max_risk}`)}</td>
                <td>{m.approver ? `${m.approver} · ${fmtDateTime(m.approved_at)}` : '—'}</td>
                <td>{m.next_review_at ? fmtDateTime(m.next_review_at) : '—'}</td>
                <td>{m.use_count}</td>
                <td>{m.failure_rate_pct == null ? '—' : `${m.failure_rate_pct} % (${m.failure_count}/${m.success_count + m.failure_count})`}</td>
                <td className="cce-acciones">
                  {m.status !== 'retired' && (
                    <Accion icono={<Pencil size={14} />} texto={t('cambios_estandar.editar')} onClick={() => setEditando(m)} />
                  )}
                  {m.status === 'proposed' && (
                    <Accion icono={<CheckCircle2 size={14} />} texto={t('cambios_estandar.aprobar')}
                      onClick={() => accion.mutate(() => cambiosEstandarApi.aprobar(m.id))} />
                  )}
                  {m.status === 'approved' && (
                    <Accion icono={<Pause size={14} />} texto={t('cambios_estandar.suspender')} onClick={() => setSuspendiendo(m)} />
                  )}
                  {m.status === 'suspended' && (
                    <Accion icono={<RotateCcw size={14} />} texto={t('cambios_estandar.reactivar')}
                      onClick={() => accion.mutate(() => cambiosEstandarApi.reactivar(m.id))} />
                  )}
                  {m.status !== 'retired' && (
                    <Accion icono={<Trash2 size={14} />} texto={t('cambios_estandar.retirar')} onClick={async () => {
                      // 23-11-2026: confirmación única (ConfirmContext); antes `ui/Confirm`.
                      if (await confirmar({ title: t('cambios_estandar.retirar'), message: t('cambios_estandar.retirar_d'), danger: true }))
                        accion.mutate(() => cambiosEstandarApi.retirar(m.id))
                    }} />
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </TablaSimple>
      )}

      {editando && <FormularioDeModelo inicial={editando === 'nuevo' ? null : editando} onClose={() => setEditando(null)} />}

      {suspendiendo && (
        <Modal open title={t('cambios_estandar.suspender')} onClose={() => setSuspendiendo(null)}>
          <div className="u-stack-12">
            <div>{t('cambios_estandar.suspender_d')}</div>
            <Textarea label={t('cambios_estandar.motivo')} required value={motivo} onChange={e => setMotivo(e.target.value)} rows={3} />
            <div className="u-actions-8">
              <Button variant="secondary" onClick={() => setSuspendiendo(null)}>{t('cambios_estandar.cancelar')}</Button>
              <Button variant="danger" loading={accion.isPending} disabled={motivo.trim().length < 5}
                onClick={() => accion.mutate(() => cambiosEstandarApi.suspender(suspendiendo.id, motivo.trim()))}>
                {t('cambios_estandar.suspender')}
              </Button>
            </div>
          </div>
        </Modal>
      )}

    </div>
  )
}
