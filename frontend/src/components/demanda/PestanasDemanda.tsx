/**
 * Pestañas del expediente de demanda (operador, 22-11-2026): Ficha, Historial,
 * Versiones de campos, Documentos, Comentarios, Comité y Ejecutar.
 * Rutas: docs/FLUJO_DE_DEMANDA.md sección 4. El historial y las versiones son
 * de solo lectura: el servidor las guarda inmutables (hash encadenado).
 */
import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Download, FileText, Lock, Play, Presentation, Send, Upload } from 'lucide-react'
import { Button, Checkbox, Input, Select, StatusBadge, TablaSimple, Textarea } from '../ui'
import { useQuery } from '@tanstack/react-query'
import { demandaApi, type DetalleDeDemanda, type DocumentoDeExpediente, type CampoDeExpediente } from '../../services/api/demanda'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr, fmtDate, fmtDateTime, downloadBlob } from '../../utils/helpers'
import { camposCambiados, valorDeCampo } from './utilDemanda'
import { etiquetaDe, opcionesDe, useCatalogoDemanda } from './comunes'
import './demanda.css'

/** Refresca el expediente abierto, la lista y las métricas tras una escritura. */
export function useRefrescarDemanda(id: string) {
  const qc = useQueryClient()
  return () => {
    qc.invalidateQueries({ queryKey: ['demand-detail', id] })
    qc.invalidateQueries({ queryKey: ['demand-requests'] })
    qc.invalidateQueries({ queryKey: ['demand-metrics'] })
  }
}

function Marcas({ campo }: { campo: CampoDeExpediente }) {
  const t = useAppT()
  return (
    <>
      {campo.critical && <span className="dem-campo__marca dem-campo__marca--critico">{t('demanda.campo_critico')}</span>}
      {campo.required_now && <span className="dem-campo__marca dem-campo__marca--obligatorio">{t('demanda.campo_obligatorio_ahora')}</span>}
      {campo.owner === 'client' && <span className="dem-campo__marca">{t('demanda.campo_del_cliente')}</span>}
    </>
  )
}

export function EntradaDeCampo({ campo, valor, onChange }: { campo: CampoDeExpediente; valor: string; onChange: (v: string) => void }) {
  const etiqueta = <>{campo.label}<Marcas campo={campo} /></>
  switch (campo.type) {
    case 'textarea':
      return <Textarea label={etiqueta} rows={4} value={valor} onChange={e => onChange(e.target.value)} />
    case 'select':
      return <Select label={etiqueta} value={valor} onChange={e => onChange(e.target.value)} options={(campo.options || []).map(o => ({ value: o.value, label: o.label }))} />
    case 'boolean':
      return <Checkbox label={etiqueta} checked={valor === 'true'} onChange={ok => onChange(ok ? 'true' : 'false')} />
    case 'number': case 'money':
      return <Input label={etiqueta} type="number" step="any" value={valor} onChange={e => onChange(e.target.value)} />
    case 'date':
      return <Input label={etiqueta} type="date" value={valor} onChange={e => onChange(e.target.value)} />
    default:
      return <Input label={etiqueta} value={valor} onChange={e => onChange(e.target.value)} />
  }
}

function textoDeValor(campo: CampoDeExpediente, v: unknown, t: ReturnType<typeof useAppT>): string {
  if (v === null || v === undefined || v === '') return '—'
  if (campo.type === 'boolean') return v ? t('demanda.si') : t('demanda.no')
  if (campo.type === 'select') return campo.options?.find(o => o.value === v)?.label ?? String(v)
  return String(v)
}

// ── Ficha ───────────────────────────────────────────────────────────────────
export function FichaDemanda({ d }: { d: DetalleDeDemanda }) {
  const t = useAppT()
  const toast = useToast()
  const refrescar = useRefrescarDemanda(d.id)
  const tipos = useMemo(() => Object.fromEntries(d.fields.map(c => [c.key, c.type])), [d.fields])
  const inicial = useMemo(() => Object.fromEntries(d.fields.map(c => [c.key, valorDeCampo(c.type, d.data?.[c.key])])), [d.fields, d.data])
  const [editado, setEditado] = useState<Record<string, string>>(inicial)
  const [titulo, setTitulo] = useState(d.title)
  const [nota, setNota] = useState('')
  useEffect(() => { setEditado(inicial); setTitulo(d.title); setNota('') }, [inicial, d.title])
  const puedeEditar = d.actions.can_edit_fields
  const cambios = camposCambiados(d.data || {}, editado, tipos)
  const hayCambios = Object.keys(cambios).length > 0 || titulo !== d.title
  const guardar = useMutation({
    mutationFn: () => demandaApi.editarCampos(d.id, { title: titulo !== d.title ? titulo : undefined, data: cambios, note: nota.trim() || undefined }),
    onSuccess: () => { toast.success(t('demanda.ficha_guardada')); refrescar() },
    onError: (e: unknown) => toast.error(extractErr(e, t('demanda.error'))),
  })
  return (
    <div className="u-stack-16">
      {d.client_locked && <div className="dem-aviso"><Lock size={13} /> {t('demanda.ficha_bloqueada_cliente')}</div>}
      <div className="dem-campos">
        {puedeEditar && <Input label={t('demanda.campo_titulo')} value={titulo} onChange={e => setTitulo(e.target.value)} className="dem-campo--ancho" />}
        {d.fields.map(c => {
          const ancho = c.type === 'textarea' ? 'dem-campo--ancho' : ''
          if (puedeEditar && c.editable) {
            return <div key={c.key} className={ancho}><EntradaDeCampo campo={c} valor={editado[c.key] ?? ''} onChange={v => setEditado(e => ({ ...e, [c.key]: v }))} /></div>
          }
          return (
            <div key={c.key} className={ancho}>
              <div className="uiinde-estiloetiqueta">{c.label}<Marcas campo={c} /></div>
              <div className="dem-valor">{textoDeValor(c, d.data?.[c.key], t)}</div>
            </div>
          )
        })}
      </div>
      {puedeEditar && (
        <div className="u-stack-12">
          <Input label={t('demanda.nota_de_cambio')} hint={t('demanda.nota_de_cambio_ayuda')} value={nota} onChange={e => setNota(e.target.value)} />
          <div className="dem-acciones"><Button loading={guardar.isPending} disabled={!hayCambios} onClick={() => guardar.mutate()}>{t('demanda.guardar_ficha')}</Button></div>
        </div>
      )}
    </div>
  )
}

// ── Historial ───────────────────────────────────────────────────────────────
export function HistorialDemanda({ d }: { d: DetalleDeDemanda }) {
  const t = useAppT()
  const { data: integridad } = useQuery({ queryKey: ['demand-verify', d.id, d.transitions.length], queryFn: () => demandaApi.verificar(d.id), retry: false })
  if (d.transitions.length === 0) return <p className="plan-muted">{t('demanda.sin_historial')}</p>
  return (
    <div className="u-stack-12">
      <p className="plan-muted"><Lock size={12} /> {t('demanda.historial_inmutable')}</p>
      {integridad && <div><StatusBadge kind={integridad.ok ? 'success' : 'danger'}>{integridad.ok ? t('demanda.log_integro') : t('demanda.log_alterado')}</StatusBadge></div>}
      {d.transitions.map(x => (
        <div key={x.id} className="dem-linea">
          <div>{x.seq != null && <span className="u-mono dem-mono">#{x.seq} </span>}<strong>{etiquetaDe(t, 'dec', x.decision)}</strong>{x.is_bypass && <> <StatusBadge kind="danger">{t('demanda.bypass')}</StatusBadge></>}{x.from_phase || x.to_phase ? ` · ${x.from_phase ?? '—'} → ${x.to_phase ?? '—'}` : ''}{x.step_key ? ` · ${x.step_key}` : ''}</div>
          <div className="dem-linea__meta">{x.actor_name ?? t('demanda.sistema')} ({etiquetaDe(t, 'actor', x.actor_kind)}{x.actor_role ? ` · ${x.actor_role}` : ''}) · {fmtDateTime(x.created_at)}</div>
          {x.justification && <div className="dem-justificacion">{x.justification}</div>}
        </div>
      ))}
    </div>
  )
}

// ── Versiones de campos ─────────────────────────────────────────────────────
export function VersionesDemanda({ d }: { d: DetalleDeDemanda }) {
  const t = useAppT()
  const etiquetaCampo = (k: string) => d.fields.find(c => c.key === k)?.label ?? k
  const porCampo = useMemo(() => {
    const m = new Map<string, DetalleDeDemanda['field_versions']>()
    for (const v of d.field_versions) m.set(v.field, [...(m.get(v.field) || []), v])
    return [...m.entries()]
  }, [d.field_versions])
  if (porCampo.length === 0) return <p className="plan-muted">{t('demanda.sin_versiones')}</p>
  return (
    <div className="u-stack-16">
      <p className="plan-muted">{t('demanda.versiones_ayuda')}</p>
      {porCampo.map(([campo, versiones]) => (
        <div key={campo} className="dem-bloque">
          <div className="dem-bloque__titulo">{etiquetaCampo(campo)}</div>
          <TablaSimple claseTabla="plan-tabla">
            <thead><tr><th>{t('demanda.col_origen')}</th><th>{t('demanda.col_valor')}</th><th>{t('demanda.col_fase')}</th><th>{t('demanda.col_autor')}</th><th>{t('demanda.col_fecha')}</th></tr></thead>
            <tbody>
              {versiones.map((v, i) => (
                <tr key={i}>
                  <td><StatusBadge kind={v.source === 'internal' ? 'info' : 'accent'}>{i === 0 && v.source === 'client' ? t('demanda.original_cliente') : t(v.source === 'client' ? 'demanda.cliente' : v.source === 'requester' ? 'demanda.solicitante' : 'demanda.refinado_interno')}</StatusBadge></td>
                  <td className="dem-justificacion">{typeof v.value === 'object' ? JSON.stringify(v.value) : String(v.value ?? '—')}</td>
                  <td>{v.phase_key ?? '—'}</td><td>{v.author_name ?? '—'}</td><td>{fmtDateTime(v.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </TablaSimple>
        </div>
      ))}
    </div>
  )
}

// ── Documentos ──────────────────────────────────────────────────────────────
export function useDescargaDeDocumento(id: string) {
  const t = useAppT()
  const toast = useToast()
  return async (doc: DocumentoDeExpediente) => {
    try { downloadBlob(await demandaApi.descargarDocumento(id, doc.id), doc.file_name) } catch (e) { toast.error(extractErr(e, t('demanda.error'))) }
  }
}

const fmtTamano = (n: number) => n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`

export function DocumentosDemanda({ d }: { d: DetalleDeDemanda }) {
  const t = useAppT()
  const toast = useToast()
  const catalogo = useCatalogoDemanda()
  const refrescar = useRefrescarDemanda(d.id)
  const descargar = useDescargaDeDocumento(d.id)
  const [archivo, setArchivo] = useState<File | null>(null)
  const [etiqueta, setEtiqueta] = useState('other')
  const [personales, setPersonales] = useState(false)
  const [claveInput, setClaveInput] = useState(0)
  const subir = useMutation({
    mutationFn: () => demandaApi.subirDocumento(d.id, { file: archivo as File, tag: etiqueta, personal_data: personales }),
    onSuccess: () => { toast.success(t('demanda.documento_subido')); setArchivo(null); setPersonales(false); setClaveInput(n => n + 1); refrescar() },
    onError: (e: unknown) => toast.error(extractErr(e, t('demanda.error'))),
  })
  const etiquetas = catalogo.document_tags.length ? catalogo.document_tags : ['other']
  return (
    <div className="u-stack-16">
      {d.actions.can_upload && (
        <div className="dem-bloque">
          <div className="dem-bloque__titulo">{t('demanda.subir_documento')}</div>
          <div className="dem-rejilla">
            <Input key={claveInput} label={t('demanda.archivo')} type="file" onChange={e => setArchivo(e.target.files?.[0] ?? null)} />
            <Select label={t('demanda.etiqueta')} placeholder={false} value={etiqueta} onChange={e => setEtiqueta(e.target.value)} options={opcionesDe(t, 'tag', etiquetas)} />
          </div>
          <Checkbox label={t('demanda.datos_personales')} ayuda={t('demanda.datos_personales_ayuda')} checked={personales} onChange={setPersonales} />
          <div className="dem-acciones"><Button icon={<Upload size={13} />} loading={subir.isPending} disabled={!archivo} onClick={() => subir.mutate()}>{t('demanda.subir')}</Button></div>
        </div>
      )}
      {d.documents.length === 0 ? <p className="plan-muted">{t('demanda.sin_documentos')}</p> : (
        <TablaSimple claseTabla="plan-tabla">
          <thead><tr><th>{t('demanda.col_archivo')}</th><th>{t('demanda.etiqueta')}</th><th>{t('demanda.col_fase')}</th><th>{t('demanda.col_autor')}</th><th>{t('demanda.col_fecha')}</th><th /></tr></thead>
          <tbody>
            {d.documents.map(x => (
              <tr key={x.id}>
                <td>{x.file_name} <span className="plan-muted">{fmtTamano(x.size)}</span></td>
                <td>{etiquetaDe(t, 'tag', x.tag)}{x.is_annex && <> <StatusBadge kind="info">{t('demanda.anexo')}</StatusBadge></>}{x.internal && <> <StatusBadge kind="neutral">{t('demanda.interno')}</StatusBadge></>}{x.personal_data && <> <StatusBadge kind="warning">{t('demanda.datos_personales_corta')}</StatusBadge></>}</td>
                <td>{x.phase_key ?? '—'}</td><td>{x.uploaded_by_name ?? '—'}</td><td>{fmtDate(x.created_at)}</td>
                <td><Button size="xs" variant="subtle" icon={<Download size={12} />} onClick={() => descargar(x)}>{t('demanda.descargar')}</Button></td>
              </tr>
            ))}
          </tbody>
        </TablaSimple>
      )}
    </div>
  )
}

// ── Comentarios ─────────────────────────────────────────────────────────────
export function ComentariosDemanda({ d }: { d: DetalleDeDemanda }) {
  const t = useAppT()
  const toast = useToast()
  const refrescar = useRefrescarDemanda(d.id)
  const [texto, setTexto] = useState('')
  const [interno, setInterno] = useState(true)
  const enviar = useMutation({
    mutationFn: () => demandaApi.comentar(d.id, { body: texto.trim(), internal: interno }),
    onSuccess: () => { setTexto(''); refrescar() },
    onError: (e: unknown) => toast.error(extractErr(e, t('demanda.error'))),
  })
  return (
    <div className="u-stack-16">
      {d.comments.length === 0 ? <p className="plan-muted">{t('demanda.sin_comentarios')}</p> : d.comments.map(c => (
        <div key={c.id} className="dem-linea">
          <div className="dem-justificacion">{c.body}</div>
          <div className="dem-linea__meta">
            {c.author_name ?? '—'} · {fmtDateTime(c.created_at)} · <StatusBadge kind={c.internal ? 'neutral' : 'accent'}>{c.internal ? t('demanda.interno') : t('demanda.visible_cliente')}</StatusBadge>
          </div>
        </div>
      ))}
      {d.actions.can_comment && (
        <div className="dem-bloque">
          <Textarea label={t('demanda.nuevo_comentario')} rows={3} value={texto} onChange={e => setTexto(e.target.value)} />
          <Checkbox label={t('demanda.comentario_interno')} ayuda={t('demanda.comentario_interno_ayuda')} checked={interno} onChange={setInterno} />
          <div className="dem-acciones"><Button icon={<Send size={13} />} loading={enviar.isPending} disabled={!texto.trim()} onClick={() => enviar.mutate()}>{t('demanda.enviar_comentario')}</Button></div>
        </div>
      )}
    </div>
  )
}

// ── Comité ──────────────────────────────────────────────────────────────────
export function ComiteDemanda({ d }: { d: DetalleDeDemanda }) {
  const t = useAppT()
  const toast = useToast()
  const refrescar = useRefrescarDemanda(d.id)
  const descargar = useDescargaDeDocumento(d.id)
  const [fecha, setFecha] = useState(d.committee.date?.slice(0, 10) ?? '')
  const resumenes = d.documents.filter(x => x.tag === 'executive_summary')
  const onError = (e: unknown) => toast.error(extractErr(e, t('demanda.error')))
  const agendar = useMutation({
    mutationFn: () => demandaApi.agendarComite(d.id, fecha),
    onSuccess: () => { toast.success(t('demanda.comite_agendado')); refrescar() }, onError,
  })
  const regenerar = useMutation({
    mutationFn: () => demandaApi.resumenEjecutivo(d.id),
    onSuccess: () => { toast.success(t('demanda.resumen_generado')); refrescar() }, onError,
  })
  const icono = (x: DocumentoDeExpediente) => x.file_name.toLowerCase().endsWith('.pptx') ? <Presentation size={12} /> : <FileText size={12} />
  return (
    <div className="u-stack-16">
      <div className="dem-bloque">
        <div className="dem-bloque__titulo">{t('demanda.comite')}</div>
        <div>{d.committee.required ? <StatusBadge kind="warning">{t('demanda.comite_requerido')}</StatusBadge> : <StatusBadge kind="neutral">{t('demanda.comite_no_requerido')}</StatusBadge>}</div>
        {d.committee.reasons.length > 0 && (
          <ul className="dem-errores">{d.committee.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
        )}
        <div className="dem-fila">
          <Input label={t('demanda.fecha_comite')} type="date" value={fecha} onChange={e => setFecha(e.target.value)} disabled={!d.actions.can_schedule_committee} />
          {d.actions.can_schedule_committee && <Button loading={agendar.isPending} disabled={!fecha} onClick={() => agendar.mutate()}>{t('demanda.agendar_comite')}</Button>}
        </div>
        <p className="plan-muted">{t('demanda.agendar_ayuda')}</p>
      </div>
      <div className="dem-bloque">
        <div className="dem-fila dem-fila--entre">
          <div className="dem-bloque__titulo">{t('demanda.resumen_ejecutivo')}</div>
          {d.actions.can_generate_summary && <Button variant="secondary" loading={regenerar.isPending} onClick={() => regenerar.mutate()}>{t('demanda.regenerar_resumen')}</Button>}
        </div>
        {resumenes.length === 0 ? <p className="plan-muted">{t('demanda.sin_resumen')}</p> : (
          <div className="dem-fila">
            {resumenes.map(x => <Button key={x.id} size="sm" variant="subtle" icon={icono(x)} onClick={() => descargar(x)}>{x.file_name}</Button>)}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Ejecutar ────────────────────────────────────────────────────────────────
export function EjecutarDemanda({ d }: { d: DetalleDeDemanda }) {
  const t = useAppT()
  const toast = useToast()
  const catalogo = useCatalogoDemanda()
  const refrescar = useRefrescarDemanda(d.id)
  const modos = catalogo.execution_modes.length ? catalogo.execution_modes : ['backlog', 'new_project', 'portfolio']
  const [modo, setModo] = useState(modos[0])
  const [nombre, setNombre] = useState(d.title)
  const [pm, setPm] = useState('')
  const ejecutar = useMutation({
    mutationFn: () => demandaApi.ejecutar(d.id, { mode: modo, name: modo === 'new_project' ? nombre.trim() || undefined : undefined, pm_id: modo === 'new_project' && pm ? pm : undefined }),
    onSuccess: () => { toast.success(t('demanda.ejecutada')); refrescar() },
    onError: (e: unknown) => toast.error(extractErr(e, t('demanda.error'))),
  })
  const r = d.result
  return (
    <div className="u-stack-16">
      {r?.kind && (
        <div className="dem-aviso">
          {t('demanda.resultado')}: <strong>{etiquetaDe(t, 'modo', r.kind)}</strong>
          {r.project_id && <> · {t('demanda.proyecto')}: <span className="u-mono dem-mono">{r.project_id}</span></>}
          {r.change_request_id && <> · CR: <span className="u-mono dem-mono">{r.change_request_id}</span></>}
          {r.proposal_id && <> · {t('demanda.propuesta')}: <span className="u-mono dem-mono">{r.proposal_id}</span></>}
          {r.actions && r.actions.length > 0 && (
            <ul className="u-stack-8">
              {r.actions.map((a, i) => (
                <li key={i}>
                  <StatusBadge kind={a.ok ? 'success' : 'danger'}>{a.ok ? t('demanda.accion_ok') : t('demanda.accion_error')}</StatusBadge> {etiquetaDe(t, 'accion', a.action)}
                  {a.id && <> · <span className="u-mono dem-mono">{a.id}</span></>}{a.error && <> · {a.error}</>}{a.at && <> · {fmtDateTime(a.at)}</>}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {!d.actions.can_execute ? <p className="plan-muted">{t('demanda.no_ejecutable')}</p> : (
        <div className="dem-bloque">
          <div className="dem-bloque__titulo">{t('demanda.ejecutar_titulo')}</div>
          <p className="plan-muted">{t('demanda.ejecutar_ayuda')}</p>
          <div className="dem-rejilla">
            <Select label={t('demanda.modo')} placeholder={false} value={modo} onChange={e => setModo(e.target.value)} options={opcionesDe(t, 'modo', modos)} />
            {modo === 'new_project' && <>
              <Input label={t('demanda.nombre_proyecto')} value={nombre} onChange={e => setNombre(e.target.value)} />
              <Select label={t('demanda.responsable_pm')} value={pm} onChange={e => setPm(e.target.value)} options={catalogo.users} />
            </>}
          </div>
          <div className="dem-acciones"><Button icon={<Play size={13} />} loading={ejecutar.isPending} onClick={() => ejecutar.mutate()}>{t('demanda.ejecutar')}</Button></div>
        </div>
      )}
    </div>
  )
}
