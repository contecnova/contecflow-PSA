// Alta/edicion y panel de las personas de un subcontratista. 23-11-2026: troceado de SubcontractorsPage sin cambio de comportamiento.
import { useState, useId } from 'react'
import { extractErr, fmtDate } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { enterpriseSubsApi, skillsApi } from '../services/api'
import { CamposDeExterno, CredencialesDeExterno, cargaDeExterno, estadoDeAcceso, externoCompleto, formularioDeExternoInicial } from '../components/externos/FormularioDeExterno'
import type { FormDeExterno } from '../components/externos/FormularioDeExterno'
import type { SubTrabajador } from '../services/api/tipos-alm'
import { Award, Mail, Pencil, Plus, Trash2, UserRound, X } from 'lucide-react'
import { Button, Card, EmptyState, IconButton, Modal, Spinner, Select, Checkbox, useErroresDeCampo, Input } from '../components/ui'
import StatusBadge from '../components/ui/StatusBadge'
import { useAppT } from '../i18n/AppLangContext'
import { useOrgSettings } from '../hooks/useOrgSettings'
import { STALE_5_MIN_MS } from '../constants/timings'
import { useFormatoMoneda } from '../hooks/useFormatoMoneda'
import { type CredsInfo, NIVELES, type Skill, type Worker, claseNivel } from './SubcontractorsComun'

// ── Worker Modal ──────────────────────────────────────────────────────────────
function WorkerModal({ subId, worker, onClose, onSaved }: { subId: string; worker?: Worker; onClose: () => void; onSaved?: () => void }) {
  const idCampo = useId()
  const toast = useToast()
  const qc = useQueryClient()
  const { currency: defaultCurrency, weekly_capacity_hours: capacidadEmpresa } = useOrgSettings()
  const isEdit = !!worker
  const [form, setForm] = useState<FormDeExterno>(() => formularioDeExternoInicial(worker, defaultCurrency, capacidadEmpresa))
  const [skillForm, setSkillForm] = useState({ skill_id: '', level: 'intermediate', years_experience: '', certified: false, cert_name: '' })
  const [showSkillForm, setShowSkillForm] = useState(false)

  const t = useAppT()
  const etiquetaNivel = (nivel: string) => NIVELES.includes(nivel) ? t(`subcontractors.nivel_${nivel}`) : nivel
  const { data: skillCatalog = [] } = useQuery<Skill[]>({
    queryKey: ['skills-catalog'],
    queryFn: () => skillsApi.catalog().then(r => r.data),
    staleTime: STALE_5_MIN_MS,
  })

  const [credsInfo, setCredsInfo] = useState<CredsInfo | null>(null)

  const campos = useErroresDeCampo()
  const { mutate: save, isPending: saving } = useMutation({
    onMutate: () => campos.limpiar(),
    // El alta devuelve además la contraseña temporal del usuario creado (SubTrabajadorCreado).
    mutationFn: async (d: Record<string, unknown>): Promise<SubTrabajador & { temp_password?: string }> => isEdit
      ? (await enterpriseSubsApi.updateWorker(worker!.id, d)).data
      : (await enterpriseSubsApi.createWorker(subId, d)).data,
    onSuccess: (creado) => {
      qc.invalidateQueries({ queryKey: ['sub-workers', subId] })
      qc.invalidateQueries({ queryKey: ['users'] })
      onSaved?.()
      // La contraseña temporal solo llega si se creó el usuario (con acceso): se enseña una vez.
      if (!isEdit && creado?.login_username && creado.temp_password) {
        setCredsInfo({ username: creado.login_username, password: creado.temp_password })
      } else {
        onClose()
        toast.success(isEdit ? t('subcontractors.trabajador_actualizado') : t('subcontractors.trabajador_anadido'))
      }
    },
    onError: (e: unknown) => { if (!campos.recoger(e)) toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) },
  })

  const { mutate: addSkill, isPending: addingSkill } = useMutation({
    mutationFn: (d: Record<string, unknown>) => enterpriseSubsApi.addWorkerSkill(worker?.id, d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sub-workers', subId] }); setShowSkillForm(false); setSkillForm({ skill_id: '', level: 'intermediate', years_experience: '', certified: false, cert_name: '' }); toast.success(t('subcontractors.skill_anadida')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const { mutate: removeSkill } = useMutation({
    mutationFn: (skill_id: string) => enterpriseSubsApi.removeWorkerSkill(worker?.id, skill_id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sub-workers', subId] }); toast.success(t('subcontractors.skill_eliminada')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  // group skill catalog by category
  const byCategory: Record<string, Skill[]> = skillCatalog.reduce((acc: Record<string, Skill[]>, s: Skill) => {
    const cat = s.category || 'other'
    if (!acc[cat]) acc[cat] = []
    acc[cat].push(s)
    return acc
  }, {} as Record<string, Skill[]>)

  if (credsInfo) return <CredencialesDeExterno usuario={credsInfo.username} contrasena={credsInfo.password} onClose={onClose} />

  return (
    <Modal open title={isEdit ? `${t('subcontractors.edit_person', { name: worker?.name })}` : t('subcontractors.new_person')} onClose={onClose} width={560}>
      <CamposDeExterno form={form} errores={campos.de} onChange={c => { Object.keys(c).forEach(k => campos.limpiar(k)); setForm(f => ({ ...f, ...c })) }} />

      {/* Skills section — only shown in edit mode */}
      {isEdit && (
        <div className="sub-skills-block">
          <div className="sub-skills-head">
            <div className="u-text1-sm-600">{t('subcontractors.skills')}</div>
            <Button size="sm" variant="ghost" icon={showSkillForm ? <X size={14} /> : <Plus size={14} />} onClick={() => setShowSkillForm(s => !s)}>
              {showSkillForm ? t('subcontractors.cancel_skill') : t('subcontractors.add_skill')}
            </Button>
          </div>

          {/* Existing skills */}
          <div className={`sub-skills${showSkillForm ? ' sub-skills--open' : ''}`}>
            {(worker?.skills || []).map(s => (
              <span key={s.skill_id} className={`sub-skill${claseNivel(s.level)}`}>
                {s.skill_name}
                <span className="sub-skill-level">({etiquetaNivel(s.level)})</span>
                {s.certified && <span title={t('subcontractors.certified')} role="img" aria-label={t('subcontractors.certified')}><Award size={12} aria-hidden /></span>}
                <IconButton type="button" className="sub-skill-remove" onClick={() => openConfirmGlobal({ message: t('subcontractors.confirmar_quitar_skill', { skill: s.skill_name }), danger: true, onConfirm: () => removeSkill(s.skill_id) })}
                  ariaLabel={t('subcontractors.quitar_skill', { skill: s.skill_name })} title={t('subcontractors.quitar_skill', { skill: s.skill_name })}><X size={12} aria-hidden /></IconButton>
              </span>
            ))}
            {(worker.skills || []).length === 0 && !showSkillForm && (
              <span className="u-text2-sm">{t('subcontractors.no_skills')}</span>
            )}
          </div>

          {/* Add skill form */}
          {showSkillForm && (
            <div className="sub-skill-form">
              <div className="u-col-full">
                <Select label={<>{t('subcontractors.add_skill')}*</>} placeholder={false} id={`${idCampo}-9`} value={skillForm.skill_id} onChange={e => { campos.limpiar('skill_id'); setSkillForm(f => ({ ...f, skill_id: e.target.value })) }}>
                  <option value="">{t('subcontractors.select_skill')}</option>
                  {Object.entries(byCategory).map(([cat, skills]) => (
                    <optgroup key={cat} label={cat.charAt(0).toUpperCase() + cat.slice(1)}>
                      {skills.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                    </optgroup>
                  ))}
                </Select>
              </div>
              <Select label={t('subcontractors.level')} placeholder={false} id={`${idCampo}-10`} value={skillForm.level} onChange={e => { campos.limpiar('level'); setSkillForm(f => ({ ...f, level: e.target.value })) }}>
                  {NIVELES.map(l => <option key={l} value={l}>{etiquetaNivel(l)}</option>)}
                </Select>
              <Input label={t('subcontractors.years_experience')} id={`${idCampo}-11`} type="number" value={skillForm.years_experience} onChange={e => { campos.limpiar('years_experience'); setSkillForm(f => ({ ...f, years_experience: e.target.value })) }} min="0" step="0.5" />
              <div className="sub-check-row">
                <Checkbox className="sub-check-label" checked={!!skillForm.certified} onChange={v => { campos.limpiar('certified'); setSkillForm(f => ({ ...f, certified: v })) }}
                  label={t('subcontractors.certified')} />
                {skillForm.certified && (
                  <Input aria-label={t('subcontractors.placeholder_cert')} value={skillForm.cert_name} onChange={e => { campos.limpiar('cert_name'); setSkillForm(f => ({ ...f, cert_name: e.target.value })) }} inputClassName="sub-input sub-input--flex" placeholder={t('subcontractors.placeholder_cert')} />
                )}
              </div>
              <div className="sub-row-end-full">
                <Button size="sm" onClick={() => addSkill(skillForm)} loading={addingSkill} disabled={!skillForm.skill_id || addingSkill}>{t('subcontractors.assign_skill')}</Button>
              </div>
            </div>
          )}
        </div>
      )}

      <div className="u-actions-8">
        <Button variant="secondary" onClick={onClose}>
          {isEdit ? t('subcontractors.close') : t('subcontractors.cancel')}
        </Button>
        <Button onClick={() => save(cargaDeExterno(form))} loading={saving} disabled={!externoCompleto(form) || saving}>{isEdit ? t('subcontractors.save_changes') : t('subcontractors.add_person')}</Button>
      </div>
    </Modal>
  )
}

// ── Workers Panel ─────────────────────────────────────────────────────────────
export function WorkersPanel({ subId, permitirAlta = true }: { subId: string; permitirAlta?: boolean }) {
  const toast = useToast()
  const qc = useQueryClient()
  const t = useAppT()
  const fmtMoneda = useFormatoMoneda()
  const [showCreate, setShowCreate] = useState(false)
  const [editWorker, setEditWorker] = useState<Worker | null>(null)
  const [deactivateTarget, setDeactivateTarget] = useState<Worker | null>(null)

  const { data: workers = [], isLoading } = useQuery<Worker[]>({
    queryKey: ['sub-workers', subId],
    queryFn: () => enterpriseSubsApi.workers(subId).then(r => r.data),
  })
  const hoy = new Date().toISOString().slice(0, 10)

  const { mutate: deactivate } = useMutation({
    mutationFn: (id: string) => enterpriseSubsApi.deleteWorker(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sub-workers', subId] })
      qc.invalidateQueries({ queryKey: ['users'] })
      toast.success(t('subcontractors.trabajador_desactivado'))
    },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  if (isLoading) return <Spinner />

  return (
    <div>
      {permitirAlta && (
        <div className="sub-toolbar-end">
          <Button size="sm" icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>{t('subcontractors.add_person')}</Button>
        </div>
      )}

      {workers.length === 0 ? (
        <EmptyState icon={<UserRound size={28} />} title={t('subcontractors.empty_people_title')} description={t('subcontractors.empty_people_desc')} />
      ) : (
        <div className="u-stack-10">
          {workers.map(w => (
            <Card key={w.id} className="sub-item">
              <div className="sub-worker">
                <div className="u-flex1-min0">
                  <div className="sub-worker-head">
                    <div className="u-md-700">{w.name}</div>
                    {w.role && <StatusBadge kind="neutral" caps={false}>{w.role}</StatusBadge>}
                    {!w.is_active && <StatusBadge kind="danger" caps={false}>{t('subcontractors.inactivo')}</StatusBadge>}
                    {(() => {
                      const acceso = estadoDeAcceso(w, hoy)
                      const tono = acceso === 'con_acceso' ? 'success' : acceso === 'caduca' ? 'info' : acceso === 'caducado' ? 'danger' : 'neutral'
                      return (
                        <StatusBadge kind={tono} caps={false}>
                          {acceso === 'caduca' || acceso === 'caducado'
                            ? t(`externos.acceso_${acceso}`, { fecha: fmtDate(w.access_until) })
                            : t(`externos.acceso_${acceso}`)}
                        </StatusBadge>
                      )
                    })()}
                  </div>
                  {w.email && <div className="sub-mail"><Mail size={12} aria-hidden />{w.email}</div>}
                  <div className="sub-mail"><UserRound size={12} aria-hidden />
                    {w.internal_owner_name ? t('externos.responsable_n', { nombre: w.internal_owner_name }) : t('externos.sin_responsable')}
                  </div>
                  {(!!w.cost_rate || !!w.sell_rate) && (
                    <div className="sub-rates">
                      {!!w.cost_rate && t('subcontractors.coste_por_hora', { importe: fmtMoneda(w.cost_rate, { moneda: w.currency }) })}
                      {!!w.cost_rate && !!w.sell_rate && ' · '}
                      {!!w.sell_rate && t('subcontractors.venta_por_hora', { importe: fmtMoneda(w.sell_rate, { moneda: w.currency }) })}
                    </div>
                  )}
                  {/* Skills */}
                  <div className="sub-skills sub-skills--compact">
                    {(w.skills || []).map(s => (
                      <span key={s.skill_id} className={`sub-skill sub-skill--chip${claseNivel(s.level)}`}>
                        {s.skill_name}
                        {s.certified && <Award size={11} aria-hidden className="sub-skill-cert" />}
                      </span>
                    ))}
                    {(w.skills || []).length === 0 && <span className="sub-no-skills">{t('subcontractors.no_skills_short')}</span>}
                  </div>
                </div>
                <div className="sub-worker-actions">
                  {(w.available_from || w.available_until) && (
                    <div className="sub-availability">
                      {w.available_from && <div>{t('subcontractors.desde_fecha', { fecha: fmtDate(w.available_from) })}</div>}
                      {w.available_until && <div>{t('subcontractors.hasta_fecha', { fecha: fmtDate(w.available_until) })}</div>}
                    </div>
                  )}
                  <Button size="sm" variant="secondary" icon={<Pencil size={14} />} onClick={() => setEditWorker(w)}>
                    {t('subcontractors.edit')}
                  </Button>
                  {w.is_active && (
                    <IconButton variante="caja" tono="peligro" onClick={() => setDeactivateTarget(w)}
                      ariaLabel={t('subcontractors.desactivar_a', { name: w.name })} title={t('subcontractors.desactivar_a', { name: w.name })}>
                      <Trash2 size={15} aria-hidden />
                    </IconButton>
                  )}
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      {showCreate && <WorkerModal subId={subId} onClose={() => setShowCreate(false)} onSaved={() => qc.invalidateQueries({ queryKey: ['subcontractors'] })} />}
      {editWorker && <WorkerModal subId={subId} worker={editWorker} onClose={() => setEditWorker(null)} onSaved={() => qc.invalidateQueries({ queryKey: ['subcontractors'] })} />}
      {deactivateTarget && (
        <Modal open title={t('subcontractors.desactivar_trabajador')} onClose={() => setDeactivateTarget(null)} width={380}>
          <p className="sub-confirm-text">
            {t('subcontractors.se_desactivara_a')} <strong>{deactivateTarget.name}</strong> {t('subcontractors.y_no_podra_iniciar_sesion_ni_ser')}
          </p>
          <div className="u-actions-8">
            <Button variant="ghost" onClick={() => setDeactivateTarget(null)}>{t('subcontractors.cancel')}</Button>
            <Button variant="danger" onClick={() => { deactivate(deactivateTarget.id); setDeactivateTarget(null) }}>{t('subcontractors.deactivate')}</Button>
          </div>
        </Modal>
      )}
    </div>
  )
}
