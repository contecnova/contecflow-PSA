/**
 * VistaPreviaDeSalida — lo que el operador envía al cliente, en el idioma del cliente
 * (traducción en tiempo real, 16-11-2026). Solo para respuestas PÚBLICAS: las notas
 * internas no salen nunca al cliente y no pasan por aquí.
 *
 * - «Vista previa en el idioma del cliente» pide `/translation/outbound/preview`.
 * - Enseña el idioma destino y de dónde sale (contacto, portal, detectado o elegido),
 *   con un selector para cambiarlo (todos los idiomas de la configuración).
 * - La traducción se puede corregir antes de enviar (textarea editable).
 * - Avisa si no hay traducción (motivo traducido), si no se sabe el idioma del
 *   cliente y si el cliente también recibirá el original (`include_original`).
 * - Si el operador cambia su texto después de previsualizar, la vista previa queda
 *   desfasada: se avisa, se pide regenerarla y no se expone (nunca se envía la
 *   traducción de otro texto).
 *
 * Al padre le llega `{ client_text, client_language }` (o `null` si no aplica, se
 * descarta o está desfasada) y si está desfasada (para no dejar enviar).
 */
import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { AlertTriangle, Info, Languages, RefreshCw, X } from 'lucide-react'
import { Button, Select } from '../ui'
import { useAppLang } from '../../i18n/AppLangContext'
import { errorDeTraduccion, motivoDeTraduccion, nombreDeIdioma, useConfigDeTraduccion } from '../../hooks/useTraduccion'
import { traduccionApi, type VistaPrevia } from '../../services/api/traduccion'
import { extractErr } from '../../utils/helpers'
import './traduccion.css'
import './VistaPreviaDeSalida.css'

export interface SalidaAlCliente { client_text: string; client_language: string }
export interface EstadoDeLaSalida { desfasada: boolean }

interface Props {
  contextType: 'ticket' | 'conversation'
  contextId: string
  /** Lo que ha escrito el operador (su idioma). */
  texto: string
  onChange: (salida: SalidaAlCliente | null, estado: EstadoDeLaSalida) => void
}

export default function VistaPreviaDeSalida({ contextType, contextId, texto, onChange }: Props) {
  const { t, lang } = useAppLang()
  const idSelector = useId()
  const idTexto = useId()
  const { data: config } = useConfigDeTraduccion()
  const [vista, setVista] = useState<VistaPrevia | null>(null)
  /** El texto del operador que se previsualizó (para saber si quedó desfasada). */
  const [base, setBase] = useState('')
  const [editada, setEditada] = useState('')
  /** Idioma elegido a mano: se mantiene al regenerar. */
  const [destinoManual, setDestinoManual] = useState<string | undefined>(undefined)
  const [error, setError] = useState('')

  const descartar = () => {
    setVista(null); setBase(''); setEditada(''); setError(''); setDestinoManual(undefined)
  }

  const pedir = useMutation({
    mutationFn: (v: { texto: string; destino?: string }) =>
      traduccionApi.vistaPrevia({ context_type: contextType, context_id: contextId, text: v.texto, target_language: v.destino }),
    onMutate: () => setError(''),
    onSuccess: (r, v) => { setVista(r); setBase(v.texto); setEditada(r.text ?? '') },
    onError: e => setError(errorDeTraduccion(t, extractErr(e, ''))),
  })

  // Otro ticket o conversación, o el texto vaciado (p. ej. tras enviar): empieza de cero.
  useEffect(() => { descartar() }, [contextType, contextId])
  useEffect(() => { if (!texto.trim()) descartar() }, [texto])

  const desfasada = !!vista && base.trim() !== texto.trim()
  const valido = !!vista && !desfasada && vista.status === 'translated' && !!vista.target_language && editada.trim().length > 0
  const clientText = valido ? editada : null
  const clientLanguage = valido ? vista?.target_language ?? null : null

  const avisar = useRef(onChange)
  avisar.current = onChange
  useEffect(() => {
    avisar.current(clientText && clientLanguage ? { client_text: clientText, client_language: clientLanguage } : null, { desfasada })
  }, [clientText, clientLanguage, desfasada])
  // Al desmontarse (p. ej. pasa a nota interna) no queda nada que enviar.
  useEffect(() => () => avisar.current(null, { desfasada: false }), [])

  const idiomas = useMemo(() => {
    const lista = [...(config?.languages ?? [])]
    if (vista?.target_language && !lista.includes(vista.target_language)) lista.push(vista.target_language)
    return lista.sort((a, b) => nombreDeIdioma(a, lang).localeCompare(nombreDeIdioma(b, lang), lang))
  }, [config?.languages, vista?.target_language, lang])

  if (!config?.enabled) return null

  const generar = (destino = destinoManual) => pedir.mutate({ texto, destino })
  const cambiarIdioma = (codigo: string) => {
    if (!codigo) return
    setDestinoManual(codigo)
    generar(codigo)
  }

  const nombreDestino = nombreDeIdioma(vista?.target_language, lang)
  const procedencia = vista?.target_source ? t(`traduccion_ui.procedencia.${vista.target_source}`) : ''
  const sinIdioma = !!vista && !vista.target_language
  const noDisponible = !!vista && !sinIdioma && (vista.status === 'unavailable' || vista.status === 'disabled' || !vista.enabled)
  const motivo = vista && !vista.enabled && !vista.reason ? 'channel_disabled' : vista?.reason

  return (
    <div className="trad-salida" aria-busy={pedir.isPending}>
      <div className="trad-salida__barra">
        <Button size="xs" variant="secondary" onClick={() => generar()} disabled={!texto.trim()} loading={pedir.isPending}
          icon={vista ? <RefreshCw size={14} aria-hidden="true" /> : <Languages size={14} aria-hidden="true" />}>
          {vista ? t('traduccion_ui.regenerar') : t('traduccion_ui.vista_previa')}
        </Button>
        {vista && (
          <Button size="xs" variant="ghost" onClick={descartar} icon={<X size={14} aria-hidden="true" />}>
            {t('traduccion_ui.descartar')}
          </Button>
        )}
      </div>

      {error && (
        <div className="trad-aviso" role="alert">
          <AlertTriangle size={12} aria-hidden="true" />
          <span>{error}</span>
        </div>
      )}

      {vista && (
        <>
          <div className="trad-salida__idioma">
            <span className="trad-salida__destino">
              {sinIdioma
                ? t('traduccion_ui.idioma_desconocido')
                : t('traduccion_ui.idioma_cliente', { idioma: nombreDestino, procedencia })}
            </span>
            <label htmlFor={idSelector} className="trad-salida__etiqueta">{t('traduccion_ui.enviar_en')}</label>
            <Select suelto id={idSelector} className="ds-input trad-salida__select" value={vista.target_language ?? ''}
              disabled={pedir.isPending} onChange={e => cambiarIdioma(e.target.value)} placeholder={false}>
              {!vista.target_language && <option value="">{t('traduccion_ui.elegir_idioma')}</option>}
              {idiomas.map(c => <option key={c} value={c}>{nombreDeIdioma(c, lang)}</option>)}
            </Select>
          </div>

          {desfasada && (
            <div className="trad-aviso" role="alert">
              <AlertTriangle size={12} aria-hidden="true" />
              <span>{t('traduccion_ui.desfasada')}</span>
            </div>
          )}

          {noDisponible && (
            <div className="trad-aviso" role="note">
              <AlertTriangle size={12} aria-hidden="true" />
              <span>{t('traduccion_ui.no_disponible', { motivo: motivoDeTraduccion(t, motivo) })}</span>
            </div>
          )}

          {!noDisponible && vista.status === 'same_language' && (
            <div className="trad-nota" role="note">
              <Info size={12} aria-hidden="true" />
              <span>{t('traduccion_ui.mismo_idioma')}</span>
            </div>
          )}

          {!noDisponible && vista.status === 'translated' && (
            <div className="trad-salida__campo">
              <label htmlFor={idTexto} className="trad-salida__etiqueta">{t('traduccion_ui.lo_que_recibira')}</label>
              <textarea id={idTexto} className="ds-input trad-salida__texto" rows={3} lang={vista.target_language ?? undefined}
                value={editada} onChange={e => setEditada(e.target.value)} aria-invalid={desfasada || !editada.trim()} />
              {!editada.trim() && (
                <div className="trad-aviso" role="note">
                  <AlertTriangle size={12} aria-hidden="true" />
                  <span>{t('traduccion_ui.traduccion_vacia')}</span>
                </div>
              )}
              {vista.include_original && (
                <div className="trad-nota" role="note">
                  <Info size={12} aria-hidden="true" />
                  <span>{t('traduccion_ui.incluye_original')}</span>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
