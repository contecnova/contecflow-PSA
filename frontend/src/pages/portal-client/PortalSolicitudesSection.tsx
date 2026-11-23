// Seccion de peticiones de cambio del portal de cliente. 23-11-2026: troceado de PortalAdvancedSections sin cambio de comportamiento.
import { useId, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Lightbulb, Plus, CheckCircle2, XCircle, Clock, FolderOpen, Wallet, CalendarDays } from 'lucide-react'
import { useToast } from '../../context/ToastContext'
import { fmtDate } from '../../utils/helpers'
import { BadgeWithTooltip } from '../../components/ui/BadgeWithTooltip'
import { IconCR } from '../../components/ui/FRCRIcons'
import { CLIENT_API, useErrorDelPortal, useLang, useClientAuth, useEtiquetaEstado } from './portalClientContext'
import PortalDemandas from './PortalDemandas'
import { PortalPageHeader, PortalCard, PortalEmpty, PortalButton, PortalModal, PortalField, PortalInput, PortalSelect, PortalTextarea, PortalTabs, formatMoney } from './PortalUI'
import { useErroresDeCampo } from '../../components/ui'
import { type ClientProject, type FeatureRequest, type FeatureRequestForm, StatusBadge } from './PortalAdvancedComun'

// ════════════════════════════════════════════════════════════════════════════
// PortalFeatureRequests
// ════════════════════════════════════════════════════════════════════════════
/**
 * «Solicitudes» (22-11-2026): pestañas «Demandas» (flujo de demanda configurable,
 * PortalDemandas) y «Peticiones de cambio (clásicas)». Si el servidor no
 * ofrece ningún tipo de demanda al cliente (`GET /portal/demand/types`), solo
 * se ve lo clásico.
 */
export function PortalFeatureRequests() {
  const t = useLang()
  const [tab, setTab] = useState<string | null>(null)
  const { data: tipos, isLoading } = useQuery<{ types?: unknown[] }>({
    queryKey: ['portal-demand-types'],
    queryFn: () => CLIENT_API.get('/portal/demand/types').then(r => r.data as { types?: unknown[] }),
    retry: false,
  })
  if (isLoading) return null
  const hayDemandas = (tipos?.types?.length ?? 0) > 0
  if (!hayDemandas) return <PortalPeticionesClasicas />
  const actual = tab ?? 'demandas'
  return (
    <div className="u-stack-16">
      <PortalTabs ariaLabel={t('dem_titulo_seccion')} value={actual} onChange={setTab} tabs={[
        { id: 'demandas', label: t('dem_tab_demandas') },
        { id: 'clasicas', label: t('dem_tab_clasicas') },
      ]} />
      {actual === 'demandas' ? <PortalDemandas /> : <PortalPeticionesClasicas />}
    </div>
  )
}

function PortalPeticionesClasicas() {
  const traducir = useLang()
  const errorDe = useErrorDelPortal()
  const etiquetaEstado = useEtiquetaEstado()
  const t = useLang()
  const toast = useToast()
  const qc = useQueryClient()
  const formIdPrefix = useId()
  const { client } = useClientAuth()
  // `projects` llega sin tipar en la sesión; aquí se usan id, nombre y código.
  const clientProjects = (client?.projects || []) as ClientProject[]
  const [showNew, setShowNew] = useState(false)
  const [editingFr, setEditingFr] = useState<FeatureRequest | null>(null)
  const [form, setForm] = useState<FeatureRequestForm>({ title: '', description: '', business_justification: '', affected_area: '', priority: 'medium', project_id: '' })

  const { data: frs = [], isLoading } = useQuery<FeatureRequest[]>({
    queryKey: ['portal-frs-client'],
    queryFn: () => CLIENT_API.get('/portal/feature-requests').then(r => r.data),
  })

  const campos = useErroresDeCampo()
  const resetForm = () => setForm({ title: '', description: '', business_justification: '', affected_area: '', priority: 'medium', project_id: '' })

  const { mutate: createFR } = useMutation({
    mutationFn: (d: FeatureRequestForm) => CLIENT_API.post('/portal/feature-requests', d),
    onMutate: () => campos.limpiar(),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['portal-frs-client'] }); setShowNew(false); resetForm(); toast.success(traducir('intake_form.success_title')) },
    onError: (e: unknown) => { if (!campos.recoger(e)) toast.error(errorDe(e, t('pas_err_generic'))) },
  })
  const { mutate: updateFR, isPending: updatingFr } = useMutation({
    mutationFn: ({ id, data }: { id: string; data: FeatureRequestForm }) => CLIENT_API.patch(`/portal/feature-requests/${id}`, data),
    onMutate: () => campos.limpiar(),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['portal-frs-client'] }); setEditingFr(null); setShowNew(false); resetForm(); toast.success(traducir('portaladvanced.actualizada')) },
    onError: (e: unknown) => { if (!campos.recoger(e)) toast.error(errorDe(e, t('pas_err_generic'))) },
  })
  const { mutate: withdrawFR, isPending: withdrawingFr } = useMutation({
    mutationFn: ({ id }: { id: string }) => CLIENT_API.post(`/portal/feature-requests/${id}/withdraw`, {}),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['portal-frs-client'] }); toast.success(traducir('portaladvanced.solicitud_retirada')) },
    onError: (e: unknown) => toast.error(errorDe(e, traducir('error_inesperado'))),
  })
  const { mutate: decide } = useMutation({
    mutationFn: ({ id, approved, reason }: { id: string; approved: boolean; reason?: string }) => CLIENT_API.post(`/portal/feature-requests/${id}/decide`, { approved, reason }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['portal-frs-client'] }); toast.success(traducir('chat.decision_registrada')) },
    onError: (e: unknown) => toast.error(errorDe(e, traducir('error_inesperado'))),
  })

  const openEdit = (fr: FeatureRequest) => {
    setEditingFr(fr); setShowNew(true)
    setForm({
      title: fr.title || '', description: fr.description || '',
      business_justification: fr.business_justification || '',
      affected_area: fr.affected_area || '', priority: fr.priority || 'medium',
      project_id: fr.project_id || '',
    })
  }

  const totalProjects = client?.projects?.length || client?.project_ids?.length || 0
  const requiresProject = totalProjects > 1

  return (
    <div>
      <PortalPageHeader
        title={traducir('portaladvanced.solicitudes_y_cambios')}
        subtitle={traducir('portaladvanced.tus_peticiones_de_nuevas_funcionalidades_y_cambios')}
        icon={Lightbulb}
        meta={[
          { value: frs.length, label: t('pas_meta_total') },
          { value: frs.filter(f => f.status === 'estimated' && f.client_approved == null).length, label: t('pas_meta_await_decision'), color: 'var(--warning)' },
          { value: frs.filter(f => f.status === 'approved').length, label: t('pas_meta_approved'), color: 'var(--success)' },
        ]}
        actions={
          client?.can_request_changes ? (
            <PortalButton icon={<Plus size={14} />} onClick={() => { resetForm(); setEditingFr(null); setShowNew(true) }}>
              {traducir('portaladvanced.nueva_solicitud')}
            </PortalButton>
          ) : null
        }
      />

      {isLoading ? null : frs.length === 0 ? (
        <PortalEmpty icon={Lightbulb}
          title={traducir('portaladvanced.sin_solicitudes')}
          description={client?.can_request_changes ? t('pas_fr_empty_can') : t('pas_fr_empty_cannot')}
          action={client?.can_request_changes ? (
            <PortalButton icon={<Plus size={14} />} onClick={() => { resetForm(); setEditingFr(null); setShowNew(true) }}>{traducir('portaladvanced.nueva_solicitud')}</PortalButton>
          ) : null}
        />
      ) : (
        <div className="u-stack-12">
          {frs.map(fr => (
            <PortalCard key={fr.id}>
              <div className="poadse-row-8">
                <div className="u-flex1-min0">
                  <div className="poadse-row-9">
                    <span className="u-text3-mono-xs">{fr.code}</span>
                    <span className="poadse-txt-2">{fr.title}</span>
                  </div>
                  <div className="poadse-row-10">
                    {fr.project_name && <span className="poadse-con-icono"><FolderOpen size={12} aria-hidden="true" />{fr.project_name}</span>}
                    {fr.submitted_at && <span>{traducir('portaladvanced.creada')} {fmtDate(fr.submitted_at)}</span>}
                    {fr.affected_area && <span>{traducir('portaladvanced.area')} {fr.affected_area}</span>}
                  </div>
                  <p className="poadse-box-7">{fr.description}</p>
                  {fr.pm_response && (
                    <div className="poadse-box-8">
                      <div className="poadse-box-9">
                        {traducir('portaladvanced.respuesta_del_pm')}
                      </div>
                      <p className="poadse-box-10">{fr.pm_response}</p>
                      <div className="poadse-row-11">
                        {fr.estimated_cost && <span className="poadse-txt-3 poadse-con-icono"><Wallet size={13} aria-hidden="true" />{formatMoney(fr.estimated_cost)}</span>}
                        {fr.estimated_hours && <span className="u-accent poadse-con-icono"><Clock size={13} aria-hidden="true" />{fr.estimated_hours} h</span>}
                        {fr.estimated_delivery_weeks && <span className="u-text2 poadse-con-icono"><CalendarDays size={13} aria-hidden="true" />~{fr.estimated_delivery_weeks} {traducir('bi.weeks')}</span>}
                      </div>
                    </div>
                  )}
                  {fr.status === 'estimated' && fr.client_approved == null && (
                    <div className="poadse-row-12">
                      <PortalButton variant="danger" size="sm" icon={<XCircle size={13} />}
                        onClick={() => decide({ id: fr.id, approved: false })}>{traducir('aus.rechazar')}</PortalButton>
                      <PortalButton size="sm" icon={<CheckCircle2 size={13} />}
                        onClick={() => decide({ id: fr.id, approved: true })}>{traducir('portaladvanced.aprobar_presupuesto')}</PortalButton>
                    </div>
                  )}
                  {fr.client_approved === true && (
                    <div className="poadse-box-11">
                      {traducir('portaladvanced.aprobado_por_ti_el')} {fmtDate(fr.client_approved_at)}
                    </div>
                  )}
                  {fr.client_approved === false && (
                    <div className="poadse-box-12">{traducir('portaladvanced.rechazado_por_ti')}</div>
                  )}
                  {fr.can_edit_by_client && (
                    <div className="poadse-row-13">
                      <PortalButton variant="secondary" size="sm" onClick={() => openEdit(fr)}>{traducir('common.edit')}</PortalButton>
                      <PortalButton variant="danger" size="sm" loading={withdrawingFr}
                        onClick={() => withdrawFR({ id: fr.id })}>{traducir('pol.retirar')}</PortalButton>
                    </div>
                  )}
                </div>
                <div className="poadse-stack-1">
                  <StatusBadge status={fr.status} />
                  {fr.cr_status ? (
                    <BadgeWithTooltip
                      label={`CR: ${etiquetaEstado(fr.cr_status)}`}
                      color={fr.cr_status_color || 'var(--text-3)'}
                      tooltip={traducir('portaladvanced.estado_de_la_change_request_vinculada')}
                      icon={<IconCR />}
                    />
                  ) : (
                    <BadgeWithTooltip
                      label={traducir('portaladvanced.sin_cr')}
                      color="var(--text-3)"
                      tooltip={traducir('portaladvanced.se_generara_change_request_al_aprobar_la')}
                      icon={<IconCR />}
                    />
                  )}
                </div>
              </div>
            </PortalCard>
          ))}
        </div>
      )}

      <PortalModal
        open={showNew}
        onClose={() => { setShowNew(false); setEditingFr(null); resetForm() }}
        title={editingFr ? t('pas_fr_edit_title') : traducir('portaladvanced.nueva_solicitud')}
        subtitle={traducir('portaladvanced.describe_lo_que_necesitas_con_el_mayor')}
        width={620}
        footer={
          <>
            <PortalButton variant="secondary" onClick={() => { setShowNew(false); setEditingFr(null); resetForm() }}>{traducir('common.cancel')}</PortalButton>
            <PortalButton
              loading={updatingFr}
              disabled={!form.title || !form.description || (requiresProject && !form.project_id)}
              onClick={() => editingFr ? updateFR({ id: editingFr.id, data: form }) : createFR(form)}
            >{editingFr ? t('pas_save_changes') : t('pas_send_request')}</PortalButton>
          </>
        }
      >
        <div className="u-stack-14">
          {requiresProject && (
            <PortalField label={traducir('gas.proyecto')} error={campos.de('project_id')} required>
              <PortalSelect id={`${formIdPrefix}-project`} value={form.project_id}
                onChange={e => { campos.limpiar('project_id'); setForm(f => ({ ...f, project_id: e.target.value })) }}>
                <option value="">{traducir('invoices.select')}</option>
                {clientProjects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
              </PortalSelect>
            </PortalField>
          )}
          <PortalField label={traducir('portaladvanced.titulo')} error={campos.de('title')} required>
            <PortalInput value={form.title} onChange={e => { campos.limpiar('title'); setForm(f => ({ ...f, title: e.target.value })) }} placeholder={traducir('portaladvanced.resumen_breve')} />
          </PortalField>
          <PortalField label={traducir('portaladvanced.descripcion')} error={campos.de('description')} required>
            <PortalTextarea rows={3} value={form.description} onChange={e => { campos.limpiar('description'); setForm(f => ({ ...f, description: e.target.value })) }} placeholder={traducir('portaladvanced.que_necesitas')} />
          </PortalField>
          <PortalField label={traducir('portaladvanced.justificacion_de_negocio')} error={campos.de('business_justification')} hint={t('pas_fr_justification_hint')}>
            <PortalTextarea rows={2} value={form.business_justification} onChange={e => { campos.limpiar('business_justification'); setForm(f => ({ ...f, business_justification: e.target.value })) }} />
          </PortalField>
          <div className="u-grid2-12">
            <PortalField label={traducir('portaladvanced.area_afectada')} error={campos.de('affected_area')}>
              <PortalInput value={form.affected_area} onChange={e => { campos.limpiar('affected_area'); setForm(f => ({ ...f, affected_area: e.target.value })) }} placeholder={traducir('portaladvanced.ej_reporting_login')} />
            </PortalField>
            <PortalField label={traducir('common.priority')} error={campos.de('priority')}>
              <PortalSelect value={form.priority} onChange={e => { campos.limpiar('priority'); setForm(f => ({ ...f, priority: e.target.value })) }}>
                <option value="low">{traducir('lec.sev_baja')}</option>
                <option value="medium">{traducir('lec.sev_media')}</option>
                <option value="high">{traducir('lec.sev_alta')}</option>
                <option value="critical">{traducir('portaladvanced.critica')}</option>
              </PortalSelect>
            </PortalField>
          </div>
        </div>
      </PortalModal>
    </div>
  )
}
