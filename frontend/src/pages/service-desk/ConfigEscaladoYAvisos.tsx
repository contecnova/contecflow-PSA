/**
 * Configuración del Service Desk: reglas de escalado y textos de los avisos.
 *
 * Las dos cosas existían solo en el servidor: las reglas se podían crear por API
 * y los avisos no se podían ver ni cambiar. Aquí se gestionan donde se buscan,
 * junto al SLA, las colas y el enrutado.
 *
 * 16-11-2026 (pasada de diseño): acción principal con icono Plus (sin «+»),
 * vacíos con EmptyState e icono lucide, borrar con Button ghost + Trash2,
 * estados con StatusBadge, campos con `ds-input`, fechas con fmtDateTime y
 * chips sin estilos en línea.
 */
import { useEffect, useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { History, Pencil, Plus, Trash2, TrendingUp } from 'lucide-react'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { extractErr, fmtDateTime } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { useToast } from '../../context/ToastContext'
import { useAppT } from '../../i18n/AppLangContext'
import { Button, Spinner, EmptyState, Modal, StatusBadge } from '../../components/ui'
import { sdEscalationApi, sdNotificationTemplatesApi, sdGroupsApi, usersApi, type UserListItem } from '../../services/api'
import type { SdAviso, SdReglaDeEscalado, SdTextoDeAviso, SdVistaPreviaDeAviso } from '../../services/api/tipos-sd'
import { PRIORITY_LABEL } from './sdUtils'
import { RuntimeGroupEditor } from '../settings-sections/SettingsAdvancedSections'
import { SLOW_INPUT_DEBOUNCE_MS } from '../../constants/timings'
import './ConfigEscaladoYAvisos.css'

const PRIORIDADES = ['p1_critical', 'p2_high', 'p3_medium', 'p4_low']
const DISPARADORES = ['sla_at_risk', 'sla_breached', 'idle_hours', 'priority', 'reopened']
const ACCIONES = ['notify_manager', 'notify_group_lead', 'notify_custom', 'reassign_group', 'elevate_priority']
const PRIORITY_LABEL_MAP = PRIORITY_LABEL as Record<string, string>

type Regla = SdReglaDeEscalado
type Cola = { id: string; name: string }
type Persona = UserListItem

// Tarjeta del sistema de diseño (`.ds-card`); aquí solo lo que cambia.

function lista(raw?: string | null): string[] {
  if (!raw) return []
  try { const v = JSON.parse(raw); return Array.isArray(v) ? v.map(String) : [] } catch { return [] }
}

function Chip({ activo, onClick, children }: { activo: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button className="coesya-chip" type="button" onClick={onClick} aria-pressed={activo}>{children}</button>
  )
}

// ── Escalado ─────────────────────────────────────────────────────────────────
export function EscalationConfig() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [editando, setEditando] = useState<Regla | 'nueva' | null>(null)

  const { data: reglas = [], isLoading } = useQuery({
    queryKey: ['sd-escalation'], queryFn: () => sdEscalationApi.list().then(r => r.data),
  })
  const { data: disparos = [] } = useQuery({
    queryKey: ['sd-escalation-logs'], queryFn: () => sdEscalationApi.logs(15).then(r => r.data),
  })
  const { data: colas = [] } = useQuery<Cola[]>({
    queryKey: ['sd-groups'], queryFn: () => sdGroupsApi.list().then(r => r.data),
  })
  const { data: personas = [] } = useQuery({
    queryKey: ['users'], queryFn: () => usersApi.list().then(r => r.data),
  })
  const refrescar = () => { qc.invalidateQueries({ queryKey: ['sd-escalation'] }) }
  const { mutate: guardar, isPending } = useMutation({
    mutationFn: ({ id, ...d }: Record<string, unknown>): Promise<unknown> =>
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
    <div className="u-stack-20">
      <div className="coesya-row-1">
        <div className="coesya-intro">{t('sd_cfg.esc_intro')}</div>
        <Button icon={<Plus size={14} />} onClick={() => setEditando('nueva')}>{t('sd_cfg.esc_new')}</Button>
      </div>

      {isLoading ? <Spinner /> : reglas.length === 0 ? (
        <EmptyState icon={<TrendingUp size={28} />} title={t('sd_cfg.esc_empty')} description={t('sd_cfg.esc_empty_desc')} />
      ) : (
        <div className="u-stack-10">
          {reglas.map(r => (
            <div key={r.id} className={`ds-card coesya-regla${r.is_active ? '' : ' coesya-regla--inactiva'}`}>
              <div className="coesya-regla__cuerpo">
                <div className="coesya-regla__nombre">
                  {r.name}
                  {!r.is_active && <StatusBadge caps={false}>{t('sd_cfg.esc_inactive')}</StatusBadge>}
                </div>
                <div className="u-text2-sm">
                  <strong>{t('sd_cfg.esc_when')}</strong> {resumenDisparo(r)}
                </div>
                <div className="u-text2-sm">
                  <strong>{t('sd_cfg.esc_then')}</strong> {resumenAccion(r)}
                </div>
              </div>
              <div className="u-row-8">
                <Button size="xs" variant="secondary" icon={<Pencil size={12} />} onClick={() => setEditando(r)}>{t('common.edit')}</Button>
                <Button size="xs" variant="ghost" icon={<Trash2 size={12} />} onClick={() => openConfirmGlobal({
                  message: t('sd_cfg.esc_delete_confirm'), onConfirm: () => borrar(r.id), danger: true,
                })}>{t('common.delete')}</Button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div>
        <div className="coesya-ls2">{t('sd_cfg.esc_log')}</div>
        {disparos.length === 0 ? (
          <EmptyState icon={<History size={28} />} title={t('sd_cfg.esc_log_empty')} />
        ) : (
          <div className="u-scroll-x">
            <table className="u-table-sm">
              <tbody>
                {disparos.map(d => (
                  <tr key={d.id} className="u-border-b">
                    <td className="coesya-fecha">{d.triggered_at ? fmtDateTime(d.triggered_at) : ''}</td>
                    <td className="coesya-celda coesya-celda--fuerte">{d.ticket_number}</td>
                    <td className="coesya-celda coesya-celda--texto">{d.action_taken}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
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
      <div><label className="coesya-ls" htmlFor="esc-name">{t('sd_cfg.esc_name')} *</label>
        <input id="esc-name" aria-label={t('sd_cfg.esc_name')} value={f.name} onChange={e => set('name', e.target.value)} className="ds-input" /></div>

      <fieldset className="ds-card coesya-grupo">
        <legend className="coesya-ls">{t('sd_cfg.esc_when')}</legend>
        <select aria-label={t('sd_cfg.esc_when')} value={f.trigger} onChange={e => set('trigger', e.target.value)} className="ds-input">
          {DISPARADORES.map(d => <option key={d} value={d}>{t(`sd_cfg.esc_trigger_${d}`)}</option>)}
        </select>
        {f.trigger === 'idle_hours' && (
          <div><label className="coesya-ls" htmlFor="esc-idle">{t('sd_cfg.esc_idle_hours')}</label>
            <input id="esc-idle" aria-label={t('sd_cfg.esc_idle_hours')} type="number" min={1} value={f.idle} onChange={e => set('idle', e.target.value)} className="ds-input coesya-corto" /></div>
        )}
        <div><span className="coesya-ls">{t('sd_cfg.esc_priorities')}</span>
          <div className="u-wrap-6">
            {PRIORIDADES.map(p => <Chip key={p} activo={f.prioridades.includes(p)} onClick={() => alternar('prioridades', p)}>{PRIORITY_LABEL_MAP[p]}</Chip>)}
          </div></div>
        <div><label className="coesya-ls" htmlFor="esc-group">{t('sd_cfg.esc_group')}</label>
          <select id="esc-group" value={f.group_id} onChange={e => set('group_id', e.target.value)} className="ds-input">
            <option value="">{t('sd_cfg.esc_any_group')}</option>
            {colas.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select></div>
      </fieldset>

      <fieldset className="ds-card coesya-grupo">
        <legend className="coesya-ls">{t('sd_cfg.esc_then')}</legend>
        <select aria-label={t('sd_cfg.esc_then')} value={f.action} onChange={e => set('action', e.target.value)} className="ds-input">
          {ACCIONES.map(a => <option key={a} value={a}>{t(`sd_cfg.esc_action_${a}`)}</option>)}
        </select>
        {f.action === 'reassign_group' && (
          <div><label className="coesya-ls" htmlFor="esc-target">{t('sd_cfg.esc_target_group')} *</label>
            <select id="esc-target" value={f.target_group_id} onChange={e => set('target_group_id', e.target.value)} className="ds-input">
              <option value="">—</option>
              {colas.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select></div>
        )}
        {f.action === 'elevate_priority' && (
          <div><label className="coesya-ls" htmlFor="esc-prio">{t('sd_cfg.esc_target_priority')}</label>
            <select id="esc-prio" value={f.target_priority} onChange={e => set('target_priority', e.target.value)} className="ds-input">
              {PRIORIDADES.map(p => <option key={p} value={p}>{PRIORITY_LABEL_MAP[p]}</option>)}
            </select></div>
        )}
        {f.action === 'notify_custom' && (
          <div><span className="coesya-ls">{t('sd_cfg.esc_users')} *</span>
            <div className="coesya-personas">
              {personas.map(p => <Chip key={p.id} activo={f.avisar.includes(p.id)} onClick={() => alternar('avisar', p.id)}>{p.full_name ?? p.id}</Chip>)}
            </div></div>
        )}
      </fieldset>

      <label className="coesya-check">
        <input type="checkbox" aria-label={t('sd_cfg.esc_active')} checked={f.is_active} onChange={e => set('is_active', e.target.checked)} />
        {t('sd_cfg.esc_active')}
      </label>
      <div className="coesya-acciones">
        {!completa && f.name.trim() && <span className="coesya-aviso">{t('sd_cfg.esc_incomplete')}</span>}
        <Button variant="secondary" onClick={onCancelar}>{t('common.cancel')}</Button>
        <Button onClick={enviar} disabled={!completa || pendiente} loading={pendiente}>{t('common.save')}</Button>
      </div>
    </div>
  )
}

// ── Avisos ───────────────────────────────────────────────────────────────────
type TextoIdioma = SdTextoDeAviso
type Aviso = SdAviso
const VARIABLES = ['ticket_number', 'ticket_title', 'ticket_status', 'ticket_priority', 'requester_name',
  'assignee_name', 'group_name', 'comment_author', 'comment_body', 'resolution', 'sla_due', 'link']

const claveAviso = (a: Aviso) => `sd_cfg.ntf_${a.event}_${a.role}`

export function NotificationsConfig() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [idioma, setIdioma] = useState('es')
  const [editando, setEditando] = useState<Aviso | null>(null)

  const { data: avisos = [], isLoading } = useQuery({
    queryKey: ['sd-notification-templates'],
    queryFn: () => sdNotificationTemplatesApi.list().then(r => r.data),
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
    <div className="u-stack-20">
      <div className="coesya-row-1">
        <div className="coesya-intro">{t('sd_cfg.ntf_intro')}</div>
        <div role="group" aria-label={t('sd_cfg.ntf_language')} className="u-row-6">
          {idiomas.map(i => <Chip key={i} activo={idioma === i} onClick={() => setIdioma(i)}>{i.toUpperCase()}</Chip>)}
        </div>
      </div>

      {isLoading ? <Spinner /> : roles.map(rol => {
        const delRol = avisos.filter(a => a.role === rol)
        if (!delRol.length) return null
        return (
          <div key={rol}>
            <div className="coesya-ls2">{t(`sd_cfg.role_${rol}`)}</div>
            <div className="ds-card ds-card--plano">
              {delRol.map(a => {
                const txt = a.languages[idioma]
                return (
                  <div className="coesya-aviso-fila" key={a.code}>
                    <div className="coesya-aviso-fila__texto">
                      <div className={`coesya-aviso-fila__nombre${txt?.is_active ? '' : ' coesya-aviso-fila__nombre--apagado'}`}>{t(claveAviso(a))}</div>
                      <div className="coesya-aviso-fila__asunto">{txt?.subject}</div>
                    </div>
                    <StatusBadge kind={txt?.is_active ? 'success' : 'neutral'} caps={false}>
                      {txt?.is_active ? t('sd_cfg.ntf_on') : t('sd_cfg.ntf_off')}
                    </StatusBadge>
                    <span className="coesya-aviso-fila__origen">
                      {txt?.customized ? t('sd_cfg.ntf_customized') : t('sd_cfg.ntf_default')}
                    </span>
                    <Button size="xs" variant="secondary" icon={<Pencil size={12} />} onClick={() => setEditando(a)}>{t('common.edit')}</Button>
                  </div>
                )
              })}
            </div>
          </div>
        )
      })}

      <div className="ds-card">
        <div className="coesya-ls2">{t('sd_cfg.ntf_who')}</div>
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
  const [vista, setVista] = useState<SdVistaPreviaDeAviso | null>(null)
  const cuerpoRef = useRef<HTMLTextAreaElement>(null)

  // La vista previa se pide al servidor: es él quien sustituye y escapa.
  useEffect(() => {
    const h = setTimeout(() => {
      sdNotificationTemplatesApi.preview({ subject, body_html: body })
        .then(r => setVista(r.data))
        .catch(() => setVista(null))
    }, SLOW_INPUT_DEBOUNCE_MS)
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
    <div className="coesya-grid-1">
      <div className="u-stack-12">
        <div><label className="coesya-ls" htmlFor="ntf-subject">{t('sd_cfg.ntf_subject')}</label>
          <input id="ntf-subject" aria-label={t('sd_cfg.ntf_subject')} value={subject} onChange={e => setSubject(e.target.value)} className="ds-input" />
          <div className="u-hint">{t('sd_cfg.ntf_subject_hint')}</div></div>
        <div><label className="coesya-ls" htmlFor="ntf-body">{t('sd_cfg.ntf_body')}</label>
          <textarea id="ntf-body" aria-label={t('sd_cfg.ntf_body')} ref={cuerpoRef} value={body} onChange={e => setBody(e.target.value)} rows={10}
            className="ds-input coesya-codigo" /></div>
        <div><span className="coesya-ls">{t('sd_cfg.ntf_variables')}</span>
          <div className="u-wrap-6">
            {VARIABLES.map(v => <Chip key={v} activo={false} onClick={() => insertar(v)}>{v}</Chip>)}
          </div></div>
        <label className="coesya-check">
          <input type="checkbox" aria-label={t('sd_cfg.ntf_on')} checked={activo} onChange={e => setActivo(e.target.checked)} />
          {t('sd_cfg.ntf_on')}
        </label>
      </div>
      <div>
        <span className="coesya-ls">{t('sd_cfg.ntf_preview')}</span>
        <div className="ds-card coesya-vista">
          <div className="coesya-vista__asunto">{vista?.subject ?? subject}</div>
          {/* El HTML lo escribe un administrador: se pinta en un iframe con
              `sandbox` vacío, donde no corre ningún script. */}
          <iframe title={t('sd_cfg.ntf_preview')} sandbox="" srcDoc={vista?.body_html ?? ''}
            className="coesya-vista__marco" />
        </div>
      </div>
      <div className="coesya-pie">
        <div>{texto.customized && <Button variant="secondary" onClick={onRestaurar}>{t('sd_cfg.ntf_restore')}</Button>}</div>
        <div className="u-row-10">
          <Button variant="secondary" onClick={onCancelar}>{t('common.cancel')}</Button>
          <Button onClick={() => onGuardar({ subject, body_html: body, is_active: activo })}
            disabled={pendiente || !subject.trim() || !body.trim()} loading={pendiente}>{t('common.save')}</Button>
        </div>
      </div>
    </div>
  )
}
