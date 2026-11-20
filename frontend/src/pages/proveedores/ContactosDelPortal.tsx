/**
 * Ficha del proveedor → Cumplimiento → Portal del proveedor (migración 191).
 *
 * Quién de las personas del proveedor puede entrar en su portal (`/supplier-portal`)
 * a subir informes, partes y evidencias de SLA y ver sus paquetes, su consumo y su
 * estado de cuenta. Mínimo privilegio: solo personas con acceso (usuario) vigente;
 * caduca con su acceso (fin de contrato) y se quita al suspender o dar de baja.
 * Cada cambio queda en la auditoría (`subcontractor_workers`).
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Globe } from 'lucide-react'
import { Card, Spinner, Switch } from '../../components/ui'
import StatusBadge from '../../components/ui/StatusBadge'
import { useToast } from '../../context/ToastContext'
import { proveedoresApi } from '../../services/api/proveedores'
import type { Subcontratista } from '../../services/api/tipos-alm'
import { extractErr, fmtDate } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { estaActivo } from './logica'
import { usePermisosDeProveedores, useT } from './comunes'

/** ¿Puede esta persona ser contacto del portal? (backend: 422 `proveedor_portal_requiere_acceso`). */
export function puedeSerContacto(c: { has_access: boolean; access_until: string | null; user_id: string | null }, hoy = new Date().toISOString().slice(0, 10)) {
  return !!c.user_id && c.has_access && (!c.access_until || c.access_until >= hoy)
}

export default function ContactosDelPortal({ sub }: { sub: Subcontratista }) {
  const t = useT()
  const toast = useToast()
  const qc = useQueryClient()
  const { gestionar } = usePermisosDeProveedores()
  const { data: contactos = [], isLoading } = useQuery({
    queryKey: ['suppliers', 'portal-contacts', sub.id],
    queryFn: () => proveedoresApi.contactosDelPortal(sub.id).then(r => r.data),
    enabled: gestionar,
  })
  const marcar = useMutation({
    mutationFn: ({ id, activo }: { id: string; activo: boolean }) => proveedoresApi.marcarContacto(sub.id, id, activo),
    onSuccess: (_r, v) => { qc.invalidateQueries({ queryKey: ['suppliers', 'portal-contacts', sub.id] }); toast.success(v.activo ? t('proveedores.portal_concedido') : t('proveedores.portal_retirado')) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  if (!gestionar) return null
  const activo = estaActivo(sub)
  return (
    <Card className="prv-bloque">
      <div className="prv-bloque-titulo"><Globe size={16} aria-hidden />{t('proveedores.portal_del_proveedor')}</div>
      <p className="u-text3-xs">{t('proveedores.portal_del_proveedor_d')}</p>
      {isLoading ? <Spinner /> : contactos.length === 0 ? <p className="u-text2-sm">{t('proveedores.portal_sin_personas')}</p> : (
        <div className="u-stack-8 prv-mt">
          {contactos.map(c => {
            const puede = puedeSerContacto(c)
            return (
              <div key={c.worker_id} className="prv-cabecera-item">
                <div className="u-min0">
                  <strong>{c.name}</strong>{c.email ? <span className="u-text3-xs"> · {c.email}</span> : null}
                  <div className="u-text3-xs">
                    {puede
                      ? (c.access_until ? t('proveedores.acceso_hasta', { fecha: fmtDate(c.access_until) }) : t('proveedores.acceso_sin_fin'))
                      : t('proveedores.portal_sin_acceso_vigente')}
                  </div>
                </div>
                <div className="u-row-center-8">
                  {c.supplier_portal && <StatusBadge kind="info" caps={false}>{t('proveedores.contacto_del_portal')}</StatusBadge>}
                  <Switch checked={c.supplier_portal} disabled={marcar.isPending || (!c.supplier_portal && (!puede || !activo))}
                    onChange={(v: boolean) => marcar.mutate({ id: c.worker_id, activo: v })}
                    label={t('proveedores.acceso_al_portal')} />
                </div>
              </div>
            )
          })}
        </div>
      )}
    </Card>
  )
}
