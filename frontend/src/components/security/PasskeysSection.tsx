/**
 * Passkeys del propio usuario: añadir, renombrar y quitar.
 *
 * Auditoría 2026-11: el backend sabía registrar passkeys y ninguna pantalla lo
 * llamaba (`startRegistration` no tenía quien la usara). Con una passkey se
 * puede entrar sin contraseña y sirve de segundo factor.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { authApi } from '../../services/api'
import { startRegistration, webauthnSupported } from '../../lib/webauthn'
import { useToast } from '../../context/ToastContext'
import { useAppLang } from '../../i18n/AppLangContext'
import { extractErr } from '../../utils/helpers'
import { useConfirm } from '../../context/ConfirmContext'
import { pedirReautenticacion, esFalloDeReautenticacion } from './reautenticacion'
import { Button, Pulsable } from '../ui'
import './PasskeysSection.css'
import { Input } from '../ui'

export default function PasskeysSection() {
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const { pedirTexto } = useConfirm()
  const [nombre, setNombre] = useState('')
  const [editando, setEditando] = useState<{ id: string; name: string } | null>(null)
  const { data: lista = [] } = useQuery({
    queryKey: ['passkeys'],
    queryFn: () => authApi.passkeyList().then(r => (Array.isArray(r.data) ? r.data : [])),
  })
  const refrescar = () => qc.invalidateQueries({ queryKey: ['passkeys'] })

  const { mutate: anadir, isPending: anadiendo } = useMutation({
    mutationFn: async () => {
      // El servidor pide la contrasena (o un codigo TOTP) antes de dar de alta
      // un factor nuevo. Cancelar el dialogo no es un error.
      const reauth = await pedirReautenticacion(pedirTexto)
      if (!reauth) return null
      const { data } = await authApi.passkeyRegisterStart(reauth)
      const credential = await startRegistration(data.options)
      return authApi.passkeyRegisterFinish({
        webauthn_challenge_token: data.webauthn_challenge_token, credential, name: nombre.trim() || undefined,
      })
    },
    onSuccess: (r) => { if (!r) return; setNombre(''); refrescar(); toast.success(t('passkeys.added')) },
    onError: (e: unknown) => toast.error(esFalloDeReautenticacion(e)
      ? 'Contraseña o código incorrectos: no se ha añadido la passkey.'
      : extractErr(e, t('passkeys.error'))),
  })
  const { mutate: renombrar } = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) => authApi.passkeyRename(id, name),
    onSuccess: () => { setEditando(null); refrescar() },
    onError: (e: unknown) => toast.error(extractErr(e, t('passkeys.error'))),
  })
  const { mutate: quitar } = useMutation({
    mutationFn: (id: string) => authApi.passkeyDelete(id),
    onSuccess: refrescar,
    onError: (e: unknown) => toast.error(extractErr(e, t('passkeys.error'))),
  })

  const soporta = webauthnSupported()
  return (
    <div className="passsect-box-1">
      <div className="passsect-box-2">{t('passkeys.title')}</div>
      <div className="passsect-box-3">{t('passkeys.desc')}</div>
      {lista.length === 0 && <div className="passsect-box-4">{t('passkeys.none')}</div>}
      <ul className="passsect-stack-1">
        {lista.map(p => (
          <li key={p.id} className="passsect-row-1">
            {editando?.id === p.id ? (
              <>
                <Input aria-label={t('passkeys.name')} value={editando.name} onChange={e => setEditando({ id: p.id, name: e.target.value })} className="u-flex1" />
                <Button variant="secondary" size="sm" onClick={() => renombrar(editando)}>{t('common.save')}</Button>
              </>
            ) : (
              <>
                <span className="u-flex1">🔑 {p.name || t('passkeys.unnamed')}
                  <span className="passsect-box-5">
                    {p.last_used_at ? `${t('passkeys.last_used')} ${String(p.last_used_at).slice(0, 10)}` : t('passkeys.never_used')}
                  </span>
                </span>
                <Pulsable aria-label={`${t('passkeys.rename')} ${p.name || ''}`} onClick={() => setEditando({ id: p.id, name: p.name || '' })}
                  className="passsect-box-6">✏</Pulsable>
                <Pulsable aria-label={`${t('passkeys.remove')} ${p.name || ''}`} onClick={() => quitar(p.id)}
                  className="passsect-box-7">🗑</Pulsable>
              </>
            )}
          </li>
        ))}
      </ul>
      {soporta ? (
        <div className="u-row-8">
          <Input aria-label={t('passkeys.name')} placeholder={t('passkeys.name_ph')} value={nombre} onChange={e => setNombre(e.target.value)} className="u-flex1" />
          <Pulsable onClick={() => anadir()} disabled={anadiendo}
            className="passsect-box-8">
            {anadiendo ? '…' : t('passkeys.add')}
          </Pulsable>
        </div>
      ) : (
        <div className="passsect-txt-1">{t('passkeys.unsupported')}</div>
      )}
    </div>
  )
}
