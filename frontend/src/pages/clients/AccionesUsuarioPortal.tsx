/**
 * Acciones sobre un usuario del portal de clientes (23-11-2026, migración portal_usuarios).
 *
 * - «Establecer contraseña»: contraseña puesta a mano (campo con mostrar/ocultar y
 *   botón de generar una aleatoria), «Obligar a cambiarla en el primer acceso»
 *   (marcada por defecto) y «Enviar acceso por correo al titular». La valida el
 *   servidor con la política de la empresa (errores con código, traducidos); no
 *   vuelve nunca en la respuesta ni queda en la auditoría. Cierra sus sesiones.
 * - «Reenviar acceso»: contraseña generada por el servidor y enviada al titular.
 * - «Eliminar o archivar»: decide el servidor (sin historial, borra; con
 *   historial, archiva) y la pantalla explica qué ha pasado.
 * - «Restaurar»: para los archivados.
 * - «Supresión RGPD» (solo `cab.administrar`): crea la solicitud de supresión,
 *   que anonimiza (Enterprise › RGPD). Es otra cosa que eliminar o archivar.
 *
 * Lo usan la pestaña «Usuarios del portal» de la ficha del cliente, sus contactos
 * y la página del portal de clientes. Docs: docs/seguridad/politicas_de_cuenta.md.
 */
import { useId, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { ArchiveRestore, ClipboardCopy, Eye, EyeOff, KeyRound, Send, ShieldX, Trash2, Dices } from 'lucide-react'
import { Button, Checkbox, GrupoDeOpciones, IconButton, Input, Modal } from '../../components/ui'
import { confirmar } from '../../context/ConfirmContext'
import { useToast } from '../../context/ToastContext'
import { gdprApi, portalClientsApi } from '../../services/api'
import { usePermiso } from '../../permisos/usePermiso'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { useAppLang } from '../../i18n/AppLangContext'

export type UsuarioDelPortalMin = {
  id: string
  full_name: string
  email: string
  archived_at?: string | null
}

export type AccesoDelPortal = { email: string; enviado: boolean | null }

const MAYUSCULAS = 'ABCDEFGHJKLMNPQRSTUVWXYZ'
const MINUSCULAS = 'abcdefghijkmnopqrstuvwxyz'
const DIGITOS = '23456789'
const ESPECIALES = '!@#$%*-_=+?'

/** Contraseña aleatoria con mayúsculas, minúsculas, dígitos y especiales (cumple
 *  la composición de cualquier política). Sin caracteres que se confunden (0/O, 1/l). */
export function generarContrasenaAleatoria(longitud = 20): string {
  const todos = MAYUSCULAS + MINUSCULAS + DIGITOS + ESPECIALES
  const azar = (n: number) => {
    const buf = new Uint32Array(1)
    crypto.getRandomValues(buf)
    return buf[0] % n
  }
  const elegir = (juego: string) => juego[azar(juego.length)]
  const chars = [elegir(MAYUSCULAS), elegir(MINUSCULAS), elegir(DIGITOS), elegir(ESPECIALES)]
  while (chars.length < longitud) chars.push(elegir(todos))
  for (let i = chars.length - 1; i > 0; i--) {
    const j = azar(i + 1)
    ;[chars[i], chars[j]] = [chars[j], chars[i]]
  }
  return chars.join('')
}

/** Campo de contraseña con mostrar/ocultar, generar una aleatoria y copiarla. */
export function CampoDeContrasenaManual({ valor, onChange, error }: { valor: string; onChange: (v: string) => void; error?: string | null }) {
  const { t } = useAppLang()
  const toast = useToast()
  const id = useId()
  const [visible, setVisible] = useState(false)
  return (
    <div className="u-stack-8">
      <label id={`${id}-et`} htmlFor={`${id}-campo`} className="u-text2-sm">{t('portalacc.contrasena')} *</label>
      <div className="u-row-8">
        <Input id={`${id}-campo`} aria-labelledby={`${id}-et`} className="u-flex1" type={visible ? 'text' : 'password'}
          value={valor} onChange={e => onChange(e.target.value)} autoComplete="new-password" spellCheck={false}
          error={error || undefined} />
        <IconButton variante="caja" ariaLabel={visible ? t('portalacc.ocultar') : t('portalacc.mostrar')} onClick={() => setVisible(v => !v)}>
          {visible ? <EyeOff size={16} /> : <Eye size={16} />}
        </IconButton>
        <IconButton variante="caja" ariaLabel={t('portalacc.generar')} onClick={() => { onChange(generarContrasenaAleatoria()); setVisible(true) }}>
          <Dices size={16} />
        </IconButton>
        <IconButton variante="caja" ariaLabel={t('portalacc.copiar')} disabled={!valor}
          onClick={() => navigator.clipboard.writeText(valor).then(() => toast.info(t('portalacc.copiada')), () => toast.error(t('portaluserstab.error_copiar')))}>
          <ClipboardCopy size={16} />
        </IconButton>
      </div>
      <div className="u-hint">{t('portalacc.ayuda_politica')}</div>
    </div>
  )
}

/** Contraseña inicial al dar acceso: generada y enviada (por defecto) o a mano. */
export type ContrasenaInicial = { modo: 'generar' | 'manual'; password: string; must_change_password: boolean; send_access: boolean }

export const contrasenaInicialPorDefecto = (): ContrasenaInicial => ({ modo: 'generar', password: '', must_change_password: true, send_access: true })

/** Lo que va al servidor: nada en modo «generar» (el servidor la genera y la envía). */
export function datosDeContrasenaInicial(c: ContrasenaInicial): { password?: string; must_change_password?: boolean; send_access?: boolean } {
  return c.modo === 'manual' ? { password: c.password, must_change_password: c.must_change_password, send_access: c.send_access } : {}
}

export function SeccionContrasenaInicial({ valor, onChange, email, error }: { valor: ContrasenaInicial; onChange: (c: ContrasenaInicial) => void; email: string; error?: string | null }) {
  const { t } = useAppLang()
  return (
    <div className="u-stack-8 u-col-full">
      <GrupoDeOpciones forma="lista" leyenda={t('portalacc.modo_leyenda')} valor={valor.modo}
        onChange={m => onChange({ ...valor, modo: m === 'manual' ? 'manual' : 'generar' })}
        opciones={[{ valor: 'generar', titulo: t('portalacc.modo_generar') }, { valor: 'manual', titulo: t('portalacc.modo_manual') }]} />
      {valor.modo === 'manual' && (
        <>
          <CampoDeContrasenaManual valor={valor.password} onChange={p => onChange({ ...valor, password: p })} error={error} />
          <Checkbox checked={valor.must_change_password} onChange={m => onChange({ ...valor, must_change_password: m })} label={t('portalacc.obligar_cambio')} />
          <Checkbox checked={valor.send_access} onChange={m => onChange({ ...valor, send_access: m })} label={t('portalacc.enviar_correo', { email: email || '—' })} />
        </>
      )}
    </div>
  )
}

/** Modal «Establecer contraseña». */
export function ModalEstablecerContrasena({ usuario, onClose, onHecho }: { usuario: UsuarioDelPortalMin; onClose: () => void; onHecho?: () => void }) {
  const { t } = useAppLang()
  const toast = useToast()
  const [clave, setClave] = useState('')
  const [obligar, setObligar] = useState(true)
  const [enviar, setEnviar] = useState(false)
  const [errorCampo, setErrorCampo] = useState<string | null>(null)
  const { mutate, isPending } = useMutation({
    onMutate: () => setErrorCampo(null),
    mutationFn: () => portalClientsApi.setPassword(usuario.id, { password: clave, must_change_password: obligar, send_access: enviar }).then(r => r.data),
    onSuccess: (r) => {
      // La contraseña se olvida en cuanto el servidor la acepta.
      setClave('')
      if (r.credenciales_enviadas === true) toast.success(t('portalacc.establecida_enviada', { email: usuario.email }))
      else if (r.credenciales_enviadas === false) toast.warning(t('portalacc.establecida_no_enviada'), 10000)
      else toast.success(t('portalacc.establecida'))
      onHecho?.()
      onClose()
    },
    onError: (e: unknown) => setErrorCampo(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  return (
    <Modal open title={t('portalacc.establecer_de', { nombre: usuario.full_name })} onClose={onClose} width={520} cambiosSinGuardar={!!clave}>
      <form onSubmit={e => { e.preventDefault(); if (clave) mutate() }} className="u-stack-8">
        <CampoDeContrasenaManual valor={clave} onChange={v => { setClave(v); setErrorCampo(null) }} error={errorCampo} />
        <Checkbox checked={obligar} onChange={m => setObligar(m)} label={t('portalacc.obligar_cambio')} />
        <Checkbox checked={enviar} onChange={m => setEnviar(m)} label={t('portalacc.enviar_correo', { email: usuario.email })} />
        <div className="u-actions-8">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button type="submit" loading={isPending} disabled={!clave || isPending}>
            {isPending ? t('portalacc.guardando') : t('portalacc.guardar')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

/** Botones de acción (IconButton de caja) de un usuario del portal. */
export function AccionesDeUsuarioDelPortal({ usuario, onCambio, onAcceso, conReenviar = true }: {
  usuario: UsuarioDelPortalMin
  onCambio: () => void
  /** Tras «Reenviar acceso»: a quién se mandó y si salió el correo. */
  onAcceso?: (a: AccesoDelPortal) => void
  conReenviar?: boolean
}) {
  const { t } = useAppLang()
  const toast = useToast()
  const puedeRgpd = usePermiso('cab.administrar')
  const [establecer, setEstablecer] = useState(false)
  const archivado = !!usuario.archived_at
  const nombre = usuario.full_name || usuario.email

  const { mutate: reenviar } = useMutation({
    mutationFn: () => portalClientsApi.sendAccess(usuario.id).then(r => r.data),
    onSuccess: (r) => {
      onCambio()
      if (onAcceso) onAcceso({ email: r.email, enviado: r.credenciales_enviadas })
      else if (r.credenciales_enviadas) toast.success(t('portaluserstab.acceso_enviado'))
      else toast.warning(t('portaluserstab.acceso_no_enviado'), 10000)
    },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: eliminar } = useMutation({
    mutationFn: () => portalClientsApi.remove(usuario.id).then(r => r.data),
    onSuccess: (r) => {
      onCambio()
      if (r.resultado === 'eliminado') toast.success(t('portalacc.eliminado', { nombre }))
      else toast.info(t('portalacc.archivado', { nombre, n: r.total ?? 0 }), 10000)
    },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: restaurar } = useMutation({
    mutationFn: () => portalClientsApi.restore(usuario.id).then(r => r.data),
    onSuccess: () => { onCambio(); toast.success(t('portalacc.restaurado', { nombre })) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: pedirRgpd } = useMutation({
    mutationFn: () => gdprApi.create({ request_type: 'erasure', subject_email: usuario.email, notes: t('portalacc.rgpd_nota') }),
    onSuccess: () => toast.success(t('portalacc.rgpd_creada'), 10000),
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const preguntar = async (accion: () => void, opts: { title: string; message: string; confirmLabel: string; danger?: boolean }) => {
    if (await confirmar(opts)) accion()
  }

  return (
    <>
      {!archivado && (
        <IconButton variante="caja" ariaLabel={t('portalacc.establecer_de', { nombre })} title={t('portalacc.titulo_establecer')} onClick={() => setEstablecer(true)}>
          <KeyRound size={16} />
        </IconButton>
      )}
      {!archivado && conReenviar && (
        <IconButton variante="caja" ariaLabel={t('portalacc.reenviar')} onClick={() => { void preguntar(() => reenviar(), { title: t('portaluserstab.reenviar_acceso'), message: t('portaluserstab.confirmar_reenviar_acceso', { email: usuario.email }), confirmLabel: t('portaluserstab.reenviar_acceso') }) }}>
          <Send size={16} />
        </IconButton>
      )}
      {archivado ? (
        <IconButton variante="caja" tono="acento" ariaLabel={t('portalacc.restaurar_de', { nombre })} title={t('portalacc.restaurar')}
          onClick={() => { void preguntar(() => restaurar(), { title: t('portalacc.restaurar'), message: t('portalacc.confirmar_restaurar', { nombre }), confirmLabel: t('portalacc.restaurar') }) }}>
          <ArchiveRestore size={16} />
        </IconButton>
      ) : (
        <IconButton variante="caja" tono="peligro" ariaLabel={t('portalacc.eliminar_de', { nombre })} title={t('portalacc.eliminar')}
          onClick={() => { void preguntar(() => eliminar(), { title: t('portalacc.eliminar'), message: t('portalacc.confirmar_eliminar', { nombre }), confirmLabel: t('portalacc.eliminar'), danger: true }) }}>
          <Trash2 size={16} />
        </IconButton>
      )}
      {puedeRgpd && (
        <IconButton variante="caja" tono="peligro" ariaLabel={t('portalacc.rgpd_de', { nombre })} title={t('portalacc.rgpd')}
          onClick={() => { void preguntar(() => pedirRgpd(), { title: t('portalacc.rgpd'), message: t('portalacc.confirmar_rgpd', { email: usuario.email }), confirmLabel: t('portalacc.rgpd'), danger: true }) }}>
          <ShieldX size={16} />
        </IconButton>
      )}
      {establecer && <ModalEstablecerContrasena usuario={usuario} onClose={() => setEstablecer(false)} onHecho={onCambio} />}
    </>
  )
}
