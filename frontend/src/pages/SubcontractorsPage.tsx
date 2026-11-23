/**
 * SubcontractorsPage — subcontratistas, sus personas, asignaciones, horas y facturas.
 *
 * 16-11-2026: acción principal en la cabecera con icono (antes en el cuerpo con
 * "+" de texto); KPIs con KpiCard en .ds-grid-stats (antes centrados y con
 * cifra monoespaciada); el detalle ya tiene PageShell + PageHeader con migas
 * (antes se pintaba sin cabecera ni márgenes de página); pestañas con iconos;
 * vacíos con EmptyState e iconos lucide (antes 🤝👤📋🕐🧾); emojis de las
 * tarjetas y botones (📧👥✏🗑🏆🎉) cambiados por iconos lucide; estados con
 * StatusBadge y botones del kit.
 *
 * 19-11-2026 (proveedores y externalización, migración 189): alta con tipo
 * (persona freelance en un paso o empresa con modos), insignias de tipo, modos,
 * ciclo de vida y riesgo, KPIs del panorama y ficha con pestañas por tipo:
 * Resumen, Personas/Asignaciones/Horas (solo si tiene personas), Contratos y
 * precios, Servicios, Paquetes de trabajo, Consumo y facturación, Rendimiento y
 * Cumplimiento. Las pestañas nuevas viven en `pages/proveedores/`.
 */
import { useState, useId } from 'react'
import { extractErr, fmtHours } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { enterpriseSubsApi, subcontractorsApi } from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Building2, CalendarClock, Clock, Coins, Handshake, HardHat, Mail, Pencil, Plus, Receipt, Scale, ShieldCheck, Trash2, UserRound, Users } from 'lucide-react'
import { Button, EmptyState, IconButton, KpiCard, Modal, Spinner, useSort, SortableTH, ViewToggle, Select, useErroresDeCampo, Input, Textarea } from '../components/ui'
import StatusBadge from '../components/ui/StatusBadge'
import { useAppT } from '../i18n/AppLangContext'
import { useOrgSettings } from '../hooks/useOrgSettings'
import { useFormatoMoneda } from '../hooks/useFormatoMoneda'
import { proveedoresApi } from '../services/api/proveedores'
import { InsigniasDeProveedor, usePermisosDeProveedores } from './proveedores/comunes'
import AltaDeProveedor from './proveedores/AltaDeProveedor'
import './SubcontractorsPage.css'
import { type Sub, onKeyboardActivate } from './SubcontractorsComun'
import { SubDetail } from './SubcontractorsFicha'

// ── Página principal ──────────────────────────────────────────────────────────
export default function SubcontractorsPage() {
  const idCampo = useId()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { currency, currencies: monedasDeLaEmpresa } = useOrgSettings()
  const fmtMoneda = useFormatoMoneda()
  const { gestionar } = usePermisosDeProveedores()
  const [elegido, setSelected] = useState<Sub | null>(null)
  const [showCreate, setShowCreate] = useState(false)

  const { data: dashboard } = useQuery({
    queryKey: ['sub-dashboard'],
    queryFn: () => enterpriseSubsApi.dashboard().then(r => r.data),
  })
  const { data: subs = [], isLoading } = useQuery<Sub[]>({
    queryKey: ['subcontractors'],
    queryFn: () => subcontractorsApi.list().then(r => r.data),
  })
  // Panorama de proveedores (tipos, documentos, revisiones, estados de cuenta, previsión del mes).
  const { data: panorama } = useQuery({
    queryKey: ['suppliers', 'overview'],
    queryFn: () => proveedoresApi.panorama().then(r => r.data),
    retry: false,
  })
  // La ficha abierta sigue a la lista (clasificación, ciclo de vida y riesgo cambian desde la ficha).
  const selected = elegido ? (subs.find(s => s.id === elegido.id) ?? elegido) : null

  const [showEdit, setShowEdit] = useState(false)
  const [editTarget, setEditTarget] = useState<Sub | null>(null)
  const [editForm, setEditForm] = useState<Record<string, string>>({})
  const [view, setView] = useState('grid')
  const { sort: subSort, setSort: setSubSort, sortedData: sortedSubs } = useSort<Sub>(subs, 'name')

  const camposEdit = useErroresDeCampo()
  const msgEdit = (k: string) => camposEdit.de(k) ? <div className="u-field-error">{camposEdit.de(k)}</div> : null
  const { mutate: update, isPending: updating } = useMutation({
    onMutate: () => camposEdit.limpiar(),
    mutationFn: ({ id, ...d }: { id: string; [k: string]: unknown }) => subcontractorsApi.update(id, d),
    onSuccess: (_res) => {
      qc.invalidateQueries({ queryKey: ['subcontractors'] })
      setShowEdit(false)
      setEditTarget(null)
      toast.success(t('subcontractors.subcontratista_actualizado'))
    },
    onError: (e: unknown) => { if (!camposEdit.recoger(e)) toast.error(extractErr(e, t('common.error_update'))) },
  })
  const { mutate: remove } = useMutation({
    mutationFn: (id: string) => subcontractorsApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['subcontractors'] })
      qc.invalidateQueries({ queryKey: ['sub-dashboard'] })
      toast.success(t('subcontractors.subcontratista_eliminado'))
    },
    onError: e => toast.error(extractErr(e, t('common.error_delete'))),
  })

  const abrirEdicion = (s: Sub) => {
    setEditTarget(s)
    setEditForm({ name: s.name||'', company: s.company||'', email: s.email||'', phone: s.phone||'', country: s.country||'España', currency: s.currency||currency, vat_number: s.vat_number||'', notes: s.notes||'' })
    setShowEdit(true)
  }
  const confirmarEliminar = (s: Sub) =>
    openConfirmGlobal({ message: t('subcontractors.confirmar_eliminar', { name: s.name }), onConfirm: () => remove(s.id), danger: true })

  if (selected) return <SubDetail sub={selected} onBack={() => setSelected(null)} onCambio={setSelected} />

  return (
    <PageShell>
      <PageHeader icon={<HardHat size={18} />} title={t('subcontractors.title')} subtitle={t('subcontractors.subtitle')}
        actions={<>
          {gestionar && <Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>{t('subcontractors.nuevo_subcontratista')}</Button>}
        </>} />

      <div className="u-stack-16">
      {/* KPIs */}
      {dashboard && (
        <div className="ds-grid-stats">
          <KpiCard icon={<Handshake size={16} />} label={t('subcontractors.kpi_activos')} value={dashboard.total_active_subs} />
          <KpiCard icon={<Clock size={16} />} label={t('subcontractors.hours_logged')} value={fmtHours(dashboard.total_hours_logged)} />
          <KpiCard icon={<Receipt size={16} />} label={t('subcontractors.kpi_facturas_pendientes')} value={dashboard.pending_invoices} warning={dashboard.pending_invoices > 0} />
        </div>
      )}
      {panorama && (
        <div className="ds-grid-stats">
          <KpiCard icon={<UserRound size={16} />} label={t('proveedores.kpi_freelance')} value={panorama.by_kind.freelance ?? 0} />
          <KpiCard icon={<Building2 size={16} />} label={t('proveedores.kpi_empresas')} value={panorama.by_kind.company ?? 0}
            sub={t('proveedores.kpi_modos', { personas: panorama.by_mode.staff_augmentation ?? 0, outsourcing: panorama.by_mode.outsourcing ?? 0, servicios: panorama.by_mode.managed_services ?? 0 })} />
          <KpiCard icon={<ShieldCheck size={16} />} label={t('proveedores.kpi_documentos')} value={panorama.documents_expired + panorama.documents_expiring}
            sub={t('proveedores.kpi_documentos_sub', { caducados: panorama.documents_expired, por_caducar: panorama.documents_expiring })}
            danger={panorama.documents_expired > 0} warning={panorama.documents_expiring > 0} />
          <KpiCard icon={<CalendarClock size={16} />} label={t('proveedores.kpi_revisiones')} value={panorama.reviews_overdue} warning={panorama.reviews_overdue > 0} />
          <KpiCard icon={<Scale size={16} />} label={t('proveedores.kpi_estados')} value={panorama.statements_pending_approval}
            sub={t('proveedores.kpi_disputados', { n: panorama.statements_disputed })} danger={panorama.statements_disputed > 0} />
          <KpiCard icon={<Coins size={16} />} label={t('proveedores.kpi_prevision_mes')} value={fmtMoneda(panorama.forecast_month, { moneda: panorama.currency })} />
        </div>
      )}

      {subs.length > 0 && (
        <div className="sub-actions-bar">
          <ViewToggle view={view} onChange={setView} />
        </div>
      )}

      {isLoading ? (
        <Spinner />
      ) : subs.length === 0 ? (
        <EmptyState
          icon={<Handshake size={28} />}
          title={t('subcontractors.sin_subcontratistas')}
          description={t('subcontractors.vacio_descripcion')}
          action={gestionar ? <Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>{t('subcontractors.nuevo_subcontratista')}</Button> : undefined}
        />
      ) : view === 'grid' ? (
        <div className="sub-grid">
          {sortedSubs.map(s => (
            <div key={s.id} onClick={() => setSelected(s)}
              role="button"
              tabIndex={0}
              onKeyDown={e => { if (e.target === e.currentTarget) onKeyboardActivate(e, () => setSelected(s)) }}
              className="sub-card"
            >
              <div className="sub-card-head">
                <div className="u-min0">
                  <div className="u-md-700">{s.name}</div>
                  {s.company && <div className="u-text2-xs">{s.company}</div>}
                </div>
              </div>
              <InsigniasDeProveedor sub={s} />
              {s.email && <div className="sub-mail"><Mail size={12} aria-hidden />{s.email}</div>}
              <div className="sub-card-meta">
                <Users size={12} aria-hidden />{t((s.worker_count || 0) === 1 ? 'subcontractors.n_persona' : 'subcontractors.n_personas', { n: s.worker_count || 0 })} · {t((s.assignment_count || 0) === 1 ? 'subcontractors.n_asignacion' : 'subcontractors.n_asignaciones', { n: s.assignment_count || 0 })}
              </div>
              {gestionar && (
              <div className="sub-card-actions">
                <Button size="sm" variant="secondary" icon={<Pencil size={14} />} onClick={e => { e.stopPropagation(); abrirEdicion(s) }}>
                  {t('subcontractors.edit')}
                </Button>
                <Button size="sm" variant="ghost" className="sub-borrar" icon={<Trash2 size={14} />} onClick={e => { e.stopPropagation(); confirmarEliminar(s) }}>
                  {t('subcontractors.delete')}
                </Button>
              </div>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="ds-card ds-card--plano">
          <div className="sub-table-head">
            <SortableTH col="name" sort={subSort} onSort={setSubSort}>{t('subcontractors.col_empresa_nombre')}</SortableTH>
            <SortableTH col="code" sort={subSort} onSort={setSubSort}>{t('subcontractors.codigo')}</SortableTH>
            <SortableTH col="email" sort={subSort} onSort={setSubSort}>{t('subcontractors.email')}</SortableTH>
            <SortableTH col="worker_count" sort={subSort} onSort={setSubSort}>{t('subcontractors.kpi_personas')}</SortableTH>
            <SortableTH col="assignment_count" sort={subSort} onSort={setSubSort}>{t('subcontractors.kpi_asignaciones')}</SortableTH>
            <SortableTH col="is_active" sort={subSort} onSort={setSubSort}>{t('subcontractors.col_estado')}</SortableTH>
            <span>{t('subcontractors.col_acciones')}</span>
          </div>
          {sortedSubs.map(s => (
            <div key={s.id} className="sub-row"
              role="button"
              tabIndex={0}
              onKeyDown={e => { if (e.target === e.currentTarget) onKeyboardActivate(e, () => setSelected(s)) }}
              onClick={() => setSelected(s)}>
              <div>
                <div className="u-base-600">{s.name}</div>
                {s.company && <div className="u-text2-xs">{s.company}</div>}
                <InsigniasDeProveedor sub={s} compacto />
              </div>
              <span className="u-text2-mono-xs">{s.code || '—'}</span>
              <span className="u-text2-sm">{s.email || '—'}</span>
              <span className="u-sm">{s.worker_count || 0}</span>
              <span className="u-sm">{s.assignment_count || 0}</span>
              <span>
                <StatusBadge kind={s.is_active ? 'success' : 'danger'} caps={false}>
                  {s.is_active ? t('subcontractors.activo') : t('subcontractors.inactivo')}
                </StatusBadge>
              </span>
              <div className="sub-row-actions">
                {gestionar && <>
                <IconButton onClick={e => { e.stopPropagation(); abrirEdicion(s) }}
                  ariaLabel={t('subcontractors.editar_a', { name: s.name })} title={t('subcontractors.editar_a', { name: s.name })}><Pencil size={14} aria-hidden /></IconButton>
                <IconButton className="sub-borrar" onClick={e => { e.stopPropagation(); confirmarEliminar(s) }}
                  ariaLabel={t('subcontractors.eliminar_a', { name: s.name })} title={t('subcontractors.eliminar_a', { name: s.name })}><Trash2 size={14} aria-hidden /></IconButton>
                </>}
              </div>
            </div>
          ))}
        </div>
      )}

      {showCreate && <AltaDeProveedor onClose={() => setShowCreate(false)} onCreado={setSelected} />}

      {showEdit && editTarget && (
        <Modal open title={t('subcontractors.editar_subcontratista')} onClose={() => { setShowEdit(false); setEditTarget(null) }} width={520}>
          <div className="sub-form-grid sub-form-grid--mb16">
            <div>
              <label id={`${idCampo}-7-et`} htmlFor={`${idCampo}-7`} className="sub-label">{t('subcontractors.nombre_razon_social')}</label>
              <Input id={`${idCampo}-7`} aria-labelledby={`${idCampo}-7-et`} value={editForm.name} onChange={e => setEditForm(f=>({...f,name:e.target.value}))} inputClassName="sub-input" />{msgEdit('name')}
            </div>
            <div>
              <label id={`${idCampo}-8-et`} htmlFor={`${idCampo}-8`} className="sub-label">{t('subcontractors.empresa')}</label>
              <Input id={`${idCampo}-8`} aria-labelledby={`${idCampo}-8-et`} value={editForm.company} onChange={e => setEditForm(f=>({...f,company:e.target.value}))} inputClassName="sub-input" />{msgEdit('company')}
            </div>
            <div>
              <label id={`${idCampo}-9-et`} htmlFor={`${idCampo}-9`} className="sub-label">{t('subcontractors.email')}</label>
              <Input id={`${idCampo}-9`} aria-labelledby={`${idCampo}-9-et`} type="email" value={editForm.email} onChange={e => setEditForm(f=>({...f,email:e.target.value}))} inputClassName="sub-input" />{msgEdit('email')}
            </div>
            <div>
              <label id={`${idCampo}-10-et`} htmlFor={`${idCampo}-10`} className="sub-label">{t('subcontractors.telefono')}</label>
              <Input id={`${idCampo}-10`} aria-labelledby={`${idCampo}-10-et`} value={editForm.phone} onChange={e => setEditForm(f=>({...f,phone:e.target.value}))} inputClassName="sub-input" />{msgEdit('phone')}
            </div>
            <div>
              <label id={`${idCampo}-11-et`} htmlFor={`${idCampo}-11`} className="sub-label">{t('subcontractors.nif_vat')}</label>
              <Input id={`${idCampo}-11`} aria-labelledby={`${idCampo}-11-et`} value={editForm.vat_number} onChange={e => setEditForm(f=>({...f,vat_number:e.target.value}))} inputClassName="sub-input" />{msgEdit('vat_number')}
            </div>
            <div>
              <label id={`${idCampo}-12-et`} htmlFor={`${idCampo}-12`} className="sub-label">{t('subcontractors.moneda')}</label>
              <Select suelto placeholder={false} id={`${idCampo}-12`} value={editForm.currency} onChange={e => setEditForm(f=>({...f,currency:e.target.value}))} className="sub-input">
                {monedasDeLaEmpresa.map(c => <option key={c} value={c}>{c}</option>)}
              </Select>{msgEdit('currency')}
            </div>
          </div>
          <div className="u-mb-16">
            <label id={`${idCampo}-13-et`} htmlFor={`${idCampo}-13`} className="sub-label">{t('subcontractors.notes')}</label>
            <Textarea id={`${idCampo}-13`} aria-labelledby={`${idCampo}-13-et`} value={editForm.notes} onChange={e => setEditForm(f=>({...f,notes:e.target.value}))} inputClassName="sub-input sub-textarea" />{msgEdit('notes')}
          </div>
          <div className="u-actions-8">
            <Button variant="secondary" onClick={() => { setShowEdit(false); setEditTarget(null) }}>{t('common.cancel')}</Button>
            <Button onClick={() => update({id: editTarget.id, ...editForm})} loading={updating} disabled={!editForm.name || updating}>{t('subcontractors.save_changes')}</Button>
          </div>
        </Modal>
      )}
      </div>
    </PageShell>
  )
}
