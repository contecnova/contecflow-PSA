/**
 * TrainingPage — Formación y Certificaciones
 * Catálogo de cursos, inscripciones por usuario, certificaciones con alertas de caducidad
 *
 * 16-11-2026: título del menú (nav.training); acción principal "Nuevo curso" /
 * "Nueva certificación" con icono (antes "+ Curso" con el "+" en el texto);
 * pestañas con Tabs (antes botones propios más grandes); vacíos, alertas,
 * tarjetas y estados con iconos lucide y StatusBadge (antes emojis).
 */
import { useState, useId } from 'react'
import './TrainingPage.css'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { trainingApi, usersApi } from '../services/api'
import type { PersonaVisible } from '../services/api'
import type { Certificacion, Curso, EstadoDeInscripcion, Inscripcion } from '../services/api/tipos-personas'
import { Button, Card, IconButton, Modal, Spinner, EmptyState, StatusBadge, Table, Tabs, Select } from '../components/ui'
import type { StatusBadgeKind } from '../components/ui/StatusBadge'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { AlertTriangle, Award, BookOpen, Clock, ExternalLink, GraduationCap, Pencil, Plus, Trash2, Users } from 'lucide-react'
import { useToast } from '../context/ToastContext'
import { extractErr, fmtDate } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useAuth } from '../context/AuthContext'
import { useAppT } from '../i18n/AppLangContext'
import { sanitizeUrl } from '../utils/security'
import DateInput from '../components/ui/DateInput'

import { useFormatoMoneda } from '../hooks/useFormatoMoneda'
type TrainingStatus = EstadoDeInscripcion
type CourseItem = Curso
type CertItem = Certificacion
type EnrollmentItem = Inscripcion

const STATUS_CFG: Record<TrainingStatus, { kind: StatusBadgeKind; label: string }> = {
  planned: { kind: 'accent', label: 'training.status_planned' },
  in_progress: { kind: 'warning', label: 'training.status_in_progress' },
  completed: { kind: 'success', label: 'training.status_completed' },
  cancelled: { kind: 'danger', label: 'training.status_cancelled' },
}

const IS = 'ds-input trn-input'
const LS = 'trn-label'

function CourseModal({ course, onClose }: { course?: CourseItem | null; onClose: () => void }) {
  const fmtMoneda = useFormatoMoneda()
  const idCampo = useId()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const isEdit = !!course?.id
  const [form, setForm] = useState({
    title: course?.title || '',
    description: course?.description || '',
    provider: course?.provider || '',
    category: course?.category || '',
    duration_h: String(course?.duration_h ?? ''),
    url: course?.url || '',
    cost: String(course?.cost ?? ''),
  })
  const { mutate, isPending } = useMutation({
    mutationFn: (d: { title: string; description: string; provider: string; category: string; duration_h: string; url: string; cost: string }): Promise<unknown> => isEdit ? trainingApi.updateCourse(course.id, d) : trainingApi.createCourse(d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['training-courses'] }); onClose() },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  return (
    <Modal open onClose={onClose} title={isEdit ? t('training.editar_curso') : t('training.new_course')} width={520}>
      <div className="u-stack-12">
        <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className={LS}>{t('training.titulo')}</label>
          <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} className={IS} autoFocus /></div>
        <div><label id={`${idCampo}-eta104`} htmlFor={`${idCampo}-a104`} className={LS}>{t('training.provider')}</label>
          <input id={`${idCampo}-a104`} aria-labelledby={`${idCampo}-eta104`} value={form.provider} onChange={e => setForm(f => ({ ...f, provider: e.target.value }))} className={IS} placeholder={t('training.nombre_del_proveedor')} /></div>
        <div className="trn-grid3">
          <div><label id={`${idCampo}-etcat`} htmlFor={`${idCampo}-cat`} className={LS}>{t('training.category')}</label>
            <input id={`${idCampo}-cat`} aria-labelledby={`${idCampo}-etcat`} value={form.category} onChange={e => setForm(f => ({ ...f, category: e.target.value }))} className={IS} placeholder={t('training.category')} /></div>
          <div><label id={`${idCampo}-eta109`} htmlFor={`${idCampo}-a109`} className={LS}>{t('training.horas')}</label>
            <input id={`${idCampo}-a109`} aria-labelledby={`${idCampo}-eta109`} type="number" value={form.duration_h} onChange={e => setForm(f => ({ ...f, duration_h: e.target.value }))} className={IS} placeholder={t('training.horas_del_curso')} /></div>
          <div><label htmlFor={`${idCampo}-cost`} className={LS}>{t('training.coste_moneda', { simbolo: fmtMoneda.simbolo })}</label>
            <input id={`${idCampo}-cost`} type="number" value={form.cost} onChange={e => setForm(f => ({ ...f, cost: e.target.value }))} className={IS} placeholder={t('training.coste_del_curso')} aria-label={t('training.coste_del_curso')} /></div>
        </div>
        <div><label id={`${idCampo}-eta114`} htmlFor={`${idCampo}-a114`} className={LS}>{t('training.url')}</label>
          <input id={`${idCampo}-a114`} aria-labelledby={`${idCampo}-eta114`} value={form.url} onChange={e => setForm(f => ({ ...f, url: e.target.value }))} className={IS} placeholder={t('training.url_del_curso')} /></div>
        <div className="u-actions-10">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => mutate(form)} disabled={isPending || !form.title} loading={isPending}>{isEdit ? t('common.save') : t('training.crear_curso')}</Button>
        </div>
      </div>
    </Modal>
  )
}

function CertModal({ cert, userId, onClose }: { cert?: CertItem | null; userId?: string | number | null; onClose: () => void }) {
  const idCampo = useId()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const isEdit = !!cert?.id
  const [form, setForm] = useState({
    user_id: String(userId || cert?.user_id || ''),
    name: cert?.name || '',
    issuer: cert?.issuer || '',
    cert_id: cert?.cert_id || '',
    obtained_at: cert?.obtained_at || '',
    expires_at: cert?.expires_at || '',
    url: cert?.url || '',
    notes: cert?.notes || '',
  })
  // Selector de personas: `/users/directory` (ficha mínima) sirve a cualquier rol; `/users` da 403 al subcontratado.
  const { data: users = [] } = useQuery<PersonaVisible[]>({
    queryKey: ['users', 'directory'],
    queryFn: () => usersApi.directory().then(r => r.data),
  })
  const { mutate, isPending } = useMutation({
    mutationFn: (d: { user_id: string; name: string; issuer: string; cert_id: string; obtained_at: string; expires_at: string; url: string; notes: string }) => isEdit ? trainingApi.updateCert(cert.id, d) : trainingApi.createCert(d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['training-certs'] }); onClose() },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  return (
    <Modal open onClose={onClose} title={isEdit ? t('training.editar_certificacion') : t('training.new_cert')} width={500}>
      <div className="u-stack-12">
        {!userId && <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className={LS}>{t('training.usuario_req')}</label>
          <Select suelto placeholder={false} id={`${idCampo}-1`} value={form.user_id} onChange={e => setForm(f => ({ ...f, user_id: e.target.value }))} className={IS}>
            <option value="">{t('training.seleccionar')}</option>
            {users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
          </Select></div>}
        <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className={LS}>{t('training.nombre_certificacion')}</label>
          <input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} className={IS} autoFocus /></div>
        <div className="u-grid2-10">
          <div><label id={`${idCampo}-eta162`} htmlFor={`${idCampo}-a162`} className={LS}>{t('training.issuer')}</label>
            <input id={`${idCampo}-a162`} aria-labelledby={`${idCampo}-eta162`} value={form.issuer} onChange={e => setForm(f => ({ ...f, issuer: e.target.value }))} className={IS} placeholder={t('training.entidad_emisora')} /></div>
          <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className={LS}>{t('training.cert_id')}</label>
            <input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.cert_id} onChange={e => setForm(f => ({ ...f, cert_id: e.target.value }))} className={IS} /></div>
          <div><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className={LS}>{t('training.obtenida')}</label>
            <DateInput id={`${idCampo}-4`} value={form.obtained_at} onChange={e => setForm(f => ({ ...f, obtained_at: e.target.value }))} className={IS} /></div>
          <div><label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className={LS}>{t('training.expires_at')}</label>
            <DateInput id={`${idCampo}-5`} value={form.expires_at} onChange={e => setForm(f => ({ ...f, expires_at: e.target.value }))} className={IS} /></div>
        </div>
        <div><label htmlFor={`${idCampo}-vurl`} className={LS}>{t('training.url_verificacion')}</label>
          <input id={`${idCampo}-vurl`} aria-label={t('training.url_verificacion')} value={form.url} onChange={e => setForm(f => ({ ...f, url: e.target.value }))} className={IS} placeholder={t('training.url_de_verificacion')} /></div>
        <div className="u-actions-10">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => mutate(form)} disabled={isPending || !form.name || !form.user_id} loading={isPending}>{isEdit ? t('common.save') : t('training.anadir')}</Button>
        </div>
      </div>
    </Modal>
  )
}

export default function TrainingPage() {
  const fmtMoneda = useFormatoMoneda()
  const t = useAppT()
  const qc = useQueryClient()
  const { user, hasRole } = useAuth()
  const isAdmin = hasRole('admin', 'hr')
  const [tab, setTab] = useState<'courses' | 'enrollments' | 'certs'>('courses')
  const [showCourseModal, setShowCourseModal] = useState(false)
  const [editingCourse, setEditingCourse] = useState<CourseItem | null>(null)
  const [showCertModal, setShowCertModal] = useState(false)
  const [editingCert, setEditingCert] = useState<CertItem | null>(null)

  const { data: courses = [], isLoading: loadC } = useQuery({
    queryKey: ['training-courses'],
    queryFn: () => trainingApi.courses({}).then(r => r.data).catch((): CourseItem[] => []),
  })
  const { data: certs = [], isLoading: loadCert } = useQuery({
    queryKey: ['training-certs'],
    queryFn: () => trainingApi.certs({}).then(r => r.data).catch((): CertItem[] => []),
    enabled: tab === 'certs',
  })
  const { data: enrollments = [] } = useQuery({
    queryKey: ['training-enrollments'],
    queryFn: () => trainingApi.enrollments({}).then(r => r.data).catch((): EnrollmentItem[] => []),
    enabled: tab === 'enrollments',
  })

  const { mutate: delCourse } = useMutation({
    mutationFn: (id: string | number) => trainingApi.deleteCourse(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['training-courses'] }),
  })
  const { mutate: delCert } = useMutation({
    mutationFn: (id: string | number) => trainingApi.deleteCert(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['training-certs'] }),
  })

  const expiringSoon = certs.filter((c) => c.expiring_soon && !c.is_expired)
  const expired = certs.filter((c) => c.is_expired)

  const tabs = [
    { id: 'courses', label: t('training.catalogo'), icon: <BookOpen size={14} /> },
    { id: 'enrollments', label: t('training.enrollments'), icon: <Users size={14} /> },
    { id: 'certs', label: t('training.certifications'), icon: <Award size={14} /> },
  ]
  const nuevoCurso = () => { setEditingCourse(null); setShowCourseModal(true) }
  const nuevaCert = () => { setEditingCert(null); setShowCertModal(true) }

  return (
    <PageShell>
      <PageHeader
        icon={<GraduationCap size={18} />}
        title={t('nav.training')}
        subtitle={t('training.subtitle')}
        actions={<>
          {tab === 'courses' && isAdmin && <Button icon={<Plus size={14} />} onClick={nuevoCurso}>{t('training.new_course')}</Button>}
          {tab === 'certs' && <Button icon={<Plus size={14} />} onClick={nuevaCert}>{t('training.new_cert')}</Button>}
        </>}
      />

      <div className="ds-page">
        <Tabs items={tabs} active={tab} onChange={id => setTab(id as typeof tab)} ariaLabel={t('nav.training')} />

        {tab === 'certs' && (expired.length > 0 || expiringSoon.length > 0) && (
          <div className="u-stack-8">
            {expired.map((c) => (
              <div key={c.id} className="trn-alert trn-alert--danger" role="alert">
                <AlertTriangle size={15} aria-hidden="true" className="trn-alert__icon" />
                <div className="trn-alert__text"><span className="u-base-700">{c.name}</span><span className="trn-alert__who">{c.user_name}</span></div>
                <span className="trn-alert__state">{t('training.expired')}</span>
              </div>
            ))}
            {expiringSoon.map((c) => (
              <div key={c.id} className="trn-alert trn-alert--warning" role="status">
                <Clock size={15} aria-hidden="true" className="trn-alert__icon" />
                <div className="trn-alert__text"><span className="u-base-700">{c.name}</span><span className="trn-alert__who">{c.user_name}</span></div>
                <span className="trn-alert__state">{t('training.caduca_en_dias', { n: c.days_until_expiry ?? 0 })}</span>
              </div>
            ))}
          </div>
        )}

        {tab === 'courses' && (
          loadC ? <Spinner /> : courses.length === 0 ? (
            <EmptyState icon={<BookOpen size={28} />} title={t('training.sin_cursos')}
              description={isAdmin ? t('training.sin_cursos_desc') : t('training.sin_cursos_desc_lector')}
              action={isAdmin ? <Button icon={<Plus size={14} />} onClick={nuevoCurso}>{t('training.new_course')}</Button> : undefined} />
          ) : (
            <div className="trn-courses">
              {courses.map((c) => (
                <Card key={c.id} className="trn-course">
                  <div className="trn-course__head">
                    <div className="u-flex1-min0">
                      <div className="u-md-700">{c.title}</div>
                      {c.provider && <div className="trn-course__provider">{c.provider}</div>}
                    </div>
                    {isAdmin && (
                      <div className="trn-course__actions">
                        <IconButton ariaLabel={t('training.editar_curso')} onClick={() => { setEditingCourse(c); setShowCourseModal(true) }}><Pencil size={14} /></IconButton>
                        <IconButton ariaLabel={t('training.eliminar_curso')} className="trn-danger" onClick={() => { openConfirmGlobal({ message: t('training.confirm_eliminar_curso'), onConfirm: () => delCourse(c.id), danger: true }) }}><Trash2 size={14} /></IconButton>
                      </div>
                    )}
                  </div>
                  {c.description && <div className="trn-course__desc">{c.description.slice(0,100)}{c.description.length>100 ? '…' : ''}</div>}
                  <div className="trn-course__meta">
                    {c.category && <StatusBadge kind="accent" caps={false}>{c.category}</StatusBadge>}
                    {c.duration_h ? <span className="trn-meta"><Clock size={12} aria-hidden="true" /> {c.duration_h} h</span> : null}
                    {c.cost && c.cost > 0 ? <span className="trn-meta">{fmtMoneda(c.cost)}</span> : null}
                    {c.url && <a href={sanitizeUrl(c.url)} target="_blank" rel="noopener noreferrer" className="trn-link"><ExternalLink size={12} aria-hidden="true" /> {t('training.ver')}</a>}
                    <span className="trn-enrolled">{t('training.n_inscritos', { n: c.enrolled || 0 })}</span>
                  </div>
                </Card>
              ))}
            </div>
          )
        )}

        {tab === 'enrollments' && (
          enrollments.length === 0 ? (
            <EmptyState icon={<Users size={28} />} title={t('training.sin_inscripciones')} description={t('training.sin_inscripciones_desc')} />
          ) : (
            <div className="ds-card ds-card--plano">
              <Table
                data={enrollments}
                columns={[
                  { key: 'user_name', label: t('training.empleado'), render: (_v, e) => <span className="u-base-600">{e.user_name}</span> },
                  { key: 'course_title', label: t('training.curso'), render: (_v, e) => <span className="trn-base">{e.course_title}</span> },
                  { key: 'status', label: t('training.estado'), render: (_v, e) => {
                    const sc = STATUS_CFG[e.status || 'planned'] || STATUS_CFG.planned
                    return <StatusBadge kind={sc.kind} caps={false}>{t(sc.label)}</StatusBadge>
                  } },
                  { key: 'start_date', label: t('training.inicio'), render: (_v, e) => <span className="u-text2-sm">{fmtDate(e.start_date)}</span> },
                  { key: 'end_date', label: t('training.fin'), render: (_v, e) => <span className="u-text2-sm">{fmtDate(e.end_date)}</span> },
                  { key: 'score', label: t('training.nota'), render: (_v, e) => <span className={`trn-score${e.score && e.score >= 7 ? ' trn-score--good' : e.score ? ' trn-score--low' : ''}`}>{e.score ? `${e.score}/10` : '—'}</span> },
                ]}
              />
            </div>
          )
        )}

        {tab === 'certs' && (
          loadCert ? <Spinner /> : certs.length === 0 ? (
            <EmptyState icon={<Award size={28} />} title={t('training.sin_certificaciones')} description={t('training.sin_certificaciones_desc')}
              action={<Button icon={<Plus size={14} />} onClick={nuevaCert}>{t('training.new_cert')}</Button>} />
          ) : (
            <div className="u-stack-8">
              {certs.map((c) => (
                <div key={c.id} className={`trn-cert${c.is_expired ? ' trn-cert--expired' : c.expiring_soon ? ' trn-cert--soon' : ''}`}>
                  <div className="trn-cert__icon" aria-hidden="true"><Award size={18} /></div>
                  <div className="u-flex1-min0">
                    <div className="u-base-700">{c.name}{c.issuer && <span className="trn-cert__issuer">{c.issuer}</span>}</div>
                    <div className="u-text2-sm-mt2">{c.user_name}{c.cert_id && <span className="trn-cert__id">#{c.cert_id}</span>}{c.obtained_at && <span className="trn-ml8">· {t('training.obtenida_el', { fecha: fmtDate(c.obtained_at) })}</span>}</div>
                  </div>
                  <div className="trn-cert__expiry">
                    {c.expires_at ? <div className="trn-cert__state">{c.is_expired ? t('training.expired') : t('training.caduca_el', { fecha: fmtDate(c.expires_at) })}</div> : <div className="trn-meta">{t('training.no_expiry')}</div>}
                  </div>
                  {c.url && <a href={sanitizeUrl(c.url)} target="_blank" rel="noopener noreferrer" className="trn-link"><ExternalLink size={12} aria-hidden="true" /> {t('training.verify')}</a>}
                  <IconButton ariaLabel={t('training.editar_certificacion')} onClick={() => { setEditingCert(c); setShowCertModal(true) }}><Pencil size={14} /></IconButton>
                  <IconButton ariaLabel={t('training.eliminar_certificacion')} className="trn-danger" onClick={() => { openConfirmGlobal({ message: t('training.confirm_eliminar_cert'), onConfirm: () => delCert(c.id), danger: true }) }}><Trash2 size={14} /></IconButton>
                </div>
              ))}
            </div>
          )
        )}
      </div>

      {showCourseModal && <CourseModal course={editingCourse} onClose={() => { setShowCourseModal(false); setEditingCourse(null) }} />}
      {showCertModal && <CertModal cert={editingCert} userId={!isAdmin ? user?.id : null} onClose={() => { setShowCertModal(false); setEditingCert(null) }} />}
    </PageShell>
  )
}
