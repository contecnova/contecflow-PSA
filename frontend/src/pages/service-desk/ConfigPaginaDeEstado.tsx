/**
 * Página de estado pública: componentes, su estado y los incidentes que ven
 * los clientes sin entrar. Existía solo en el servidor.
 */
import { type CSSProperties, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { Button, EmptyState, Modal, Spinner } from '../../components/ui'
import { COLOR } from '../../constants/theme'
import { sdStatusPageApi } from '../../services/api'
import type { SdComponenteDeEstado } from '../../services/api/tipos-sd'
import './ConfigPaginaDeEstado.css'

type Componente = SdComponenteDeEstado
const ESTADOS = ['operational', 'degraded_performance', 'partial_outage', 'major_outage', 'maintenance']
const COLOR_ESTADO: Record<string, string> = {
  operational: COLOR.success, degraded_performance: COLOR.warning, partial_outage: 'var(--orange)',
  major_outage: COLOR.danger, maintenance: 'var(--accent)',
}

export default function ConfigPaginaDeEstado() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [nuevo, setNuevo] = useState(false)
  const [declarando, setDeclarando] = useState<Componente | null>(null)
  const { data: enlace } = useQuery({
    queryKey: ['sd-status-link'], queryFn: () => sdStatusPageApi.link().then(r => r.data),
  })
  const { data: componentes = [], isLoading } = useQuery({
    queryKey: ['sd-status-components'], queryFn: () => sdStatusPageApi.components().then(r => r.data),
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
    <div className="copadees-stack-1">
      <div className="copadees-box-1">{t('sd_cfg.sp_intro')}</div>
      {enlace?.url && (
        <div className="ds-card copadees-stack-2">
          <span className="copadees-ls">{t('sd_cfg.sp_public_url')}</span>
          <a href={enlace.url} target="_blank" rel="noopener noreferrer" className="copadees-txt-1">{enlace.url}</a>
          <span className="copadees-ls">{t('sd_cfg.sp_embed')}</span>
          <code className="copadees-txt-2">{enlace.embed}</code>
        </div>
      )}
      <div className="u-row-end"><Button onClick={() => setNuevo(true)}>+ {t('sd_cfg.sp_new')}</Button></div>
      {isLoading ? <Spinner /> : componentes.length === 0 ? <EmptyState icon="🟢" title={t('sd_cfg.sp_empty')} description={t('sd_cfg.sp_intro')} /> : (
        <div className="ds-card copadees-box-2">
          {componentes.map((c, i) => (
            <div className={`copadees-row-2 ${i ? 'config-pagina-de-estado-m1' : 'config-pagina-de-estado-m2'}`} key={c.id}>
              <span className="copadees-box-4 config-pagina-de-estado-e3" aria-hidden style={{ '--config-pagina-de-estado-background': COLOR_ESTADO[c.status] ?? 'var(--text-3)' } as CSSProperties} />
              <strong className="copadees-box-3">{c.name}</strong>
              <span className="u-text3-xs">{c.group_name}</span>
              <select aria-label={c.name} value={c.status} onChange={e => cambiar.mutate({ c, status: e.target.value })} className="copadees-is2">
                {ESTADOS.map(s => <option key={s} value={s}>{t(`sd_cfg.sp_st_${s}`)}</option>)}
              </select>
              <Button variant="secondary" onClick={() => setDeclarando(c)}>{t('sd_cfg.sp_declare')}</Button>
              <Button variant="secondary" onClick={() => openConfirmGlobal({ message: t('sd_cfg.chg_delete_confirm'), onConfirm: () => borrar.mutate(c.id), danger: true })}>
                <span className="config-pagina-de-estado-e4" style={{ '--config-pagina-de-estado-color': COLOR.danger } as CSSProperties}>{t('common.delete')}</span></Button>
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
    <div className="u-stack-12">
      <div className="copadees-grid-1">
        <div><label className="copadees-ls" htmlFor="sp-name">{t('sd_cfg.chg_name')} *</label><input id="sp-name" aria-label={t('sd_cfg.chg_name')} value={f.name} onChange={e => setF({ ...f, name: e.target.value })} className="copadees-is" /></div>
        <div><label className="copadees-ls" htmlFor="sp-group">{t('sd_cfg.sp_group')}</label><input id="sp-group" aria-label={t('sd_cfg.sp_group')} value={f.group_name} onChange={e => setF({ ...f, group_name: e.target.value })} className="copadees-is" /></div>
      </div>
      <label className="copadees-row-1">
        <input type="checkbox" aria-label={t('sd_cfg.sp_public')} checked={f.is_public} onChange={e => setF({ ...f, is_public: e.target.checked })} />{t('sd_cfg.sp_public')}
      </label>
      <div className="u-actions-10">
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
    <div className="u-stack-12">
      <div><label className="copadees-ls" htmlFor="sp-title">{t('sd_cfg.sp_incident_title')} *</label><input id="sp-title" aria-label={t('sd_cfg.sp_incident_title')} value={titulo} onChange={e => setTitulo(e.target.value)} className="copadees-is" /></div>
      <div><label className="copadees-ls" htmlFor="sp-impact">{t('sd_cfg.chg_status')}</label>
        <select id="sp-impact" aria-label={t('sd_cfg.chg_status')} value={impacto} onChange={e => setImpacto(e.target.value)} className="copadees-is">
          {ESTADOS.filter(s => s !== 'operational').map(s => <option key={s} value={s}>{t(`sd_cfg.sp_st_${s}`)}</option>)}
        </select></div>
      <div><label className="copadees-ls" htmlFor="sp-msg">{t('sd_cfg.sp_message')}</label><textarea id="sp-msg" aria-label={t('sd_cfg.sp_message')} rows={3} value={mensaje} onChange={e => setMensaje(e.target.value)} className="copadees-is3" /></div>
      <div className="u-actions-10">
        <Button variant="secondary" onClick={onCancelar}>{t('common.cancel')}</Button>
        <Button disabled={!titulo.trim() || pendiente} loading={pendiente}
          onClick={() => onGuardar({ title: titulo.trim(), impact: impacto, update_message: mensaje || null })}>{t('sd_cfg.sp_declare')}</Button>
      </div>
    </div>
  )
}
