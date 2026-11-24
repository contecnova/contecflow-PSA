/**
 * Seguimiento de una pregunta sin respuesta de la base de conocimiento (23-11-2026).
 *
 * Lo que contecmind ya tenía: la pregunta es trabajo con dueño y fecha.
 *  - responsable, plazo y estado (pendiente, en curso, hecho), con aviso al responsable;
 *  - «Convertir en tarea»: una tarea en el proyecto elegido, asignada al responsable;
 *  - el artículo que la responderá: al PUBLICARLO, la pregunta y su tarea se cierran solas.
 * Endpoints: PATCH /sd/kb/gaps/{id}/seguimiento, POST …/tarea, PUT …/articulo (`sd.completo`).
 */
import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { CalendarClock, ClipboardList, Link2, UserRound } from 'lucide-react'
import { sdKbApi } from '../../services/api'
import type { SdCalidadKb } from '../../services/api/tipos-sd'
import { Button, Modal, Select, UserSelect } from '../ui'
import DateInput from '../ui/DateInput'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr, fmtDate } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { useListaDeProyectos } from '../../hooks/useListas'

type Hueco = SdCalidadKb['gaps'][number]
const ESTADOS = ['pendiente', 'en_curso', 'hecho'] as const

export default function SeguimientoDeHueco({ h, onCambio }: { h: Hueco; onCambio: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const [abierto, setAbierto] = useState<'seguimiento' | 'tarea' | 'articulo' | null>(null)
  const [owner, setOwner] = useState(h.owner_id ?? '')
  const [plazo, setPlazo] = useState(h.due_date ?? '')
  const [estado, setEstado] = useState<string>(h.follow_status ?? 'pendiente')
  const [proyecto, setProyecto] = useState('')
  const [articulo, setArticulo] = useState(h.article_id ?? '')
  const { data: proyectos = [] } = useListaDeProyectos(undefined, { enabled: abierto === 'tarea' })
  const articulos = useQuery({ queryKey: ['sd-kb', 'para-hueco'], queryFn: () => sdKbApi.list().then(r => r.data), enabled: abierto === 'articulo' })
  const hecho = () => { setAbierto(null); onCambio(); toast.success(t('kb_hueco.guardado')) }
  const fallo = (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  const guardar = useMutation({
    mutationFn: () => sdKbApi.gapFollowUp(h.id, { owner_id: owner || null, due_date: plazo || null, follow_status: estado }),
    onSuccess: hecho, onError: fallo,
  })
  const tarea = useMutation({
    mutationFn: () => sdKbApi.gapToTask(h.id, { project_id: proyecto, owner_id: owner || null, due_date: plazo || null }),
    onSuccess: hecho, onError: fallo,
  })
  const enlazar = useMutation({ mutationFn: () => sdKbApi.gapArticle(h.id, articulo || null), onSuccess: hecho, onError: fallo })
  const vencida = !!h.due_date && h.follow_status !== 'hecho' && h.due_date < new Date().toISOString().slice(0, 10)
  return (
    <>
      <div className="itk-q-meta">
        <UserRound size={12} aria-hidden /> {h.owner_name || t('kb_hueco.sin_responsable')}
        {h.due_date && <> · <CalendarClock size={12} aria-hidden /> <span className={vencida ? 'u-danger' : undefined}>{fmtDate(h.due_date)}</span></>}
        {' · '}{t(`kb_hueco.estado_${h.follow_status || 'pendiente'}`)}
        {h.task_id && <> · <ClipboardList size={12} aria-hidden /> {t('kb_hueco.con_tarea')}</>}
        {h.article_number && <> · <Link2 size={12} aria-hidden /> {h.article_number}</>}
      </div>
      <div className="itk-q-actions">
        <Button size="xs" variant="ghost" onClick={() => setAbierto('seguimiento')}>{t('kb_hueco.seguimiento')}</Button>
        {!h.task_id && <Button size="xs" variant="ghost" icon={<ClipboardList size={12} />} onClick={() => setAbierto('tarea')}>{t('kb_hueco.convertir_en_tarea')}</Button>}
        <Button size="xs" variant="ghost" icon={<Link2 size={12} />} onClick={() => setAbierto('articulo')}>{t('kb_hueco.enlazar_articulo')}</Button>
      </div>
      {abierto && (
        <Modal open onClose={() => setAbierto(null)} size="sm" title={t(`kb_hueco.titulo_${abierto}`)} subtitle={h.question.slice(0, 160)}>
          <form className="u-stack-12" onSubmit={e => {
            e.preventDefault()
            if (abierto === 'seguimiento') guardar.mutate()
            else if (abierto === 'tarea' && proyecto) tarea.mutate()
            else if (abierto === 'articulo') enlazar.mutate()
          }}>
            {abierto !== 'articulo' && (
              <>
                <UserSelect value={owner} onChange={(uid: string) => setOwner(uid)} placeholder={t('kb_hueco.responsable')} />
                <DateInput aria-label={t('kb_hueco.plazo')} value={plazo} onChange={e => setPlazo(e.target.value)} />
              </>
            )}
            {abierto === 'seguimiento' && (
              <Select suelto placeholder={false} aria-label={t('kb_hueco.estado')} value={estado} onChange={e => setEstado(e.target.value)}>
                {ESTADOS.map(s => <option key={s} value={s}>{t(`kb_hueco.estado_${s}`)}</option>)}
              </Select>
            )}
            {abierto === 'tarea' && (
              <Select suelto placeholder={false} aria-label={t('kb_hueco.proyecto')} value={proyecto} onChange={e => setProyecto(e.target.value)} required>
                <option value="">{t('kb_hueco.elige_proyecto')}</option>
                {proyectos.map(p => <option key={p.id} value={p.id}>{p.code ? `${p.code} — ${p.name}` : p.name}</option>)}
              </Select>
            )}
            {abierto === 'articulo' && (
              <>
                <div className="u-text3-xs">{t('kb_hueco.articulo_ayuda')}</div>
                <Select suelto placeholder={false} aria-label={t('kb_hueco.articulo')} value={articulo} onChange={e => setArticulo(e.target.value)}>
                  <option value="">{t('kb_hueco.sin_articulo')}</option>
                  {(articulos.data ?? []).map(a => <option key={a.id} value={a.id}>{`${a.number} — ${a.title}`}</option>)}
                </Select>
              </>
            )}
            <div className="u-row-8">
              <Button type="submit" loading={guardar.isPending || tarea.isPending || enlazar.isPending} disabled={abierto === 'tarea' && !proyecto}>
                {t(abierto === 'tarea' ? 'kb_hueco.crear_tarea' : 'kb_hueco.guardar')}
              </Button>
              <Button type="button" variant="ghost" onClick={() => setAbierto(null)}>{t('common.cancel')}</Button>
            </div>
          </form>
        </Modal>
      )}
    </>
  )
}
