/**
 * MFAPage — Configuración de autenticación en dos pasos (TOTP)
 *
 * Auditoria 2026-11: usa /auth/mfa/*, el TOTP que exige el login. Antes usaba
 * /mfa/*, que guardaba otra tabla y el login no la miraba.
 *
 * 16-11-2026: a todo el ancho (tenía un ancho máximo de 640px centrado), con
 * Card/Section/Button del kit e iconos lucide en lugar de emojis (candado,
 * llave, móvil, reloj, salvavidas). Título = el del menú. Campo del código con
 * ds-input en vez de un estilo en línea con fondo gris propio.
 */
import { useState } from 'react'
import { extractErr, fmtDate } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useConfirm } from '../context/ConfirmContext'
import { pedirReautenticacion, esFalloDeReautenticacion } from '../components/security/reautenticacion'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { mfaApi } from '../services/api'
import type { AltaMfa, EstadoMfa } from '../services/api/tipos-plataforma'
import { Button, Card, Section, Spinner, Modal } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { CheckCircle2, KeyRound, LifeBuoy, Lock, ShieldCheck, ShieldOff, Smartphone, Timer } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import './MFAPage.css'

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

  const header = <PageHeader icon={<Lock size={18} />} title={t('nav.mfa')} subtitle={t('mfa.subtitle')} showListExport={false} />

  if (isLoading) return <PageShell>{header}<Spinner /></PageShell>

  const pasos = [
    { icon: <KeyRound size={16} />, title: t('mfa.how_1_title'), desc: t('mfa.how_1_desc') },
    { icon: <Smartphone size={16} />, title: t('mfa.how_2_title'), desc: t('mfa.how_2_desc') },
    { icon: <Timer size={16} />, title: t('mfa.how_3_title'), desc: t('mfa.how_3_desc') },
    { icon: <LifeBuoy size={16} />, title: t('mfa.how_4_title'), desc: t('mfa.how_4_desc') },
  ]

  return (
    <PageShell>
      {header}

      <div className="u-stack-16">
        {/* Estado */}
        <Card>
          <div className="mfa-estado">
            <div className="mfa-estado__texto">
              <div className="mfa-estado__titulo">
                <span className={`mfa-estado__icono${status?.enabled ? ' mfa-estado__icono--ok' : ''}`}>
                  {status?.enabled ? <ShieldCheck size={20} aria-hidden /> : <ShieldOff size={20} aria-hidden />}
                </span>
                {status?.enabled ? t('mfa.enabled') : t('mfa.disabled')}
              </div>
              <div className="mfa-texto">
                {status?.enabled
                  ? t('mfa.enabled_on', { date: status.verified_at ? fmtDate(status.verified_at) : '—', codes: status.backup_codes_remaining })
                  : t('mfa.not_protected')}
              </div>
            </div>
            {status?.enabled ? (
              <Button variant="danger" icon={<ShieldOff size={14} />} onClick={() => setShowDisable(true)}>{t('mfa.deactivate')}</Button>
            ) : (
              <Button icon={<ShieldCheck size={14} />} onClick={() => setup()} loading={setting}>{setting ? t('mfa.generating') : t('mfa.activate')}</Button>
            )}
          </div>
        </Card>

        {/* Alta: QR y verificación */}
        {step === 'setup' && setupData && (
          <Card>
            <Section title={t('mfa.step1')}>
              <div className="mfa-qr">
                <img src={setupData.qr_url} alt={t('pagina_mfa.qr_mfa')} className="mfa-qr__img" />
                <div className="mfa-qr__texto">
                  <div className="mfa-texto">{t('mfa.scan_qr')}</div>
                  <code className="mfa-secreto">{setupData.secret}</code>
                </div>
              </div>
            </Section>
            <Section title={t('mfa.step2')}>
              <input aria-label={t('mfa.code_placeholder')}
                className="ds-input mfa-codigo"
                value={code}
                onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                placeholder={t('mfa.code_placeholder')}
                inputMode="numeric"
                maxLength={6}
                autoFocus
              />
              {verifyError && <div className="mfa-error" role="alert">{t('mfa.code_error')}</div>}
              <div className="mfa-acciones">
                <Button variant="secondary" onClick={() => setStep('status')}>{t('mfa.cancel')}</Button>
                <Button onClick={() => verify(code)} disabled={code.length !== 6} loading={verifying}>
                  {verifying ? t('mfa.verifying') : t('mfa.activate')}
                </Button>
              </div>
            </Section>
          </Card>
        )}

        {/* Hecho: códigos de respaldo */}
        {step === 'done' && backupCodes.length > 0 && (
          <Card>
            <div className="mfa-hecho">
              <div className="mfa-hecho__titulo"><CheckCircle2 size={16} aria-hidden />{t('mfa.activated')}</div>
              <div className="mfa-texto">{t('mfa.backup_codes_info')}</div>
              <div className="mfa-codigos">
                {backupCodes.map((c, i) => (
                  <code key={i} className="mfa-codigos__item">{c}</code>
                ))}
              </div>
              <div>
                <Button onClick={() => { setStep('status'); setBackupCodes([]) }}>{t('mfa.understood')}</Button>
              </div>
            </div>
          </Card>
        )}

        {/* Cómo funciona */}
        {!status?.enabled && step === 'status' && (
          <Card>
            <Section title={t('mfa.how_title')}>
              <ul className="mfa-pasos">
                {pasos.map((p, i) => (
                  <li key={i} className="mfa-paso">
                    <span className="mfa-paso__icono" aria-hidden>{p.icon}</span>
                    <div className="u-min0">
                      <div className="mfa-paso__titulo">{p.title}</div>
                      <div className="mfa-texto">{p.desc}</div>
                    </div>
                  </li>
                ))}
              </ul>
            </Section>
          </Card>
        )}
      </div>

      {/* Auditoria 2026-11 (#41): overlay propio sin trampa de foco ni Esc -> Modal del kit. */}
      <Modal open={showDisable} onClose={() => setShowDisable(false)} title={t('mfa.disable_title')} size="sm">
        <div className="mfa-texto mfa-texto--mb">{t('mfa.disable_desc')}</div>
        <input aria-label={t('mfa.code_placeholder')} className="ds-input mfa-codigo" value={disableCode}
          onChange={e => setDisableCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
          placeholder={t('mfa.code_placeholder')} inputMode="numeric" maxLength={6} autoFocus />
        <div className="mfa-acciones">
          <Button variant="secondary" onClick={() => setShowDisable(false)}>{t('mfa.cancel')}</Button>
          <Button variant="danger" onClick={() => disable(disableCode)} disabled={disableCode.length !== 6} loading={disabling}>
            {disabling ? t('mfa.disabling') : t('mfa.confirm_disable')}
          </Button>
        </div>
      </Modal>
    </PageShell>
  )
}
