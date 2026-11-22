/**
 * Pegar una transcripción (19-11-2026): la vía de siempre, ahora con proyecto,
 * cliente, fecha y asistentes. Formato admitido por el servidor: texto libre,
 * `Nombre: texto` por línea o WebVTT.
 */
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Sparkles } from 'lucide-react'
import { Button, ClientSelect, FormField, Input, Modal, ProjectSelect, Select, Textarea } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { reunionesApi } from '../../services/api/reuniones'
import { CLAVES } from './comun'
import './Reuniones.css'

const PLATAFORMAS = ['teams', 'zoom', 'meet', 'presencial', 'otra'] as const

interface Props { onClose: () => void; onCreada?: (id: string) => void }

export default function ModalPegarTranscripcion({ onClose, onCreada }: Props) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [titulo, setTitulo] = useState('')
  const [plataforma, setPlataforma] = useState<string>('teams')
  const [proyecto, setProyecto] = useState('')
  const [cliente, setCliente] = useState('')
  const [fecha, setFecha] = useState('')
  const [asistentes, setAsistentes] = useState('')
  const [texto, setTexto] = useState('')

  const crear = useMutation({
    mutationFn: () => reunionesApi.crear({
      title: titulo.trim(),
      origin: 'transcript',
      transcript: texto,
      platform: plataforma,
      project_id: proyecto || null,
      client_id: cliente || null,
      meeting_date: fecha || null,
      participants: asistentes.split(',').map(n => n.trim()).filter(Boolean).map(name => ({ name })),
    }),
    onSuccess: r => {
      qc.invalidateQueries({ queryKey: CLAVES.lista })
      toast.success(t('reuniones.pegar.creada'))
      onCreada?.(r.id)
      onClose()
    },
    onError: e => toast.error(extractErr(e, t('reuniones.pegar.error'))),
  })

  return (
    <Modal open size="lg" title={t('reuniones.pegar.titulo')} subtitle={t('reuniones.pegar.subtitulo')} onClose={onClose}>
      <div className="reu-form">
        <Input className="u-col-full" label={t('reuniones.campo.titulo')} required value={titulo} onChange={e => setTitulo(e.target.value)} />
        <Select label={t('reuniones.campo.plataforma')} value={plataforma} onChange={e => setPlataforma(e.target.value)} placeholder={false}
          options={PLATAFORMAS.map(p => ({ value: p, label: t(`reuniones.plataforma.${p}`) }))} />
        <Input label={t('reuniones.campo.fecha')} type="date" value={fecha} onChange={e => setFecha(e.target.value)} />
        <FormField label={t('reuniones.campo.proyecto')}>
          <ProjectSelect value={proyecto} onChange={id => setProyecto(id)} />
        </FormField>
        <FormField label={t('reuniones.campo.cliente')}>
          <ClientSelect value={cliente} onChange={id => setCliente(id)} />
        </FormField>
        <Input className="u-col-full" label={t('reuniones.pegar.asistentes')} hint={t('reuniones.pegar.asistentes_ayuda')}
          value={asistentes} onChange={e => setAsistentes(e.target.value)} />
        <div className="u-col-full">
          <FormField label={t('reuniones.pegar.transcripcion')} required hint={t('reuniones.pegar.transcripcion_ayuda')}>
            <Textarea rows={12} value={texto} onChange={e => setTexto(e.target.value)} inputClassName="reu-textarea" />
          </FormField>
        </div>
        <div className="u-col-full reu-botonera">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button icon={<Sparkles size={14} />} loading={crear.isPending} disabled={!titulo.trim() || !texto.trim()}
            onClick={() => crear.mutate()}>
            {t('reuniones.pegar.procesar')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
