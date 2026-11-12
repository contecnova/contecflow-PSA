/**
 * Configuración del Service Desk: reglas de escalado y textos de los avisos.
 *
 * Las dos cosas existían solo en el servidor: las reglas se podían crear por API
 * y los avisos no se podían ver ni cambiar. Aquí se gestionan donde se buscan,
 * junto al SLA, las colas y el enrutado.
 */
import { useEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { extractErr, localeActivo } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { useToast } from '../../context/ToastContext'
import { useAppT } from '../../i18n/AppLangContext'
import { Button, Spinner, EmptyState, Modal } from '../../components/ui'
import { COLOR } from '../../constants/theme'
import { sdEscalationApi, sdNotificationTemplatesApi, sdGroupsApi, usersApi } from '../../services/api'
import { PRIORITY_LABEL } from './sdUtils'
import { RuntimeGroupEditor } from '../settings-sections/SettingsAdvancedSections'

const PRIORIDADES = ['p1_critical', 'p2_high', 'p3_medium', 'p4_low']
const DISPARADORES = ['sla_at_risk', 'sla_breached', 'idle_hours', 'priority', 'reopened']
const ACCIONES = ['notify_manager', 'notify_group_lead', 'notify_custom', 'reassign_group', 'elevate_priority']
const PRIORITY_LABEL_MAP = PRIORITY_LABEL as Record<string, string>

type Regla = {
  id: string; name: string; is_active: boolean; sort_order: number
  trigger: string; action: string; applies_to_priority?: string | null
  idle_hours_threshold?: number | null; group_id?: string | null
  target_group_id?: string | null; notify_user_ids?: string | null; target_priority?: string | null
}
type Disparo = { id: string; rule_name?: string; ticket_number?: string; action_taken?: string; triggered_at?: string }
type Cola = { id: string; name: string }
type Persona = { id: string; full_name?: string }

const IS: CSSProperties = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
  borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: 'var(--text-base)',
  outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const LS: CSSProperties = { fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--text-2)', display: 'block',
  marginBottom: 5, textTransform: 'uppercase', letterSpacing: '0.06em' }
// Tarjeta del sistema de diseño (`.ds-card`); aquí solo lo que cambia.
const TARJETA: CSSProperties = { padding: 16 }

function lista(raw?: string | null): string[] {
  if (!raw) return []
  try { const v = JSON.parse(raw); return Array.isArray(v) ? v.map(String) : [] } catch { return [] }
}

function Chip({ activo, onClick, children }: { activo: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" onClick={onClick} aria-pressed={activo} style={{
      padding: '5px 11px', borderRadius: 999, cursor: 'pointer', fontFamily: 'inherit', fontSize: 'var(--text-sm)',
      border: `1px solid ${activo ? 'var(--accent)' : 'var(--surface-4)'}`,
      background: activo ? 'var(--accent-muted)' : 'transparent', color: activo ? 'var(--accent)' : 'var(--text-2)',
    }}>{children}</button>
  )
}

// ── Escalado ─────────────────────────────────────────────────────────────────
export function EscalationConfig() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [editando, setEditando] = useState<Regla | 'nueva' | null>(null)

  const { data: reglas = [], isLoading } = useQuery<Regla[]>({
    queryKey: ['sd-escalation'], queryFn: () => sdEscalationApi.list().then(r => r.data as Regla[]),
  })
  const { data: disparos = [] } = useQuery<Disparo[]>({
    queryKey: ['sd-escalation-logs'], queryFn: () => sdEscalationApi.logs(15).then(r => r.data as Disparo[]),
  })
  const { data: colas = [] } = useQuery<Cola[]>({
    queryKey: ['sd-groups'], queryFn: () => sdGroupsApi.list().then(r => r.data as Cola[]),
  })
  const { data: personas = [] } = useQuery<Persona[]>({
    queryKey: ['users'], queryFn: () => usersApi.list().then(r => r.data as unknown as Persona[]),
  })
  const refrescar = () => { qc.invalidateQueries({ queryKey: ['sd-escalation'] }) }
  const { mutate: guardar, isPending } = useMutation({
    mutationFn: ({ id, ...d }: Record<string, unknown>) =>
      id ? sdEscalationApi.update(String(id), d) : sdEscalationApi.create(d),
    onSuccess: () => { refrescar(); setEditando(null); toast.success(t('sd_cfg.esc_saved')) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: borrar } = useMutation({
    mutationFn: (id: string) => sdEscalationApi.delete(id),
    onSuccess: refrescar,
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const nombreCola = (id?: string | null) => colas.find(c => c.id === id)?.name ?? '—'

  const resumenAccion = (r: Regla) => {
    const base = t(`sd_cfg.esc_action_${r.action}`)
    if (r.action === 'reassign_group') return `${base}: ${nombreCola(r.target_group_id)}`
    if (r.action === 'elevate_priority') return `${base}: ${PRIORITY_LABEL_MAP[r.target_priority || ''] ?? ''}`
    if (r.action === 'notify_custom') {
      const ids = lista(r.notify_user_ids)
      return `${base}: ${ids.map(i => personas.find(p => p.id === i)?.full_name ?? i).join(', ')}`
    }
    return base
  }
  const resumenDisparo = (r: Regla) => {
    const base = t(`sd_cfg.esc_trigger_${r.trigger}`)
    const extra = [
      r.trigger === 'idle_hours' && r.idle_hours_threshold ? `${r.idle_hours_threshold} h` : null,
      lista(r.applies_to_priority).map(p => PRIORITY_LABEL_MAP[p] ?? p).join(', ') || null,
      r.group_id ? nombreCola(r.group_id) : null,
    ].filter(Boolean)
    return extra.length ? `${base} · ${extra.join(' · ')}` : base
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'flex-start', flexWrap: 'wrap' }}>
        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-3)', maxWidth: 640 }}>{t('sd_cfg.esc_intro')}</div>
        <Button onClick={() => setEditando('nueva')}>+ {t('sd_cfg.esc_new')}</Button>
      </div>

      {isLoading ? <Spinner /> : reglas.length === 0 ? (
        <EmptyState icon="⬆️" title={t('sd_cfg.esc_empty')} description={t('sd_cfg.esc_empty_desc')} />
      ) : (
        <div className="u-stack-10">
          {reglas.map(r => (
            <div key={r.id} className="ds-card" style={{ ...TARJETA, opacity: r.is_active ? 1 : 0.6, display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
              <div style={{ flex: '1 1 320px', minWidth: 0 }}>
                <div style={{ fontWeight: 600, color: 'var(--text-1)', marginBottom: 6 }}>
                  {r.name}
                  {!r.is_active && <span style={{ marginLeft: 8, fontSize: 'var(--text-2xs)', color: 'var(--text-3)' }}>{t('sd_cfg.esc_inactive')}</span>}
                </div>
                <div className="u-text2-sm">
                  <strong>{t('sd_cfg.esc_when')}</strong> {resumenDisparo(r)}
                </div>
                <div className="u-text2-sm">
                  <strong>{t('sd_cfg.esc_then')}</strong> {resumenAccion(r)}
                </div>
              </div>
              <div className="u-row-8">
                <Button variant="secondary" onClick={() => setEditando(r)}>{t('common.edit')}</Button>
                <Button variant="secondary" onClick={() => openConfirmGlobal({
                  message: t('sd_cfg.esc_delete_confirm'), onConfirm: () => borrar(r.id), danger: true,
                })}><span style={{ color: COLOR.danger }}>{t('common.delete')}</span></Button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div>
        <div style={{ ...LS, marginBottom: 10 }}>{t('sd_cfg.esc_log')}</div>
        {disparos.length === 0 ? (
          <div className="u-text3-sm">{t('sd_cfg.esc_log_empty')}</div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-sm)' }}>
            <tbody>
              {disparos.map(d => (
                <tr key={d.id} style={{ borderBottom: '1px solid var(--surface-4)' }}>
                  <td style={{ padding: '7px 8px', color: 'var(--text-3)', whiteSpace: 'nowrap' }}>{d.triggered_at ? new Date(d.triggered_at).toLocaleString(localeActivo()) : ''}</td>
                  <td style={{ padding: '7px 8px', fontWeight: 600 }}>{d.ticket_number}</td>
                  <td style={{ padding: '7px 8px', color: 'var(--text-2)' }}>{d.action_taken}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {editando && (
        <Modal open size="lg" title={editando === 'nueva' ? t('sd_cfg.esc_new') : t('sd_cfg.esc_edit')} onClose={() => setEditando(null)}>
          <FormularioRegla inicial={editando === 'nueva' ? null : editando} colas={colas} personas={personas}
            pendiente={isPending} onCancelar={() => setEditando(null)} onGuardar={guardar} />
        </Modal>
      )}
    </div>
  )
}

function FormularioRegla({ inicial, colas, personas, pendiente, onCancelar, onGuardar }: {
  inicial: Regla | null; colas: Cola[]; personas: Persona[]; pendiente: boolean
  onCancelar: () => void; onGuardar: (d: Record<string, unknown>) => void
}) {
  const t = useAppT()
  const [f, setF] = useState({
    name: inicial?.name ?? '', trigger: inicial?.trigger ?? 'sla_breached', action: inicial?.action ?? 'notify_group_lead',
    idle: inicial?.idle_hours_threshold ?? 24, prioridades: lista(inicial?.applies_to_priority),
    group_id: inicial?.group_id ?? '', target_group_id: inicial?.target_group_id ?? '',
    target_priority: inicial?.target_priority ?? 'p1_critical', avisar: lista(inicial?.notify_user_ids),
    is_active: inicial?.is_active ?? true,
  })
  const set = (k: string, v: unknown) => setF(prev => ({ ...prev, [k]: v }))
  const alternar = (k: 'prioridades' | 'avisar', v: string) =>
    set(k, f[k].includes(v) ? f[k].filter(x => x !== v) : [...f[k], v])
  const completa = !!f.name.trim()
    && (f.trigger !== 'idle_hours' || Number(f.idle) > 0)
    && (f.action !== 'reassign_group' || !!f.target_group_id)
    && (f.action !== 'notify_custom' || f.avisar.length > 0)

  const enviar = () => onGuardar({
    id: inicial?.id, name: f.name.trim(), trigger: f.trigger, action: f.action, is_active: f.is_active,
    idle_hours_threshold: f.trigger === 'idle_hours' ? Number(f.idle) : null,
    applies_to_priority: f.prioridades.length ? JSON.stringify(f.prioridades) : null,
    group_id: f.group_id || null,
    target_group_id: f.action === 'reassign_group' ? f.target_group_id : null,
    target_priority: f.action === 'elevate_priority' ? f.target_priority : null,
    notify_user_ids: f.action === 'notify_custom' ? JSON.stringify(f.avisar) : null,
    sort_order: inicial?.sort_order ?? 100,
  })

  return (
    <div className="u-stack-16">
      <div><label style={LS} htmlFor="esc-name">{t('sd_cfg.esc_name')} *</label>
        <input id="esc-name" aria-label={t('sd_cfg.esc_name')} value={f.name} onChange={e => set('name', e.target.value)} style={IS} /></div>

      <fieldset className="ds-card" style={{ ...TARJETA, display: 'flex', flexDirection: 'column', gap: 12 }}>
        <legend style={LS}>{t('sd_cfg.esc_when')}</legend>
        <select aria-label={t('sd_cfg.esc_when')} value={f.trigger} onChange={e => set('trigger', e.target.value)} style={IS}>
          {DISPARADORES.map(d => <option key={d} value={d}>{t(`sd_cfg.esc_trigger_${d}`)}</option>)}
        </select>
        {f.trigger === 'idle_hours' && (
          <div><label style={LS} htmlFor="esc-idle">{t('sd_cfg.esc_idle_hours')}</label>
            <input id="esc-idle" aria-label={t('sd_cfg.esc_idle_hours')} type="number" min={1} value={f.idle} onChange={e => set('idle', e.target.value)} style={{ ...IS, maxWidth: 160 }} /></div>
        )}
        <div><span style={LS}>{t('sd_cfg.esc_priorities')}</span>
          <div className="u-wrap-6">
            {PRIORIDADES.map(p => <Chip key={p} activo={f.prioridades.includes(p)} onClick={() => alternar('prioridades', p)}>{PRIORITY_LABEL_MAP[p]}</Chip>)}
          </div></div>
        <div><label style={LS} htmlFor="esc-group">{t('sd_cfg.esc_group')}</label>
          <select id="esc-group" value={f.group_id} onChange={e => set('group_id', e.target.value)} style={IS}>
            <option value="">{t('sd_cfg.esc_any_group')}</option>
            {colas.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select></div>
      </fieldset>

      <fieldset className="ds-card" style={{ ...TARJETA, display: 'flex', flexDirection: 'column', gap: 12 }}>
        <legend style={LS}>{t('sd_cfg.esc_then')}</legend>
        <select aria-label={t('sd_cfg.esc_then')} value={f.action} onChange={e => set('action', e.target.value)} style={IS}>
          {ACCIONES.map(a => <option key={a} value={a}>{t(`sd_cfg.esc_action_${a}`)}</option>)}
        </select>
        {f.action === 'reassign_group' && (
          <div><label style={LS} htmlFor="esc-target">{t('sd_cfg.esc_target_group')} *</label>
            <select id="esc-target" value={f.target_group_id} onChange={e => set('target_group_id', e.target.value)} style={IS}>
              <option value="">—</option>
              {colas.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select></div>
        )}
        {f.action === 'elevate_priority' && (
          <div><label style={LS} htmlFor="esc-prio">{t('sd_cfg.esc_target_priority')}</label>
            <select id="esc-prio" value={f.target_priority} onChange={e => set('target_priority', e.target.value)} style={IS}>
              {PRIORIDADES.map(p => <option key={p} value={p}>{PRIORITY_LABEL_MAP[p]}</option>)}
            </select></div>
        )}
        {f.action === 'notify_custom' && (
          <div><span style={LS}>{t('sd_cfg.esc_users')} *</span>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', maxHeight: 180, overflowY: 'auto' }}>
              {personas.map(p => <Chip key={p.id} activo={f.avisar.includes(p.id)} onClick={() => alternar('avisar', p.id)}>{p.full_name ?? p.id}</Chip>)}
            </div></div>
        )}
      </fieldset>

      <label style={{ display: 'flex', gap: 8, alignItems: 'center', cursor: 'pointer', color: 'var(--text-1)' }}>
        <input type="checkbox" aria-label={t('sd_cfg.esc_active')} checked={f.is_active} onChange={e => set('is_active', e.target.checked)} />
        {t('sd_cfg.esc_active')}
      </label>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, alignItems: 'center' }}>
        {!completa && f.name.trim() && <span style={{ fontSize: 'var(--text-sm)', color: COLOR.warning }}>{t('sd_cfg.esc_incomplete')}</span>}
        <Button variant="secondary" onClick={onCancelar}>{t('common.cancel')}</Button>
        <Button onClick={enviar} disabled={!completa || pendiente} loading={pendiente}>{t('common.save')}</Button>
      </div>
    </div>
  )
}

// ── Avisos ───────────────────────────────────────────────────────────────────
type TextoIdioma = { subject: string; body_html: string; is_active: boolean; customized: boolean }
type Aviso = { code: string; event: string; role: string; languages: Record<string, TextoIdioma> }
const VARIABLES = ['ticket_number', 'ticket_title', 'ticket_status', 'ticket_priority', 'requester_name',
  'assignee_name', 'group_name', 'comment_author', 'comment_body', 'resolution', 'sla_due', 'link']

const claveAviso = (a: Aviso) => `sd_cfg.ntf_${a.event}_${a.role}`

export function NotificationsConfig() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [idioma, setIdioma] = useState('es')
  const [editando, setEditando] = useState<Aviso | null>(null)

  const { data: avisos = [], isLoading } = useQuery<Aviso[]>({
    queryKey: ['sd-notification-templates'],
    queryFn: () => sdNotificationTemplatesApi.list().then(r => r.data as Aviso[]),
  })
  const refrescar = () => qc.invalidateQueries({ queryKey: ['sd-notification-templates'] })
  const { mutate: guardar, isPending } = useMutation({
    mutationFn: ({ code, ...d }: { code: string; subject: string; body_html: string; is_active: boolean }) =>
      sdNotificationTemplatesApi.save(code, idioma, d),
    onSuccess: () => { refrescar(); setEditando(null); toast.success(t('sd_cfg.ntf_saved')) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: restaurar } = useMutation({
    mutationFn: (code: string) => sdNotificationTemplatesApi.restore(code, idioma),
    onSuccess: () => { refrescar(); setEditando(null) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const idiomas = Object.keys(avisos[0]?.languages ?? { es: 1, en: 1 })
  const roles = ['requester', 'agent', 'approver']

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap', alignItems: 'flex-start' }}>
        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-3)', maxWidth: 640 }}>{t('sd_cfg.ntf_intro')}</div>
        <div role="group" aria-label={t('sd_cfg.ntf_language')} className="u-row-6">
          {idiomas.map(i => <Chip key={i} activo={idioma === i} onClick={() => setIdioma(i)}>{i.toUpperCase()}</Chip>)}
        </div>
      </div>

      {isLoading ? <Spinner /> : roles.map(rol => {
        const delRol = avisos.filter(a => a.role === rol)
        if (!delRol.length) return null
        return (
          <div key={rol}>
            <div style={{ ...LS, marginBottom: 8 }}>{t(`sd_cfg.role_${rol}`)}</div>
            <div className="ds-card" style={{ ...TARJETA, padding: 0, overflow: 'hidden' }}>
              {delRol.map((a, i) => {
                const txt = a.languages[idioma]
                return (
                  <div key={a.code} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '11px 16px',
                    borderTop: i ? '1px solid var(--surface-4)' : 'none', flexWrap: 'wrap' }}>
                    <div style={{ flex: '1 1 260px', minWidth: 0 }}>
                      <div style={{ fontWeight: 600, color: txt?.is_active ? 'var(--text-1)' : 'var(--text-3)' }}>{t(claveAviso(a))}</div>
                      <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-3)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{txt?.subject}</div>
                    </div>
                    <span style={{ fontSize: 'var(--text-2xs)', fontWeight: 600, padding: '2px 8px', borderRadius: 4,
                      background: txt?.is_active ? 'var(--accent-muted)' : 'var(--surface-4)', color: txt?.is_active ? 'var(--accent)' : 'var(--text-3)' }}>
                      {txt?.is_active ? t('sd_cfg.ntf_on') : t('sd_cfg.ntf_off')}
                    </span>
                    <span style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-3)', minWidth: 90 }}>
                      {txt?.customized ? t('sd_cfg.ntf_customized') : t('sd_cfg.ntf_default')}
                    </span>
                    <Button variant="secondary" onClick={() => setEditando(a)}>{t('common.edit')}</Button>
                  </div>
                )
              })}
            </div>
          </div>
        )
      })}

      <div className="ds-card" style={TARJETA}>
        <div style={{ ...LS, marginBottom: 10 }}>{t('sd_cfg.ntf_who')}</div>
        <RuntimeGroupEditor groupId="service_desk" />
      </div>

      {editando && (
        <Modal open size="lg" title={`${t('sd_cfg.ntf_edit')} · ${t(claveAviso(editando))} · ${idioma.toUpperCase()}`} onClose={() => setEditando(null)}>
          <FormularioAviso aviso={editando} texto={editando.languages[idioma]} pendiente={isPending}
            onCancelar={() => setEditando(null)}
            onGuardar={d => guardar({ code: editando.code, ...d })}
            onRestaurar={() => openConfirmGlobal({ message: t('sd_cfg.ntf_restore_confirm'), onConfirm: () => restaurar(editando.code) })} />
        </Modal>
      )}
    </div>
  )
}

function FormularioAviso({ texto, pendiente, onCancelar, onGuardar, onRestaurar }: {
  aviso: Aviso; texto: TextoIdioma; pendiente: boolean
  onCancelar: () => void; onRestaurar: () => void
  onGuardar: (d: { subject: string; body_html: string; is_active: boolean }) => void
}) {
  const t = useAppT()
  const [subject, setSubject] = useState(texto.subject)
  const [body, setBody] = useState(texto.body_html)
  const [activo, setActivo] = useState(texto.is_active)
  const [vista, setVista] = useState<{ subject: string; body_html: string } | null>(null)
  const cuerpoRef = useRef<HTMLTextAreaElement>(null)

  // La vista previa se pide al servidor: es él quien sustituye y escapa.
  useEffect(() => {
    const h = setTimeout(() => {
      sdNotificationTemplatesApi.preview({ subject, body_html: body })
        .then(r => setVista(r.data as { subject: string; body_html: string }))
        .catch(() => setVista(null))
    }, 400)
    return () => clearTimeout(h)
  }, [subject, body])

  const insertar = (v: string) => {
    const el = cuerpoRef.current
    const marca = `{{${v}}}`
    if (!el) { setBody(b => b + marca); return }
    const a = el.selectionStart ?? body.length
    const b = el.selectionEnd ?? body.length
    setBody(body.slice(0, a) + marca + body.slice(b))
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 16 }}>
      <div className="u-stack-12">
        <div><label style={LS} htmlFor="ntf-subject">{t('sd_cfg.ntf_subject')}</label>
          <input id="ntf-subject" aria-label={t('sd_cfg.ntf_subject')} value={subject} onChange={e => setSubject(e.target.value)} style={IS} />
          <div className="u-hint">{t('sd_cfg.ntf_subject_hint')}</div></div>
        <div><label style={LS} htmlFor="ntf-body">{t('sd_cfg.ntf_body')}</label>
          <textarea id="ntf-body" aria-label={t('sd_cfg.ntf_body')} ref={cuerpoRef} value={body} onChange={e => setBody(e.target.value)} rows={10}
            style={{ ...IS, resize: 'vertical', fontFamily: 'var(--font-mono, monospace)', fontSize: 'var(--text-sm)' }} /></div>
        <div><span style={LS}>{t('sd_cfg.ntf_variables')}</span>
          <div className="u-wrap-6">
            {VARIABLES.map(v => <Chip key={v} activo={false} onClick={() => insertar(v)}>{v}</Chip>)}
          </div></div>
        <label style={{ display: 'flex', gap: 8, alignItems: 'center', cursor: 'pointer', color: 'var(--text-1)' }}>
          <input type="checkbox" aria-label={t('sd_cfg.ntf_on')} checked={activo} onChange={e => setActivo(e.target.checked)} />
          {t('sd_cfg.ntf_on')}
        </label>
      </div>
      <div>
        <span style={LS}>{t('sd_cfg.ntf_preview')}</span>
        <div className="ds-card" style={{ ...TARJETA, background: 'var(--surface-1)' }}>
          <div style={{ fontWeight: 600, marginBottom: 10, color: 'var(--text-1)' }}>{vista?.subject ?? subject}</div>
          {/* El HTML lo escribe un administrador: se pinta en un iframe con
              `sandbox` vacío, donde no corre ningún script. */}
          <iframe title={t('sd_cfg.ntf_preview')} sandbox="" srcDoc={vista?.body_html ?? ''}
            style={{ width: '100%', minHeight: 260, border: 'none', background: 'var(--on-accent-light)', borderRadius: 8 }} />
        </div>
      </div>
      <div style={{ gridColumn: '1/-1', display: 'flex', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
        <div>{texto.customized && <Button variant="secondary" onClick={onRestaurar}>{t('sd_cfg.ntf_restore')}</Button>}</div>
        <div style={{ display: 'flex', gap: 10 }}>
          <Button variant="secondary" onClick={onCancelar}>{t('common.cancel')}</Button>
          <Button onClick={() => onGuardar({ subject, body_html: body, is_active: activo })}
            disabled={pendiente || !subject.trim() || !body.trim()} loading={pendiente}>{t('common.save')}</Button>
        </div>
      </div>
    </div>
  )
}
