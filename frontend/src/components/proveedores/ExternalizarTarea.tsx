/**
 * «Externalizar a» en el formulario de tarea (19-11-2026, migración 189).
 *
 * Proveedores de outsourcing activos (`GET /suppliers/assignable?project_id=`)
 * y, opcional, uno de sus paquetes de trabajo del proyecto. Es excluyente con
 * el asignado: quien llama aplica `asignacionExclusiva` (pages/proveedores/logica)
 * al cambiar cualquiera de los dos. Sin proveedores asignables (o sin permiso
 * para verlos: la ruta es de gestores) no pinta nada, salvo que la tarea ya
 * esté externalizada, para no perder el valor.
 */
import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Select } from '../ui'
import { proveedoresApi } from '../../services/api/proveedores'
import { useAppT } from '../../i18n/AppLangContext'
import { STALE_REFERENCE_DATA_MS } from '../../constants/timings'

export interface ExternalizarTareaProps {
  projectId: string | null | undefined
  supplierId: string
  paqueteId: string
  /** Nombre del proveedor que ya trae la tarea (`supplier_name`), por si no está en la lista. */
  nombreActual?: string | null
  onChange: (campo: 'supplier_id' | 'supplier_work_package_id', valor: string) => void
  idBase: string
  claseEtiqueta?: string
  claseControl?: string
  error?: (campo: string) => ReactNode
}

export default function ExternalizarTarea({ projectId, supplierId, paqueteId, nombreActual, onChange, idBase, claseEtiqueta = '', claseControl = '', error }: ExternalizarTareaProps) {
  const t = useAppT()
  const { data: proveedores = [], isError } = useQuery({
    queryKey: ['suppliers', 'assignable', projectId || ''],
    queryFn: () => proveedoresApi.asignables(projectId).then(r => r.data),
    enabled: !!projectId,
    staleTime: STALE_REFERENCE_DATA_MS,
    retry: false,
  })
  if (!projectId || ((isError || proveedores.length === 0) && !supplierId)) return null
  const elegido = proveedores.find(p => p.id === supplierId)
  const paquetes = (elegido?.work_packages || []).filter(w => w.project_id === projectId)
  return (
    <>
      <div className="u-col-full">
        <label id={`${idBase}-prov-et`} htmlFor={`${idBase}-prov`} className={claseEtiqueta}>{t('proveedores.externalizar_a')}</label>
        <Select suelto placeholder={false} id={`${idBase}-prov`} aria-describedby={`${idBase}-prov-ayuda`} value={supplierId}
          onChange={e => onChange('supplier_id', e.target.value)} className={claseControl}>
          <option value="">{t('proveedores.no_externalizada')}</option>
          {proveedores.map(p => <option key={p.id} value={p.id}>{p.code ? `${p.code} — ${p.name}` : p.name}</option>)}
          {supplierId && !elegido && <option value={supplierId}>{nombreActual || supplierId}</option>}
        </Select>
        <div id={`${idBase}-prov-ayuda`} className="u-text3-xs">{t('proveedores.externalizar_a_d')}</div>
        {error?.('supplier_id')}
      </div>
      {supplierId && (
        <div className="u-col-full">
          <label id={`${idBase}-paq-et`} htmlFor={`${idBase}-paq`} className={claseEtiqueta}>{t('proveedores.paquete_de_trabajo')}</label>
          <Select suelto placeholder={false} id={`${idBase}-paq`} value={paqueteId} onChange={e => onChange('supplier_work_package_id', e.target.value)} className={claseControl}>
            <option value="">{t('proveedores.sin_paquete')}</option>
            {paquetes.map(w => <option key={w.id} value={w.id}>{w.title}</option>)}
          </Select>
          {error?.('supplier_work_package_id')}
        </div>
      )}
    </>
  )
}
