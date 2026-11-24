/**
 * Configuración → Catálogos (19-11-2026): tipos de proyecto, sectores de
 * cliente y categorías de gasto, editables por empresa.
 *
 * Eran enums cerrados de la base de datos. Ahora cada empresa añade los suyos;
 * los valores del sistema (filas globales) se ven pero no se editan aquí (el
 * backend responde 403: son comunes a todas las empresas). Backend:
 * `app/services/settings_service/catalogos_de_clave.py`.
 */
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Pencil, Tags, Trash2, X } from 'lucide-react'
import { Button, Spinner, Input, IconButton } from '../../components/ui'
import SeccionDeAjustes from '../settings-sections/SeccionDeAjustes'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { catalogosApi, type NombreDeCatalogo, type ValorDeCatalogo } from '../../services/api/catalogos'
import { claveDeConsultaDeCatalogo, useCatalogo } from '../../hooks/useCatalogo'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { COLOR_DATO_POR_DEFECTO } from '../../constants/theme'
import './CatalogosDeClave.css'

const EDITABLES: NombreDeCatalogo[] = ['project-types', 'client-industries', 'expense-categories']

/** Clave técnica a partir del nombre: «Sector público» → `sector_publico`. */
const claveDe = (nombre: string) => nombre.normalize('NFD').replace(/\p{M}/gu, '').trim().toLowerCase()
  .replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 50)

/**
 * Un catálogo editable. Exportado (19-11-2026) para que la sección Proveedores
 * pinte allí sus dos catálogos (tipos de servicio y unidades de cobro) en vez de
 * repetirlos aquí: cada catálogo vive en un solo sitio de Configuración.
 */
export function Catalogo({ catalogo }: { catalogo: NombreDeCatalogo }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { etiqueta } = useCatalogo(catalogo)
  const { data = [], isLoading } = useQuery({ queryKey: claveDeConsultaDeCatalogo(catalogo), queryFn: () => catalogosApi.listar(catalogo) })
  const [nuevo, setNuevo] = useState({ label: '', color: COLOR_DATO_POR_DEFECTO })
  const [editando, setEditando] = useState<ValorDeCatalogo | null>(null)
  const refrescar = () => qc.invalidateQueries({ queryKey: claveDeConsultaDeCatalogo(catalogo) })
  const alFallar = (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  const crear = useMutation({
    mutationFn: () => catalogosApi.crear(catalogo, { value: claveDe(nuevo.label), label: nuevo.label.trim(), color: nuevo.color, sort_order: data.length }),
    onSuccess: () => { setNuevo({ label: '', color: COLOR_DATO_POR_DEFECTO }); refrescar() }, onError: alFallar,
  })
  const guardar = useMutation({
    mutationFn: (v: ValorDeCatalogo) => catalogosApi.guardar(catalogo, v.id, { value: v.value, label: v.label, color: v.color, sort_order: v.sort_order }),
    onSuccess: () => { setEditando(null); refrescar() }, onError: alFallar,
  })
  const borrar = useMutation({ mutationFn: (id: string) => catalogosApi.borrar(catalogo, id), onSuccess: refrescar, onError: alFallar })
  // 23-11-2026: borrar un valor de catálogo pide confirmación.
  const borrarValor = (v: ValorDeCatalogo) => openConfirmGlobal({
    message: t('catalogos_ajustes.confirmar_borrar_valor', { nombre: v.label }), confirmLabel: t('common.delete'), danger: true,
    onConfirm: () => borrar.mutate(v.id),
  })
  const titulo = t(`catalogos_ajustes.${catalogo.replace(/-/g, '_')}`)

  return (
    <SeccionDeAjustes icon={<Tags size={18} />} title={titulo} description={t('catalogos_ajustes.ayuda')}>
      {isLoading ? <Spinner /> : (
        <div className="set-stack-mb12">
          {data.map(v => (
            <div key={v.id} className="set-item set-item--wrap">
              {editando?.id === v.id ? (
                <>
                  <Input value={editando.label} onChange={e => setEditando({ ...editando, label: e.target.value })} aria-label={t('catalogos_ajustes.nombre')} autoFocus className="set-input--f2" />
                  <input type="color" value={editando.color} onChange={e => setEditando({ ...editando, color: e.target.value })} aria-label={t('catalogos_ajustes.color')} />
                  <IconButton variante="caja" tono="acento" onClick={() => guardar.mutate(editando)} disabled={!editando.label.trim()} ariaLabel={t('common.save')} title={t('common.save')}><Check size={14} aria-hidden /></IconButton>
                  <IconButton variante="caja" onClick={() => setEditando(null)} ariaLabel={t('common.cancel')} title={t('common.cancel')}><X size={14} aria-hidden /></IconButton>
                </>
              ) : (
                <>
                  <span className="set-area-tag cat-punto" style={{ '--cat-color': v.color } as CSSProperties} aria-hidden>●</span>
                  <span className="u-base-600">{etiqueta(v.value)}</span>
                  <span className="u-text2-sm">{v.value}</span>
                  {v.organization_id
                    ? <>
                        <IconButton variante="caja" onClick={() => setEditando(v)} ariaLabel={t('settings_sections.editar_x', { nombre: v.label })} title={t('common.edit')}><Pencil size={14} aria-hidden /></IconButton>
                        <IconButton variante="caja" tono="peligro" onClick={() => borrarValor(v)} ariaLabel={t('settings_sections.eliminar_x', { nombre: v.label })} title={t('common.delete')}><Trash2 size={14} aria-hidden /></IconButton>
                      </>
                    : <span className="u-text2-sm">{t('catalogos_ajustes.del_sistema')}</span>}
                </>
              )}
            </div>
          ))}
        </div>
      )}
      <div className="set-add-inline">
        <Input value={nuevo.label} onChange={e => setNuevo(n => ({ ...n, label: e.target.value }))} placeholder={t('catalogos_ajustes.nombre')} aria-label={t('catalogos_ajustes.nombre')} className="set-input--f2" />
        <input type="color" value={nuevo.color} onChange={e => setNuevo(n => ({ ...n, color: e.target.value }))} aria-label={t('catalogos_ajustes.color')} />
        <Button onClick={() => crear.mutate()} disabled={!claveDe(nuevo.label) || crear.isPending}>{t('settings.anadir')}</Button>
      </div>
    </SeccionDeAjustes>
  )
}

export default function CatalogosDeClave() {
  return <>{EDITABLES.map(c => <Catalogo key={c} catalogo={c} />)}</>
}
