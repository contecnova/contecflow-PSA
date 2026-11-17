/**
 * VersionesKbPanel — versiones de un artículo de la base de conocimiento en otros
 * idiomas (traducción en tiempo real, 16-11-2026).
 *
 * Lista las versiones (`GET /translation/kb/{id}`) con su estado y el aviso de
 * desfasada; genera todas o las elegidas; abre una versión para leerla o editarla
 * (editar la devuelve a revisión); publica o rechaza (rechazar exige comentario) y
 * borra con confirmación. Los fallos de generación se dicen con su motivo.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, Eye, Languages, RefreshCw, Trash2, Undo2 } from 'lucide-react'
import { Button, Confirm, IconButton, Modal, Spinner, StatusBadge, Checkbox } from '../ui'
import type { StatusBadgeKind } from '../ui/StatusBadge'
import { useToast } from '../../context/ToastContext'
import { useAppLang } from '../../i18n/AppLangContext'
import { traduccionApi, type EstadoDeVersionKb, type GeneracionKb, type VersionKb } from '../../services/api/traduccion'
import { errorDeTraduccion, motivoDeTraduccion, nombreDeIdioma } from '../../hooks/useTraduccion'
import { extractErr } from '../../utils/helpers'
import './VersionesKbPanel.css'

const TIPO_DE_ESTADO: Record<EstadoDeVersionKb, StatusBadgeKind> = {
  draft: 'neutral',
  in_review: 'warning',
  published: 'success',
  rejected: 'danger',
}

export default function VersionesKbPanel({ articleId }: { articleId: string }) {
  const { t, lang } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const clave = ['traduccion-kb', articleId]
  const mensajeDeError = (e: unknown) => errorDeTraduccion(t, extractErr(e, ''))
  const { data, isLoading, isError, error } = useQuery({ queryKey: clave, queryFn: () => traduccionApi.versionesKb(articleId) })
  const [elegidos, setElegidos] = useState<string[]>([])
  const [fallos, setFallos] = useState<GeneracionKb['failed']>([])
  const [abierta, setAbierta] = useState<VersionKb | null>(null)
  const [borrando, setBorrando] = useState<VersionKb | null>(null)

  const refrescar = () => qc.invalidateQueries({ queryKey: clave })
  const generar = useMutation({
    mutationFn: (languages?: string[]) => traduccionApi.generarKb(articleId, languages),
    onSuccess: r => {
      setFallos(r.failed ?? [])
      setElegidos([])
      if (r.generated?.length) toast.success(t('traduccion_admin.kb_generadas', { n: r.generated.length }))
      refrescar()
    },
    onError: (e: unknown) => toast.error(mensajeDeError(e)),
  })
  const borrar = useMutation({
    mutationFn: (language: string) => traduccionApi.borrarKb(articleId, language),
    onSuccess: () => { setBorrando(null); refrescar(); toast.success(t('traduccion_admin.kb_borrada')) },
    onError: (e: unknown) => toast.error(mensajeDeError(e)),
  })

  if (isLoading) return <section className="trad-kb" aria-label={t('traduccion_admin.kb_titulo')}><Spinner /></section>
  if (isError || !data) {
    return (
      <section className="trad-kb" aria-label={t('traduccion_admin.kb_titulo')}>
        <p className="trad-kb__error" role="alert">{mensajeDeError(error)}</p>
      </section>
    )
  }

  const porIdioma = new Map(data.items.map(v => [v.language, v]))
  const idiomas = data.languages.filter(l => l !== data.source_language)
  const alternar = (l: string) => setElegidos(s => s.includes(l) ? s.filter(x => x !== l) : [...s, l])

  return (
    <section className="trad-kb" aria-labelledby={`trad-kb-${articleId}`}>
      <div className="trad-kb__cabecera">
        <h3 id={`trad-kb-${articleId}`} className="trad-kb__titulo">
          <Languages size={15} aria-hidden="true" /> {t('traduccion_admin.kb_titulo')}
        </h3>
        {data.source_language && (
          <span className="trad-kb__origen">{t('traduccion_admin.kb_original_en', { idioma: nombreDeIdioma(data.source_language, lang) })}</span>
        )}
      </div>

      {!data.enabled ? (
        <p className="trad-kb__nota">{t('traduccion_admin.kb_desactivado')}</p>
      ) : (
        <>
          {idiomas.length > 0 && (
            <fieldset className="ds-grupo-opciones trad-kb__idiomas">
              <legend className="trad-kb__leyenda">{t('traduccion_admin.kb_elegir_idiomas')}</legend>
              <div className="trad-kb__casillas">
                {idiomas.map(l => (
                  <Checkbox key={l} className="trad-kb__casilla" label={nombreDeIdioma(l, lang)} checked={elegidos.includes(l)} onChange={() => alternar(l)} />
                ))}
              </div>
              <div className="trad-kb__acciones">
                <Button size="sm" icon={<RefreshCw size={13} />} loading={generar.isPending} onClick={() => generar.mutate(undefined)}>
                  {t('traduccion_admin.kb_generar_todos')}
                </Button>
                <Button size="sm" variant="secondary" disabled={elegidos.length === 0 || generar.isPending} onClick={() => generar.mutate(elegidos)}>
                  {t('traduccion_admin.kb_generar_elegidos', { n: elegidos.length })}
                </Button>
              </div>
            </fieldset>
          )}

          {fallos.length > 0 && (
            <ul className="trad-kb__fallos" role="alert">
              {fallos.map(f => (
                <li key={f.language}>
                  <AlertTriangle size={13} aria-hidden="true" />
                  <span>{t('traduccion_admin.kb_fallo', { idioma: nombreDeIdioma(f.language, lang), motivo: motivoDeTraduccion(t, f.reason) })}</span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}

      {data.items.length === 0 ? (
        <p className="trad-kb__nota">{t('traduccion_admin.kb_sin_versiones')}</p>
      ) : (
        <ul className="trad-kb__lista">
          {[...porIdioma.values()].map(v => (
            <li key={v.id} className="trad-kb__version">
              <div className="trad-kb__version-info">
                <span className="trad-kb__idioma">{nombreDeIdioma(v.language, lang)}</span>
                <StatusBadge kind={TIPO_DE_ESTADO[v.status] ?? 'neutral'}>{t(`traduccion_admin.kb_estado.${v.status}`)}</StatusBadge>
                {v.outdated && (
                  <StatusBadge kind="orange" title={t('traduccion_admin.kb_desfasada_ayuda')}>
                    {t('traduccion_admin.kb_desfasada')}
                  </StatusBadge>
                )}
                <span className="trad-kb__version-titulo">{v.title}</span>
              </div>
              <div className="trad-kb__version-acciones">
                <IconButton ariaLabel={t('traduccion_admin.kb_abrir_x', { idioma: nombreDeIdioma(v.language, lang) })} title={t('traduccion_admin.kb_abrir')} onClick={() => setAbierta(v)}>
                  <Eye size={14} aria-hidden="true" />
                </IconButton>
                <IconButton ariaLabel={t('traduccion_admin.kb_borrar_x', { idioma: nombreDeIdioma(v.language, lang) })} title={t('traduccion_admin.borrar')} onClick={() => setBorrando(v)}>
                  <Trash2 size={14} aria-hidden="true" />
                </IconButton>
              </div>
            </li>
          ))}
        </ul>
      )}

      {abierta && (
        <ModalDeVersionKb
          articleId={articleId}
          version={abierta}
          onClose={() => setAbierta(null)}
          onCambio={() => { refrescar(); setAbierta(null) }}
        />
      )}
      <Confirm
        open={!!borrando}
        title={t('traduccion_admin.kb_borrar_titulo')}
        description={t('traduccion_admin.kb_borrar_desc', { idioma: nombreDeIdioma(borrando?.language, lang) })}
        onCancel={() => setBorrando(null)}
        onConfirm={() => borrando && borrar.mutate(borrando.language)}
        loading={borrar.isPending}
      />
    </section>
  )
}

export function ModalDeVersionKb({ articleId, version, onClose, onCambio }: {
  articleId: string; version: VersionKb; onClose: () => void; onCambio: () => void
}) {
  const { t, lang } = useAppLang()
  const toast = useToast()
  const mensajeDeError = (e: unknown) => errorDeTraduccion(t, extractErr(e, ''))
  const [form, setForm] = useState({ title: version.title, summary: version.summary ?? '', body: version.body })
  const [comentario, setComentario] = useState('')
  const [rechazando, setRechazando] = useState(false)
  const cambiado = form.title !== version.title || form.summary !== (version.summary ?? '') || form.body !== version.body

  const guardar = useMutation({
    mutationFn: () => traduccionApi.editarKb(articleId, version.language, form),
    onSuccess: () => { toast.success(t('traduccion_admin.kb_guardada')); onCambio() },
    onError: (e: unknown) => toast.error(mensajeDeError(e)),
  })
  const revisar = useMutation({
    mutationFn: (publish: boolean) => traduccionApi.revisarKb(articleId, version.language, publish ? { publish } : { publish, comment: comentario.trim() }),
    onSuccess: (_r, publish) => { toast.success(publish ? t('traduccion_admin.kb_publicada') : t('traduccion_admin.kb_rechazada')); onCambio() },
    onError: (e: unknown) => toast.error(mensajeDeError(e)),
  })
  const idioma = nombreDeIdioma(version.language, lang)

  return (
    <Modal open onClose={onClose} size="lg" title={t('traduccion_admin.kb_version_de', { idioma })}
      subtitle={<StatusBadge kind={TIPO_DE_ESTADO[version.status] ?? 'neutral'}>{t(`traduccion_admin.kb_estado.${version.status}`)}</StatusBadge>}>
      <div className="u-stack-14" lang={version.language}>
        {version.outdated && (
          <p className="trad-kb__aviso" role="note"><AlertTriangle size={13} aria-hidden="true" /> {t('traduccion_admin.kb_desfasada_ayuda')}</p>
        )}
        {version.status === 'rejected' && version.review_comment && (
          <p className="trad-kb__aviso" role="note">{t('traduccion_admin.kb_comentario_rechazo', { comentario: version.review_comment })}</p>
        )}
        <div className="ds-field">
          <label className="ds-field__label" htmlFor="trad-kb-titulo">{t('traduccion_admin.kb_campo_titulo')}</label>
          <input id="trad-kb-titulo" className="ds-input" value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} />
        </div>
        <div className="ds-field">
          <label className="ds-field__label" htmlFor="trad-kb-resumen">{t('traduccion_admin.kb_campo_resumen')}</label>
          <input id="trad-kb-resumen" className="ds-input" value={form.summary} onChange={e => setForm(f => ({ ...f, summary: e.target.value }))} />
        </div>
        <div className="ds-field">
          <label className="ds-field__label" htmlFor="trad-kb-cuerpo">{t('traduccion_admin.kb_campo_cuerpo')}</label>
          <textarea id="trad-kb-cuerpo" className="ds-input" rows={10} value={form.body} onChange={e => setForm(f => ({ ...f, body: e.target.value }))} />
          {cambiado && <span className="ds-field__hint">{t('traduccion_admin.kb_editar_vuelve_a_revision')}</span>}
        </div>

        {rechazando && (
          <div className="ds-field">
            <label className="ds-field__label" htmlFor="trad-kb-comentario">{t('traduccion_admin.kb_comentario')}</label>
            <textarea id="trad-kb-comentario" className="ds-input" rows={3} value={comentario} onChange={e => setComentario(e.target.value)}
              aria-describedby="trad-kb-comentario-ayuda" />
            <span id="trad-kb-comentario-ayuda" className="ds-field__hint">{t('traduccion_admin.kb_comentario_obligatorio')}</span>
          </div>
        )}

        <div className="trad-kb__pie">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          {cambiado ? (
            <Button onClick={() => guardar.mutate()} loading={guardar.isPending} disabled={!form.title.trim() || !form.body.trim()}>
              {t('traduccion_admin.guardar')}
            </Button>
          ) : rechazando ? (
            <Button variant="danger" icon={<Undo2 size={14} />} disabled={!comentario.trim()} loading={revisar.isPending} onClick={() => revisar.mutate(false)}>
              {t('traduccion_admin.kb_confirmar_rechazo')}
            </Button>
          ) : (
            <>
              {version.status !== 'rejected' && (
                <Button variant="secondary" icon={<Undo2 size={14} />} onClick={() => setRechazando(true)}>{t('traduccion_admin.kb_rechazar')}</Button>
              )}
              {version.status !== 'published' && (
                <Button icon={<CheckCircle2 size={14} />} loading={revisar.isPending} onClick={() => revisar.mutate(true)}>{t('traduccion_admin.kb_publicar')}</Button>
              )}
            </>
          )}
        </div>
      </div>
    </Modal>
  )
}
