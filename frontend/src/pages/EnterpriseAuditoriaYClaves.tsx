// Pestañas de auditoria (con su cadena) y API keys de Enterprise. 23-11-2026: troceado de EnterprisePage sin cambio de comportamiento.
import { useAppLang, useAppT } from '../i18n/AppLangContext'
import { useState, useId, useRef } from 'react'
import type { CSSProperties } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr, downloadBlob, fmtDateTime } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { enterpriseApi, apiKeysApi } from '../services/api'
import type { ClaveDeApi, ClaveDeApiCreada, EventoDeAuditoria, VerificacionDeCadena } from '../services/api/tipos'
import { Button, Modal, EmptyState, KpiCard, Input } from '../components/ui'
import { CheckCircle2, FileUp, Key, KeyRound, Plus, ScrollText, ShieldCheck } from 'lucide-react'
import { AUDIT_LOG_PAGE_SIZE, AUDIT_LOG_SMALL_PAGE_SIZE } from '../constants/pagination'
import { type AltaProps, type ApiKeyForm, etiq } from './EnterpriseComun'

/** Cadena a prueba de manipulación del registro (revisión 2026-11). */
function CadenaDeAuditoria() {
  const t = useAppT()
  const toast = useToast()
  const [resultado, setResultado] = useState<VerificacionDeCadena | null>(null)
  const [ocupado, setOcupado] = useState<'' | 'verificar' | 'exportar'>('')
  const ficheroRef = useRef<HTMLInputElement | null>(null)
  const verificar = async (esperada?: { seq: number; entry_hash: string }) => {
    setOcupado('verificar')
    try {
      const params = esperada ? { expected_seq: esperada.seq, expected_hash: esperada.entry_hash } : undefined
      const r = await enterpriseApi.verifyAuditChain(params)
      setResultado(r.data)
    } catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) } finally { setOcupado('') }
  }
  const exportar = async () => {
    setOcupado('exportar')
    try {
      const r = await enterpriseApi.exportAuditChain()
      downloadBlob(r.data, `audit-chain-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '')}.json`)
    } catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) } finally { setOcupado('') }
  }
  const comparar = async (fichero?: File) => {
    if (!fichero) return
    try {
      const head = JSON.parse(await fichero.text())?.head
      if (!head?.seq || !head?.entry_hash) { toast.error(t('enterprise.cadena_fichero_sin_cabeza')); return }
      await verificar(head)
    } catch { toast.error(t('enterprise.cadena_fichero_sin_cabeza')) }
  }
  const color = resultado ? (resultado.ok ? 'var(--success)' : 'var(--danger)') : 'var(--text-3)'
  return (
    <div className="enterprise-page-e8">
      <div className="ent-row-9">
        <div className="ent-box-12">
          <div className="u-md-700">{t('enterprise.cadena_titulo')}</div>
          <div className="u-text2-sm-mt2">{t('enterprise.cadena_ayuda')}</div>
        </div>
        <Button size="sm" icon={<ShieldCheck size={14} />} onClick={() => verificar()} disabled={!!ocupado && ocupado !== 'verificar'} loading={ocupado === 'verificar'}>{t('enterprise.cadena_verificar')}</Button>
        <Button size="sm" variant="secondary" onClick={exportar} disabled={!!ocupado && ocupado !== 'exportar'} loading={ocupado === 'exportar'}>{t('enterprise.cadena_exportar')}</Button>
        <Button size="sm" variant="ghost" icon={<FileUp size={14} />} onClick={() => ficheroRef.current?.click()} disabled={!!ocupado}>{t('enterprise.cadena_comparar')}</Button>
        <input ref={ficheroRef} type="file" accept="application/json,.json" className="ent-input" aria-label={t('enterprise.cadena_comparar')}
          onChange={e => { comparar(e.target.files?.[0]); e.target.value = '' }} />
      </div>
      {resultado && (
        <div role="status" className="ent-box-13 enterpri-sx5 enterprise-page-e7" style={{ '--enterprise-page-border': `1px solid ${color}` } as CSSProperties}>
          <div className="ent-box-14 enterprise-page-e3" style={{ '--enterprise-page-color': color } as CSSProperties}>
            {resultado.ok ? t('enterprise.cadena_ok') : resultado.breaks_total > 0 ? t('enterprise.cadena_rota', { n: resultado.breaks_total }) : t('enterprise.cadena_no_casa')}
          </div>
          <div className="ent-box-15">
            {t('enterprise.cadena_recorridas', { n: resultado.rows_checked })}
            {resultado.head.entry_hash && <> · {t('enterprise.cadena_cabeza')} #{resultado.head.seq} <code className="ds-codigo u-mono">{resultado.head.entry_hash.slice(0, 16)}…</code></>}
          </div>
          {resultado.expected_head && (
            <div className={`ent-box-16 ${resultado.expected_head.found ? 'enterpri-sx3' : 'enterpri-sx4'}`}>
              {t(resultado.expected_head.found ? 'enterprise.cadena_cabeza_sigue' : 'enterprise.cadena_cabeza_falta', { seq: resultado.expected_head.seq })}
            </div>
          )}
          {resultado.breaks.length > 0 && (
            <ul className="ent-box-17">
              {resultado.breaks.slice(0, 20).map((b, i) => (
                <li key={i}>#{b.seq ?? '—'} · {t(`enterprise.cadena_razon_${b.reason}`)}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

export function AuditTab() {
  const { t } = useAppLang()
  const traducir = useAppT()
  const { data: logs = [] } = useQuery<EventoDeAuditoria[]>({
    queryKey: ['audit-ent'],
    queryFn: () => enterpriseApi.auditLog({page:1,page_size:AUDIT_LOG_PAGE_SIZE}).then(r => r.data?.logs || []), // 23-11-2026: sin .catch tragado (avisa el onError global)
  })
  const { data: resetRequestLogs = [] } = useQuery<EventoDeAuditoria[]>({
    queryKey: ['audit-ent-reset-request'],
    queryFn: () => enterpriseApi.auditLog({page:1,page_size:AUDIT_LOG_SMALL_PAGE_SIZE,action:'PASSWORD_RESET_REQUEST'}).then(r => r.data?.logs || []),
  })
  const { data: resetCompleteLogs = [] } = useQuery<EventoDeAuditoria[]>({
    queryKey: ['audit-ent-reset-complete'],
    queryFn: () => enterpriseApi.auditLog({page:1,page_size:AUDIT_LOG_SMALL_PAGE_SIZE,action:'PASSWORD_RESET_COMPLETE'}).then(r => r.data?.logs || []),
  })

  const passwordResetLogs = [...resetCompleteLogs, ...resetRequestLogs]
    .sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))
    .slice(0, 20)

  return (
    <div className="ent-grid-6">
      <CadenaDeAuditoria />
      <div className="ds-grid-stats">
        <KpiCard icon={<ScrollText size={16} />} label={t('pagina_ent.total_eventos')} value={logs.length} />
        <KpiCard icon={<KeyRound size={16} />} label={t('pagina_ent.reset_solicitados')} value={resetRequestLogs.length} />
        <KpiCard icon={<CheckCircle2 size={16} />} label={t('pagina_ent.reset_completados')} value={resetCompleteLogs.length} />
      </div>

      <div className="enterprise-page-e2">
        <div className="ent-box-20">
          {traducir('enterprise.eventos_de_recuperacion_de_contrasena')}
        </div>
        {passwordResetLogs.length === 0 ? <EmptyState icon={<KeyRound size={28} />} title={traducir('enterprise.sin_eventos_de_recuperacion')} /> :
          passwordResetLogs.map((l, i) => (
            <div key={l.id||i} className="ent-grid-8">
              <span className="ent-label-8">{fmtDateTime(l.created_at)}</span>
              <span className={`u-600 ${l.action === 'PASSWORD_RESET_COMPLETE' ? 'enterpri-sx3' : 'enterpri-sx9'}`}>{etiq(t, 'pagina_ent.accion', l.action)}</span>
              <span className="u-text2">{l.resource_name || l.resource || '-'}</span>
              <span className="u-text3">{l.user_name||''}</span>
            </div>
          ))
        }
      </div>

      <div className="enterprise-page-e2">
        <div className="ent-box-20">
          {t('pagina_ent.audit_log_general_ultimos_30')}
        </div>
      {logs.length === 0 ? <EmptyState icon={<ScrollText size={28} />} title={traducir('enterprise.sin_entradas_en_el_audit_log')} /> :
        logs.slice(0,30).map((l, i) => (
          <div key={l.id||i} className="ent-grid-8">
            <span className="ent-label-8">{fmtDateTime(l.created_at)}</span>
            <span className="ent-label-4">{l.action}</span>
            <span className="u-text2">{l.resource} {l.resource_name||''}</span>
            <span className="u-text3">{l.user_name||''}</span>
          </div>
        ))
      }
      </div>
    </div>
  )
}

export function APIKeysTab({ showCreate, setShowCreate }: AltaProps) {
  const { t } = useAppLang()
  const idCampo = useId()
  const traducir = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [newKey, setNewKey] = useState<ClaveDeApiCreada | null>(null)
  const [form, setForm] = useState<ApiKeyForm>({ name:'', rate_limit_per_hour:1000 })

  const { data: keys = [] } = useQuery<ClaveDeApi[]>({ queryKey:['api-keys'], queryFn:() => apiKeysApi.list().then(r => r.data) })
  const { mutate: create } = useMutation({
    mutationFn: (d: ApiKeyForm) => apiKeysApi.create({ ...d, scopes:['read'] }).then(r => r.data),
    onSuccess: (data) => { qc.invalidateQueries({ queryKey: ['api-keys'] }); setNewKey(data); setShowCreate(false) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: revoke } = useMutation({
    mutationFn: (id: string) => apiKeysApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['api-keys'] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  return (
    <div>
      {newKey && (
        <div className="ent-card-9">
          <div className="ent-box-22">{traducir('enterprise.copiala_ahora_no_se_mostrara_de_nuevo')}</div>
          <code className="ds-codigo ent-card-10">{newKey.key}</code>
          <div className="ent-cerrar-clave"><Button size="sm" variant="secondary" onClick={() => setNewKey(null)}>{t('pagina_ent.cerrar')}</Button></div>
        </div>
      )}
      {keys.length === 0 ? <EmptyState icon={<Key size={28} />} title={traducir('enterprise.sin_api_keys')} description={t('pagina_ent.genera_una_clave_para_integraciones_externas')}
        action={<Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>{traducir('enterprise.nueva_api_key')}</Button>} /> : (
        <div className="enterprise-page-e2">
          {keys.map(k => (
            <div key={k.id} className="ent-grid-9">
              <div>
                <div className="ent-label-4">{k.name}</div>
                <code className="ds-codigo u-text2-xs">{k.key_prefix}...</code>
              </div>
              <span className="u-text2">{(k.scopes||[]).map(s => etiq(t, 'developer.scope', s)).join(', ')}</span>
              <span className="u-text2">{t('pagina_ent.peticiones_hoy', { usadas: k.requests_today || 0, limite: k.rate_limit_per_day })}</span>
              <span className="u-text3">{k.last_used_at ? fmtDateTime(k.last_used_at) : t('pagina_ent.nunca_usado')}</span>
              <Button size="sm" variant="danger" onClick={() => { openConfirmGlobal({ message: t('pagina_ent.revocar_clave'), onConfirm: () => revoke(k.id), danger: true }) }}>{t('pagina_ent.revocar')}</Button>
            </div>
          ))}
        </div>
      )}
      {showCreate && (
        <Modal open title={traducir('enterprise.nueva_api_key_2')} onClose={() => setShowCreate(false)} width={420}>
          <div className="u-stack-14">
            <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="enterprise-page-e16">{t('pagina_ent.nombre')}</label><Input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.name} onChange={e => setForm(f => ({...f, name:e.target.value}))} placeholder={traducir('enterprise.nombre_de_la_clave')} inputClassName="enterprise-page-e17" /></div>
            <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="enterprise-page-e16">{traducir('enterprise.limite_por_hora')}</label><Input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} type="number" value={form.rate_limit_per_hour} onChange={e => setForm(f => ({...f, rate_limit_per_hour:+e.target.value}))} inputClassName="enterprise-page-e17" /></div>
            <div className="u-actions-10">
              <Button variant="secondary" onClick={() => setShowCreate(false)}>{t('pagina_ent.cancelar')}</Button>
              <Button onClick={() => create(form)} disabled={!form.name}>{t('pagina_ent.crear')}</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}
