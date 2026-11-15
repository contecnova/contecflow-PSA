/**
 * MFAPage — Configuración de autenticación en dos pasos (TOTP)
 *
 * Auditoria 2026-11: usa /auth/mfa/*, el TOTP que exige el login. Antes usaba
 * /mfa/*, que guardaba otra tabla y el login no la miraba.
 */
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useConfirm } from '../context/ConfirmContext'
import { pedirReautenticacion, esFalloDeReautenticacion } from '../components/security/reautenticacion'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { mfaApi } from '../services/api'
import type { AltaMfa, EstadoMfa } from '../services/api/tipos-plataforma'
import { Button, Spinner, Modal } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Lock } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import './MFAPage.css'

const fs: CSSProperties = { width:'100%', background:'var(--surface-2)', border:'.5px solid var(--surface-4)', borderRadius:8, padding:'9px 12px', color:'var(--text-1)', fontSize: "var(--text-xl-em)", outline:'none', fontFamily:'inherit', boxSizing:'border-box', letterSpacing:4, textAlign:'center' }

export default function MFAPage() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const { pedirTexto } = useConfirm()
  const [step, setStep] = useState<'status' | 'setup' | 'verify' | 'done'>('status')
  const [setupData, setSetupData] = useState<AltaMfa | null>(null)
  const [code, setCode] = useState('')
  const [backupCodes, setBackupCodes] = useState<string[]>([])
  const [disableCode, setDisableCode] = useState('')
  const [showDisable, setShowDisable] = useState(false)

  const { data: status, isLoading } = useQuery<EstadoMfa>({
    queryKey: ['mfa-status'],
    queryFn: () => mfaApi.status().then(r => r.data),
  })

  const { mutate: setup, isPending: setting } = useMutation({
    mutationFn: async (): Promise<AltaMfa | null> => {
      // Con una passkey ya registrada, el servidor pide contrasena o codigo.
      // Cancelar el dialogo no es un error.
      let reauth
      if (status?.reauth_required) {
        reauth = await pedirReautenticacion(pedirTexto)
        if (!reauth) return null
      }
      return mfaApi.setup(reauth).then(r => r.data)
    },
    onSuccess: (data: AltaMfa | null) => { if (!data) return; setSetupData(data); setStep('setup') },
    onError: (e: unknown) => toast.error(esFalloDeReautenticacion(e)
      ? t('pagina_mfa.contrasena_o_codigo_incorrectos_no_se')
      : extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: verify, isPending: verifying, isError: verifyError } = useMutation({
    mutationFn: (codeValue: string) => mfaApi.verify(codeValue).then(r => r.data),
    onSuccess: (data) => {
      setBackupCodes(data.backup_codes)
      setStep('done')
      qc.invalidateQueries({ queryKey: ['mfa-status'] })
    },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: disable, isPending: disabling } = useMutation({
    mutationFn: (codeValue: string) => mfaApi.disable(codeValue),
    onSuccess: () => { setShowDisable(false); setDisableCode(''); qc.invalidateQueries({ queryKey: ['mfa-status'] }) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  if (isLoading) return <PageShell><Spinner /></PageShell>

  return (
    <PageShell className="mfa-box-11">
      <PageHeader icon={<Lock size={18} />} title={t('mfa.title')} subtitle={t('mfa.subtitle')} showListExport={false} />

      {/* Status card */}
      <div className="mfapage-e1">
        <div className="u-row-between">
          <div>
            <div className="mfa-row">
              <span className="mfa-label">{status?.enabled ? '🔒' : '🔓'}</span>
              <div className="mfa-box">{status?.enabled ? t('mfa.enabled') : t('mfa.disabled')}</div>
            </div>
            {status?.enabled ? (
              <div className="u-text2-sm">
                {t('mfa.enabled_on', { date: status.verified_at || '—', codes: status.backup_codes_remaining })}
              </div>
            ) : (
              <div className="u-text2-sm">
                {t('mfa.not_protected')}
              </div>
            )}
          </div>
          {status?.enabled ? (
            <button onClick={() => setShowDisable(true)}
              className="mfa-btn">
              {t('mfa.deactivate')}
            </button>
          ) : (
            <Button onClick={() => setup()} disabled={setting}>{setting ? t('mfa.generating') : t('mfa.activate')}</Button>
          )}
        </div>
      </div>

      {/* Setup step */}
      {step === 'setup' && setupData && (
        <div className="mfapage-e2">
          <div className="mfa-box-2">{t('mfa.step1')}</div>
          <div className="mfa-row-2">
            <img src={setupData.qr_url} alt={t('pagina_mfa.qr_mfa')} className="mfa-card" />
            <div>
              <div className="mfa-box-3">
                {t('mfa.scan_qr')}
              </div>
              <code className="mfa-card-2">
                {setupData.secret}
              </code>
            </div>
          </div>
          <div className="mfa-box-4">{t('mfa.step2')}</div>
          <input aria-label={t('mfa.code_placeholder')}
            value={code}
            onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
            style={fs}
            placeholder={t('mfa.code_placeholder')}
            maxLength={6}
            autoFocus
          />
          {verifyError && <div className="mfa-box-5">{t('mfa.code_error')}</div>}
          <div className="mfa-row-3">
            <Button variant="secondary" onClick={() => setStep('status')}>{t('mfa.cancel')}</Button>
            <Button onClick={() => verify(code)} disabled={code.length !== 6 || verifying}>
              {verifying ? t('mfa.verifying') : t('mfa.activate')}
            </Button>
          </div>
        </div>
      )}

      {/* Done step — backup codes */}
      {step === 'done' && backupCodes.length > 0 && (
        <div className="mfapage-e3">
          <div className="mfa-box-6">{t('mfa.activated')}</div>
          <div className="mfa-box-7">
            {t('mfa.backup_codes_info')}
          </div>
          <div className="mfa-grid">
            {backupCodes.map((c, i) => (
              <code key={i} className="mfa-card-3">{c}</code>
            ))}
          </div>
          <Button onClick={() => { setStep('status'); setBackupCodes([]) }}>{t('mfa.understood')}</Button>
        </div>
      )}

      {/* How it works */}
      {!status?.enabled && step === 'status' && (
        <div className="mfapage-e4">
          <div className="mfa-box-8">{t('mfa.how_title')}</div>
          {[
            ['🔑', t('mfa.how_1_title'), t('mfa.how_1_desc')],
            ['📱', t('mfa.how_2_title'), t('mfa.how_2_desc')],
            ['⏱', t('mfa.how_3_title'), t('mfa.how_3_desc')],
            ['🆘', t('mfa.how_4_title'), t('mfa.how_4_desc')],
          ].map(([icon, title, desc], i) => (
            <div key={i} className={`mfa-row-4 ${i < 3 ? 'mfapage-sx1' : 'mfapage-sx2'}`}>
              <span className="mfa-label-2">{icon}</span>
              <div>
                <div className="mfa-box-9">{title}</div>
                <div className="u-text2-xs">{desc}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Disable modal */}
      {/* Auditoria 2026-11 (#41): overlay propio sin trampa de foco ni Esc -> Modal del kit. */}
      <Modal open={showDisable} onClose={() => setShowDisable(false)} title={t('mfa.disable_title')} size="sm">
            <div className="mfa-box-10">{t('mfa.disable_desc')}</div>
            <input aria-label={t('mfa.code_placeholder')} value={disableCode} onChange={e => setDisableCode(e.target.value.replace(/\D/g,'').slice(0,6))} style={fs} placeholder={t('mfa.code_placeholder')} autoFocus />
            <div className="mfa-row-3">
              <Button variant="secondary" onClick={() => setShowDisable(false)}>{t('mfa.cancel')}</Button>
              <button onClick={() => disable(disableCode)} disabled={disableCode.length !== 6 || disabling}
                className={`mfa-btn ${disableCode.length !== 6 ? 'mfapage-sx3' : 'mfapage-sx4'}`}>
                {disabling ? t('mfa.disabling') : t('mfa.confirm_disable')}
              </button>
            </div>
      </Modal>
    </PageShell>
  )
}
