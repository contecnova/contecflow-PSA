/**
 * TextoTraducido — un texto guardado, en el idioma de quien mira (traducción en tiempo
 * real, 16-11-2026).
 *
 * - `translated` + `auto`: la traducción, con la marca «Traducido automáticamente del X»
 *   y «Ver original» (y vuelta).
 * - `translated` + `author`: lo que escribió el agente (en su idioma); «Ver lo enviado al
 *   cliente» enseña la versión que recibió el cliente (el texto guardado).
 * - `translated` + `system`: texto del sistema en el idioma de quien mira, sin marca.
 * - `unavailable`: el original con el aviso del motivo.
 * - `same_language`, `disabled` o sin resultado: el original, sin nada más.
 */
import { useState } from 'react'
import { AlertTriangle, Languages } from 'lucide-react'
import { useAppLang } from '../../i18n/AppLangContext'
import { motivoDeTraduccion, nombreDeIdioma } from '../../hooks/useTraduccion'
import type { MensajeTraducido } from '../../services/api/traduccion'
import './traduccion.css'
import { Pulsable } from '../ui'

interface Props {
  /** El texto guardado (lo que escribió el cliente o lo que recibió). */
  original: string
  traduccion?: MensajeTraducido | null
  /** Clase del contenedor del texto (p. ej. la del cuerpo del comentario). */
  className?: string
  /** Mientras se pide la traducción. */
  cargando?: boolean
}

export default function TextoTraducido({ original, traduccion, className, cargando }: Props) {
  const { t, lang } = useAppLang()
  const [verOriginal, setVerOriginal] = useState(false)
  const estado = traduccion?.status
  const hayTraduccion = estado === 'translated' && !!traduccion?.text
  const origen = traduccion?.origin ?? 'auto'

  if (!hayTraduccion) {
    return (
      <div className="trad-bloque">
        <div className={className}>{original}</div>
        {estado === 'unavailable' && (
          <div className="trad-aviso" role="note">
            <AlertTriangle size={12} aria-hidden="true" />
            <span>{t('traduccion.no_disponible', { motivo: motivoDeTraduccion(t, traduccion?.reason) })}</span>
          </div>
        )}
        {cargando && <div className="trad-marca" aria-live="polite">{t('traduccion.traduciendo')}</div>}
      </div>
    )
  }

  if (origen === 'system') return <div className={className}>{traduccion?.text}</div>

  const idiomaOrigen = nombreDeIdioma(traduccion?.source_language, lang)
  const mostrado = verOriginal ? original : (traduccion?.text ?? original)
  const marca = origen === 'author'
    ? (verOriginal
      ? t('traduccion.marca_enviado', { idioma: idiomaOrigen })
      : t('traduccion.marca_autor', { idioma: idiomaOrigen }))
    : (verOriginal
      ? t('traduccion.marca_original', { idioma: idiomaOrigen })
      : t('traduccion.marca_auto', { idioma: idiomaOrigen }))
  const alternar = origen === 'author'
    ? (verOriginal ? t('traduccion.ver_mio') : t('traduccion.ver_enviado'))
    : (verOriginal ? t('traduccion.ver_traduccion') : t('traduccion.ver_original'))

  return (
    <div className="trad-bloque">
      <div className={className} lang={verOriginal ? traduccion?.source_language ?? undefined : traduccion?.target_language}>{mostrado}</div>
      <div className="trad-marca">
        <Languages size={12} aria-hidden="true" />
        <span>{marca}</span>
        <Pulsable className="trad-enlace" aria-pressed={verOriginal} onClick={() => setVerOriginal(v => !v)}>
          {alternar}
        </Pulsable>
      </div>
    </div>
  )
}
