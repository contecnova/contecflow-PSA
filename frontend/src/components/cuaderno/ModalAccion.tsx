/**
 * De nota a acción: el texto seleccionado (o la casilla) pasa a tarea, ticket,
 * solicitud de demanda, idea de cartera o recordatorio de calendario. El objeto
 * creado lleva el enlace a la nota y la nota recibe su chip (vínculo en los dos
 * sentidos). Cada opción solo se ofrece a quien tiene su permiso.
 */
import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Button, CampoFecha, FormField, Input, Modal, ProjectSelect, Segmentado, Textarea } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { cuadernoApi } from '../../services/api/cuaderno'
import type { Chip, TipoDeAccion } from '../../services/api/cuaderno'
import { olvidarChips } from './resolverChips'

export interface OrigenDeAccion { texto: string; blockId?: string | null; due?: string | null }

export default function ModalAccion({ pageId, origen, onClose, onCreado }: {
  pageId: string; origen: OrigenDeAccion; onClose: () => void; onCreado: (c: Chip & { label: string }) => void
}) {
  const t = useAppT()
  const toast = useToast()
  const { puede } = useAuth()
  const tipos = ([
    ['task', puede('tareas.usar') || puede('tareas.crear')],
    ['ticket', puede('sd.trabajar')],
    ['demand', true],
    ['proposal', puede('cartera.usar')],
    ['event', true],
  ] as [TipoDeAccion, boolean][]).filter(([, ok]) => ok).map(([k]) => k)
  const [tipo, setTipo] = useState<TipoDeAccion>(tipos[0] ?? 'event')
  const primera = origen.texto.split('\n')[0].trim()
  const [titulo, setTitulo] = useState(primera.slice(0, 255))
  const [texto, setTexto] = useState(origen.texto)
  const [proyecto, setProyecto] = useState('')
  const [fecha, setFecha] = useState(origen.due || '')
  const [inicio, setInicio] = useState('')

  const crear = useMutation({
    mutationFn: () => cuadernoApi.convertir(pageId, {
      kind: tipo, title: titulo, text: texto, block_id: origen.blockId || undefined,
      ...(tipo === 'task' ? { project_id: proyecto, due_date: fecha || undefined } : {}),
      ...(tipo === 'ticket' && proyecto ? { project_id: proyecto } : {}),
      ...(tipo === 'event' && inicio ? { start: new Date(inicio).toISOString() } : {}),
    }),
    onSuccess: c => {
      olvidarChips()
      toast.success(t('cuaderno.accion_creada', { tipo: t(`cuaderno.accion_${tipo}`) }))
      onCreado(c)
    },
    onError: e => toast.error(extractErr(e)),
  })

  const falta = !titulo.trim() || (tipo === 'task' && !proyecto)
  return (
    <Modal open onClose={onClose} title={t('cuaderno.accion_titulo')} size="md">
      <div className="cdn-form">
        <Segmentado aria-label={t('cuaderno.accion_tipo')} valor={tipo} onChange={v => setTipo(v as TipoDeAccion)}
          opciones={tipos.map(k => ({ valor: k, etiqueta: t(`cuaderno.accion_${k}`) }))} />
        <Input label={t('cuaderno.accion_titulo_campo')} value={titulo} onChange={e => setTitulo(e.target.value)} maxLength={255} required />
        <Textarea label={t('cuaderno.accion_descripcion')} value={texto} onChange={e => setTexto(e.target.value)} rows={4} />
        {(tipo === 'task' || tipo === 'ticket') && (
          <FormField label={tipo === 'task' ? t('cuaderno.accion_proyecto_obligatorio') : t('cuaderno.accion_proyecto')}>
            <ProjectSelect value={proyecto} onChange={id => setProyecto(id)} required={tipo === 'task'} />
          </FormField>
        )}
        {tipo === 'task' && (
          <FormField label={t('cuaderno.fecha')}>
            <CampoFecha value={fecha} onChange={setFecha} aria-label={t('cuaderno.fecha')} />
          </FormField>
        )}
        {tipo === 'event' && (
          <FormField label={t('cuaderno.accion_cuando')}>
            <CampoFecha modo="fechaHora" value={inicio} onChange={setInicio} aria-label={t('cuaderno.accion_cuando')} />
          </FormField>
        )}
        <p className="cdn-ayuda">{t('cuaderno.accion_ayuda')}</p>
        <div className="cdn-form__acciones">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => crear.mutate()} disabled={falta} loading={crear.isPending}>{t('cuaderno.accion_crear')}</Button>
        </div>
      </div>
    </Modal>
  )
}
