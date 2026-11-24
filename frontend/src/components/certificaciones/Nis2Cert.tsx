/**
 * Obligaciones regulatorias NIS2 (§3.8): incidente notificable enlazado a un ticket del Service
 * Desk con los relojes de 24 h (alerta temprana), 72 h (notificación) y 1 mes (informe final),
 * plantillas de notificación a la autoridad y registro de comunicaciones.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, Send, Siren } from 'lucide-react'
import { Button, Card, Checkbox, Input, Modal, SelectRico, Tabla, Textarea } from '../ui'
import { useAppLang, useAppT } from '../../i18n/AppLangContext'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { extractErr, fmtDateTime } from '../../utils/helpers'
import { CLAVES_CERT, certApi } from '../../services/api/certificaciones'
import type { Incidente, Reloj } from '../../services/api/certificaciones'
import { Estado } from './comun'
import type { PropsDePestana } from './comun'

const TIPOS = ['alerta_temprana', 'notificacion', 'informe_intermedio', 'informe_final', 'otra']

function CeldaReloj({ reloj }: { reloj: Reloj }) {
  const t = useAppT()
  const horas = reloj.segundos_restantes == null ? null : Math.round(reloj.segundos_restantes / 3600)
  return (
    <div className="cert-reloj">
      <Estado valor={reloj.estado} />
      <span className="cert-apagado">{fmtDateTime(reloj.plazo)}</span>
      {horas != null && reloj.estado === 'pendiente' && <span className="cert-apagado">{t('cert.quedan_horas', { n: horas })}</span>}
    </div>
  )
}

export default function Nis2Cert({ programaId }: PropsDePestana) {
  const t = useAppT()
  const { puede } = useAuth()
  const gestionar = puede('certificaciones.gestionar')
  const { data = [], isLoading } = useQuery({ queryKey: CLAVES_CERT.incidentes, queryFn: certApi.incidentes })
  const [nuevo, setNuevo] = useState(false)
  const [abierto, setAbierto] = useState<string | null>(null)
  return (
    <div className="u-stack-12">
      <p className="cert-apagado">{t('cert.nis2_ayuda')}</p>
      {gestionar && <div className="cert-acciones"><Button icon={<Plus size={14} />} onClick={() => setNuevo(true)}>{t('cert.incidente_nuevo')}</Button></div>}
      <Tabla<Incidente> etiqueta={t('cert.incidentes')} filas={data} cargando={isLoading} onFila={i => setAbierto(i.id)}
        vacio={{ icono: <Siren size={28} />, titulo: t('cert.sin_incidentes') }}
        columnas={[
          { key: 'codigo', label: t('cert.codigo'), cabeceraDeFila: true },
          { key: 'titulo', label: t('cert.titulo'), render: (_v, i) => (
            <div className="cert-celda"><span>{i.titulo}</span>{i.ticket && <span className="cert-apagado">{i.ticket.number}</span>}</div>) },
          { key: 'detectado_en', label: t('cert.detectado'), render: (_v, i) => fmtDateTime(i.detectado_en) },
          { key: 'alerta', label: t('cert.reloj_alerta'), sortable: false, render: (_v, i) => <CeldaReloj reloj={i.relojes.alerta} /> },
          { key: 'notificacion', label: t('cert.reloj_notificacion'), sortable: false, render: (_v, i) => <CeldaReloj reloj={i.relojes.notificacion} /> },
          { key: 'informe_final', label: t('cert.reloj_informe_final'), sortable: false, render: (_v, i) => <CeldaReloj reloj={i.relojes.informe_final} /> },
          { key: 'estado', label: t('cert.estado'), render: (_v, i) => t(`cert.nis2_estado_${i.estado}`) },
        ]} />
      {nuevo && <NuevoIncidente programaId={programaId} onClose={() => setNuevo(false)} />}
      {abierto && <FichaIncidente id={abierto} onClose={() => setAbierto(null)} />}
    </div>
  )
}

function NuevoIncidente({ programaId, onClose }: { programaId: string; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [d, setD] = useState({ ticket: '', titulo: '', descripcion: '', impacto: '', detectado_en: '', significativo: true,
    transfronterizo: false })
  const crear = useMutation({
    mutationFn: () => certApi.crearIncidente({ ...d, ticket: d.ticket || undefined, detectado_en: d.detectado_en || undefined,
      programa_id: programaId || undefined }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: CLAVES_CERT.todo }); onClose() },
    onError: e => toast.error(extractErr(e)),
  })
  return (
    <Modal open title={t('cert.incidente_nuevo')} subtitle={t('cert.incidente_ayuda')} onClose={onClose} size="lg"
      cambiosSinGuardar={!!(d.titulo || d.ticket)}>
      <div className="u-stack-12">
        <div className="cert-rejilla">
          <Input label={t('cert.ticket')} value={d.ticket} hint={t('cert.ticket_ayuda')} onChange={e => setD({ ...d, ticket: e.target.value })} />
          <Input label={t('cert.detectado')} type="datetime-local" value={d.detectado_en}
            onChange={e => setD({ ...d, detectado_en: e.target.value })} hint={t('cert.detectado_ayuda')} />
        </div>
        <Input label={t('cert.titulo')} value={d.titulo} onChange={e => setD({ ...d, titulo: e.target.value })} />
        <Textarea label={t('cert.descripcion')} value={d.descripcion} onChange={e => setD({ ...d, descripcion: e.target.value })} />
        <Textarea label={t('cert.impacto')} value={d.impacto} onChange={e => setD({ ...d, impacto: e.target.value })} />
        <Checkbox checked={d.significativo} label={t('cert.significativo')} onChange={v => setD({ ...d, significativo: v })} />
        <Checkbox checked={d.transfronterizo} label={t('cert.transfronterizo')} onChange={v => setD({ ...d, transfronterizo: v })} />
        <div className="cert-acciones">
          <Button disabled={!d.titulo.trim() && !d.ticket.trim()} loading={crear.isPending} onClick={() => crear.mutate()}>{t('cert.crear')}</Button>
          <Button variant="secondary" onClick={onClose}>{t('cert.cancelar')}</Button>
        </div>
      </div>
    </Modal>
  )
}

function FichaIncidente({ id, onClose }: { id: string; onClose: () => void }) {
  const t = useAppT()
  const { lang } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const { puede } = useAuth()
  const { data: inc } = useQuery({ queryKey: ['cert', 'incidente', id], queryFn: () => certApi.incidente(id) })
  const [c, setC] = useState({ tipo: 'alerta_temprana', destinatario: '', asunto: '', contenido: '', referencia: '' })
  const cargarPlantilla = useMutation({
    mutationFn: () => certApi.plantillaNis2(id, c.tipo, lang),
    onSuccess: p => setC(x => ({ ...x, asunto: p.asunto, contenido: p.contenido })), onError: e => toast.error(extractErr(e)),
  })
  const enviar = useMutation({
    mutationFn: () => certApi.comunicar(id, c),
    onSuccess: () => { qc.invalidateQueries({ queryKey: CLAVES_CERT.todo }); qc.invalidateQueries({ queryKey: ['cert', 'incidente', id] });
      toast.success(t('cert.comunicacion_registrada')); setC({ ...c, asunto: '', contenido: '', referencia: '' }) },
    onError: e => toast.error(extractErr(e)),
  })
  if (!inc) return null
  return (
    <Modal open title={`${inc.codigo} · ${inc.titulo}`} subtitle={inc.autoridad ?? undefined} onClose={onClose} size="xl"
      cambiosSinGuardar={!!c.contenido}>
      <div className="u-stack-16">
        <div className="cert-rejilla">
          {(['alerta', 'notificacion', 'informe_final'] as const).map(k => (
            <Card key={k}><h4 className="cert-bloque__titulo">{t(`cert.reloj_${k}`)}</h4><CeldaReloj reloj={inc.relojes[k]} /></Card>))}
        </div>
        <Card>
          <h3 className="cert-bloque__titulo">{t('cert.comunicaciones')}</h3>
          <Tabla etiqueta={t('cert.comunicaciones')} filas={inc.comunicaciones ?? []} vacio={{ titulo: t('cert.sin_comunicaciones') }}
            columnas={[
              { key: 'enviado_en', label: t('cert.cuando'), render: (_v, x) => fmtDateTime(x.enviado_en) },
              { key: 'tipo', label: t('cert.tipo'), render: (_v, x) => t(`cert.comunicacion_${x.tipo}`) },
              { key: 'destinatario', label: t('cert.destinatario'), render: (_v, x) => x.destinatario || '—' },
              { key: 'referencia', label: t('cert.referencia'), render: (_v, x) => x.referencia || '—' },
              { key: 'enviado_por', label: t('cert.enviado_por'), render: (_v, x) => x.enviado_por || '—' },
            ]} />
        </Card>
        {puede('certificaciones.gestionar') && (
          <Card>
            <h3 className="cert-bloque__titulo"><Send size={16} aria-hidden />{t('cert.registrar_comunicacion')}</h3>
            <div className="cert-rejilla">
              <SelectRico label={t('cert.tipo')} valor={c.tipo} onChange={v => setC({ ...c, tipo: v })}
                opciones={TIPOS.map(x => ({ valor: x, etiqueta: t(`cert.comunicacion_${x}`) }))} />
              <Input label={t('cert.destinatario')} value={c.destinatario} placeholder={inc.autoridad ?? ''}
                onChange={e => setC({ ...c, destinatario: e.target.value })} />
              <Input label={t('cert.referencia')} value={c.referencia} onChange={e => setC({ ...c, referencia: e.target.value })} />
            </div>
            <Input label={t('cert.asunto')} value={c.asunto} onChange={e => setC({ ...c, asunto: e.target.value })} />
            <Textarea label={t('cert.contenido')} value={c.contenido} rows={10} onChange={e => setC({ ...c, contenido: e.target.value })} />
            <div className="cert-acciones">
              <Button variant="secondary" loading={cargarPlantilla.isPending} onClick={() => cargarPlantilla.mutate()}>{t('cert.usar_plantilla')}</Button>
              <Button icon={<Send size={14} />} loading={enviar.isPending} onClick={() => enviar.mutate()}>{t('cert.registrar_envio')}</Button>
            </div>
          </Card>
        )}
      </div>
    </Modal>
  )
}
