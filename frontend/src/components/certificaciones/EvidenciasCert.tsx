/**
 * Evidencias (§3.4): siempre bajo control de flujos. Una evidencia documental se apoya en
 * Documentos (versiones, aprobación obligatoria, permisos, retención y bloqueo legal) y no
 * cuenta hasta que su documento está aprobado; caduca y avisa. También las del sistema
 * (medidas firmadas con su huella), las de tareas cerradas y las del GRC.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FileCheck2, Plus, Trash2 } from 'lucide-react'
import { Button, DateInput, IconButton, Input, Modal, SelectRico, Tabla } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { confirmar } from '../../context/ConfirmContext'
import { extractErr, fmtDate } from '../../utils/helpers'
import { CLAVES_CERT, certApi } from '../../services/api/certificaciones'
import type { Evidencia } from '../../services/api/certificaciones'
import { Estado } from './comun'
import type { PropsDePestana } from './comun'

const ESTADOS = ['valida', 'caducada', 'pendiente_aprobacion', 'pendiente']

export default function EvidenciasCert({ programaId }: PropsDePestana) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { puede } = useAuth()
  const [estado, setEstado] = useState('')
  const [nueva, setNueva] = useState(false)
  const filtros = { programa_id: programaId || undefined, estado: estado || undefined }
  const { data: filas = [], isLoading } = useQuery({ queryKey: CLAVES_CERT.evidencias(filtros), queryFn: () => certApi.evidencias(filtros) })
  const borrar = useMutation({
    mutationFn: (id: string) => certApi.borrarEvidencia(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: CLAVES_CERT.todo }), onError: e => toast.error(extractErr(e)),
  })
  return (
    <div className="u-stack-12">
      <div className="cert-acciones">
        <SelectRico aria-label={t('cert.estado')} valor={estado} onChange={setEstado} opciones={[
          { valor: '', etiqueta: t('cert.todos_los_estados') }, ...ESTADOS.map(e => ({ valor: e, etiqueta: t(`cert.estado_${e}`) }))]} />
        {puede('certificaciones.gestionar') && programaId && (
          <Button icon={<Plus size={14} />} onClick={() => setNueva(true)}>{t('cert.evidencia_nueva')}</Button>)}
      </div>
      <Tabla<Evidencia> etiqueta={t('cert.evidencias')} filas={filas} cargando={isLoading} ordenable
        vacio={{ icono: <FileCheck2 size={28} />, titulo: t('cert.sin_evidencias') }}
        columnas={[
          { key: 'titulo', label: t('cert.titulo'), cabeceraDeFila: true, render: (_v, e) => (
            <div className="cert-celda"><span>{e.titulo}</span><span className="cert-apagado">{e.control} · {e.control_titulo}</span></div>) },
          { key: 'origen', label: t('cert.origen'), render: (_v, e) => t(`cert.origen_${e.origen}`) },
          { key: 'tipo', label: t('cert.tipo'), render: (_v, e) => t(`cert.tipo_evidencia_${e.tipo}`) },
          { key: 'estado', label: t('cert.estado'), render: (_v, e) => <Estado valor={e.estado} /> },
          { key: 'sha256', label: t('cert.huella'), sortable: false, render: (_v, e) => (e.sha256 ? `${e.sha256.slice(0, 12)}…` : '—') },
          { key: 'caduca_el', label: t('cert.caduca'), render: (_v, e) => fmtDate(e.caduca_el) },
          ...(puede('certificaciones.administrar') ? [{ key: 'borrar', label: t('cert.acciones'), sortable: false,
            render: (_v: never, e: Evidencia) => (
              <IconButton variante="caja" tono="peligro" ariaLabel={t('cert.borrar_evidencia', { titulo: e.titulo })}
                onClick={async () => { if (await confirmar({ message: t('cert.confirmar_borrar_evidencia'), danger: true })) borrar.mutate(e.id) }}>
                <Trash2 /></IconButton>) }] : []),
        ]} />
      {nueva && <NuevaEvidencia programaId={programaId} onClose={() => setNueva(false)} />}
    </div>
  )
}

function NuevaEvidencia({ programaId, onClose }: { programaId: string; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: filas = [] } = useQuery({ queryKey: CLAVES_CERT.aplicabilidad(programaId, {}),
    queryFn: () => certApi.aplicabilidad(programaId) })
  const vacia = { aplicabilidad_id: '', titulo: '', tipo: 'documento', document_id: '', uri: '', sha256: '', valida_desde: '', caduca_el: '' }
  const [e, setE] = useState(vacia)
  const set = (k: keyof typeof vacia, v: string) => setE(x => ({ ...x, [k]: v }))
  const crear = useMutation({
    mutationFn: () => certApi.crearEvidencia(Object.fromEntries(Object.entries(e).filter(([, v]) => v !== ''))),
    onSuccess: () => { qc.invalidateQueries({ queryKey: CLAVES_CERT.todo }); toast.success(t('cert.guardado')); onClose() },
    onError: err => toast.error(extractErr(err)),
  })
  return (
    <Modal open title={t('cert.evidencia_nueva')} subtitle={t('cert.evidencia_ayuda')} onClose={onClose} size="lg"
      cambiosSinGuardar={!!e.titulo}>
      <div className="u-stack-12">
        <SelectRico label={t('cert.control')} valor={e.aplicabilidad_id} onChange={v => set('aplicabilidad_id', v)} opciones={[
          { valor: '', etiqueta: t('cert.elige_control') },
          ...filas.map(f => ({ valor: f.id, etiqueta: `${f.control} · ${f.titulo}${f.sede ? ` (${f.sede})` : ''}` }))]} />
        <Input label={t('cert.titulo')} value={e.titulo} onChange={x => set('titulo', x.target.value)} required />
        <div className="cert-rejilla">
          <SelectRico label={t('cert.tipo')} valor={e.tipo} onChange={v => set('tipo', v)} opciones={
            ['documento', 'registro', 'enlace', 'informe_sistema'].map(x => ({ valor: x, etiqueta: t(`cert.tipo_evidencia_${x}`) }))} />
          <Input label={t('cert.documento_id')} value={e.document_id} onChange={x => set('document_id', x.target.value)}
            hint={t('cert.documento_id_ayuda')} />
          <Input label={t('cert.enlace')} value={e.uri} onChange={x => set('uri', x.target.value)} />
          <Input label={t('cert.huella_sha256')} value={e.sha256} onChange={x => set('sha256', x.target.value)} />
          <DateInput label={t('cert.valida_desde')} value={e.valida_desde} onChange={x => set('valida_desde', x.target.value)} />
          <DateInput label={t('cert.caduca')} value={e.caduca_el} onChange={x => set('caduca_el', x.target.value)} />
        </div>
        <div className="cert-acciones">
          <Button disabled={!e.aplicabilidad_id || !e.titulo.trim()} loading={crear.isPending} onClick={() => crear.mutate()}>
            {t('cert.guardar')}</Button>
          <Button variant="secondary" onClick={onClose}>{t('cert.cancelar')}</Button>
        </div>
      </div>
    </Modal>
  )
}
