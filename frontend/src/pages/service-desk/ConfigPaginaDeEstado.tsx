/**
 * Página de estado pública: componentes, su estado y los incidentes que ven
 * los clientes sin entrar. Existía solo en el servidor.
 *
 * 16-11-2026 (pasada de diseño): acción principal en la barra con icono Plus,
 * vacío con EmptyState e icono lucide (antes emoji), borrar con Button ghost,
 * campos con `ds-input`, punto de estado y textos sin estilos en línea.
 */
import { type CSSProperties, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Megaphone, MonitorCheck, Plus, Trash2 } from 'lucide-react'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { Button, Checkbox, EmptyState, Modal, Select, Spinner } from '../../components/ui'
import { sdStatusPageApi } from '../../services/api'
import type { SdComponenteDeEstado } from '../../services/api/tipos-sd'
import './ConfigPaginaDeEstado.css'

type Componente = SdComponenteDeEstado
const ESTADOS = ['operational', 'degraded_performance', 'partial_outage', 'major_outage', 'maintenance']
const COLOR_ESTADO: Record<string, string> = {
  operational: 'var(--success)', degraded_performance: 'var(--warning)', partial_outage: 'var(--orange)',
  major_outage: 'var(--danger)', maintenance: 'var(--accent)',
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
      <div className="copadees-head">
        <div className="copadees-intro">{t('sd_cfg.sp_intro')}</div>
        <Button icon={<Plus size={14} />} onClick={() => setNuevo(true)}>{t('sd_cfg.sp_new')}</Button>
      </div>
      {enlace?.url && (
        <div className="ds-card">
          <span className="copadees-ls">{t('sd_cfg.sp_public_url')}</span>
          <a href={enlace.url} target="_blank" rel="noopener noreferrer" className="copadees-enlace">{enlace.url}</a>
          <span className="copadees-ls">{t('sd_cfg.sp_embed')}</span>
          <code className="copadees-codigo">{enlace.embed}</code>
        </div>
      )}
      {isLoading ? <Spinner /> : componentes.length === 0 ? <EmptyState icon={<MonitorCheck size={28} />} title={t('sd_cfg.sp_empty')} description={t('sd_cfg.cfg_sp_empty_desc')} /> : (
        <div className="ds-card ds-card--plano">
          {componentes.map(c => (
            <div className="copadees-fila" key={c.id}>
              <span className="copadees-punto" aria-hidden style={{ '--copadees-color': COLOR_ESTADO[c.status] ?? 'var(--text-3)' } as CSSProperties} />
              <strong className="copadees-nombre">{c.name}</strong>
              {c.group_name && <span className="u-text2-xs">{c.group_name}</span>}
              <Select suelto placeholder={false} aria-label={c.name} value={c.status} onChange={e => cambiar.mutate({ c, status: e.target.value })} className="copadees-estado">
                {ESTADOS.map(s => <option key={s} value={s}>{t(`sd_cfg.sp_st_${s}`)}</option>)}
              </Select>
              <Button size="xs" variant="secondary" icon={<Megaphone size={12} />} onClick={() => setDeclarando(c)}>{t('sd_cfg.sp_declare')}</Button>
              <Button size="xs" variant="ghost" icon={<Trash2 size={12} />} onClick={() => openConfirmGlobal({ message: t('sd_cfg.chg_delete_confirm'), onConfirm: () => borrar.mutate(c.id), danger: true })}>
                {t('common.delete')}</Button>
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
        <div><label className="copadees-ls" htmlFor="sp-name">{t('sd_cfg.chg_name')} *</label><input id="sp-name" aria-label={t('sd_cfg.chg_name')} value={f.name} onChange={e => setF({ ...f, name: e.target.value })} className="ds-input" /></div>
        <div><label className="copadees-ls" htmlFor="sp-group">{t('sd_cfg.sp_group')}</label><input id="sp-group" aria-label={t('sd_cfg.sp_group')} value={f.group_name} onChange={e => setF({ ...f, group_name: e.target.value })} className="ds-input" /></div>
      </div>
      <Checkbox className="copadees-check" aria-label={t('sd_cfg.sp_public')} checked={!!f.is_public} onChange={v => setF({ ...f, is_public: v })} label={t('sd_cfg.sp_public')} />
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
      <div><label className="copadees-ls" htmlFor="sp-title">{t('sd_cfg.sp_incident_title')} *</label><input id="sp-title" aria-label={t('sd_cfg.sp_incident_title')} value={titulo} onChange={e => setTitulo(e.target.value)} className="ds-input" /></div>
      <div><label className="copadees-ls" htmlFor="sp-impact">{t('sd_cfg.chg_status')}</label>
        <Select suelto placeholder={false} id="sp-impact" aria-label={t('sd_cfg.chg_status')} value={impacto} onChange={e => setImpacto(e.target.value)}>
          {ESTADOS.filter(s => s !== 'operational').map(s => <option key={s} value={s}>{t(`sd_cfg.sp_st_${s}`)}</option>)}
        </Select></div>
      <div><label className="copadees-ls" htmlFor="sp-msg">{t('sd_cfg.sp_message')}</label><textarea id="sp-msg" aria-label={t('sd_cfg.sp_message')} rows={3} value={mensaje} onChange={e => setMensaje(e.target.value)} className="ds-input copadees-texto" /></div>
      <div className="u-actions-10">
        <Button variant="secondary" onClick={onCancelar}>{t('common.cancel')}</Button>
        <Button disabled={!titulo.trim() || pendiente} loading={pendiente}
          onClick={() => onGuardar({ title: titulo.trim(), impact: impacto, update_message: mensaje || null })}>{t('sd_cfg.sp_declare')}</Button>
      </div>
    </div>
  )
}
