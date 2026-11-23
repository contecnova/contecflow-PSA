/**
 * Cambio de contraseña obligatorio del portal de clientes (23-11-2026).
 *
 * La contraseña generada por el sistema (alta del contacto o «Reenviar acceso»)
 * solo sirve para entrar aquí: el servidor responde 403
 * `portal_cambio_de_contrasena_obligatorio` al resto de rutas del portal hasta
 * que el cliente la cambia (`PATCH /portal/auth/me` con `current_password`).
 * Textos en los 8 idiomas del portal (`i18n/portal/*`, `portal_cambio_obligatorio.*`).
 */
import { useState } from 'react'
import type { ChangeEvent } from 'react'
import { useMutation } from '@tanstack/react-query'
import { KeyRound, LogOut } from 'lucide-react'
import { CLIENT_API, useClientAuth, useErrorDelPortal, useLang } from './portalClientContext'
import { PortalBanner, PortalButton, PortalCard, PortalField, PortalInput, PortalSection } from './PortalUI'
import './CambioDeContrasenaObligatorio.css'

/** Longitud mínima que exige el servidor (`MIN_PASSWORD_LENGTH`, 8 por defecto). */
const MINIMO = 8

export function CambioDeContrasenaObligatorio() {
  const traducir = useLang()
  const errorDe = useErrorDelPortal()
  const sesion = useClientAuth()
  const [form, setForm] = useState({ actual: '', nueva: '', repetida: '' })
  const [aviso, setAviso] = useState('')

  const { mutate, isPending } = useMutation({
    mutationFn: () => CLIENT_API.patch('/portal/auth/me', { password: form.nueva, current_password: form.actual }).then(r => r.data),
    onSuccess: () => sesion?.contrasenaCambiada?.(),
    onError: (e: unknown) => setAviso(errorDe(e, traducir('portal_perfil.error_contrasena'))),
  })

  const enviar = () => {
    setAviso('')
    if (form.nueva !== form.repetida) { setAviso(traducir('portal_perfil.contrasenas_no_coinciden')); return }
    if (form.nueva.length < MINIMO) { setAviso(traducir('portal_perfil.minimo_8')); return }
    if (form.nueva === form.actual) { setAviso(traducir('err_srv.portal_contrasena_igual_a_la_anterior')); return }
    mutate()
  }
  const campo = (k: keyof typeof form) => (e: ChangeEvent<HTMLInputElement>) => setForm(f => ({ ...f, [k]: e.target.value }))

  return (
    <main className="u-stack-12 pcco-marco">
      <PortalCard>
        <PortalSection title={traducir('portal_cambio_obligatorio.titulo')} hint={traducir('portal_cambio_obligatorio.explicacion')}>
          <form className="u-stack-12" onSubmit={(e) => { e.preventDefault(); enviar() }}>
            <PortalField label={traducir('portal_cambio_obligatorio.contrasena_recibida')} required>
              <PortalInput type="password" autoComplete="current-password" value={form.actual} onChange={campo('actual')} autoFocus />
            </PortalField>
            <PortalField label={traducir('portalcliente.nueva_contrasena')} hint={traducir('portal_perfil.minimo_8')} required>
              <PortalInput type="password" autoComplete="new-password" value={form.nueva} onChange={campo('nueva')} />
            </PortalField>
            <PortalField label={traducir('portalcliente.confirmar_nueva_contrasena')} required>
              <PortalInput type="password" autoComplete="new-password" value={form.repetida} onChange={campo('repetida')} />
            </PortalField>
            {aviso && <PortalBanner tone="danger" title={aviso} />}
            <div className="pcl-row-5">
              <PortalButton type="submit" icon={<KeyRound size={13} />} loading={isPending}
                disabled={!form.actual || !form.nueva || !form.repetida}>
                {traducir('portal_cambio_obligatorio.guardar')}
              </PortalButton>
              <PortalButton variant="ghost" icon={<LogOut size={13} />} onClick={() => { void sesion?.logout() }}>
                {traducir('portalclientcontext.cerrar_sesion')}
              </PortalButton>
            </div>
          </form>
        </PortalSection>
      </PortalCard>
    </main>
  )
}
