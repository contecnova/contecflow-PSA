/**
 * Proveedores críticos de la cadena de suministro (NIS2 art. 21.2.d, §3.8): evaluación por
 * programa enlazada con la ficha de Proveedores (contratos, documentos y riesgo siguen allí).
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, Truck } from 'lucide-react'
import { Button, DateInput, Input, Modal, SelectRico, Tabla, Textarea } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { extractErr, fmtDate } from '../../utils/helpers'
import { CLAVES_CERT, certApi } from '../../services/api/certificaciones'
import type { ProveedorCritico } from '../../services/api/certificaciones'
import { Estado } from './comun'
import type { PropsDePestana } from './comun'

export default function ProveedoresCert({ programaId }: PropsDePestana) {
  const t = useAppT()
  const { puede } = useAuth()
  const gestionar = puede('certificaciones.gestionar')
  const { data = [], isLoading } = useQuery({ queryKey: CLAVES_CERT.proveedores, queryFn: certApi.proveedores })
  const [ficha, setFicha] = useState<ProveedorCritico | 'nuevo' | null>(null)
  const filas = programaId ? data.filter(p => !p.programa_id || p.programa_id === programaId) : data
  return (
    <div className="u-stack-12">
      {gestionar && <div className="cert-acciones"><Button icon={<Plus size={14} />} onClick={() => setFicha('nuevo')}>
        {t('cert.proveedor_nuevo')}</Button></div>}
      <Tabla<ProveedorCritico> etiqueta={t('cert.proveedores')} filas={filas} cargando={isLoading} ordenable
        onFila={gestionar ? setFicha : undefined} vacio={{ icono: <Truck size={28} />, titulo: t('cert.sin_proveedores') }}
        columnas={[
          { key: 'nombre', label: t('cert.nombre'), cabeceraDeFila: true },
          { key: 'criticidad', label: t('cert.criticidad'), render: (_v, p) => t(`cert.criticidad_${p.criticidad}`) },
          { key: 'resultado', label: t('cert.resultado'), render: (_v, p) => <Estado valor={p.resultado} /> },
          { key: 'evaluado_en', label: t('cert.evaluado'), render: (_v, p) => `${fmtDate(p.evaluado_en)}${p.evaluado_por ? ` · ${p.evaluado_por}` : ''}` },
          { key: 'proxima_evaluacion', label: t('cert.proxima_evaluacion'), render: (_v, p) => (
            <span className={p.vencida ? 'cert-aviso cert-aviso--peligro' : undefined}>{fmtDate(p.proxima_evaluacion)}</span>) },
        ]} />
      {ficha && <FichaProveedor proveedor={ficha === 'nuevo' ? null : ficha} programaId={programaId} onClose={() => setFicha(null)} />}
    </div>
  )
}

function FichaProveedor({ proveedor: p, programaId, onClose }: { proveedor: ProveedorCritico | null; programaId: string; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [f, setF] = useState({ nombre: p?.nombre ?? '', subcontractor_id: p?.subcontractor_id ?? '', criticidad: p?.criticidad ?? 'alta',
    resultado: p?.resultado ?? 'pendiente', servicios: p?.servicios ?? '', riesgo: p?.riesgo ?? '',
    proxima_evaluacion: p?.proxima_evaluacion ?? '', notas: p?.notas ?? '' })
  const guardar = useMutation({
    mutationFn: () => certApi.guardarProveedor({ ...f, subcontractor_id: f.subcontractor_id || null,
      proxima_evaluacion: f.proxima_evaluacion || null, ...(p ? {} : { programa_id: programaId || null }) }, p?.id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: CLAVES_CERT.todo }); onClose() },
    onError: e => toast.error(extractErr(e)),
  })
  return (
    <Modal open title={p ? p.nombre : t('cert.proveedor_nuevo')} subtitle={t('cert.proveedor_ayuda')} onClose={onClose} size="lg">
      <div className="u-stack-12">
        <div className="cert-rejilla">
          <Input label={t('cert.nombre')} value={f.nombre} onChange={e => setF({ ...f, nombre: e.target.value })} />
          <Input label={t('cert.ficha_de_proveedor')} value={f.subcontractor_id} hint={t('cert.ficha_de_proveedor_ayuda')}
            onChange={e => setF({ ...f, subcontractor_id: e.target.value })} />
          <SelectRico label={t('cert.criticidad')} valor={f.criticidad} onChange={v => setF({ ...f, criticidad: v })}
            opciones={['alta', 'media', 'baja'].map(x => ({ valor: x, etiqueta: t(`cert.criticidad_${x}`) }))} />
          <SelectRico label={t('cert.resultado')} valor={f.resultado} onChange={v => setF({ ...f, resultado: v })}
            opciones={['pendiente', 'aceptable', 'con_condiciones', 'no_aceptable'].map(x => ({ valor: x, etiqueta: t(`cert.estado_${x}`) }))} />
          <DateInput label={t('cert.proxima_evaluacion')} value={f.proxima_evaluacion}
            onChange={e => setF({ ...f, proxima_evaluacion: e.target.value })} />
        </div>
        <Textarea label={t('cert.servicios')} value={f.servicios} onChange={e => setF({ ...f, servicios: e.target.value })} />
        <Textarea label={t('cert.riesgo')} value={f.riesgo} onChange={e => setF({ ...f, riesgo: e.target.value })} />
        <Textarea label={t('cert.notas')} value={f.notas} onChange={e => setF({ ...f, notas: e.target.value })} />
        <div className="cert-acciones">
          <Button disabled={!f.nombre.trim() && !f.subcontractor_id} loading={guardar.isPending} onClick={() => guardar.mutate()}>{t('cert.guardar')}</Button>
          <Button variant="secondary" onClick={onClose}>{t('cert.cancelar')}</Button>
        </div>
      </div>
    </Modal>
  )
}
