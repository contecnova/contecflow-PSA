/**
 * Página de estado pública: componentes, su estado y los incidentes que ven
 * los clientes sin entrar. Existía solo en el servidor.
 */
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { Button, EmptyState, Modal, Spinner } from '../../components/ui'
import { COLOR } from '../../constants/theme'
import { sdStatusPageApi } from '../../services/api'

type Componente = { id: string; name: string; description?: string | null; group_name?: string | null; status: string; is_public: boolean; sort_order?: number }
const ESTADOS = ['operational', 'degraded_performance', 'partial_outage', 'major_outage', 'maintenance']
const COLOR_ESTADO: Record<string, string> = {
  operational: COLOR.success, degraded_performance: COLOR.warning, partial_outage: 'var(--orange)',
  major_outage: COLOR.danger, maintenance: 'var(--accent)',
}
const IS: CSSProperties = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8,
  padding: '9px 13px', color: 'var(--text-1)', fontSize: 'var(--text-base)', outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const LS: CSSProperties = { fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--text-2)', display: 'block', marginBottom: 5,
  textTransform: 'uppercase', letterSpacing: '0.06em' }

export default function ConfigPaginaDeEstado() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [nuevo, setNuevo] = useState(false)
  const [declarando, setDeclarando] = useState<Componente | null>(null)
  const { data: enlace } = useQuery<{ url?: string | null; embed?: string }>({
    queryKey: ['sd-status-link'], queryFn: () => sdStatusPageApi.link().then(r => r.data as { url?: string | null; embed?: string }),
  })
  const { data: componentes = [], isLoading } = useQuery<Componente[]>({
    queryKey: ['sd-status-components'], queryFn: () => sdStatusPageApi.components().then(r => r.data as Componente[]),
  })
  const refrescar = () => qc.invalidateQueries({ queryKey: ['sd-status-components'] })
  const err = (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  const crear = useMutation({ mutationFn: (d: unknown) => sdStatusPageApi.createComponent(d), onSuccess: () => { refrescar(); setNuevo(false) }, onError: err })
  const cambiar = useMutation({ mutationFn: ({ c, ...d }: { c: Componente } & Record<string, unknown>) =>
    sdStatusPageApi.updateComponent(c.id, { name: c.name, description: c.description, group_name: c.group_name, sort_order: c.sort_order ?? 0, status: c.status, is_public: c.is_public, ...d }),
    onSuccess: refrescar, onError: err })
  const borrar = useMutation({ mutationFn: (id: string) => sdStatusPageApi.deleteComponent(id), onSuccess: refrescar, onError: err })
  const declarar = useMutation({ mutationFn: ({ id, ...d }: Record<string, unknown>) => sdStatusPageApi.declare(String(id), d),
    onSuccess: () => { refrescar(); setDeclarando(null) }, onError: err })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-3)', maxWidth: 720 }}>{t('sd_cfg.sp_intro')}</div>
      {enlace?.url && (
        <div className="ds-card" style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 8 }}>
          <span style={LS}>{t('sd_cfg.sp_public_url')}</span>
          <a href={enlace.url} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent)', wordBreak: 'break-all' }}>{enlace.url}</a>
          <span style={LS}>{t('sd_cfg.sp_embed')}</span>
          <code style={{ fontSize: 'var(--text-xs)', wordBreak: 'break-all', color: 'var(--text-2)' }}>{enlace.embed}</code>
        </div>
      )}
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}><Button onClick={() => setNuevo(true)}>+ {t('sd_cfg.sp_new')}</Button></div>
      {isLoading ? <Spinner /> : componentes.length === 0 ? <EmptyState icon="🟢" title={t('sd_cfg.sp_empty')} description={t('sd_cfg.sp_intro')} /> : (
        <div className="ds-card" style={{ padding: 0, overflow: 'hidden' }}>
          {componentes.map((c, i) => (
            <div key={c.id} style={{ display: 'flex', gap: 10, alignItems: 'center', padding: '10px 14px', borderTop: i ? '1px solid var(--surface-4)' : 'none', flexWrap: 'wrap' }}>
              <span aria-hidden style={{ width: 10, height: 10, borderRadius: 999, background: COLOR_ESTADO[c.status] ?? 'var(--text-3)' }} />
              <strong style={{ flex: '1 1 160px' }}>{c.name}</strong>
              <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{c.group_name}</span>
              <select aria-label={c.name} value={c.status} onChange={e => cambiar.mutate({ c, status: e.target.value })} style={{ ...IS, width: 200 }}>
                {ESTADOS.map(s => <option key={s} value={s}>{t(`sd_cfg.sp_st_${s}`)}</option>)}
              </select>
              <Button variant="secondary" onClick={() => setDeclarando(c)}>{t('sd_cfg.sp_declare')}</Button>
              <Button variant="secondary" onClick={() => openConfirmGlobal({ message: t('sd_cfg.chg_delete_confirm'), onConfirm: () => borrar.mutate(c.id), danger: true })}>
                <span style={{ color: COLOR.danger }}>{t('common.delete')}</span></Button>
            </div>
          ))}
        </div>
      )}
      {nuevo && (
        <Modal open title={t('sd_cfg.sp_new')} onClose={() => setNuevo(false)}>
          <FormComponente pendiente={crear.isPending} onCancelar={() => setNuevo(false)} onGuardar={d => crear.mutate(d)} />
        </Modal>
      )}
      {declarando && (
        <Modal open title={`${t('sd_cfg.sp_declare')} · ${declarando.name}`} onClose={() => setDeclarando(null)}>
          <FormIncidente pendiente={declarar.isPending} onCancelar={() => setDeclarando(null)}
            onGuardar={d => declarar.mutate({ id: declarando.id, ...d })} />
        </Modal>
      )}
    </div>
  )
}

function FormComponente({ pendiente, onCancelar, onGuardar }: { pendiente: boolean; onCancelar: () => void; onGuardar: (d: Record<string, unknown>) => void }) {
  const t = useAppT()
  const [f, setF] = useState({ name: '', group_name: '', description: '', is_public: true })
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 10 }}>
        <div><label style={LS} htmlFor="sp-name">{t('sd_cfg.chg_name')} *</label><input id="sp-name" aria-label={t('sd_cfg.chg_name')} value={f.name} onChange={e => setF({ ...f, name: e.target.value })} style={IS} /></div>
        <div><label style={LS} htmlFor="sp-group">{t('sd_cfg.sp_group')}</label><input id="sp-group" aria-label={t('sd_cfg.sp_group')} value={f.group_name} onChange={e => setF({ ...f, group_name: e.target.value })} style={IS} /></div>
      </div>
      <label style={{ display: 'flex', gap: 8, alignItems: 'center', cursor: 'pointer' }}>
        <input type="checkbox" aria-label={t('sd_cfg.sp_public')} checked={f.is_public} onChange={e => setF({ ...f, is_public: e.target.checked })} />{t('sd_cfg.sp_public')}
      </label>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
        <Button variant="secondary" onClick={onCancelar}>{t('common.cancel')}</Button>
        <Button disabled={!f.name.trim() || pendiente} loading={pendiente}
          onClick={() => onGuardar({ name: f.name.trim(), group_name: f.group_name || null, description: f.description || null, is_public: f.is_public })}>{t('common.save')}</Button>
      </div>
    </div>
  )
}

function FormIncidente({ pendiente, onCancelar, onGuardar }: { pendiente: boolean; onCancelar: () => void; onGuardar: (d: Record<string, unknown>) => void }) {
  const t = useAppT()
  const [titulo, setTitulo] = useState('')
  const [impacto, setImpacto] = useState('partial_outage')
  const [mensaje, setMensaje] = useState('')
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div><label style={LS} htmlFor="sp-title">{t('sd_cfg.sp_incident_title')} *</label><input id="sp-title" aria-label={t('sd_cfg.sp_incident_title')} value={titulo} onChange={e => setTitulo(e.target.value)} style={IS} /></div>
      <div><label style={LS} htmlFor="sp-impact">{t('sd_cfg.chg_status')}</label>
        <select id="sp-impact" aria-label={t('sd_cfg.chg_status')} value={impacto} onChange={e => setImpacto(e.target.value)} style={IS}>
          {ESTADOS.filter(s => s !== 'operational').map(s => <option key={s} value={s}>{t(`sd_cfg.sp_st_${s}`)}</option>)}
        </select></div>
      <div><label style={LS} htmlFor="sp-msg">{t('sd_cfg.sp_message')}</label><textarea id="sp-msg" aria-label={t('sd_cfg.sp_message')} rows={3} value={mensaje} onChange={e => setMensaje(e.target.value)} style={{ ...IS, resize: 'vertical' }} /></div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
        <Button variant="secondary" onClick={onCancelar}>{t('common.cancel')}</Button>
        <Button disabled={!titulo.trim() || pendiente} loading={pendiente}
          onClick={() => onGuardar({ title: titulo.trim(), impact: impacto, update_message: mensaje || null })}>{t('sd_cfg.sp_declare')}</Button>
      </div>
    </div>
  )
}
