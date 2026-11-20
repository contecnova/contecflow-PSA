/**
 * Ficha del proveedor → Contratos y precios (19-11-2026).
 *
 * Contratos (borrador → activo → terminado), sus líneas de precio con todos
 * los modelos, mínimos y topes, y alta desde plantilla. Activar exige el GRC
 * del proveedor al día (409 `proveedor_requisitos_grc_pendientes`, el mensaje
 * lista lo que falta).
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Copy, FileText, Pencil, Plus, Square } from 'lucide-react'
import { Button, Card, EmptyState, Modal, Select, Spinner } from '../../components/ui'
import StatusBadge from '../../components/ui/StatusBadge'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { useToast } from '../../context/ToastContext'
import { proveedoresApi } from '../../services/api/proveedores'
import type { ContratoDeProveedor, LineaDePrecio } from '../../services/api/tipos-proveedores'
import type { Subcontratista } from '../../services/api/tipos-alm'
import { useFormatoMoneda } from '../../hooks/useFormatoMoneda'
import { extractErr, fmtDate } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { TONO_CONTRATO } from './logica'
import { etiquetaDe, usePermisosDeProveedores, useT } from './comunes'
import { FormularioDeContrato, FormularioDeLinea, ListaDeLineas } from './FormulariosDeContrato'

export default function PestanaContratos({ sub }: { sub: Subcontratista }) {
  const t = useT()
  const toast = useToast()
  const qc = useQueryClient()
  const fmtMoneda = useFormatoMoneda()
  const { gestionar } = usePermisosDeProveedores()
  const [editando, setEditando] = useState<ContratoDeProveedor | null | 'nuevo'>(null)
  const [linea, setLinea] = useState<{ contrato: string; linea: LineaDePrecio | null } | null>(null)
  const [desdePlantilla, setDesdePlantilla] = useState(false)
  const [plantillaId, setPlantillaId] = useState('')

  const { data: contratos = [], isLoading } = useQuery({
    queryKey: ['suppliers', 'contracts', sub.id],
    queryFn: () => proveedoresApi.contratos(sub.id).then(r => r.data),
  })
  const { data: servicios = [] } = useQuery({
    queryKey: ['suppliers', 'services', sub.id],
    queryFn: () => proveedoresApi.servicios(sub.id).then(r => r.data),
    enabled: !!linea,
  })
  const { data: paquetes = [] } = useQuery({
    queryKey: ['suppliers', 'work-packages', sub.id],
    queryFn: () => proveedoresApi.paquetes(sub.id).then(r => r.data),
    enabled: !!linea,
  })
  const { data: plantillas = [] } = useQuery({
    queryKey: ['suppliers', 'contract-templates'],
    queryFn: () => proveedoresApi.plantillas().then(r => r.data),
    enabled: desdePlantilla,
  })

  const alFallar = (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  const refrescar = () => qc.invalidateQueries({ queryKey: ['suppliers'] })
  const activar = useMutation({ mutationFn: (id: string) => proveedoresApi.activarContrato(id), onSuccess: () => { refrescar(); toast.success(t('proveedores.contrato_activado')) }, onError: alFallar })
  const terminar = useMutation({ mutationFn: (id: string) => proveedoresApi.terminarContrato(id), onSuccess: () => { refrescar(); toast.success(t('proveedores.contrato_terminado')) }, onError: alFallar })
  const crearDesdePlantilla = useMutation({
    mutationFn: () => proveedoresApi.contratoDesdePlantilla(sub.id, plantillaId),
    onSuccess: () => { refrescar(); setDesdePlantilla(false); setPlantillaId(''); toast.success(t('proveedores.contrato_guardado')) },
    onError: alFallar,
  })

  if (isLoading) return <Spinner />
  return (
    <div>
      {gestionar && (
        <div className="sub-toolbar-end u-row-6">
          <Button size="sm" variant="secondary" icon={<Copy size={14} />} onClick={() => setDesdePlantilla(true)}>{t('proveedores.desde_plantilla')}</Button>
          <Button size="sm" icon={<Plus size={14} />} onClick={() => setEditando('nuevo')}>{t('proveedores.nuevo_contrato')}</Button>
        </div>
      )}
      {contratos.length === 0 ? (
        <EmptyState icon={<FileText size={28} />} title={t('proveedores.sin_contratos')} description={t('proveedores.sin_contratos_d')} />
      ) : (
        <div className="u-stack-8">
          {contratos.map(c => (
            <Card key={c.id} className="sub-item">
              <div className="prv-cabecera-item">
                <div className="u-min0">
                  <div className="u-row-center-8">
                    <span className="prv-titulo-item">{c.title}</span>
                    {c.code && <span className="u-text2-mono-xs">{c.code}</span>}
                    <StatusBadge kind={TONO_CONTRATO[c.status] || 'neutral'} caps={false}>{etiquetaDe(t, 'contrato_estado_', c.status)}</StatusBadge>
                  </div>
                  <div className="prv-sub">
                    {[
                      etiquetaDe(t, 'contrato_tipo_', c.contract_type),
                      (c.start_date || c.end_date) && `${fmtDate(c.start_date)} – ${fmtDate(c.end_date)}`,
                      c.auto_renew && t('proveedores.renovacion_automatica'),
                      c.committed_minimum != null && t('proveedores.minimo_n', { importe: fmtMoneda(c.committed_minimum, { moneda: c.currency }) }),
                      c.total_cap != null && t('proveedores.tope_n', { importe: fmtMoneda(c.total_cap, { moneda: c.currency }) }),
                      c.po_number && t('subcontractors.po_numero', { po: c.po_number }),
                      c.modes.length > 0 && c.modes.map(m => etiquetaDe(t, 'modo_', m)).join(', '),
                    ].filter(Boolean).join(' · ')}
                  </div>
                </div>
                {gestionar && (
                  <div className="u-row-6">
                    <Button size="xs" variant="secondary" icon={<Pencil size={13} />} onClick={() => setEditando(c)}>{t('subcontractors.edit')}</Button>
                    <Button size="xs" variant="secondary" icon={<Plus size={13} />} onClick={() => setLinea({ contrato: c.id, linea: null })}>{t('proveedores.nueva_linea')}</Button>
                    {(c.status === 'draft' || c.status === 'suspended') && (
                      <Button size="xs" icon={<CheckCircle2 size={13} />} loading={activar.isPending} onClick={() => activar.mutate(c.id)}>{t('proveedores.activar')}</Button>
                    )}
                    {c.status === 'active' && (
                      <Button size="xs" variant="ghost" className="sub-borrar" icon={<Square size={13} />}
                        onClick={() => openConfirmGlobal({ message: t('proveedores.terminar_contrato_confirmar', { titulo: c.title }), danger: true, onConfirm: () => terminar.mutate(c.id) })}>
                        {t('proveedores.terminar')}
                      </Button>
                    )}
                  </div>
                )}
              </div>
              <ListaDeLineas contrato={c} editable={gestionar} onEditar={l => setLinea({ contrato: c.id, linea: l })} />
            </Card>
          ))}
        </div>
      )}

      {editando && <FormularioDeContrato subId={sub.id} contrato={editando === 'nuevo' ? null : editando} onClose={() => setEditando(null)} />}
      {linea && (
        <FormularioDeLinea contratoId={linea.contrato} linea={linea.linea} tarifas={sub.rates || []} servicios={servicios} paquetes={paquetes}
          onClose={() => setLinea(null)} />
      )}
      {desdePlantilla && (
        <Modal open title={t('proveedores.desde_plantilla')} onClose={() => setDesdePlantilla(false)} width={480}>
          <div className="u-stack-8">
            <p className="u-text2-sm">{t('proveedores.desde_plantilla_d')}</p>
            <Select label={t('proveedores.plantilla')} value={plantillaId} onChange={e => setPlantillaId(e.target.value)} placeholder={plantillas.length ? t('proveedores.elegir') : t('proveedores.sin_plantillas')}
              options={plantillas.map(p => ({ value: p.id, label: p.title }))} />
            <div className="u-actions-8">
              <Button variant="secondary" onClick={() => setDesdePlantilla(false)}>{t('common.cancel')}</Button>
              <Button onClick={() => crearDesdePlantilla.mutate()} disabled={!plantillaId || crearDesdePlantilla.isPending} loading={crearDesdePlantilla.isPending}>{t('proveedores.crear_contrato')}</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}
