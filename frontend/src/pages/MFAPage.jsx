/**
 * MFAPage — Configuración de autenticación en dos pasos (TOTP)
 */
import { useState } from 'react'
import { extractErr } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../services/api'
import { Button, Spinner } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { useAppT } from '../i18n/AppLangContext'

const card = { background:'var(--color-background-primary)', border:'.5px solid var(--color-border-tertiary)', borderRadius:12 }
const fs = { width:'100%', background:'var(--color-background-secondary)', border:'.5px solid var(--color-border-secondary)', borderRadius:8, padding:'9px 12px', color:'var(--color-text-primary)', fontSize:22, outline:'none', fontFamily:'inherit', boxSizing:'border-box', letterSpacing:4, textAlign:'center' }

export default function MFAPage() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [step, setStep] = useState('status')  // status | setup | verify | done
  const [setupData, setSetupData] = useState(null)
  const [code, setCode] = useState('')
  const [backupCodes, setBackupCodes] = useState([])
  const [disableCode, setDisableCode] = useState('')
  const [showDisable, setShowDisable] = useState(false)

  const { data: status, isLoading } = useQuery({
    queryKey: ['mfa-status'],
    queryFn: () => api.get('/mfa/status').then(r => r.data),
  })

  const { mutate: setup, isPending: setting } = useMutation({
    mutationFn: () => api.post('/mfa/setup').then(r => r.data),
    onSuccess: data => { setSetupData(data); setStep('setup') },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: verify, isPending: verifying, isError: verifyError } = useMutation({
    mutationFn: code => api.post('/mfa/verify', { code }),
    onSuccess: data => {
      setBackupCodes(data.data?.backup_codes || [])
      setStep('done')
      qc.invalidateQueries(['mfa-status'])
    },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: disable, isPending: disabling } = useMutation({
    mutationFn: code => api.delete('/mfa/disable', { data: { code } }),
    onSuccess: () => { setShowDisable(false); setDisableCode(''); qc.invalidateQueries(['mfa-status']) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  if (isLoading) return <div style={{ padding:32 }}><Spinner /></div>

  return (
    <div style={{ padding:32, maxWidth:640, margin:'0 auto' }}>
      <PageHeader title={t('mfa.title')} subtitle="MFA/2FA — Protege tu cuenta con TOTP" />

      {/* Status card */}
      <div style={{ ...card, padding:'20px 24px', marginBottom:24 }}>
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
          <div>
            <div style={{ display:'flex', gap:10, alignItems:'center', marginBottom:6 }}>
              <span style={{ fontSize:24 }}>{status?.enabled ? '🔒' : '🔓'}</span>
              <div style={{ fontSize:15, fontWeight:500 }}>{status?.enabled ? 'MFA activado' : 'MFA no activado'}</div>
            </div>
            {status?.enabled ? (
              <div style={{ fontSize:12, color:'var(--color-text-secondary)' }}>
                Activado el {status.verified_at || '—'} · {status.backup_codes_remaining} códigos de respaldo restantes
              </div>
            ) : (
              <div style={{ fontSize:12, color:'var(--color-text-secondary)' }}>
                Tu cuenta no tiene protección adicional. Activa el MFA para mayor seguridad.
              </div>
            )}
          </div>
          {status?.enabled ? (
            <button onClick={() => setShowDisable(true)}
              style={{ background:'var(--color-background-danger)', border:'.5px solid var(--color-border-danger)', borderRadius:8, padding:'8px 16px', color:'var(--color-text-danger)', cursor:'pointer', fontSize:12, fontFamily:'inherit' }}>
              Desactivar MFA
            </button>
          ) : (
            <Button onClick={() => setup()} disabled={setting}>{setting ? 'Generando...' : 'Activar MFA'}</Button>
          )}
        </div>
      </div>

      {/* Setup step */}
      {step === 'setup' && setupData && (
        <div style={{ ...card, padding:'24px 28px' }}>
          <div style={{ fontSize:14, fontWeight:500, marginBottom:16 }}>Paso 1 — Escanea el código QR</div>
          <div style={{ display:'flex', gap:28, alignItems:'flex-start', marginBottom:20 }}>
            <img src={setupData.qr_url} alt="QR MFA" style={{ width:160, height:160, borderRadius:8, border:'.5px solid var(--color-border-tertiary)' }} />
            <div>
              <div style={{ fontSize:12, color:'var(--color-text-secondary)', marginBottom:12, lineHeight:1.6 }}>
                Abre <strong>Google Authenticator</strong>, <strong>Authy</strong> o cualquier app TOTP y escanea el código QR.
                Si no puedes escanear, introduce este código manualmente:
              </div>
              <code style={{ display:'block', background:'var(--color-background-secondary)', padding:'8px 12px', borderRadius:8, fontSize:13, letterSpacing:2, wordBreak:'break-all' }}>
                {setupData.secret}
              </code>
            </div>
          </div>
          <div style={{ fontSize:14, fontWeight:500, marginBottom:10 }}>Paso 2 — Introduce el código de 6 dígitos</div>
          <input
            value={code}
            onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
            style={fs}
            placeholder="000000"
            maxLength={6}
            autoFocus
          />
          {verifyError && <div style={{ color:'var(--color-text-danger)', fontSize:12, marginTop:8 }}>Código incorrecto. Inténtalo de nuevo.</div>}
          <div style={{ display:'flex', justifyContent:'flex-end', gap:10, marginTop:16 }}>
            <Button variant="secondary" onClick={() => setStep('status')}>Cancelar</Button>
            <Button onClick={() => verify(code)} disabled={code.length !== 6 || verifying}>
              {verifying ? 'Verificando...' : 'Activar MFA'}
            </Button>
          </div>
        </div>
      )}

      {/* Done step — backup codes */}
      {step === 'done' && backupCodes.length > 0 && (
        <div style={{ ...card, padding:'24px 28px', background:'var(--color-background-success)', border:'.5px solid var(--color-border-success)' }}>
          <div style={{ fontSize:14, fontWeight:500, color:'var(--color-text-success)', marginBottom:6 }}>✓ MFA activado correctamente</div>
          <div style={{ fontSize:12, color:'var(--color-text-success)', marginBottom:16 }}>
            Guarda estos códigos de respaldo en un lugar seguro. Cada uno solo se puede usar una vez si pierdes acceso a tu app de autenticación.
          </div>
          <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:8, marginBottom:16 }}>
            {backupCodes.map((c, i) => (
              <code key={i} style={{ background:'var(--color-background-primary)', padding:'6px 10px', borderRadius:6, fontSize:13, textAlign:'center', border:'.5px solid var(--color-border-success)' }}>{c}</code>
            ))}
          </div>
          <Button onClick={() => { setStep('status'); setBackupCodes([]) }}>Entendido, ya los he guardado</Button>
        </div>
      )}

      {/* How it works */}
      {!status?.enabled && step === 'status' && (
        <div style={{ ...card, padding:'20px 24px' }}>
          <div style={{ fontSize:13, fontWeight:500, marginBottom:14 }}>¿Cómo funciona?</div>
          {[
            ['🔑', 'Activas MFA una sola vez', 'Escaneas un código QR con tu app de autenticación.'],
            ['📱', 'Al iniciar sesión', 'Además de tu contraseña, introduces un código de 6 dígitos de tu app.'],
            ['⏱', 'El código cambia cada 30 segundos', 'Aunque alguien robe tu contraseña, no puede acceder sin tu móvil.'],
            ['🆘', 'Códigos de respaldo', 'Si pierdes tu móvil, 8 códigos de un solo uso te permiten recuperar el acceso.'],
          ].map(([icon, title, desc], i) => (
            <div key={i} style={{ display:'flex', gap:12, padding:'10px 0', borderBottom: i < 3 ? '.5px solid var(--color-border-tertiary)' : 'none' }}>
              <span style={{ fontSize:20, flexShrink:0 }}>{icon}</span>
              <div>
                <div style={{ fontSize:12, fontWeight:500, marginBottom:2 }}>{title}</div>
                <div style={{ fontSize:11, color:'var(--color-text-secondary)' }}>{desc}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Disable modal */}
      {showDisable && (
        <div style={{ position:'fixed', top:0, left:0, right:0, bottom:0, background:'rgba(0,0,0,0.45)', zIndex:999, display:'flex', alignItems:'center', justifyContent:'center' }}
          onClick={() => setShowDisable(false)}>
          <div style={{ background:'var(--color-background-primary)', borderRadius:14, padding:24, width:400, border:'.5px solid var(--color-border-secondary)' }}
            onClick={e => e.stopPropagation()}>
            <div style={{ fontSize:14, fontWeight:500, marginBottom:14 }}>⚠ Desactivar MFA</div>
            <div style={{ fontSize:12, color:'var(--color-text-secondary)', marginBottom:16 }}>Introduce tu código TOTP actual para confirmar que deseas desactivar la autenticación en dos pasos.</div>
            <input value={disableCode} onChange={e => setDisableCode(e.target.value.replace(/\D/g,'').slice(0,6))} style={fs} placeholder="000000" autoFocus />
            <div style={{ display:'flex', justifyContent:'flex-end', gap:10, marginTop:16 }}>
              <Button variant="secondary" onClick={() => setShowDisable(false)}>Cancelar</Button>
              <button onClick={() => disable(disableCode)} disabled={disableCode.length !== 6 || disabling}
                style={{ background:'var(--color-background-danger)', border:'.5px solid var(--color-border-danger)', borderRadius:8, padding:'8px 16px', color:'var(--color-text-danger)', cursor:'pointer', fontSize:12, fontFamily:'inherit', opacity: disableCode.length !== 6 ? 0.6 : 1 }}>
                {disabling ? 'Desactivando...' : 'Confirmar desactivación'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
