/**
 * Configuración › Seguridad › Seguridad de cuentas (23-11-2026,
 * docs/seguridad/politicas_de_cuenta.md). Capacidad `seguridad.administrar`.
 *
 * Pestañas:
 * - Política: contraseñas, bloqueo, MFA, sesiones, acceso y gobierno, con el
 *   valor recomendado de cada campo (NIST SP 800-63B, ISO 27001, CIS). Con
 *   separación de funciones, guardar crea una solicitud para otro administrador.
 * - Usuarios: estado (contraseña, bloqueo, MFA, sesiones) y acciones.
 * - Sesiones: activas en la empresa, con cierre remoto.
 * - Aprobaciones: cambios pendientes de un segundo administrador.
 * - Recertificación: campañas de revisión de accesos.
 */
import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { KeyRound, Save } from 'lucide-react'
import {
  Button, Input, Section, Spinner, StatusBadge, Switch, Tabla, Tabs, Textarea, type ColumnaTabla,
} from '../../components/ui'
import { confirmar, pedirTexto } from '../../context/ConfirmContext'
import { useToast } from '../../context/ToastContext'
import { useAppLang } from '../../i18n/AppLangContext'
import { extractErr, fmtDate, fmtDateTime } from '../../utils/helpers'
import {
  seguridadApi, type DescripcionDePolitica, type EstadoDeUsuario, type Politica, type SesionDeEmpresa,
  type SolicitudDeSeguridad, type ValorDePolitica,
} from '../../services/api/seguridadDeCuentas'
import SeccionDeAjustes from './SeccionDeAjustes'
import { Campanas } from './RecertificacionSection'
import './SeguridadDeCuentasSection.css'

/** Campos de cada bloque de la política (el orden es el de la pantalla). */
const BLOQUES: { id: string; campos: string[] }[] = [
  { id: 'contrasenas', campos: ['MIN_PASSWORD_LENGTH', 'PASSWORD_MAX_LENGTH', 'PASSWORD_BLOCK_COMMON', 'PASSWORD_BLOCK_PERSONAL',
    'PASSWORD_HISTORY_COUNT', 'PASSWORD_MIN_AGE_HOURS', 'PASSWORD_EXPIRY_DAYS', 'PASSWORD_EXPIRY_WARNING_DAYS',
    'TEMP_PASSWORD_EXPIRY_HOURS', 'PASSWORD_REQUIRE_UPPERCASE', 'PASSWORD_REQUIRE_LOWERCASE', 'PASSWORD_REQUIRE_DIGIT',
    'PASSWORD_REQUIRE_SPECIAL'] },
  { id: 'bloqueo', campos: ['LOGIN_MAX_ATTEMPTS', 'LOGIN_ATTEMPT_WINDOW_SECONDS', 'LOGIN_LOCKOUT_SECONDS', 'LOGIN_LOCKOUT_NOTIFY_USER'] },
  { id: 'mfa', campos: ['require_mfa', 'MFA_REQUIRED_ROLES', 'MFA_REQUIRED_FOR_SENSITIVE', 'MFA_ALLOWED_METHODS', 'MFA_GRACE_DAYS',
    'MFA_REMEMBER_DEVICE_DAYS'] },
  { id: 'sesiones', campos: ['idle_timeout_enabled', 'idle_timeout_minutes', 'SESSION_MAX_HOURS', 'SESSION_MAX_CONCURRENT'] },
  { id: 'acceso', campos: ['ACCESS_IP_ALLOWLIST', 'ACCESS_HOURS', 'ACCESS_DAYS', 'ACCESS_HOURS_EXEMPT_ROLES', 'ACCESS_BLOCKED_COUNTRIES'] },
  { id: 'gobierno', campos: ['SECURITY_SOD_TWO_ADMINS', 'ACCOUNT_INACTIVE_DISABLE_DAYS', 'SECURITY_ALERT_FAILED_LOGINS',
    'SECURITY_ALERT_NEW_IP', 'ACCESS_REVIEW_INTERVAL_DAYS'] },
]

const PESTANAS = ['politica', 'usuarios', 'sesiones', 'aprobaciones', 'recertificacion'] as const
type Pestana = typeof PESTANAS[number]

const clave = (campo: string) => `seguridad_cuentas.c_${campo.toLowerCase()}`

export default function SeguridadDeCuentasSection() {
  const { t } = useAppLang()
  const [pestana, setPestana] = useState<Pestana>('politica')
  return (
    <SeccionDeAjustes icon={<KeyRound size={18} />} title={t('seguridad_cuentas.titulo')}
      description={t('seguridad_cuentas.descripcion')}>
      <Tabs ariaLabel={t('seguridad_cuentas.titulo')} active={pestana} onChange={id => setPestana(id as Pestana)}
        items={PESTANAS.map(id => ({ id, label: t(`seguridad_cuentas.p_${id}`) }))} />
      <div className="segc-panel">
        {pestana === 'politica' && <PoliticaPanel />}
        {pestana === 'usuarios' && <UsuariosPanel />}
        {pestana === 'sesiones' && <SesionesPanel />}
        {pestana === 'aprobaciones' && <AprobacionesPanel />}
        {pestana === 'recertificacion' && <Campanas />}
      </div>
    </SeccionDeAjustes>
  )
}

// ── Política ────────────────────────────────────────────────────────────────

function textoDeValor(v: ValorDePolitica, si: string, no: string) {
  if (typeof v === 'boolean') return v ? si : no
  return v === '' ? '—' : String(v)
}

function PoliticaPanel() {
  const { t } = useAppLang()
  const qc = useQueryClient()
  const toast = useToast()
  const q = useQuery({ queryKey: ['seguridad-politica'], queryFn: seguridadApi.politica })
  const [cambios, setCambios] = useState<Politica>({})
  const [motivo, setMotivo] = useState('')
  const guardar = useMutation({
    mutationFn: () => seguridadApi.guardarPolitica(cambios, motivo || undefined),
    onSuccess: r => {
      setCambios({})
      setMotivo('')
      qc.invalidateQueries({ queryKey: ['seguridad-politica'] })
      toast.success(r.applied ? t('seguridad_cuentas.guardado') : r.pending_request_id
        ? t('seguridad_cuentas.pendiente_de_aprobacion') : t('seguridad_cuentas.sin_cambios'))
    },
    onError: e => toast.error(extractErr(e, t('seguridad_cuentas.err_guardar'))),
  })
  if (q.isLoading || !q.data) return <Spinner label={t('seguridad_cuentas.cargando')} />
  const d: DescripcionDePolitica = q.data
  const valor = (c: string) => (c in cambios ? cambios[c] : d.values[c])
  const poner = (c: string, v: ValorDePolitica) => setCambios(a => {
    const nuevo = { ...a }
    if (v === d.values[c]) delete nuevo[c]
    else nuevo[c] = v
    return nuevo
  })
  const sucio = Object.keys(cambios).length > 0
  return (
    <div className="segc-politica">
      {d.platform.superadmin_bypass_enabled && (
        <p className="segc-aviso segc-aviso--peligro" role="alert">{t('seguridad_cuentas.aviso_bypass')}</p>
      )}
      {d.pending_requests > 0 && (
        <p className="segc-aviso" role="status">{t('seguridad_cuentas.aviso_pendientes', { n: d.pending_requests })}</p>
      )}
      {BLOQUES.map(b => (
        <Section key={b.id} title={t(`seguridad_cuentas.b_${b.id}`)} subtitle={t(`seguridad_cuentas.b_${b.id}_d`)}>
          <div className="segc-campos">
            {b.campos.map(c => {
              const v = valor(c)
              const rec = d.recommended[c]
              const ayuda = rec ? t('seguridad_cuentas.recomendado', {
                valor: textoDeValor(rec.value, t('seguridad_cuentas.si'), t('seguridad_cuentas.no')), fuente: rec.source,
              }) : undefined
              if (typeof d.values[c] === 'boolean') {
                return (
                  <div key={c} className="segc-campo">
                    <Switch checked={Boolean(v)} onChange={m => poner(c, m)} label={t(clave(c))} ayuda={ayuda} />
                  </div>
                )
              }
              const rango = d.ranges[c]
              return (
                <div key={c} className="segc-campo">
                  <Input label={t(clave(c))} hint={ayuda} value={String(v ?? '')}
                    type={typeof d.values[c] === 'number' ? 'number' : 'text'}
                    min={rango?.[0]} max={rango?.[1]}
                    onChange={e => poner(c, typeof d.values[c] === 'number' ? Number(e.target.value) : e.target.value)} />
                </div>
              )
            })}
          </div>
        </Section>
      ))}
      <div className="segc-guardar">
        <Textarea label={t('seguridad_cuentas.motivo')} value={motivo} rows={2} maxLength={500}
          onChange={e => setMotivo(e.target.value)} />
        <Button icon={<Save size={15} />} disabled={!sucio} loading={guardar.isPending} onClick={() => guardar.mutate()}>
          {t('seguridad_cuentas.guardar', { n: Object.keys(cambios).length })}
        </Button>
      </div>
    </div>
  )
}

// ── Usuarios ────────────────────────────────────────────────────────────────

function UsuariosPanel() {
  const { t } = useAppLang()
  const qc = useQueryClient()
  const toast = useToast()
  const q = useQuery({ queryKey: ['seguridad-usuarios'], queryFn: seguridadApi.usuarios })
  const hecho = (texto: string) => { toast.success(texto); qc.invalidateQueries({ queryKey: ['seguridad-usuarios'] }) }
  const fallo = (e: unknown) => toast.error(extractErr(e, t('seguridad_cuentas.err_accion')))

  const accion = async (u: EstadoDeUsuario, que: 'desbloquear' | 'forzar' | 'restablecer' | 'temporal' | 'mfa' | 'sesiones') => {
    try {
      if (que === 'desbloquear') { await seguridadApi.desbloquear(u.id); hecho(t('seguridad_cuentas.hecho')); return }
      if (que === 'forzar') { await seguridadApi.forzarCambio(u.id); hecho(t('seguridad_cuentas.hecho')); return }
      if (que === 'sesiones') { await seguridadApi.cerrarSesionesDe(u.id); hecho(t('seguridad_cuentas.hecho')); return }
      if (que === 'restablecer') {
        // 23-11-2026: cambio obligatorio + cierre de sesiones + enlace, con motivo (auditado).
        const motivo = await pedirTexto({ title: t('seguridad_cuentas.a_restablecer'), message: t('seguridad_cuentas.confirmar_restablecer', { nombre: u.full_name }), label: t('seguridad_cuentas.motivo'), required: true })
        if (motivo === null) return
        const r = await seguridadApi.forzarRestablecimiento(u.id, motivo)
        hecho(r.link_sent ? t('seguridad_cuentas.restablecido') : t('seguridad_cuentas.restablecido_sin_enlace'))
        return
      }
      if (que === 'temporal') {
        const ok = await confirmar({ title: t('seguridad_cuentas.a_temporal'), message: t('seguridad_cuentas.confirmar_temporal', { nombre: u.full_name }) })
        if (!ok) return
        const r = await seguridadApi.contrasenaTemporal(u.id)
        await confirmar({ title: t('seguridad_cuentas.a_temporal'), message: t('seguridad_cuentas.temporal_generada', { clave: r.password ?? '', fecha: fmtDateTime(r.expires_at) }), confirmLabel: t('seguridad_cuentas.entendido') })
        hecho(t('seguridad_cuentas.hecho'))
        return
      }
      const motivo = await pedirTexto({ title: t('seguridad_cuentas.a_mfa'), message: t('seguridad_cuentas.confirmar_mfa', { nombre: u.full_name }), label: t('seguridad_cuentas.motivo'), required: true })
      if (motivo === null) return
      const r = await seguridadApi.restablecerMfa(u.id, motivo)
      hecho(r.applied ? t('seguridad_cuentas.hecho') : t('seguridad_cuentas.pendiente_de_aprobacion'))
    } catch (e) {
      fallo(e)
    }
  }

  const forzarTodos = async () => {
    const ok = await confirmar({ title: t('seguridad_cuentas.a_forzar_todos'), message: t('seguridad_cuentas.confirmar_forzar_todos'), danger: true })
    if (!ok) return
    try {
      const r = await seguridadApi.forzarCambioATodos()
      hecho(t('seguridad_cuentas.forzados', { n: r.users }))
    } catch (e) { fallo(e) }
  }

  const columnas: ColumnaTabla<EstadoDeUsuario>[] = useMemo(() => [
    { key: 'full_name', label: t('seguridad_cuentas.col_usuario'), sortable: true,
      render: (_: never, u) => <span>{u.full_name}<br /><span className="segc-tenue">{u.email}</span></span> },
    { key: 'password', label: t('seguridad_cuentas.col_contrasena'),
      render: (_: never, u) => u.sso ? <StatusBadge kind="info">SSO</StatusBadge>
        : u.password_expired ? <StatusBadge kind="danger">{t('seguridad_cuentas.caducada')}</StatusBadge>
          : u.password_must_change ? <StatusBadge kind="warning">{t('seguridad_cuentas.cambio_pendiente')}</StatusBadge>
            : <span className="segc-tenue">{fmtDate(u.password_changed_at)}</span> },
    { key: 'mfa', label: 'MFA',
      render: (_: never, u) => (u.mfa_totp || u.mfa_passkey)
        ? <StatusBadge kind="success">{[u.mfa_totp && 'TOTP', u.mfa_passkey && 'Passkey'].filter(Boolean).join(' + ')}</StatusBadge>
        : u.mfa_enrollment_required ? <StatusBadge kind="danger">{t('seguridad_cuentas.mfa_vencido')}</StatusBadge>
          : u.mfa_required ? <StatusBadge kind="warning">{t('seguridad_cuentas.mfa_en_gracia', { fecha: fmtDate(u.mfa_grace_until) })}</StatusBadge>
            : <span className="segc-tenue">—</span> },
    { key: 'locked_seconds', label: t('seguridad_cuentas.col_bloqueo'),
      render: (_: never, u) => u.locked_seconds > 0
        ? <StatusBadge kind="danger">{t('seguridad_cuentas.bloqueada_min', { n: Math.ceil(u.locked_seconds / 60) })}</StatusBadge> : '—' },
    { key: 'active_sessions', label: t('seguridad_cuentas.col_sesiones'), alinear: 'derecha' },
    { key: 'last_login', label: t('seguridad_cuentas.col_ultimo_acceso'), render: (_: never, u) => fmtDateTime(u.last_login) },
    { key: 'acciones', label: t('seguridad_cuentas.col_acciones'),
      render: (_: never, u) => (
        <div className="segc-acciones">
          {u.locked_seconds > 0 && <Button size="sm" variant="secondary" onClick={() => accion(u, 'desbloquear')}>{t('seguridad_cuentas.a_desbloquear')}</Button>}
          {!u.sso && <Button size="sm" variant="secondary" onClick={() => accion(u, 'forzar')}>{t('seguridad_cuentas.a_forzar')}</Button>}
          {!u.sso && <Button size="sm" variant="secondary" onClick={() => accion(u, 'restablecer')}>{t('seguridad_cuentas.a_restablecer')}</Button>}
          {!u.sso && <Button size="sm" variant="secondary" onClick={() => accion(u, 'temporal')}>{t('seguridad_cuentas.a_temporal')}</Button>}
          {(u.mfa_totp || u.mfa_passkey) && <Button size="sm" variant="secondary" onClick={() => accion(u, 'mfa')}>{t('seguridad_cuentas.a_mfa')}</Button>}
          {u.active_sessions > 0 && <Button size="sm" variant="secondary" onClick={() => accion(u, 'sesiones')}>{t('seguridad_cuentas.a_sesiones')}</Button>}
        </div>
      ) },
  // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [t])

  return (
    <div>
      <div className="segc-barra">
        <Button variant="secondary" onClick={forzarTodos}>{t('seguridad_cuentas.a_forzar_todos')}</Button>
      </div>
      <Tabla etiqueta={t('seguridad_cuentas.p_usuarios')} columnas={columnas} filas={q.data ?? []} cargando={q.isLoading} ordenable />
    </div>
  )
}

// ── Sesiones ────────────────────────────────────────────────────────────────

function SesionesPanel() {
  const { t } = useAppLang()
  const qc = useQueryClient()
  const toast = useToast()
  const q = useQuery({ queryKey: ['seguridad-sesiones'], queryFn: seguridadApi.sesiones })
  const cerrar = useMutation({
    mutationFn: (id: string) => seguridadApi.cerrarSesion(id),
    onSuccess: () => { toast.success(t('seguridad_cuentas.hecho')); qc.invalidateQueries({ queryKey: ['seguridad-sesiones'] }) },
    onError: e => toast.error(extractErr(e, t('seguridad_cuentas.err_accion'))),
  })
  const columnas: ColumnaTabla<SesionDeEmpresa>[] = [
    { key: 'user', label: t('seguridad_cuentas.col_usuario'), sortable: true },
    { key: 'ip_address', label: 'IP' },
    { key: 'device_name', label: t('seguridad_cuentas.col_dispositivo') },
    { key: 'auth_method', label: t('seguridad_cuentas.col_metodo') },
    { key: 'created_at', label: t('seguridad_cuentas.col_inicio'), render: (_: never, s) => fmtDateTime(s.created_at) },
    { key: 'last_seen_at', label: t('seguridad_cuentas.col_actividad'), render: (_: never, s) => fmtDateTime(s.last_seen_at) },
    { key: 'cerrar', label: t('seguridad_cuentas.col_acciones'),
      render: (_: never, s) => <Button size="sm" variant="secondary" onClick={() => cerrar.mutate(s.id)}>{t('seguridad_cuentas.a_cerrar_sesion')}</Button> },
  ]
  return <Tabla etiqueta={t('seguridad_cuentas.p_sesiones')} columnas={columnas} filas={q.data ?? []} cargando={q.isLoading} ordenable />
}

// ── Aprobaciones ────────────────────────────────────────────────────────────

function AprobacionesPanel() {
  const { t } = useAppLang()
  const qc = useQueryClient()
  const toast = useToast()
  const q = useQuery({ queryKey: ['seguridad-solicitudes'], queryFn: seguridadApi.solicitudes })
  const decidir = async (s: SolicitudDeSeguridad, aprobar: boolean) => {
    const comentario = await pedirTexto({ title: t(aprobar ? 'seguridad_cuentas.a_aprobar' : 'seguridad_cuentas.a_rechazar'),
      message: t('seguridad_cuentas.comentario_decision'), label: t('seguridad_cuentas.comentario') })
    if (comentario === null) return
    try {
      await (aprobar ? seguridadApi.aprobar(s.id, comentario) : seguridadApi.rechazar(s.id, comentario))
      toast.success(t('seguridad_cuentas.hecho'))
      qc.invalidateQueries({ queryKey: ['seguridad-solicitudes'] })
      qc.invalidateQueries({ queryKey: ['seguridad-politica'] })
    } catch (e) { toast.error(extractErr(e, t('seguridad_cuentas.err_accion'))) }
  }
  const columnas: ColumnaTabla<SolicitudDeSeguridad>[] = [
    { key: 'kind', label: t('seguridad_cuentas.col_tipo'), render: (_: never, s) => t(`seguridad_cuentas.tipo_${s.kind}`) },
    { key: 'detalle', label: t('seguridad_cuentas.col_detalle'),
      render: (_: never, s) => s.kind === 'policy' ? Object.keys(s.payload).map(k => t(clave(k))).join(', ') : (s.target_user ?? '—') },
    { key: 'requested_by_name', label: t('seguridad_cuentas.col_pedida_por') },
    { key: 'requested_at', label: t('seguridad_cuentas.col_fecha'), render: (_: never, s) => fmtDateTime(s.requested_at) },
    { key: 'status', label: t('seguridad_cuentas.col_estado'),
      render: (_: never, s) => <StatusBadge kind={s.status === 'pending' ? 'warning' : s.status === 'applied' ? 'success' : 'neutral'}>{t(`seguridad_cuentas.estado_${s.status}`)}</StatusBadge> },
    { key: 'acciones', label: t('seguridad_cuentas.col_acciones'),
      render: (_: never, s) => s.status !== 'pending' ? (s.decided_by_name ?? '—') : (
        <div className="segc-acciones">
          <Button size="sm" onClick={() => decidir(s, true)}>{t('seguridad_cuentas.a_aprobar')}</Button>
          <Button size="sm" variant="secondary" onClick={() => decidir(s, false)}>{t('seguridad_cuentas.a_rechazar')}</Button>
        </div>
      ) },
  ]
  return (
    <div>
      <p className="segc-tenue">{t('seguridad_cuentas.aprobaciones_d')}</p>
      <Tabla etiqueta={t('seguridad_cuentas.p_aprobaciones')} columnas={columnas} filas={q.data ?? []} cargando={q.isLoading} />
    </div>
  )
}
