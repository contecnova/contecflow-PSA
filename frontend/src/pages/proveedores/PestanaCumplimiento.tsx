/**
 * Ficha del proveedor → Cumplimiento (GRC de terceros, 19-11-2026).
 *
 * Documentos con caducidad (DPA art. 28, NDA, ISO 27001, SOC 2, ENS, seguros…),
 * evaluación de riesgo (criterios 1-5 → nivel y próxima revisión), registro de
 * accesos con revocación, y ciclo de vida: suspender (bloquea trabajo nuevo y
 * quita el acceso a sus personas), reactivar y dar de baja (termina contratos y
 * servicios, cancela paquetes, revoca accesos y da de baja a sus personas).
 * Todo deja auditoría en el backend; los documentos caducados y los accesos
 * revocados entran en la política de retención.
 *
 * Migración 191: quién del proveedor es contacto de su portal (`ContactosDelPortal`).
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Ban, FileCheck2, KeyRound, Pencil, PlayCircle, Plus, ShieldAlert, Trash2, UserX } from 'lucide-react'
import { Button, Card, Checkbox, IconButton, Input, Modal, Select, Spinner, TablaSimple, useErroresDeCampo, Textarea } from '../../components/ui'
import StatusBadge from '../../components/ui/StatusBadge'
import { confirmar, pedirTexto } from '../../context/ConfirmContext'
import { useToast } from '../../context/ToastContext'
import { enterpriseSubsApi } from '../../services/api'
import { proveedoresApi } from '../../services/api/proveedores'
import type { AccesoIn, CriterioDeRiesgo, DocumentoDeProveedor, DocumentoIn, NivelDeAcceso, TipoDeDocumentoProveedor } from '../../services/api/tipos-proveedores'
import type { Subcontratista } from '../../services/api/tipos-alm'
import { useFormatoMoneda } from '../../hooks/useFormatoMoneda'
import { extractErr, fmtDate, fmtNumber } from '../../utils/helpers'
import { sanitizeUrl } from '../../utils/security'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { CRITERIOS, NIVELES_DE_ACCESO, TIPOS_DE_DOCUMENTO, TONO_CUMPLIMIENTO, TONO_DOCUMENTO, TONO_RIESGO, numeroONull, texto, textoONull } from './logica'
import { etiquetaDe, usePermisosDeProveedores, useT } from './comunes'
import ContactosDelPortal from './ContactosDelPortal'

function FormularioDeDocumento({ subId, doc, onClose }: { subId: string; doc: DocumentoDeProveedor | null; onClose: () => void }) {
  const t = useT()
  const toast = useToast()
  const qc = useQueryClient()
  const campos = useErroresDeCampo()
  const [f, setF] = useState({
    doc_type: (doc?.doc_type || 'nda') as TipoDeDocumentoProveedor, reference: texto(doc?.reference), issuer: texto(doc?.issuer),
    issued_at: texto(doc?.issued_at), expires_at: texto(doc?.expires_at), coverage_amount: texto(doc?.coverage_amount),
    document_url: texto(doc?.document_url), notes: texto(doc?.notes), verified: !!doc?.verified_at,
  })
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => { campos.limpiar(k); setF(x => ({ ...x, [k]: e.target.value })) }
  const esSeguro = f.doc_type === 'insurance_liability' || f.doc_type === 'insurance_cyber'
  const guardar = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: () => {
      const d: DocumentoIn = {
        doc_type: f.doc_type, reference: textoONull(f.reference), issuer: textoONull(f.issuer), issued_at: f.issued_at || null,
        expires_at: f.expires_at || null, coverage_amount: esSeguro ? numeroONull(f.coverage_amount) : null,
        document_url: textoONull(f.document_url), notes: textoONull(f.notes), verified: f.verified,
      }
      return doc ? proveedoresApi.editarDocumento(doc.id, d) : proveedoresApi.crearDocumento(subId, d)
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['suppliers'] }); toast.success(t('proveedores.documento_guardado')); onClose() },
    onError: (e: unknown) => { if (!campos.recoger(e)) toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) },
  })
  return (
    <Modal open title={doc ? t('proveedores.editar_documento') : t('proveedores.nuevo_documento')} onClose={onClose} width={600}>
      <div className="u-stack-8">
        <div className="prv-rejilla">
          <Select className="prv-completo" label={t('proveedores.tipo_de_documento')} value={f.doc_type} placeholder={false} onChange={set('doc_type')} error={campos.de('doc_type')}
            options={TIPOS_DE_DOCUMENTO.map(d => ({ value: d, label: etiquetaDe(t, 'doc_', d) }))} />
          <Input label={t('proveedores.referencia')} value={f.reference} onChange={set('reference')} error={campos.de('reference')} />
          <Input label={t('proveedores.emisor')} value={f.issuer} onChange={set('issuer')} error={campos.de('issuer')} />
          <Input label={t('proveedores.emitido')} type="date" value={f.issued_at} onChange={set('issued_at')} error={campos.de('issued_at')} />
          <Input label={t('proveedores.caduca')} type="date" value={f.expires_at} onChange={set('expires_at')} error={campos.de('expires_at')} />
          {esSeguro && <Input label={t('proveedores.cobertura')} type="number" min={0} step="0.01" value={f.coverage_amount} onChange={set('coverage_amount')} error={campos.de('coverage_amount')} />}
          <Input label={t('proveedores.documento_url')} value={f.document_url} onChange={set('document_url')} error={campos.de('document_url')} />
          <Input className="prv-completo" label={t('subcontractors.notes')} value={f.notes} onChange={set('notes')} error={campos.de('notes')} />
        </div>
        <Checkbox checked={f.verified} onChange={v => setF(x => ({ ...x, verified: v }))} label={t('proveedores.verificado')} ayuda={t('proveedores.verificado_d')} />
        <div className="u-actions-8">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => guardar.mutate()} loading={guardar.isPending} disabled={guardar.isPending}>{t('common.save')}</Button>
        </div>
      </div>
    </Modal>
  )
}

function FormularioDeEvaluacion({ subId, onClose }: { subId: string; onClose: () => void }) {
  const t = useT()
  const toast = useToast()
  const qc = useQueryClient()
  const [criterios, setCriterios] = useState<Record<CriterioDeRiesgo, string>>({ data_access: '3', criticality: '3', dependency: '3', financial: '3', location: '3', security: '3' })
  const [diligencia, setDiligencia] = useState(false)
  const [notas, setNotas] = useState('')
  const guardar = useMutation({
    mutationFn: () => proveedoresApi.crearEvaluacion(subId, {
      criteria: Object.fromEntries(CRITERIOS.map(c => [c, Number(criterios[c])])) as Record<CriterioDeRiesgo, number>,
      due_diligence_done: diligencia, notes: textoONull(notas),
    }),
    onSuccess: r => {
      qc.invalidateQueries({ queryKey: ['suppliers'] })
      qc.invalidateQueries({ queryKey: ['subcontractors'] })
      toast.success(t('proveedores.evaluacion_guardada', { nivel: etiquetaDe(t, 'riesgo_', r.data.level) }))
      onClose()
    },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const opciones = [1, 2, 3, 4, 5].map(n => ({ value: String(n), label: t(`proveedores.puntos_${n}`) }))
  return (
    <Modal open title={t('proveedores.nueva_evaluacion')} onClose={onClose} width={600}>
      <div className="u-stack-8">
        <p className="u-text2-sm">{t('proveedores.nueva_evaluacion_d')}</p>
        <div className="prv-rejilla">
          {CRITERIOS.map(c => (
            <Select key={c} label={etiquetaDe(t, 'criterio_', c)} hint={t(`proveedores.criterio_${c}_d`)} value={criterios[c]} placeholder={false}
              onChange={e => setCriterios(x => ({ ...x, [c]: e.target.value }))} options={opciones} />
          ))}
        </div>
        <Checkbox checked={diligencia} onChange={setDiligencia} label={t('proveedores.due_diligence')} />
        <div className="ui-field">
          <label htmlFor="prv-evaluacion-notas" className="uiinde-estiloetiqueta">{t('subcontractors.notes')}</label>
          <Textarea id="prv-evaluacion-notas" value={notas} onChange={e => setNotas(e.target.value)} inputClassName="prv-textarea" />
        </div>
        <div className="u-actions-8">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => guardar.mutate()} loading={guardar.isPending} disabled={guardar.isPending}>{t('common.save')}</Button>
        </div>
      </div>
    </Modal>
  )
}

function FormularioDeAcceso({ subId, onClose }: { subId: string; onClose: () => void }) {
  const t = useT()
  const toast = useToast()
  const qc = useQueryClient()
  const campos = useErroresDeCampo()
  const { data: personas = [] } = useQuery({ queryKey: ['sub-workers', subId], queryFn: () => enterpriseSubsApi.workers(subId).then(r => r.data) })
  const [f, setF] = useState({ worker_id: '', system: '', data_category: '', access_level: 'read' as NivelDeAcceso, personal_data: false, justification: '', granted_at: '', expires_at: '' })
  const set = (k: 'worker_id' | 'system' | 'data_category' | 'access_level' | 'justification' | 'granted_at' | 'expires_at') =>
    (e: { target: { value: string } }) => { campos.limpiar(k); setF(x => ({ ...x, [k]: e.target.value })) }
  const guardar = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: () => {
      const d: AccesoIn = {
        worker_id: f.worker_id || null, system: f.system.trim(), data_category: textoONull(f.data_category), access_level: f.access_level,
        personal_data: f.personal_data, justification: textoONull(f.justification), granted_at: f.granted_at || null, expires_at: f.expires_at || null,
      }
      return proveedoresApi.crearAcceso(subId, d)
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['suppliers'] }); toast.success(t('proveedores.acceso_registrado')); onClose() },
    onError: (e: unknown) => { if (!campos.recoger(e)) toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) },
  })
  return (
    <Modal open title={t('proveedores.nuevo_acceso')} onClose={onClose} width={600}>
      <div className="u-stack-8">
        <div className="prv-rejilla">
          <Input label={t('proveedores.sistema')} required value={f.system} onChange={set('system')} error={campos.de('system')} />
          <Input label={t('proveedores.categoria_de_datos')} value={f.data_category} onChange={set('data_category')} error={campos.de('data_category')} />
          <Select label={t('proveedores.nivel_de_acceso')} value={f.access_level} placeholder={false} onChange={set('access_level')}
            options={NIVELES_DE_ACCESO.map(n => ({ value: n, label: etiquetaDe(t, 'acceso_', n) }))} />
          <Select label={t('externos.persona')} value={f.worker_id} onChange={set('worker_id')} placeholder={t('proveedores.todo_el_proveedor')}
            options={personas.filter(p => p.is_active).map(p => ({ value: p.id, label: p.name }))} />
          <Input label={t('proveedores.concedido')} type="date" value={f.granted_at} onChange={set('granted_at')} error={campos.de('granted_at')} />
          <Input label={t('proveedores.caduca')} type="date" value={f.expires_at} onChange={set('expires_at')} error={campos.de('expires_at')} hint={t('proveedores.caducidad_acceso_d')} />
          <Input className="prv-completo" label={t('proveedores.justificacion')} value={f.justification} onChange={set('justification')} error={campos.de('justification')} />
        </div>
        <Checkbox checked={f.personal_data} onChange={v => setF(x => ({ ...x, personal_data: v }))} label={t('proveedores.datos_personales')} />
        <div className="u-actions-8">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => guardar.mutate()} loading={guardar.isPending} disabled={!f.system.trim() || guardar.isPending}>{t('common.save')}</Button>
        </div>
      </div>
    </Modal>
  )
}

export default function PestanaCumplimiento({ sub, onCambio }: { sub: Subcontratista; onCambio?: (s: Subcontratista) => void }) {
  const t = useT()
  const toast = useToast()
  const qc = useQueryClient()
  const fmtMoneda = useFormatoMoneda()
  const { gestionar } = usePermisosDeProveedores()
  const [documento, setDocumento] = useState<DocumentoDeProveedor | null | 'nuevo'>(null)
  const [evaluando, setEvaluando] = useState(false)
  const [acceso, setAcceso] = useState(false)
  const { data: c, isLoading } = useQuery({
    queryKey: ['suppliers', 'compliance', sub.id],
    queryFn: () => proveedoresApi.cumplimiento(sub.id).then(r => r.data),
  })
  const { data: evaluaciones = [] } = useQuery({
    queryKey: ['suppliers', 'risk-assessments', sub.id],
    queryFn: () => proveedoresApi.evaluaciones(sub.id).then(r => r.data),
  })
  const alFallar = (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  const refrescar = () => { qc.invalidateQueries({ queryKey: ['suppliers'] }); qc.invalidateQueries({ queryKey: ['subcontractors'] }) }
  const borrarDoc = useMutation({ mutationFn: (id: string) => proveedoresApi.borrarDocumento(id), onSuccess: refrescar, onError: alFallar })
  const revocar = useMutation({
    mutationFn: ({ id, motivo }: { id: string; motivo: string | null }) => proveedoresApi.revocarAcceso(id, motivo),
    onSuccess: () => { refrescar(); toast.success(t('proveedores.acceso_revocado')) }, onError: alFallar,
  })
  const ciclo = useMutation({
    mutationFn: ({ accion, motivo }: { accion: 'suspend' | 'reactivate' | 'offboard'; motivo: string | null }) =>
      accion === 'suspend' ? proveedoresApi.suspender(sub.id, motivo) : accion === 'reactivate' ? proveedoresApi.reactivar(sub.id, motivo) : proveedoresApi.darDeBaja(sub.id, motivo),
    onSuccess: (r, v) => {
      refrescar()
      qc.invalidateQueries({ queryKey: ['sub-workers', sub.id] })
      qc.invalidateQueries({ queryKey: ['users'] })
      toast.success(t(`proveedores.ciclo_hecho_${v.accion}`))
      onCambio?.({ ...sub, ...r.data })
    },
    onError: alFallar,
  })
  const cambiarCiclo = async (accion: 'suspend' | 'reactivate' | 'offboard') => {
    if (accion === 'offboard') {
      const ok = await confirmar({ title: t('proveedores.dar_de_baja'), message: t('proveedores.baja_confirmar', { nombre: sub.name }), danger: true, palabraConfirmacion: t('proveedores.palabra_baja') })
      if (!ok) return
    }
    const motivo = await pedirTexto({ message: t(`proveedores.ciclo_motivo_${accion}`), label: t('proveedores.motivo'), required: accion !== 'reactivate', danger: accion !== 'reactivate' })
    if (motivo === null) return
    ciclo.mutate({ accion, motivo: motivo || null })
  }

  if (isLoading || !c) return <Spinner />
  const estado = sub.lifecycle_status || 'active'
  return (
    <div className="u-stack-16">
      {/* Estado y ciclo de vida */}
      <Card className="prv-bloque">
        <div className="prv-cabecera-item">
          <div className="prv-bloque-titulo"><ShieldAlert size={16} aria-hidden />{t('proveedores.estado_grc')}
            <StatusBadge kind={TONO_CUMPLIMIENTO[c.status] || 'neutral'} caps={false}>{etiquetaDe(t, 'cumplimiento_', c.status)}</StatusBadge>
            {c.review_overdue && <StatusBadge kind="danger" caps={false}>{t('proveedores.revision_vencida')}</StatusBadge>}
          </div>
          {gestionar && estado !== 'offboarded' && (
            <div className="u-row-6">
              {estado === 'suspended'
                ? <Button size="sm" variant="secondary" icon={<PlayCircle size={14} />} onClick={() => cambiarCiclo('reactivate')}>{t('proveedores.reactivar')}</Button>
                : <Button size="sm" variant="secondary" icon={<Ban size={14} />} onClick={() => cambiarCiclo('suspend')}>{t('proveedores.suspender')}</Button>}
              <Button size="sm" variant="danger" icon={<UserX size={14} />} onClick={() => cambiarCiclo('offboard')}>{t('proveedores.dar_de_baja')}</Button>
            </div>
          )}
        </div>
        {c.required.length > 0 && <p className="u-text2-sm">{t('proveedores.exigidos_n', { docs: c.required.map(d => etiquetaDe(t, 'doc_', d)).join(', ') })}</p>}
        {c.missing.length > 0 && <div className="prv-aviso prv-aviso--peligro prv-mt">{t('proveedores.faltan_n', { docs: c.missing.map(d => etiquetaDe(t, 'doc_', d)).join(', ') })}</div>}
        {c.expiring.length > 0 && <div className="prv-aviso prv-mt">{t('proveedores.caducan_n', { docs: c.expiring.map(d => `${etiquetaDe(t, 'doc_', d.doc_type)} (${fmtDate(d.expires_at)})`).join(', ') })}</div>}
      </Card>

      {/* Documentos */}
      <Card className="prv-bloque">
        <div className="prv-cabecera-item">
          <div className="prv-bloque-titulo"><FileCheck2 size={16} aria-hidden />{t('proveedores.documentos')}</div>
          {gestionar && <Button size="sm" icon={<Plus size={14} />} onClick={() => setDocumento('nuevo')}>{t('proveedores.nuevo_documento')}</Button>}
        </div>
        {c.documents.length === 0 ? <p className="u-text2-sm">{t('proveedores.sin_documentos')}</p> : (
          <div className="u-scroll-x">
            <TablaSimple claseTabla="u-table">
              <thead>
                <tr className="u-border-b">
                  {[t('proveedores.tipo_de_documento'), t('proveedores.referencia'), t('proveedores.emisor'), t('proveedores.caduca'), t('subcontractors.col_estado')].map(h => (
                    <th key={h} scope="col" className="sub-th">{h}</th>
                  ))}
                  <th scope="col" className="sub-th"><span className="u-sr-only">{t('subcontractors.col_acciones')}</span></th>
                </tr>
              </thead>
              <tbody>
                {c.documents.map(d => (
                  <tr key={d.id} className="sub-tr">
                    <td className="sub-td sub-td--strong">{etiquetaDe(t, 'doc_', d.doc_type)}
                      {d.coverage_amount != null && <div className="u-text3-xs">{t('proveedores.cobertura_n', { importe: fmtMoneda(d.coverage_amount) })}</div>}
                    </td>
                    <td className="sub-td">{d.document_url ? <a href={sanitizeUrl(d.document_url)} target="_blank" rel="noreferrer">{d.reference || d.document_url}</a> : (d.reference || '—')}</td>
                    <td className="sub-td sub-td--muted">{d.issuer || '—'}</td>
                    <td className="sub-td sub-td--muted">{d.expires_at ? fmtDate(d.expires_at) : t('proveedores.sin_caducidad')}</td>
                    <td className="sub-td">
                      <StatusBadge kind={TONO_DOCUMENTO[d.status] || 'neutral'} caps={false}>{etiquetaDe(t, 'doc_estado_', d.status)}</StatusBadge>
                      {d.verified_at && <div className="u-text3-xs">{t('proveedores.verificado_el', { fecha: fmtDate(d.verified_at) })}</div>}
                    </td>
                    <td className="sub-td">
                      {gestionar && (
                        <div className="u-row-6">
                          <IconButton onClick={() => setDocumento(d)} ariaLabel={t('proveedores.editar_documento')} title={t('proveedores.editar_documento')}><Pencil size={14} aria-hidden /></IconButton>
                          <IconButton className="sub-borrar" onClick={async () => { if (await confirmar({ message: t('proveedores.borrar_documento_confirmar'), danger: true })) borrarDoc.mutate(d.id) }}
                            ariaLabel={t('proveedores.borrar_documento')} title={t('proveedores.borrar_documento')}><Trash2 size={14} aria-hidden /></IconButton>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </TablaSimple>
          </div>
        )}
      </Card>

      {/* Evaluación de riesgo */}
      <Card className="prv-bloque">
        <div className="prv-cabecera-item">
          <div className="prv-bloque-titulo"><ShieldAlert size={16} aria-hidden />{t('proveedores.evaluacion_de_riesgo')}</div>
          {gestionar && <Button size="sm" icon={<Plus size={14} />} onClick={() => setEvaluando(true)}>{t('proveedores.nueva_evaluacion')}</Button>}
        </div>
        {c.latest_assessment ? (
          <div className="u-stack-8">
            <div className="u-row-center-8">
              <StatusBadge kind={TONO_RIESGO[c.latest_assessment.level] || 'neutral'} caps={false}>{t('proveedores.riesgo_n', { nivel: etiquetaDe(t, 'riesgo_', c.latest_assessment.level) })}</StatusBadge>
              <span className="u-text2-sm">{t('proveedores.puntuacion_riesgo_n', { n: fmtNumber(c.latest_assessment.score, 1) })}</span>
              <span className="u-text2-sm">{t('proveedores.evaluado_el', { fecha: fmtDate(c.latest_assessment.assessed_at) })}</span>
              {c.latest_assessment.next_review_date && <span className="u-text2-sm">{t('proveedores.proxima_revision_n', { fecha: fmtDate(c.latest_assessment.next_review_date) })}</span>}
              {c.latest_assessment.due_diligence_done && <StatusBadge kind="success" caps={false}>{t('proveedores.due_diligence')}</StatusBadge>}
            </div>
            <div className="prv-datos">
              {CRITERIOS.map(k => (
                <div key={k} className="prv-dato"><div className="prv-dato-etiqueta">{etiquetaDe(t, 'criterio_', k)}</div>
                  <div className="prv-dato-valor prv-numero">{c.latest_assessment?.criteria[k] ?? '—'} / 5</div></div>
              ))}
            </div>
            {evaluaciones.length > 1 && <p className="u-text3-xs">{t('proveedores.n_evaluaciones', { n: c.assessments_count || evaluaciones.length })}</p>}
          </div>
        ) : <p className="u-text2-sm">{t('proveedores.sin_evaluacion')}</p>}
      </Card>

      {/* Registro de accesos */}
      <Card className="prv-bloque">
        <div className="prv-cabecera-item">
          <div className="prv-bloque-titulo"><KeyRound size={16} aria-hidden />{t('proveedores.registro_de_accesos')}</div>
          {gestionar && <Button size="sm" icon={<Plus size={14} />} onClick={() => setAcceso(true)}>{t('proveedores.nuevo_acceso')}</Button>}
        </div>
        {c.access_grants.length === 0 ? <p className="u-text2-sm">{t('proveedores.sin_accesos')}</p> : (
          <div className="u-scroll-x">
            <TablaSimple claseTabla="u-table">
              <thead>
                <tr className="u-border-b">
                  {[t('proveedores.sistema'), t('proveedores.categoria_de_datos'), t('proveedores.nivel_de_acceso'), t('proveedores.concedido'), t('proveedores.caduca'), t('subcontractors.col_estado')].map(h => (
                    <th key={h} scope="col" className="sub-th">{h}</th>
                  ))}
                  <th scope="col" className="sub-th"><span className="u-sr-only">{t('subcontractors.col_acciones')}</span></th>
                </tr>
              </thead>
              <tbody>
                {c.access_grants.map(g => (
                  <tr key={g.id} className="sub-tr">
                    <td className="sub-td sub-td--strong">{g.system}{g.personal_data && <div className="u-text3-xs">{t('proveedores.datos_personales')}</div>}</td>
                    <td className="sub-td sub-td--muted">{g.data_category || '—'}</td>
                    <td className="sub-td">{etiquetaDe(t, 'acceso_', g.access_level)}</td>
                    <td className="sub-td sub-td--muted">{fmtDate(g.granted_at)}</td>
                    <td className="sub-td sub-td--muted">{g.expires_at ? fmtDate(g.expires_at) : t('proveedores.sin_caducidad')}</td>
                    <td className="sub-td">
                      <StatusBadge kind={g.active ? 'success' : 'neutral'} caps={false}>{g.active ? t('proveedores.acceso_activo') : t('proveedores.acceso_revocado_el', { fecha: fmtDate(g.revoked_at) })}</StatusBadge>
                      {g.revoke_reason && <div className="u-text3-xs">{g.revoke_reason}</div>}
                    </td>
                    <td className="sub-td">
                      {gestionar && g.active && (
                        <Button size="xs" variant="ghost" className="sub-borrar"
                          onClick={async () => {
                            const motivo = await pedirTexto({ message: t('proveedores.revocar_acceso_confirmar', { sistema: g.system }), label: t('proveedores.motivo'), danger: true })
                            if (motivo !== null) revocar.mutate({ id: g.id, motivo: motivo || null })
                          }}>{t('proveedores.revocar')}</Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </TablaSimple>
          </div>
        )}
      </Card>

      <ContactosDelPortal sub={sub} />

      {documento && <FormularioDeDocumento subId={sub.id} doc={documento === 'nuevo' ? null : documento} onClose={() => setDocumento(null)} />}
      {evaluando && <FormularioDeEvaluacion subId={sub.id} onClose={() => setEvaluando(false)} />}
      {acceso && <FormularioDeAcceso subId={sub.id} onClose={() => setAcceso(false)} />}
    </div>
  )
}
