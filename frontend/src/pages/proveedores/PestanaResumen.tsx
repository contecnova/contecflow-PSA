/**
 * Ficha del proveedor → Resumen (19-11-2026): perfil, contadores, cumplimiento,
 * puntuación y a quién se asigna el trabajo. `GET /suppliers/{id}/profile`.
 */
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Briefcase, FileText, Gauge, Layers, Pencil, Receipt, ShieldCheck, Users } from 'lucide-react'
import { Button, Card, KpiCard, Spinner } from '../../components/ui'
import StatusBadge from '../../components/ui/StatusBadge'
import { usePersonasInternas } from '../../components/externos/FormularioDeExterno'
import { proveedoresApi } from '../../services/api/proveedores'
import type { Subcontratista } from '../../services/api/tipos-alm'
import { fmtDate, fmtNumber } from '../../utils/helpers'
import { TONO_CUMPLIMIENTO, aQuienSeAsigna, tonoDePuntuacion } from './logica'
import { Dato, InsigniasDeProveedor, etiquetaDe, usePermisosDeProveedores, useT } from './comunes'
import ClasificacionModal from './ClasificacionModal'

export default function PestanaResumen({ sub }: { sub: Subcontratista }) {
  const t = useT()
  const { gestionar } = usePermisosDeProveedores()
  const [editando, setEditando] = useState(false)
  const { personas } = usePersonasInternas()
  const { data: ficha, isLoading } = useQuery({
    queryKey: ['suppliers', 'profile', sub.id],
    queryFn: () => proveedoresApi.ficha(sub.id).then(r => r.data),
  })
  const p = ficha ?? sub
  const responsable = useMemo(() => personas.find(x => x.id === p.internal_owner_id)?.full_name, [personas, p.internal_owner_id])
  const asignacion = ficha?.assign_to ?? aQuienSeAsigna(p)

  if (isLoading) return <Spinner />
  return (
    <div className="u-stack-16">
      <Card className="prv-bloque">
        <div className="prv-cabecera-item">
          <div>
            <div className="prv-titulo-item">{p.legal_name || p.name}</div>
            <InsigniasDeProveedor sub={p} />
          </div>
          {gestionar && <Button size="sm" variant="secondary" icon={<Pencil size={14} />} onClick={() => setEditando(true)}>{t('proveedores.editar_clasificacion')}</Button>}
        </div>
        <div className="prv-datos prv-mt">
          <Dato etiqueta={t('subcontractors.codigo')}>{p.code || '—'}</Dato>
          <Dato etiqueta={t('subcontractors.nif_vat')}>{p.vat_number || '—'}</Dato>
          <Dato etiqueta={t('proveedores.pais')}>{p.country || '—'}</Dato>
          <Dato etiqueta={t('subcontractors.moneda')}>{p.currency || '—'}</Dato>
          <Dato etiqueta={t('subcontractors.email')}>{p.email || '—'}</Dato>
          <Dato etiqueta={t('proveedores.web')}>{p.website || '—'}</Dato>
          <Dato etiqueta={t('proveedores.direccion')}>{p.address || '—'}</Dato>
          <Dato etiqueta={t('externos.responsable_interno')}>{responsable || t('externos.sin_responsable')}</Dato>
          <Dato etiqueta={t('proveedores.acceso_a_datos')}>{p.data_access ? (p.data_categories || t('proveedores.si')) : t('proveedores.no')}</Dato>
          <Dato etiqueta={t('proveedores.sistemas')}>{p.systems_access || '—'}</Dato>
          <Dato etiqueta={t('proveedores.formacion')}>{p.training_enabled ? t('proveedores.si') : t('proveedores.no')}</Dato>
          <Dato etiqueta={t('proveedores.proxima_revision')}>{p.next_review_date ? fmtDate(p.next_review_date) : '—'}</Dato>
        </div>
        {p.lifecycle_status === 'offboarded' && p.offboarding_reason && (
          <div className="prv-aviso prv-mt">{t('proveedores.baja_motivo', { fecha: fmtDate(p.offboarded_at), motivo: p.offboarding_reason })}</div>
        )}
      </Card>

      <Card className="prv-bloque">
        <div className="prv-bloque-titulo"><Users size={16} aria-hidden />{t('proveedores.a_quien_se_asigna')}</div>
        <p className="u-text2-sm">{t(`proveedores.asignar_${asignacion}`)}</p>
      </Card>

      {ficha && (
        <div className="ds-grid-stats">
          <KpiCard icon={<FileText size={16} />} label={t('proveedores.kpi_contratos_activos')} value={ficha.counts.contracts_active} />
          <KpiCard icon={<Layers size={16} />} label={t('proveedores.kpi_servicios_activos')} value={ficha.counts.services_active} />
          <KpiCard icon={<Briefcase size={16} />} label={t('proveedores.kpi_paquetes_abiertos')} value={ficha.counts.work_packages_open} />
          <KpiCard icon={<Receipt size={16} />} label={t('proveedores.kpi_estados_pendientes')} value={ficha.counts.statements_pending} warning={ficha.counts.statements_pending > 0} />
        </div>
      )}

      {ficha && (
        <div className="prv-rejilla">
          <Card className="prv-bloque">
            <div className="prv-bloque-titulo"><ShieldCheck size={16} aria-hidden />{t('proveedores.tab_cumplimiento')}
              <StatusBadge kind={TONO_CUMPLIMIENTO[ficha.compliance.status] || 'neutral'} caps={false}>{etiquetaDe(t, 'cumplimiento_', ficha.compliance.status)}</StatusBadge>
            </div>
            {ficha.compliance.missing.length > 0 && (
              <p className="u-text2-sm">{t('proveedores.faltan_n', { docs: ficha.compliance.missing.map(d => etiquetaDe(t, 'doc_', d)).join(', ') })}</p>
            )}
            {ficha.compliance.expiring.length > 0 && (
              <p className="u-text2-sm">{t('proveedores.caducan_n', { docs: ficha.compliance.expiring.map(d => `${etiquetaDe(t, 'doc_', d.doc_type)} (${fmtDate(d.expires_at)})`).join(', ') })}</p>
            )}
            {ficha.compliance.missing.length === 0 && ficha.compliance.expiring.length === 0 && <p className="u-text2-sm">{t('proveedores.cumplimiento_al_dia')}</p>}
          </Card>
          <Card className="prv-bloque">
            <div className="prv-bloque-titulo"><Gauge size={16} aria-hidden />{t('proveedores.tab_rendimiento')}</div>
            {ficha.scorecard.score == null ? <p className="u-text2-sm">{t('proveedores.sin_puntuacion')}</p> : (
              <div className="u-row-center-8">
                <span className="prv-puntuacion">{fmtNumber(ficha.scorecard.score, 0)}</span>
                <StatusBadge kind={tonoDePuntuacion(ficha.scorecard.tone)} caps={false}>{t('proveedores.sobre_100')}</StatusBadge>
              </div>
            )}
          </Card>
        </div>
      )}

      {editando && <ClasificacionModal sub={p} onClose={() => setEditando(false)} />}
    </div>
  )
}
