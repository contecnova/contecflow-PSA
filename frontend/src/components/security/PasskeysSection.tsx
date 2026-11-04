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

export default function PasskeysSection() {
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const [nombre, setNombre] = useState('')
  const [editando, setEditando] = useState<{ id: string; name: string } | null>(null)
  const { data: lista = [] } = useQuery({
    queryKey: ['passkeys'],
    queryFn: () => authApi.passkeyList().then(r => (Array.isArray(r.data) ? r.data : [])),
  })
  const refrescar = () => qc.invalidateQueries({ queryKey: ['passkeys'] })

  const { mutate: anadir, isPending: anadiendo } = useMutation({
    mutationFn: async () => {
      const { data } = await authApi.passkeyRegisterStart()
      const credential = await startRegistration(data.options)
      return authApi.passkeyRegisterFinish({
        webauthn_challenge_token: data.webauthn_challenge_token, credential, name: nombre.trim() || undefined,
      })
    },
    onSuccess: () => { setNombre(''); refrescar(); toast.success(t('passkeys.added')) },
    onError: (e: unknown) => toast.error(extractErr(e, t('passkeys.error'))),
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
    <div style={{ padding: '12px 14px', background: 'var(--surface-3)', borderRadius: 8 }}>
      <div style={{ fontSize: 'var(--text-base)', fontWeight: 600, marginBottom: 4 }}>{t('passkeys.title')}</div>
      <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-2)', marginBottom: 10 }}>{t('passkeys.desc')}</div>
      {lista.length === 0 && <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-3)', marginBottom: 8 }}>{t('passkeys.none')}</div>}
      <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 10px', display: 'flex', flexDirection: 'column', gap: 6 }}>
        {lista.map(p => (
          <li key={p.id} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 'var(--text-sm)' }}>
            {editando?.id === p.id ? (
              <>
                <input aria-label={t('passkeys.name')} value={editando.name} onChange={e => setEditando({ id: p.id, name: e.target.value })}
                  className="ds-input" style={{ flex: 1 }} />
                <button type="button" className="ds-btn" onClick={() => renombrar(editando)}>{t('common.save')}</button>
              </>
            ) : (
              <>
                <span style={{ flex: 1 }}>🔑 {p.name || t('passkeys.unnamed')}
                  <span style={{ color: 'var(--text-3)', marginLeft: 6 }}>
                    {p.last_used_at ? `${t('passkeys.last_used')} ${String(p.last_used_at).slice(0, 10)}` : t('passkeys.never_used')}
                  </span>
                </span>
                <button type="button" aria-label={`${t('passkeys.rename')} ${p.name || ''}`} onClick={() => setEditando({ id: p.id, name: p.name || '' })}
                  style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 6, padding: '2px 8px', cursor: 'pointer', color: 'var(--text-2)' }}>✏</button>
                <button type="button" aria-label={`${t('passkeys.remove')} ${p.name || ''}`} onClick={() => quitar(p.id)}
                  style={{ background: 'none', border: '1px solid var(--danger-border)', borderRadius: 6, padding: '2px 8px', cursor: 'pointer', color: 'var(--danger)' }}>🗑</button>
              </>
            )}
          </li>
        ))}
      </ul>
      {soporta ? (
        <div style={{ display: 'flex', gap: 8 }}>
          <input aria-label={t('passkeys.name')} placeholder={t('passkeys.name_ph')} value={nombre}
            onChange={e => setNombre(e.target.value)} className="ds-input" style={{ flex: 1 }} />
          <button type="button" onClick={() => anadir()} disabled={anadiendo}
            style={{ padding: '7px 14px', background: 'var(--accent)', border: 'none', borderRadius: 7, color: '#fff',
              fontSize: 'var(--text-sm)', cursor: 'pointer', fontFamily: 'inherit', fontWeight: 600 }}>
            {anadiendo ? '…' : t('passkeys.add')}
          </button>
        </div>
      ) : (
        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--warning)' }}>{t('passkeys.unsupported')}</div>
      )}
    </div>
  )
}
