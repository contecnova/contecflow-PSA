/**
 * Adjunto de un mensaje del chat del portal (24-11-2026, docs/portal/CHAT_DEL_PORTAL.md).
 *
 * El fichero NUNCA llega por un enlace público: se pide a la API con la sesión
 * (que comprueba que participas en la conversación y eres de la misma empresa)
 * y se pinta desde un blob. Las imágenes salen en miniatura y se amplían en un
 * modal; el resto, como ficha con nombre, tamaño y botón de descarga. Un
 * adjunto en cuarentena (antivirus/DLP) se ve pero no se descarga.
 */
import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, Download, FileText } from 'lucide-react'
import { Button, IconButton, Modal, Pulsable } from '../ui'
import { downloadBlob } from '../../utils/helpers'
import type { PortalAdjuntoDeMensaje } from '../../services/api/tipos-alm'
import { tamanoLegible } from './chatDelPortalApi'

type T = (clave: string, vars?: Record<string, string | number>) => string

/** Lo mínimo de un adjunto (conversaciones gobernadas y chat de colaboración). */
type AdjuntoMinimo = Pick<PortalAdjuntoDeMensaje, 'id' | 'name' | 'mime_type' | 'size_bytes' | 'is_quarantined'> & { is_image?: boolean }

interface Props {
  adjunto: AdjuntoMinimo
  /** Pide el fichero a la API con la sesión (la API comprueba que participas). */
  cargar: (adjuntoId: string) => Promise<Blob>
  t: T
  onError: (e: unknown) => void
}

export default function AdjuntoDelChat({ adjunto, cargar, t, onError }: Props) {
  const [url, setUrl] = useState<string | null>(null)
  const [ampliada, setAmpliada] = useState(false)
  const [bajando, setBajando] = useState(false)
  // El cargador puede ser una función nueva en cada pintado: se lee de una ref
  // para no volver a pedir la imagen cada vez.
  const cargarRef = useRef(cargar)
  cargarRef.current = cargar
  const esImagen = (adjunto.is_image ?? (adjunto.mime_type || '').startsWith('image/')) && !adjunto.is_quarantined

  useEffect(() => {
    if (!esImagen) return undefined
    let vivo = true
    let creada: string | null = null
    cargarRef.current(adjunto.id)
      .then(blob => {
        if (!vivo) return
        creada = URL.createObjectURL(blob)
        setUrl(creada)
      })
      .catch(() => { /* accesorio: sin miniatura queda la ficha con su botón de descarga */ })
    return () => {
      vivo = false
      if (creada) URL.revokeObjectURL(creada)
    }
  }, [adjunto.id, esImagen])

  const descargar = async () => {
    setBajando(true)
    try {
      downloadBlob(await cargar(adjunto.id), adjunto.name)
    } catch (e) {
      onError(e)
    } finally {
      setBajando(false)
    }
  }

  if (adjunto.is_quarantined) {
    return (
      <div className="chat-portal-adjunto chat-portal-adjunto--cuarentena" role="note">
        <AlertTriangle size={14} aria-hidden="true" />
        <span className="chat-portal-adjunto__nombre">{adjunto.name}</span>
        <span>{t('governedconversations.adjunto_cuarentena')}</span>
      </div>
    )
  }

  if (esImagen && url) {
    return (
      <>
        <Pulsable className="chat-portal-adjunto__miniatura" onClick={() => setAmpliada(true)}
          aria-label={t('governedconversations.ver_imagen', { name: adjunto.name })}>
          <img src={url} alt={adjunto.name} loading="lazy" />
        </Pulsable>
        <Modal open={ampliada} onClose={() => setAmpliada(false)} title={adjunto.name} size="xl" avisarSinGuardar={false}>
          <div className="chat-portal-adjunto__ampliada">
            <img src={url} alt={adjunto.name} />
          </div>
          <div className="chat-portal-adjunto__acciones">
            <Button size="sm" variant="secondary" icon={<Download size={13} />} onClick={descargar} loading={bajando}>
              {t('governedconversations.descargar')}
            </Button>
          </div>
        </Modal>
      </>
    )
  }

  return (
    <div className="chat-portal-adjunto">
      <FileText size={15} aria-hidden="true" />
      <span className="chat-portal-adjunto__nombre" title={adjunto.name}>{adjunto.name}</span>
      <span className="chat-portal-adjunto__tamano">{tamanoLegible(adjunto.size_bytes)}</span>
      <IconButton variante="caja" tamano="xs" ariaLabel={t('governedconversations.descargar')} onClick={descargar} disabled={bajando}>
        <Download size={13} aria-hidden="true" />
      </IconButton>
    </div>
  )
}
