/**
 * Configuración → Finanzas → Proveedores (19-11-2026, migración 189).
 *
 * Lo que es ajuste y no operación del día a día (docs/CONFIGURACION.md):
 * - plantillas de contrato con sus líneas de precio (`/suppliers/contract-templates`);
 * - catálogos de tipos de servicio gestionado y unidades de cobro (mismo
 *   componente que Catálogos; los valores del sistema no se editan);
 * - umbrales en caliente del grupo «proyectos» de la configuración dinámica:
 *   tolerancia de conciliación, aviso de caducidad de documentos y meses entre
 *   revisiones de riesgo. Escribirlos es de administración: a otro rol el
 *   backend le responde 403 y aquí se ven en solo lectura.
 */
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { FileText, Pencil, Plus, SlidersHorizontal, Trash2 } from 'lucide-react'
import { Button, Card, IconButton, Input, Spinner } from '../../components/ui'
import SeccionDeAjustes from '../settings-sections/SeccionDeAjustes'
import { Catalogo } from '../settings/CatalogosDeClave'
import { confirmar } from '../../context/ConfirmContext'
import { useToast } from '../../context/ToastContext'
import { useAuth } from '../../context/AuthContext'
import { settingsApi } from '../../services/api/settings'
import type { RuntimeSetting } from '../../services/api/settings'
import { proveedoresApi } from '../../services/api/proveedores'
import type { ContratoDeProveedor, LineaDePrecio } from '../../services/api/tipos-proveedores'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { conRespaldo } from './logica'
import { etiquetaDe, useT } from './comunes'
import { FormularioDeContrato, FormularioDeLinea, ListaDeLineas } from './FormulariosDeContrato'

/** Claves de la configuración dinámica (grupo «proyectos») que usa el módulo. */
export const CLAVES_EN_CALIENTE = ['PROVEEDORES_TOLERANCIA_CONCILIACION_PCT', 'PROVEEDORES_AVISO_DOCUMENTO_DIAS', 'PROVEEDORES_REVISION_RIESGO_MESES'] as const
const GRUPO = 'proyectos'
const delModulo = (items: RuntimeSetting[] | undefined) => (items || []).filter(i => (CLAVES_EN_CALIENTE as readonly string[]).includes(i.key))

function PlantillasDeContrato() {
  const t = useT()
  const toast = useToast()
  const qc = useQueryClient()
  const [editando, setEditando] = useState<ContratoDeProveedor | null | 'nueva'>(null)
  const [linea, setLinea] = useState<{ contrato: string; linea: LineaDePrecio | null } | null>(null)
  const { data: plantillas = [], isLoading } = useQuery({
    queryKey: ['suppliers', 'contract-templates'],
    queryFn: () => proveedoresApi.plantillas().then(r => r.data),
  })
  const borrar = useMutation({
    mutationFn: (id: string) => proveedoresApi.borrarPlantilla(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['suppliers', 'contract-templates'] }); toast.success(t('proveedores.plantilla_borrada')) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  return (
    <SeccionDeAjustes icon={<FileText size={18} />} title={t('proveedores.plantillas')} description={t('proveedores.plantillas_d')}>
      <div className="prv-barra">
        <span />
        <Button size="sm" icon={<Plus size={14} />} onClick={() => setEditando('nueva')}>{t('proveedores.nueva_plantilla')}</Button>
      </div>
      {isLoading ? <Spinner /> : plantillas.length === 0 ? <p className="u-text2-sm">{t('proveedores.sin_plantillas')}</p> : (
        <div className="u-stack-8">
          {plantillas.map(p => (
            <Card key={p.id} className="prv-bloque">
              <div className="prv-cabecera-item">
                <div className="u-min0">
                  <span className="prv-titulo-item">{p.title}</span>
                  <div className="prv-sub">{[etiquetaDe(t, 'contrato_tipo_', p.contract_type), p.modes.map(m => etiquetaDe(t, 'modo_', m)).join(', ')].filter(Boolean).join(' · ')}</div>
                </div>
                <div className="u-row-6">
                  <Button size="xs" variant="secondary" icon={<Plus size={13} />} onClick={() => setLinea({ contrato: p.id, linea: null })}>{t('proveedores.nueva_linea')}</Button>
                  <IconButton onClick={() => setEditando(p)} ariaLabel={t('proveedores.editar_plantilla')} title={t('proveedores.editar_plantilla')}><Pencil size={14} aria-hidden /></IconButton>
                  <IconButton onClick={async () => { if (await confirmar({ message: t('proveedores.borrar_plantilla_confirmar', { titulo: p.title }), danger: true })) borrar.mutate(p.id) }}
                    ariaLabel={t('proveedores.borrar_plantilla')} title={t('proveedores.borrar_plantilla')}><Trash2 size={14} aria-hidden /></IconButton>
                </div>
              </div>
              <ListaDeLineas contrato={p} editable onEditar={l => setLinea({ contrato: p.id, linea: l })} />
            </Card>
          ))}
        </div>
      )}
      {editando && <FormularioDeContrato plantilla contrato={editando === 'nueva' ? null : editando} onClose={() => setEditando(null)} />}
      {linea && <FormularioDeLinea contratoId={linea.contrato} linea={linea.linea} onClose={() => setLinea(null)} />}
    </SeccionDeAjustes>
  )
}

function UmbralesEnCaliente() {
  const t = useT()
  const toast = useToast()
  const qc = useQueryClient()
  const esAdmin = useAuth().puede('org.administrar')
  const { data, isError } = useQuery({
    queryKey: ['runtime-flags', GRUPO],
    queryFn: () => settingsApi.runtimeGroup(GRUPO).then(r => r.data),
    retry: false,
  })
  const items = delModulo(data?.items)
  const [borrador, setBorrador] = useState<Record<string, string>>({})
  useEffect(() => {
    setBorrador(Object.fromEntries(delModulo(data?.items).map(i => [i.key, i.value == null ? '' : String(i.value)])))
  }, [data])
  const guardar = useMutation({
    mutationFn: ({ key, value }: { key: string; value: string }) => settingsApi.setRuntime(GRUPO, key, value),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['runtime-flags', GRUPO] }); toast.success(t('proveedores.ajuste_guardado')) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  return (
    <SeccionDeAjustes icon={<SlidersHorizontal size={18} />} title={t('proveedores.umbrales')} description={t('proveedores.umbrales_d')}>
      {isError || items.length === 0 ? (
        <p className="u-text2-sm">{t('proveedores.umbrales_en_config_dinamica')}{' '}
          {esAdmin && <Link to="/settings/runtime-flags">{t('proveedores.abrir_config_dinamica')}</Link>}
        </p>
      ) : (
        <div className="u-stack-8">
          {items.map(i => {
            const etiqueta = conRespaldo(t, `ajuste_clave.${i.key}`, i.label)
            const sucio = String(i.value ?? '') !== (borrador[i.key] ?? '')
            return (
              <div key={i.key} className="prv-barra">
                <Input className="u-flex1" label={etiqueta} type="number" step={i.type === 'float' ? 'any' : '1'} min={0} value={borrador[i.key] ?? ''}
                  disabled={!esAdmin} onChange={e => setBorrador(b => ({ ...b, [i.key]: e.target.value }))} />
                {esAdmin && (
                  <Button size="sm" variant={sucio ? 'primary' : 'secondary'} disabled={!sucio || guardar.isPending}
                    onClick={() => guardar.mutate({ key: i.key, value: borrador[i.key] ?? '' })}>{t('common.save')}</Button>
                )}
              </div>
            )
          })}
          {!esAdmin && <p className="u-text3-xs">{t('proveedores.umbrales_solo_admin')}</p>}
        </div>
      )}
    </SeccionDeAjustes>
  )
}

export default function ConfigProveedores() {
  return (
    <>
      <PlantillasDeContrato />
      <Catalogo catalogo="supplier-service-types" />
      <Catalogo catalogo="supplier-billing-units" />
      <UmbralesEnCaliente />
    </>
  )
}
