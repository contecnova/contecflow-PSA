/**
 * PortalDemandas — «Demandas» del portal de clientes (22-11-2026).
 *
 * El cliente pide un cambio en un proyecto, una nueva funcionalidad (incluso
 * fuera de todo proyecto) o un servicio, y sigue el expediente por las fases
 * que la empresa ha configurado (solo ve nombres y estado de las fases, nunca
 * comentarios internos). Rutas `/api/v1/portal/demand/...` (token del cliente);
 * ver docs/FLUJO_DE_DEMANDA.md. Desde la fase que la empresa marca, la ficha
 * queda bloqueada: el cliente solo añade comentarios y anexos registrados.
 * Textos: claves `dem_*` de los 8 diccionarios de `i18n/portal`.
 */
import { useId, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Download, FilePlus2, Lock, Plus, Send, Undo2, Upload } from 'lucide-react'
import { useToast } from '../../context/ToastContext'
import { downloadBlob, fmtDate, fmtDateTime } from '../../utils/helpers'
import { Checkbox } from '../../components/ui'
import { CLIENT_API, useErrorDelPortal, useLang } from './portalClientContext'
import {
  PortalBadge, PortalBanner, PortalButton, PortalCard, PortalEmpty, PortalField, PortalInput, PortalModal,
  PortalSelect, PortalTabs, PortalTextarea,
} from './PortalUI'

// ── Formas de las respuestas (docs/FLUJO_DE_DEMANDA.md, sección 4) ───────────
interface CampoDelPortal {
  key: string; label: string; type: string; options?: Array<{ value: string; label: string }>
  critical?: boolean; editable?: boolean; required_now?: boolean; required?: boolean
}
interface TipoDelPortal {
  key: string; name: string; requires_project: boolean; allows_standalone: boolean
  fields: CampoDelPortal[]; submit_required: string[]
}
interface TiposDelPortal { types: TipoDelPortal[]; projects: Array<{ id: string; name: string }> }
interface ResumenDelPortal {
  id: string; code: string; title: string; type_name: string; status: string
  current_phase_name: string | null; project_name: string | null; standalone: boolean
  created_at: string; submitted_at: string | null; closed_at: string | null
}
interface DetalleDelPortal extends ResumenDelPortal {
  data: Record<string, unknown>
  fields: CampoDelPortal[]
  phases: Array<{ key: string; name: string; status: 'done' | 'current' | 'pending' | 'skipped'; steps?: Array<{ key: string; name: string; status?: string; decisions?: string[] }> }>
  info_request?: string | null
  transitions: Array<{ id: string; decision: string; actor_name: string | null; actor_kind: string; justification: string | null; created_at: string }>
  documents: Array<{ id: string; tag: string; file_name: string; size: number; is_annex: boolean; uploaded_by_name: string | null; created_at: string }>
  comments: Array<{ id: string; body: string; author_name: string | null; author_kind: string; created_at: string }>
  actions: { can_edit_fields: boolean; can_submit: boolean; can_comment: boolean; can_upload: boolean; can_withdraw: boolean; client_editable_phase?: boolean }
  client_locked: boolean
}

const TONO: Record<string, string> = {
  draft: 'default', in_progress: 'accent', pending_info: 'warning', on_hold: 'default',
  approved: 'success', rejected: 'danger', withdrawn: 'default', done: 'success',
}
const ETIQUETAS_DE_ADJUNTO = ['mockup', 'regulation', 'presentation', 'annex', 'other']

const valorInicial = (c: CampoDelPortal, v: unknown): string => v === null || v === undefined ? '' : c.type === 'boolean' ? (v ? 'true' : 'false') : String(v)
function valorGuardado(c: CampoDelPortal, s: string): unknown {
  if (c.type === 'boolean') return s === 'true'
  if (c.type === 'number' || c.type === 'money') return s.trim() === '' ? null : Number(s)
  return s
}

/** Etiqueta traducida por clave del portal; si no existe, el valor técnico. */
function useEtiqueta() {
  const t = useLang()
  return (prefijo: string, valor: string) => { const k = `dem_${prefijo}_${valor}`; const v = t(k); return v === k ? valor : v }
}

// ── Campos de la ficha ──────────────────────────────────────────────────────
function CamposDeFicha({ campos, valores, onChange, errores }: {
  campos: CampoDelPortal[]; valores: Record<string, string>; onChange: (k: string, v: string) => void; errores?: (k: string) => string | undefined
}) {
  const t = useLang()
  const id = useId()
  return (
    <>
      {campos.map(c => {
        const v = valores[c.key] ?? ''
        const comun = { id: `${id}-${c.key}`, value: v }
        let control
        if (c.type === 'textarea') control = <PortalTextarea rows={4} {...comun} onChange={e => onChange(c.key, e.target.value)} />
        else if (c.type === 'select') control = (
          <PortalSelect {...comun} onChange={e => onChange(c.key, e.target.value)}>
            <option value="">{t('dem_elegir')}</option>
            {(c.options || []).map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </PortalSelect>
        )
        else if (c.type === 'boolean') control = <Checkbox checked={v === 'true'} aria-label={c.label} onChange={ok => onChange(c.key, ok ? 'true' : 'false')} />
        else if (c.type === 'number' || c.type === 'money') control = <PortalInput type="number" step="any" {...comun} onChange={e => onChange(c.key, e.target.value)} />
        else if (c.type === 'date') control = <PortalInput type="date" {...comun} onChange={e => onChange(c.key, e.target.value)} />
        else control = <PortalInput {...comun} onChange={e => onChange(c.key, e.target.value)} />
        return <PortalField key={c.key} label={c.label} required={c.required || c.required_now} error={errores?.(c.key)}>{control}</PortalField>
      })}
    </>
  )
}

// ── Nueva solicitud ─────────────────────────────────────────────────────────
function NuevaDemanda({ datos, onClose, onCreada }: { datos: TiposDelPortal; onClose: () => void; onCreada: (id: string) => void }) {
  const t = useLang()
  const errorDe = useErrorDelPortal()
  const toast = useToast()
  const qc = useQueryClient()
  const [tipoKey, setTipoKey] = useState(datos.types[0]?.key ?? '')
  const [titulo, setTitulo] = useState('')
  const [proyecto, setProyecto] = useState('')
  const [independiente, setIndependiente] = useState(false)
  const [valores, setValores] = useState<Record<string, string>>({})
  const tipo = datos.types.find(x => x.key === tipoKey)
  const sinProyecto = !!tipo?.allows_standalone && !tipo?.requires_project && (independiente || datos.projects.length === 0)
  const faltaProyecto = !!tipo && !sinProyecto && !proyecto && (tipo.requires_project || !tipo.allows_standalone)
  const faltantes = useMemo(() => (tipo?.submit_required || []).filter(k => k === 'title' ? !titulo.trim() : !(valores[k] ?? '').trim()), [tipo, titulo, valores])
  const crear = useMutation({
    mutationFn: (enviar: boolean) => {
      const data: Record<string, unknown> = {}
      for (const c of tipo?.fields || []) if ((valores[c.key] ?? '') !== '') data[c.key] = valorGuardado(c, valores[c.key])
      return CLIENT_API.post('/portal/demand/requests', { type_key: tipoKey, title: titulo.trim(), project_id: sinProyecto ? null : proyecto || null, data, submit: enviar })
        .then(r => r.data as { id: string })
    },
    onSuccess: (r, enviar) => {
      qc.invalidateQueries({ queryKey: ['portal-demand-list'] })
      toast.success(enviar ? t('dem_enviada') : t('dem_borrador_guardado'))
      onCreada(r.id)
    },
    onError: (e: unknown) => toast.error(errorDe(e, t('pas_err_generic'))),
  })
  return (
    <PortalModal open onClose={onClose} title={t('dem_nueva')} subtitle={t('dem_nueva_ayuda')} width={680}
      footer={(
        <>
          <PortalButton variant="secondary" onClick={onClose}>{t('common.cancel')}</PortalButton>
          <PortalButton variant="secondary" loading={crear.isPending} disabled={!titulo.trim() || faltaProyecto} onClick={() => crear.mutate(false)}>{t('dem_guardar_borrador')}</PortalButton>
          <PortalButton icon={<Send size={14} />} loading={crear.isPending} disabled={!titulo.trim() || faltaProyecto || faltantes.length > 0} onClick={() => crear.mutate(true)}>{t('dem_enviar')}</PortalButton>
        </>
      )}>
      <div className="u-stack-14">
        <PortalField label={t('dem_tipo')} required>
          <PortalSelect value={tipoKey} onChange={e => { setTipoKey(e.target.value); setValores({}) }}>
            {datos.types.map(x => <option key={x.key} value={x.key}>{x.name}</option>)}
          </PortalSelect>
        </PortalField>
        {tipo && tipo.allows_standalone && !tipo.requires_project && datos.projects.length > 0 && (
          <Checkbox label={t('dem_iniciativa_independiente')} ayuda={t('dem_iniciativa_independiente_ayuda')} checked={independiente} onChange={setIndependiente} />
        )}
        {tipo && !sinProyecto && (
          <PortalField label={t('dem_proyecto')} required>
            <PortalSelect value={proyecto} onChange={e => setProyecto(e.target.value)}>
              <option value="">{t('dem_elegir')}</option>
              {datos.projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
            </PortalSelect>
          </PortalField>
        )}
        <PortalField label={t('dem_titulo')} required>
          <PortalInput value={titulo} onChange={e => setTitulo(e.target.value)} />
        </PortalField>
        {tipo && <CamposDeFicha campos={tipo.fields.map(c => ({ ...c, required: tipo.submit_required.includes(c.key) }))} valores={valores} onChange={(k, v) => setValores(x => ({ ...x, [k]: v }))} />}
        {faltantes.length > 0 && <p className="u-text3-xs">{t('dem_faltan_para_enviar')}</p>}
      </div>
    </PortalModal>
  )
}

// ── Detalle ─────────────────────────────────────────────────────────────────
function EdicionDeFicha({ d, onClose }: { d: DetalleDelPortal; onClose: () => void }) {
  const t = useLang()
  const errorDe = useErrorDelPortal()
  const toast = useToast()
  const qc = useQueryClient()
  const editables = d.fields.filter(c => c.editable !== false)
  const [titulo, setTitulo] = useState(d.title)
  const [valores, setValores] = useState<Record<string, string>>(() => Object.fromEntries(editables.map(c => [c.key, valorInicial(c, d.data?.[c.key])])))
  const guardar = useMutation({
    mutationFn: () => CLIENT_API.patch(`/portal/demand/requests/${d.id}`, {
      title: titulo.trim(), data: Object.fromEntries(editables.map(c => [c.key, valorGuardado(c, valores[c.key] ?? '')])),
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['portal-demand', d.id] }); qc.invalidateQueries({ queryKey: ['portal-demand-list'] }); toast.success(t('dem_ficha_guardada')); onClose() },
    onError: (e: unknown) => toast.error(errorDe(e, t('pas_err_generic'))),
  })
  return (
    <PortalModal open onClose={onClose} title={t('dem_editar_ficha')} width={680}
      footer={(<><PortalButton variant="secondary" onClick={onClose}>{t('common.cancel')}</PortalButton><PortalButton loading={guardar.isPending} disabled={!titulo.trim()} onClick={() => guardar.mutate()}>{t('dem_guardar')}</PortalButton></>)}>
      <div className="u-stack-14">
        <PortalField label={t('dem_titulo')} required><PortalInput value={titulo} onChange={e => setTitulo(e.target.value)} /></PortalField>
        <CamposDeFicha campos={editables} valores={valores} onChange={(k, v) => setValores(x => ({ ...x, [k]: v }))} />
      </div>
    </PortalModal>
  )
}

function DetalleDeDemanda({ id, onVolver }: { id: string; onVolver: () => void }) {
  const t = useLang()
  const etiqueta = useEtiqueta()
  const errorDe = useErrorDelPortal()
  const toast = useToast()
  const qc = useQueryClient()
  const [pestana, setPestana] = useState('ficha')
  const [editando, setEditando] = useState(false)
  const [retirando, setRetirando] = useState(false)
  const [motivo, setMotivo] = useState('')
  const [comentario, setComentario] = useState('')
  const [decidiendo, setDecidiendo] = useState<{ step: string; nombre: string; decision: string } | null>(null)
  const [justificacion, setJustificacion] = useState('')
  const [archivo, setArchivo] = useState<File | null>(null)
  const [tag, setTag] = useState('other')
  const [claveArchivo, setClaveArchivo] = useState(0)
  const { data: d, isLoading } = useQuery<DetalleDelPortal>({ queryKey: ['portal-demand', id], queryFn: () => CLIENT_API.get(`/portal/demand/requests/${id}`).then(r => r.data as DetalleDelPortal) })
  const refrescar = () => { qc.invalidateQueries({ queryKey: ['portal-demand', id] }); qc.invalidateQueries({ queryKey: ['portal-demand-list'] }) }
  const onError = (e: unknown) => toast.error(errorDe(e, t('pas_err_generic')))
  const enviar = useMutation({ mutationFn: () => CLIENT_API.post(`/portal/demand/requests/${id}/submit`, {}), onSuccess: () => { toast.success(t('dem_enviada')); refrescar() }, onError })
  const retirar = useMutation({ mutationFn: () => CLIENT_API.post(`/portal/demand/requests/${id}/withdraw`, { reason: motivo.trim() }), onSuccess: () => { toast.success(t('dem_retirada')); setRetirando(false); refrescar() }, onError })
  const decidir = useMutation({
    mutationFn: () => CLIENT_API.post(`/portal/demand/requests/${id}/decide`, { step_key: decidiendo?.step, decision: decidiendo?.decision, justification: justificacion.trim() || undefined }),
    onSuccess: () => { toast.success(t('dem_decision_registrada')); setDecidiendo(null); setJustificacion(''); refrescar() }, onError,
  })
  const comentar = useMutation({ mutationFn: () => CLIENT_API.post(`/portal/demand/requests/${id}/comments`, { body: comentario.trim() }), onSuccess: () => { setComentario(''); refrescar() }, onError })
  const subir = useMutation({
    mutationFn: () => {
      const fd = new FormData()
      fd.append('file', archivo as File); fd.append('tag', tag)
      return CLIENT_API.post(`/portal/demand/requests/${id}/documents`, fd)
    },
    onSuccess: () => { toast.success(t('dem_adjunto_subido')); setArchivo(null); setClaveArchivo(n => n + 1); refrescar() }, onError,
  })
  const descargar = async (docId: string, nombre: string) => {
    try { const r = await CLIENT_API.get(`/portal/demand/requests/${id}/documents/${docId}/download`, { responseType: 'blob' }); downloadBlob(r.data as Blob, nombre) } catch (e) { onError(e) }
  }
  if (isLoading || !d) return null
  const peticionDeInfo = [...d.transitions].reverse().find(x => x.decision === 'request_info')
  const mostrarCampos = d.fields.filter(c => c.type !== 'hidden')
  return (
    <div className="u-stack-16">
      <div><PortalButton variant="subtle" size="sm" icon={<ArrowLeft size={14} />} onClick={onVolver}>{t('dem_volver')}</PortalButton></div>
      <PortalCard>
        <div className="u-stack-12">
          <div className="u-flex1-min0">
            <span className="u-text3-mono-xs">{d.code} · {d.type_name}</span>
            <h2>{d.title}</h2>
            <div className="u-text3-xs">{d.project_name ?? (d.standalone ? t('dem_iniciativa_independiente') : '')}{d.submitted_at ? ` · ${t('dem_enviada_el')} ${fmtDate(d.submitted_at)}` : ''}</div>
          </div>
          <div><PortalBadge tone={TONO[d.status] || 'default'}>{etiqueta('estado', d.status)}</PortalBadge>{d.current_phase_name && <> <span className="u-text3-xs">{t('dem_fase_actual')}: {d.current_phase_name}</span></>}</div>
          <div role="list" aria-label={t('dem_fases')} className="u-stack-8">
            {d.phases.map(f => (
              <div key={f.key} role="listitem"><PortalBadge tone={f.status === 'done' ? 'success' : f.status === 'current' ? 'accent' : 'default'}>{etiqueta('fase', f.status)}</PortalBadge> {f.name}
                {f.status === 'current' && (f.steps || []).map(p => (
                  <div key={p.key} className="u-stack-8">
                    <div className="u-text3-xs">{p.name}: {t('dem_paso_pendiente_tuyo')}</div>
                    <div>
                      {(p.decisions || []).map(dec => (
                        <PortalButton key={dec} size="sm" variant={dec === 'reject' ? 'danger' : 'secondary'} onClick={() => { setJustificacion(''); setDecidiendo({ step: p.key, nombre: p.name, decision: dec }) }}>{etiqueta('decidir', dec)}</PortalButton>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            ))}
          </div>
          <div>
            {d.actions.can_submit && d.status === 'draft' && <PortalButton icon={<Send size={14} />} loading={enviar.isPending} onClick={() => enviar.mutate()}>{t('dem_enviar')}</PortalButton>}
            {d.actions.can_withdraw && <PortalButton variant="danger" icon={<Undo2 size={14} />} onClick={() => setRetirando(true)}>{t('dem_retirar')}</PortalButton>}
          </div>
        </div>
      </PortalCard>
      {d.status === 'pending_info' && (
        <PortalBanner tone="warning" title={t('dem_pendiente_info')}
          body={d.info_request || peticionDeInfo?.justification || t('dem_pendiente_info_ayuda')}
          action={(
            <>
              {d.actions.can_edit_fields && <PortalButton variant="secondary" size="sm" onClick={() => setEditando(true)}>{t('dem_aportar_informacion')}</PortalButton>}
              {d.actions.can_submit && <PortalButton size="sm" icon={<Send size={14} />} loading={enviar.isPending} onClick={() => enviar.mutate()}>{t('dem_reenviar')}</PortalButton>}
            </>
          )} />
      )}
      {d.client_locked && <PortalBanner tone="info" icon={<Lock size={14} />} title={t('dem_ficha_bloqueada')} body={t('dem_ficha_bloqueada_ayuda')} />}
      <PortalTabs ariaLabel={t('dem_pestanas')} value={pestana} onChange={setPestana} tabs={[
        { id: 'ficha', label: t('dem_tab_ficha') },
        { id: 'adjuntos', label: t('dem_tab_adjuntos'), badge: d.documents.length },
        { id: 'comentarios', label: t('dem_tab_comentarios'), badge: d.comments.length },
        { id: 'historial', label: t('dem_tab_historial'), badge: d.transitions.length },
      ]} />
      {pestana === 'ficha' && (
        <PortalCard>
          <div className="u-stack-12">
            {mostrarCampos.map(c => {
              const v = d.data?.[c.key]
              const texto = v === null || v === undefined || v === '' ? '—' : c.type === 'boolean' ? (v ? t('dem_si') : t('dem_no')) : c.type === 'select' ? (c.options?.find(o => o.value === v)?.label ?? String(v)) : String(v)
              return <div key={c.key}><div className="u-text3-xs">{c.label}</div><div>{texto}</div></div>
            })}
            {d.actions.can_edit_fields && <div><PortalButton variant="secondary" icon={<FilePlus2 size={14} />} onClick={() => setEditando(true)}>{t('dem_editar_ficha')}</PortalButton></div>}
          </div>
        </PortalCard>
      )}
      {pestana === 'adjuntos' && (
        <PortalCard>
          <div className="u-stack-12">
            {d.documents.length === 0 ? <p className="u-text3-xs">{t('dem_sin_adjuntos')}</p> : d.documents.map(x => (
              <div key={x.id}>
                <PortalButton variant="subtle" size="sm" icon={<Download size={13} />} onClick={() => descargar(x.id, x.file_name)}>{x.file_name}</PortalButton>
                {' '}<PortalBadge>{etiqueta('tag', x.tag)}</PortalBadge>{x.is_annex && <> <PortalBadge tone="accent">{t('dem_anexo')}</PortalBadge></>}
                <span className="u-text3-xs"> {x.uploaded_by_name ?? ''} · {fmtDate(x.created_at)}</span>
              </div>
            ))}
            {d.actions.can_upload && (
              <div className="u-stack-12">
                <PortalField label={t('dem_archivo')}><PortalInput key={claveArchivo} type="file" onChange={e => setArchivo(e.target.files?.[0] ?? null)} /></PortalField>
                <PortalField label={t('dem_etiqueta')}>
                  <PortalSelect value={tag} onChange={e => setTag(e.target.value)}>
                    {ETIQUETAS_DE_ADJUNTO.map(k => <option key={k} value={k}>{etiqueta('tag', k)}</option>)}
                  </PortalSelect>
                </PortalField>
                <div><PortalButton icon={<Upload size={14} />} loading={subir.isPending} disabled={!archivo} onClick={() => subir.mutate()}>{t('dem_subir')}</PortalButton></div>
              </div>
            )}
            {d.client_locked && <p className="u-text3-xs">{t('dem_solo_anexos')}</p>}
          </div>
        </PortalCard>
      )}
      {pestana === 'comentarios' && (
        <PortalCard>
          <div className="u-stack-12">
            {d.comments.length === 0 ? <p className="u-text3-xs">{t('dem_sin_comentarios')}</p> : d.comments.map(c => (
              <div key={c.id}><div>{c.body}</div><div className="u-text3-xs">{c.author_name ?? ''} · {fmtDateTime(c.created_at)}</div></div>
            ))}
            {d.actions.can_comment && (
              <div className="u-stack-12">
                <PortalField label={t('dem_nuevo_comentario')}><PortalTextarea rows={3} value={comentario} onChange={e => setComentario(e.target.value)} /></PortalField>
                <div><PortalButton icon={<Send size={14} />} loading={comentar.isPending} disabled={!comentario.trim()} onClick={() => comentar.mutate()}>{t('dem_comentar')}</PortalButton></div>
              </div>
            )}
          </div>
        </PortalCard>
      )}
      {pestana === 'historial' && (
        <PortalCard>
          <div className="u-stack-12">
            {d.transitions.length === 0 ? <p className="u-text3-xs">{t('dem_sin_historial')}</p> : d.transitions.map(x => (
              <div key={x.id}>
                <strong>{etiqueta('dec', x.decision)}</strong>
                <span className="u-text3-xs"> {x.actor_name ?? ''} · {fmtDateTime(x.created_at)}</span>
                {x.justification && <div>{x.justification}</div>}
              </div>
            ))}
          </div>
        </PortalCard>
      )}
      {editando && <EdicionDeFicha d={d} onClose={() => setEditando(false)} />}
      <PortalModal open={!!decidiendo} onClose={() => setDecidiendo(null)} title={decidiendo ? `${etiqueta('decidir', decidiendo.decision)} · ${decidiendo.nombre}` : ''}
        footer={(<><PortalButton variant="secondary" onClick={() => setDecidiendo(null)}>{t('common.cancel')}</PortalButton>
          <PortalButton loading={decidir.isPending} disabled={!!decidiendo && ['reject', 'return', 'request_info', 'skip', 'hold'].includes(decidiendo.decision) && !justificacion.trim()} onClick={() => decidir.mutate()}>{t('dem_confirmar')}</PortalButton></>)}>
        <PortalField label={t('dem_justificacion')} required={!!decidiendo && ['reject', 'return', 'request_info', 'skip', 'hold'].includes(decidiendo.decision)}
          hint={t('dem_justificacion_ayuda')}><PortalTextarea rows={3} value={justificacion} onChange={e => setJustificacion(e.target.value)} /></PortalField>
      </PortalModal>
      <PortalModal open={retirando} onClose={() => setRetirando(false)} title={t('dem_retirar')} subtitle={t('dem_retirar_ayuda')}
        footer={(<><PortalButton variant="secondary" onClick={() => setRetirando(false)}>{t('common.cancel')}</PortalButton><PortalButton variant="danger" loading={retirar.isPending} onClick={() => retirar.mutate()}>{t('dem_retirar')}</PortalButton></>)}>
        <PortalField label={t('dem_motivo')}><PortalTextarea rows={3} value={motivo} onChange={e => setMotivo(e.target.value)} /></PortalField>
      </PortalModal>
    </div>
  )
}

// ── Lista ───────────────────────────────────────────────────────────────────
export default function PortalDemandas() {
  const t = useLang()
  const etiqueta = useEtiqueta()
  const [abierta, setAbierta] = useState('')
  const [nueva, setNueva] = useState(false)
  const { data: tipos } = useQuery<TiposDelPortal>({ queryKey: ['portal-demand-types'], queryFn: () => CLIENT_API.get('/portal/demand/types').then(r => r.data as TiposDelPortal) })
  const { data: lista = [], isLoading } = useQuery<ResumenDelPortal[]>({
    queryKey: ['portal-demand-list'],
    queryFn: () => CLIENT_API.get('/portal/demand/requests').then(r => (Array.isArray(r.data) ? r.data : (r.data as { items?: ResumenDelPortal[] })?.items ?? []) as ResumenDelPortal[]),
  })
  if (abierta) return <DetalleDeDemanda id={abierta} onVolver={() => setAbierta('')} />
  const puedeCrear = (tipos?.types.length ?? 0) > 0
  return (
    <div className="u-stack-16">
      <div>
        {puedeCrear && <PortalButton icon={<Plus size={14} />} onClick={() => setNueva(true)}>{t('dem_nueva')}</PortalButton>}
      </div>
      {isLoading ? null : lista.length === 0 ? (
        <PortalEmpty title={t('dem_sin_demandas')} description={t('dem_sin_demandas_ayuda')}
          action={puedeCrear ? <PortalButton icon={<Plus size={14} />} onClick={() => setNueva(true)}>{t('dem_nueva')}</PortalButton> : null} />
      ) : (
        <div className="u-stack-12">
          {lista.map(x => (
            <PortalCard key={x.id} onClick={() => setAbierta(x.id)}>
              <div className="u-stack-8">
                <div><span className="u-text3-mono-xs">{x.code}</span> <strong>{x.title}</strong></div>
                <div className="u-text3-xs">{x.type_name}{x.project_name ? ` · ${x.project_name}` : x.standalone ? ` · ${t('dem_iniciativa_independiente')}` : ''}{x.submitted_at ? ` · ${fmtDate(x.submitted_at)}` : ''}</div>
                <div><PortalBadge tone={TONO[x.status] || 'default'}>{etiqueta('estado', x.status)}</PortalBadge>{x.current_phase_name && <> <span className="u-text3-xs">{x.current_phase_name}</span></>}</div>
              </div>
            </PortalCard>
          ))}
        </div>
      )}
      {nueva && tipos && <NuevaDemanda datos={tipos} onClose={() => setNueva(false)} onCreada={id => { setNueva(false); setAbierta(id) }} />}
    </div>
  )
}
