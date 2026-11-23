/**
 * VersionesPanel — versiones revisables de un contenido en los idiomas del
 * portal (17-11-2026; generaliza el panel de la base de conocimiento).
 *
 * Lo usan los artículos de la KB (`VersionesKbPanel`) y los avisos y el
 * catálogo de servicios (`VersionesDeContenidoPanel`). Cada uso da un
 * `AdaptadorDeVersiones`: sus campos (título, cuerpo, nombre, descripción…) y
 * las llamadas a la API. El panel lista las versiones con su estado y el
 * aviso de desactualizada; genera todas o las elegidas; abre una versión para
 * leerla junto al original o corregirla (corregir la devuelve a revisión);
 * publica o rechaza (rechazar exige comentario; solo quien puede revisar) y
 * borra con confirmación. Los fallos de generación se dicen con su motivo.
 */
import { useId, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, Eye, Languages, RefreshCw, Trash2, Undo2 } from 'lucide-react'
import { Button, FormField, IconButton, Input, Modal, Spinner, StatusBadge, Checkbox, Textarea } from '../ui'
import type { StatusBadgeKind } from '../ui/StatusBadge'
import { useToast } from '../../context/ToastContext'
import { confirmar } from '../../context/ConfirmContext'
import { useAppLang } from '../../i18n/AppLangContext'
import type { EstadoDeVersionKb } from '../../services/api/traduccion'
import { errorDeTraduccion, motivoDeTraduccion, nombreDeIdioma } from '../../hooks/useTraduccion'
import { extractErr } from '../../utils/helpers'
import './VersionesKbPanel.css'

export interface VersionGenerica {
  id: string
  language: string
  status: EstadoDeVersionKb
  /** El original cambió después de generar (o corregir) esta versión. */
  outdated: boolean
  review_comment: string | null
  campos: Record<string, string>
}

export interface DatosDeVersiones {
  source_language: string | null
  languages: string[]
  enabled: boolean
  /** Si quien mira puede publicar o rechazar (sin dato: el servidor decide). */
  can_review?: boolean
  /** Textos del original, para revisar al lado. */
  original?: Record<string, string>
  items: VersionGenerica[]
}

export interface CampoDeVersion {
  clave: string
  /** Clave i18n de la etiqueta. */
  etiqueta: string
  multilinea?: boolean
  obligatorio?: boolean
}

type ClaveDeTexto = 'titulo' | 'sin_versiones' | 'desactivado' | 'desfasada_ayuda'

export interface AdaptadorDeVersiones {
  /** Clave de la consulta (React Query). */
  clave: readonly unknown[]
  campos: CampoDeVersion[]
  listar: () => Promise<DatosDeVersiones>
  generar: (languages?: string[]) => Promise<{ generated?: unknown[]; failed?: { language: string; reason: string }[] }>
  editar: (language: string, campos: Record<string, string>) => Promise<unknown>
  revisar: (language: string, d: { publish: boolean; comment?: string }) => Promise<unknown>
  borrar: (language: string) => Promise<unknown>
  /** Claves i18n propias (por defecto, las de la KB). */
  textos?: Partial<Record<ClaveDeTexto, string>>
  /** Avisa a quien contiene el panel (p. ej. el resumen de la pantalla de revisión). */
  alCambiar?: () => void
}

const TEXTOS_POR_DEFECTO: Record<ClaveDeTexto, string> = {
  titulo: 'traduccion_admin.kb_titulo',
  sin_versiones: 'traduccion_admin.kb_sin_versiones',
  desactivado: 'traduccion_admin.kb_desactivado',
  desfasada_ayuda: 'traduccion_admin.kb_desfasada_ayuda',
}

export const TIPO_DE_ESTADO: Record<EstadoDeVersionKb, StatusBadgeKind> = {
  draft: 'neutral',
  in_review: 'warning',
  published: 'success',
  rejected: 'danger',
}

export default function VersionesPanel({ adaptador }: { adaptador: AdaptadorDeVersiones }) {
  const { t, lang } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const idTitulo = useId()
  const texto = (k: ClaveDeTexto) => t(adaptador.textos?.[k] ?? TEXTOS_POR_DEFECTO[k])
  const mensajeDeError = (e: unknown) => errorDeTraduccion(t, extractErr(e, ''))
  const { data, isLoading, isError, error } = useQuery({ queryKey: adaptador.clave, queryFn: adaptador.listar })
  const [elegidos, setElegidos] = useState<string[]>([])
  const [fallos, setFallos] = useState<{ language: string; reason: string }[]>([])
  const [abierta, setAbierta] = useState<VersionGenerica | null>(null)

  const refrescar = () => { qc.invalidateQueries({ queryKey: adaptador.clave }); adaptador.alCambiar?.() }
  const generar = useMutation({
    mutationFn: (languages?: string[]) => adaptador.generar(languages),
    onSuccess: r => {
      setFallos(r.failed ?? [])
      setElegidos([])
      if (r.generated?.length) toast.success(t('traduccion_admin.kb_generadas', { n: r.generated.length }))
      refrescar()
    },
    onError: (e: unknown) => toast.error(mensajeDeError(e)),
  })
  const borrar = useMutation({
    mutationFn: (language: string) => adaptador.borrar(language),
    onSuccess: () => { refrescar(); toast.success(t('traduccion_admin.kb_borrada')) },
    onError: (e: unknown) => toast.error(mensajeDeError(e)),
  })

  if (isLoading) return <section className="trad-kb" aria-label={texto('titulo')}><Spinner /></section>
  if (isError || !data) {
    return (
      <section className="trad-kb" aria-label={texto('titulo')}>
        <p className="trad-kb__error" role="alert">{mensajeDeError(error)}</p>
      </section>
    )
  }

  const principal = adaptador.campos[0]?.clave
  const idiomas = data.languages.filter(l => l !== data.source_language)
  const alternar = (l: string) => setElegidos(s => s.includes(l) ? s.filter(x => x !== l) : [...s, l])

  return (
    <section className="trad-kb" aria-labelledby={idTitulo}>
      <div className="trad-kb__cabecera">
        <h3 id={idTitulo} className="trad-kb__titulo">
          <Languages size={15} aria-hidden="true" /> {texto('titulo')}
        </h3>
        {data.source_language && (
          <span className="trad-kb__origen">{t('traduccion_admin.kb_original_en', { idioma: nombreDeIdioma(data.source_language, lang) })}</span>
        )}
      </div>

      {!data.enabled ? (
        <p className="trad-kb__nota">{texto('desactivado')}</p>
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
        <p className="trad-kb__nota">{texto('sin_versiones')}</p>
      ) : (
        <ul className="trad-kb__lista">
          {data.items.map(v => (
            <li key={v.id} className="trad-kb__version">
              <div className="trad-kb__version-info">
                <span className="trad-kb__idioma">{nombreDeIdioma(v.language, lang)}</span>
                <StatusBadge kind={TIPO_DE_ESTADO[v.status] ?? 'neutral'}>{t(`traduccion_admin.kb_estado.${v.status}`)}</StatusBadge>
                {v.outdated && (
                  <StatusBadge kind="orange" title={texto('desfasada_ayuda')}>
                    {t('traduccion_admin.kb_desfasada')}
                  </StatusBadge>
                )}
                <span className="trad-kb__version-titulo">{principal ? v.campos[principal] : ''}</span>
              </div>
              <div className="trad-kb__version-acciones">
                <IconButton ariaLabel={t('traduccion_admin.kb_abrir_x', { idioma: nombreDeIdioma(v.language, lang) })} title={t('traduccion_admin.kb_abrir')} onClick={() => setAbierta(v)}>
                  <Eye size={14} aria-hidden="true" />
                </IconButton>
                <IconButton ariaLabel={t('traduccion_admin.kb_borrar_x', { idioma: nombreDeIdioma(v.language, lang) })} title={t('traduccion_admin.borrar')} onClick={async () => {
                  if (await confirmar({ title: t('traduccion_admin.kb_borrar_titulo'), message: t('traduccion_admin.kb_borrar_desc', { idioma: nombreDeIdioma(v.language, lang) }), danger: true })) borrar.mutate(v.language)
                }}>
                  <Trash2 size={14} aria-hidden="true" />
                </IconButton>
              </div>
            </li>
          ))}
        </ul>
      )}

      {abierta && (
        <ModalDeVersion
          adaptador={adaptador}
          version={abierta}
          original={data.original}
          puedeRevisar={data.can_review !== false}
          ayudaDesfasada={texto('desfasada_ayuda')}
          onClose={() => setAbierta(null)}
          onCambio={() => { refrescar(); setAbierta(null) }}
        />
      )}
    </section>
  )
}

export function ModalDeVersion({ adaptador, version, original, puedeRevisar = true, ayudaDesfasada, onClose, onCambio }: {
  adaptador: AdaptadorDeVersiones
  version: VersionGenerica
  original?: Record<string, string>
  puedeRevisar?: boolean
  ayudaDesfasada: string
  onClose: () => void
  onCambio: () => void
}) {
  const { t, lang } = useAppLang()
  const toast = useToast()
  const idBase = useId()
  const mensajeDeError = (e: unknown) => errorDeTraduccion(t, extractErr(e, ''))
  const inicial = Object.fromEntries(adaptador.campos.map(c => [c.clave, version.campos[c.clave] ?? '']))
  const [form, setForm] = useState<Record<string, string>>(inicial)
  const [comentario, setComentario] = useState('')
  const [rechazando, setRechazando] = useState(false)
  const cambiado = adaptador.campos.some(c => form[c.clave] !== inicial[c.clave])
  const faltaObligatorio = adaptador.campos.some(c => c.obligatorio && !(form[c.clave] ?? '').trim())

  const guardar = useMutation({
    mutationFn: () => adaptador.editar(version.language, form),
    onSuccess: () => { toast.success(t('traduccion_admin.kb_guardada')); onCambio() },
    onError: (e: unknown) => toast.error(mensajeDeError(e)),
  })
  const revisar = useMutation({
    mutationFn: (publish: boolean) => adaptador.revisar(version.language, publish ? { publish } : { publish, comment: comentario.trim() }),
    onSuccess: (_r, publish) => { toast.success(publish ? t('traduccion_admin.kb_publicada') : t('traduccion_admin.kb_rechazada')); onCambio() },
    onError: (e: unknown) => toast.error(mensajeDeError(e)),
  })
  const idioma = nombreDeIdioma(version.language, lang)

  return (
    <Modal open onClose={onClose} size="lg" title={t('traduccion_admin.kb_version_de', { idioma })}
      subtitle={<StatusBadge kind={TIPO_DE_ESTADO[version.status] ?? 'neutral'}>{t(`traduccion_admin.kb_estado.${version.status}`)}</StatusBadge>}>
      <div className="u-stack-14">
        {version.outdated && (
          <p className="trad-kb__aviso" role="note"><AlertTriangle size={13} aria-hidden="true" /> {ayudaDesfasada}</p>
        )}
        {version.status === 'rejected' && version.review_comment && (
          <p className="trad-kb__aviso" role="note">{t('traduccion_admin.kb_comentario_rechazo', { comentario: version.review_comment })}</p>
        )}
        {adaptador.campos.map((c, i) => (
          <div key={c.clave} className="u-stack-8" lang={version.language}>
            {c.multilinea ? (
              <FormField label={t(c.etiqueta)} required={c.obligatorio} hint={i === adaptador.campos.length - 1 && cambiado ? t('traduccion_admin.kb_editar_vuelve_a_revision') : undefined}>
                <Textarea id={`${idBase}-${c.clave}`} rows={8} value={form[c.clave] ?? ''} onChange={e => setForm(f => ({ ...f, [c.clave]: e.target.value }))} />
              </FormField>
            ) : (
              <Input id={`${idBase}-${c.clave}`} label={t(c.etiqueta)} required={c.obligatorio} value={form[c.clave] ?? ''}
                hint={i === adaptador.campos.length - 1 && cambiado ? t('traduccion_admin.kb_editar_vuelve_a_revision') : undefined}
                onChange={e => setForm(f => ({ ...f, [c.clave]: e.target.value }))} />
            )}
            {original?.[c.clave] && (
              <details className="trad-kb__original">
                <summary>{t('traduccion_admin.portal_ver_original')}</summary>
                <p className="trad-kb__original-texto">{original[c.clave]}</p>
              </details>
            )}
          </div>
        ))}

        {rechazando && (
          <FormField label={t('traduccion_admin.kb_comentario')} hint={t('traduccion_admin.kb_comentario_obligatorio')}>
            <Textarea id={`${idBase}-comentario`} rows={3} value={comentario} onChange={e => setComentario(e.target.value)} />
          </FormField>
        )}
        {!puedeRevisar && !cambiado && (
          <p className="trad-kb__nota">{t('traduccion_admin.portal_solo_revisores')}</p>
        )}

        <div className="trad-kb__pie">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          {cambiado ? (
            <Button onClick={() => guardar.mutate()} loading={guardar.isPending} disabled={faltaObligatorio}>
              {t('traduccion_admin.guardar')}
            </Button>
          ) : !puedeRevisar ? null : rechazando ? (
            <Button variant="danger" icon={<Undo2 size={14} />} disabled={!comentario.trim()} loading={revisar.isPending} onClick={() => revisar.mutate(false)}>
              {t('traduccion_admin.kb_confirmar_rechazo')}
            </Button>
          ) : (
            <>
              {version.status !== 'rejected' && version.status !== 'published' && (
                <Button variant="secondary" icon={<Undo2 size={14} />} onClick={() => setRechazando(true)}>{t('traduccion_admin.kb_rechazar')}</Button>
              )}
              {version.status !== 'published' && version.status !== 'rejected' && (
                <Button icon={<CheckCircle2 size={14} />} loading={revisar.isPending} onClick={() => revisar.mutate(true)}>{t('traduccion_admin.kb_publicar')}</Button>
              )}
            </>
          )}
        </div>
      </div>
    </Modal>
  )
}
