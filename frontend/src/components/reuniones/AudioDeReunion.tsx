/**
 * Audio de una reunión grabada (19-11-2026): solo para quien puede escucharlo
 * (`permissions.listen`: asistentes o `reuniones.ver_todas`). Cada escucha y
 * cada descarga quedan auditadas en el servidor. El gestor puede borrar todo
 * el audio (la transcripción y el análisis se quedan). El audio caduca según
 * la retención de la empresa.
 */
import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, Headphones, Play, Trash2 } from 'lucide-react'
import { Button, Card, Section, Spinner } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { confirmar } from '../../context/ConfirmContext'
import { downloadBlob, extractErr, fmtDate } from '../../utils/helpers'
import { reunionesApi } from '../../services/api/reuniones'
import type { ReunionDetalle, TrozoDeAudio } from '../../services/api/reuniones'
import { CLAVES, mmss, tamano } from './comun'
import './Reuniones.css'

export default function AudioDeReunion({ reunion }: { reunion: ReunionDetalle }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [sonando, setSonando] = useState<{ id: string; url: string } | null>(null)
  const [cargando, setCargando] = useState<string | null>(null)
  const urlRef = useRef<string | null>(null)

  const { data: trozos = [], isLoading } = useQuery({
    queryKey: CLAVES.audio(reunion.id),
    queryFn: () => reunionesApi.audio(reunion.id),
  })

  // Liberar el object URL al cambiar de trozo o al salir.
  useEffect(() => () => { if (urlRef.current) URL.revokeObjectURL(urlRef.current) }, [])

  const escuchar = async (tr: TrozoDeAudio) => {
    setCargando(tr.id)
    try {
      const blob = await reunionesApi.trozo(reunion.id, tr.id, false)
      if (urlRef.current) URL.revokeObjectURL(urlRef.current)
      const url = URL.createObjectURL(blob)
      urlRef.current = url
      setSonando({ id: tr.id, url })
    } catch (e) {
      toast.error(extractErr(e))
    } finally {
      setCargando(null)
    }
  }

  const descargar = async (tr: TrozoDeAudio) => {
    setCargando(tr.id)
    try {
      const blob = await reunionesApi.trozo(reunion.id, tr.id, true)
      const ext = (tr.mime || 'audio/webm').includes('ogg') ? 'ogg' : 'webm'
      downloadBlob(blob, `reunion-${reunion.id}-trozo-${tr.seq}.${ext}`)
    } catch (e) {
      toast.error(extractErr(e))
    } finally {
      setCargando(null)
    }
  }

  const borrar = useMutation({
    mutationFn: () => reunionesApi.borrarAudio(reunion.id),
    onSuccess: () => {
      setSonando(null)
      toast.success(t('reuniones.audio.borrado'))
      qc.invalidateQueries({ queryKey: CLAVES.audio(reunion.id) })
      qc.invalidateQueries({ queryKey: CLAVES.detalle(reunion.id) })
      qc.invalidateQueries({ queryKey: CLAVES.lista })
    },
    onError: e => toast.error(extractErr(e)),
  })

  return (
    <Card>
      <Section
        title={<span className="reu-seccion"><Headphones size={16} aria-hidden />{t('reuniones.audio.titulo')}</span>}
        subtitle={reunion.audio?.expires_at ? t('reuniones.audio.caduca', { fecha: fmtDate(reunion.audio.expires_at) }) : undefined}
        actions={reunion.permissions.manage && trozos.length > 0 ? (
          <Button size="sm" variant="danger" icon={<Trash2 size={14} />} disabled={reunion.legal_hold} loading={borrar.isPending}
            onClick={async () => { if (await confirmar({ title: t('reuniones.audio.borrar_titulo'), message: t('reuniones.audio.borrar_desc'), danger: true })) borrar.mutate() }}>
            {t('reuniones.audio.borrar')}
          </Button>
        ) : undefined}
      >
        <p className="u-text3-xs">{t('reuniones.audio.auditado')}</p>
        {sonando && (
          <audio className="reu-audio" controls autoPlay src={sonando.url}>
            <track kind="captions" />
          </audio>
        )}
        {isLoading ? <Spinner /> : trozos.length === 0 ? <p className="u-text3-xs">{t('reuniones.audio.vacio')}</p> : (
          <ul className="reu-lista">
            {trozos.map(tr => (
              <li key={tr.id} className={`reu-trozo${sonando?.id === tr.id ? ' reu-trozo--activo' : ''}`}>
                <span className="reu-turno__marca">{mmss(tr.offset_ms)}</span>
                <span className="u-flex1-min0 u-text3-xs">{t('reuniones.audio.trozo', { n: tr.seq + 1 })} · {tamano(tr.bytes)}</span>
                <Button size="xs" variant="secondary" icon={<Play size={12} />} loading={cargando === tr.id} onClick={() => { void escuchar(tr) }}>
                  {t('reuniones.audio.escuchar')}
                </Button>
                <Button size="xs" variant="ghost" icon={<Download size={12} />} disabled={cargando === tr.id} onClick={() => { void descargar(tr) }}>
                  {t('reuniones.audio.descargar')}
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </Card>
  )
}
