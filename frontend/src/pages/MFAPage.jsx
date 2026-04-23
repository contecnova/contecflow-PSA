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
import { Lock } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'

const card = { background:'var(--surface-1)', border:'.5px solid var(--surface-4)', borderRadius:12 }
const fs = { width:'100%', background:'var(--surface-2)', border:'.5px solid var(--surface-4)', borderRadius:8, padding:'9px 12px', color:'var(--text-1)', fontSize:22, outline:'none', fontFamily:'inherit', boxSizing:'border-box', letterSpacing:4, textAlign:'center' }

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
      <PageHeader icon={<Lock size={18} />} title={t('mfa.title')} subtitle={t('mfa.subtitle')} />

      {/* Status card */}
      <div style={{ ...card, padding:'20px 24px', marginBottom:24 }}>
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
          <div>
            <div style={{ display:'flex', gap:10, alignItems:'center', marginBottom:6 }}>
              <span style={{ fontSize:24 }}>{status?.enabled ? '🔒' : '🔓'}</span>
              <div style={{ fontSize:15, fontWeight:500 }}>{status?.enabled ? t('mfa.enabled') : t('mfa.disabled')}</div>
            </div>
            {status?.enabled ? (
              <div style={{ fontSize:12, color:'var(--text-2)' }}>
                {t('mfa.enabled_on', { date: status.verified_at || '—', codes: status.backup_codes_remaining })}
              </div>
            ) : (
              <div style={{ fontSize:12, color:'var(--text-2)' }}>
                {t('mfa.not_protected')}
              </div>
            )}
          </div>
          {status?.enabled ? (
            <button onClick={() => setShowDisable(true)}
              style={{ background:'var(--danger-bg)', border:'.5px solid rgba(239,68,68,0.25)', borderRadius:8, padding:'8px 16px', color:'var(--danger)', cursor:'pointer', fontSize:12, fontFamily:'inherit' }}>
              {t('mfa.deactivate')}
            </button>
          ) : (
            <Button onClick={() => setup()} disabled={setting}>{setting ? t('mfa.generating') : t('mfa.activate')}</Button>
          )}
        </div>
      </div>

      {/* Setup step */}
      {step === 'setup' && setupData && (
        <div style={{ ...card, padding:'24px 28px' }}>
          <div style={{ fontSize:14, fontWeight:500, marginBottom:16 }}>{t('mfa.step1')}</div>
          <div style={{ display:'flex', gap:28, alignItems:'flex-start', marginBottom:20 }}>
            <img src={setupData.qr_url} alt="QR MFA" style={{ width:160, height:160, borderRadius:8, border:'.5px solid var(--surface-4)' }} />
            <div>
              <div style={{ fontSize:12, color:'var(--text-2)', marginBottom:12, lineHeight:1.6 }}>
                {t('mfa.scan_qr')}
              </div>
              <code style={{ display:'block', background:'var(--surface-2)', padding:'8px 12px', borderRadius:8, fontSize:13, letterSpacing:2, wordBreak:'break-all' }}>
                {setupData.secret}
              </code>
            </div>
          </div>
          <div style={{ fontSize:14, fontWeight:500, marginBottom:10 }}>{t('mfa.step2')}</div>
          <input
            value={code}
            onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
            style={fs}
            placeholder={t('mfa.code_placeholder')}
            maxLength={6}
            autoFocus
          />
          {verifyError && <div style={{ color:'var(--danger)', fontSize:12, marginTop:8 }}>{t('mfa.code_error')}</div>}
          <div style={{ display:'flex', justifyContent:'flex-end', gap:10, marginTop:16 }}>
            <Button variant="secondary" onClick={() => setStep('status')}>{t('mfa.cancel')}</Button>
            <Button onClick={() => verify(code)} disabled={code.length !== 6 || verifying}>
              {verifying ? t('mfa.verifying') : t('mfa.activate')}
            </Button>
          </div>
        </div>
      )}

      {/* Done step — backup codes */}
      {step === 'done' && backupCodes.length > 0 && (
        <div style={{ ...card, padding:'24px 28px', background:'var(--success-bg)', border:'.5px solid rgba(52,211,153,0.25)' }}>
          <div style={{ fontSize:14, fontWeight:500, color:'var(--success)', marginBottom:6 }}>{t('mfa.activated')}</div>
          <div style={{ fontSize:12, color:'var(--success)', marginBottom:16 }}>
            {t('mfa.backup_codes_info')}
          </div>
          <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:8, marginBottom:16 }}>
            {backupCodes.map((c, i) => (
              <code key={i} style={{ background:'var(--surface-1)', padding:'6px 10px', borderRadius:6, fontSize:13, textAlign:'center', border:'.5px solid rgba(52,211,153,0.25)' }}>{c}</code>
            ))}
          </div>
          <Button onClick={() => { setStep('status'); setBackupCodes([]) }}>{t('mfa.understood')}</Button>
        </div>
      )}

      {/* How it works */}
      {!status?.enabled && step === 'status' && (
        <div style={{ ...card, padding:'20px 24px' }}>
          <div style={{ fontSize:13, fontWeight:500, marginBottom:14 }}>{t('mfa.how_title')}</div>
          {[
            ['🔑', t('mfa.how_1_title'), t('mfa.how_1_desc')],
            ['📱', t('mfa.how_2_title'), t('mfa.how_2_desc')],
            ['⏱', t('mfa.how_3_title'), t('mfa.how_3_desc')],
            ['🆘', t('mfa.how_4_title'), t('mfa.how_4_desc')],
          ].map(([icon, title, desc], i) => (
            <div key={i} style={{ display:'flex', gap:12, padding:'10px 0', borderBottom: i < 3 ? '.5px solid var(--surface-4)' : 'none' }}>
              <span style={{ fontSize:20, flexShrink:0 }}>{icon}</span>
              <div>
                <div style={{ fontSize:12, fontWeight:500, marginBottom:2 }}>{title}</div>
                <div style={{ fontSize:11, color:'var(--text-2)' }}>{desc}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Disable modal */}
      {showDisable && (
        <div role="presentation" style={{ position:'fixed', top:0, left:0, right:0, bottom:0, background:'rgba(0,0,0,0.45)', zIndex:999, display:'flex', alignItems:'center', justifyContent:'center' }}
          onMouseDown={() => setShowDisable(false)}>
          <div role="presentation" style={{ background:'var(--surface-1)', borderRadius:14, padding:24, width:400, border:'.5px solid var(--surface-4)' }}
            onMouseDown={e => e.stopPropagation()}>
            <div style={{ fontSize:14, fontWeight:500, marginBottom:14 }}>{t('mfa.disable_title')}</div>
            <div style={{ fontSize:12, color:'var(--text-2)', marginBottom:16 }}>{t('mfa.disable_desc')}</div>
            <input value={disableCode} onChange={e => setDisableCode(e.target.value.replace(/\D/g,'').slice(0,6))} style={fs} placeholder={t('mfa.code_placeholder')} autoFocus />
            <div style={{ display:'flex', justifyContent:'flex-end', gap:10, marginTop:16 }}>
              <Button variant="secondary" onClick={() => setShowDisable(false)}>{t('mfa.cancel')}</Button>
              <button onClick={() => disable(disableCode)} disabled={disableCode.length !== 6 || disabling}
                style={{ background:'var(--danger-bg)', border:'.5px solid rgba(239,68,68,0.25)', borderRadius:8, padding:'8px 16px', color:'var(--danger)', cursor:'pointer', fontSize:12, fontFamily:'inherit', opacity: disableCode.length !== 6 ? 0.6 : 1 }}>
                {disabling ? t('mfa.disabling') : t('mfa.confirm_disable')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
