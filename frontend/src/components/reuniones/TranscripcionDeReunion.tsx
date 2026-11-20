/**
 * Transcripción por turnos (19-11-2026): marca `mm:ss`, hablante y texto.
 * El gestor puede renombrar un hablante («Hablante 1» → «Ana») o asignarlo a
 * una persona de la empresa; el cambio se aplica a todos los turnos con ese
 * mismo hablante. Si viene de la búsqueda, se resalta y se lleva a la vista el
 * turno encontrado.
 */
import { useEffect, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Check, MessageSquareText, Pencil, X } from 'lucide-react'
import { Button, Card, IconButton, Input, Section, UserSelect } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr, fmtDate } from '../../utils/helpers'
import { reunionesApi } from '../../services/api/reuniones'
import type { ReunionDetalle } from '../../services/api/reuniones'
import { CLAVES, mmss } from './comun'
import './Reuniones.css'

interface Props {
  reunion: ReunionDetalle
  /** Turno que hay que resaltar (resultado de la búsqueda). */
  segmentoResaltado?: string | null
}

export default function TranscripcionDeReunion({ reunion, segmentoResaltado }: Props) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [editando, setEditando] = useState<string | null>(null)
  const [nombre, setNombre] = useState('')
  const [persona, setPersona] = useState('')
  const refResaltado = useRef<HTMLLIElement | null>(null)
  const gestor = reunion.permissions.manage
  const segmentos = [...reunion.segments].sort((a, b) => a.order - b.order)

  useEffect(() => {
    if (segmentoResaltado && refResaltado.current) refResaltado.current.scrollIntoView?.({ block: 'center', behavior: 'smooth' })
  }, [segmentoResaltado, reunion.id])

  const renombrar = useMutation({
    mutationFn: async (c: { hablante: string | null; speaker: string; user_id: string | null }) => {
      const mismos = segmentos.filter(s => (s.speaker ?? '') === (c.hablante ?? ''))
      for (const s of mismos) {
        await reunionesApi.editarSegmento(reunion.id, s.id, { speaker: c.speaker, ...(c.user_id ? { user_id: c.user_id } : {}) })
      }
    },
    onSuccess: () => {
      setEditando(null)
      toast.success(t('reuniones.transcripcion.hablante_cambiado'))
      qc.invalidateQueries({ queryKey: CLAVES.detalle(reunion.id) })
    },
    onError: e => toast.error(extractErr(e)),
  })

  const abrirEdicion = (segId: string, hablante: string | null) => {
    setEditando(segId)
    setNombre(hablante ?? '')
    setPersona('')
  }

  return (
    <Card>
      <Section title={<span className="reu-seccion"><MessageSquareText size={16} aria-hidden />{t('reuniones.transcripcion.titulo')}</span>}>
        {reunion.transcript_purged ? (
          <p className="u-text3-xs">{t('reuniones.transcripcion.purgada')}</p>
        ) : segmentos.length === 0 ? (
          <p className="u-text3-xs">{t('reuniones.transcripcion.vacia')}</p>
        ) : (
          <>
            {reunion.transcript_expires_at && (
              <p className="u-text3-xs">{t('reuniones.transcripcion.caduca', { fecha: fmtDate(reunion.transcript_expires_at) })}</p>
            )}
            <ol className="reu-transcripcion">
              {segmentos.map(s => {
                const resaltado = s.id === segmentoResaltado
                return (
                  <li key={s.id} ref={resaltado ? refResaltado : undefined}
                    className={`reu-turno${resaltado ? ' reu-turno--resaltado' : ''}`}>
                    <span className="reu-turno__marca">{mmss(s.start_ms)}</span>
                    <div className="u-flex1-min0">
                      {editando === s.id ? (
                        <div className="reu-turno__edicion">
                          <Input aria-label={t('reuniones.transcripcion.nombre_hablante')} value={nombre} onChange={e => setNombre(e.target.value)} autoFocus />
                          <UserSelect value={persona} placeholder={t('reuniones.transcripcion.persona_opcional')}
                            onChange={(id, u) => { setPersona(id); if (u?.full_name) setNombre(u.full_name) }} />
                          <IconButton ariaLabel={t('common.save')} disabled={!nombre.trim() || renombrar.isPending}
                            onClick={() => renombrar.mutate({ hablante: s.speaker, speaker: nombre.trim(), user_id: persona || null })}>
                            <Check size={14} aria-hidden />
                          </IconButton>
                          <IconButton ariaLabel={t('common.cancel')} onClick={() => setEditando(null)}><X size={14} aria-hidden /></IconButton>
                        </div>
                      ) : (
                        <div className="reu-turno__cab">
                          <span className="reu-turno__hablante">{s.speaker || t('reuniones.transcripcion.sin_hablante')}</span>
                          {gestor && (
                            <Button variant="ghost" size="xs" icon={<Pencil size={12} />} aria-label={t('reuniones.transcripcion.renombrar')}
                              onClick={() => abrirEdicion(s.id, s.speaker)}>
                              {t('reuniones.transcripcion.renombrar')}
                            </Button>
                          )}
                        </div>
                      )}
                      <p className="reu-turno__texto">{s.text}</p>
                    </div>
                  </li>
                )
              })}
            </ol>
          </>
        )}
      </Section>
    </Card>
  )
}
