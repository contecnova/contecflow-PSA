// Formulario de alta/edicion de un elemento de la CMDB. 23-11-2026: troceado de CMDBPage sin cambio de comportamiento.
import { useState } from 'react'
import { extractErr } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { cmdbApi } from '../services/api'
import { Button, Modal, Select, useErroresDeCampo, Input, Textarea } from '../components/ui'
import { IconoCi } from '../components/cmdb/iconosCi'
import DateInput from '../components/ui/DateInput'
import { useAppT } from '../i18n/AppLangContext'
import { STALE_DEFAULT_MS } from '../constants/timings'
import { cmdbMercadoApi } from '../services/api/serviceDeskMercado'
import { type CI, CI_TYPES, CRITICALITIES, ENV_COLOR, STATUS_COLOR, useCamposDeClase, useEtiqueta, useEtiquetaDeCampo } from './CMDBComun'

export function CMDBItemForm({ item, onClose }: { item: CI | null; onClose: () => void }) {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const isEdit = !!item?.id
  const [form, setForm] = useState<Record<string, string>>({
    name:        item?.name        || '',
    ci_type:     item?.ci_type     || 'server',
    status:      item?.status      || 'operational',
    environment: item?.environment || 'production',
    criticality: item?.criticality || 'medium',
    description: item?.description || '',
    ip_address:  item?.ip_address  || '',
    hostname:    item?.hostname    || '',
    version:     item?.version     || '',
    // Clase propia de la empresa (mejoras de mercado 16-11-2026): su clase base va en ci_type.
    ci_class:    (item as { ci_class?: string | null } | null)?.ci_class || '',
  })
  const { data: propias } = useQuery({ queryKey: ['sdm-ci-classes'], queryFn: cmdbMercadoApi.clases, staleTime: STALE_DEFAULT_MS })
  const [attrs, setAttrs] = useState<Record<string, string>>(
    Object.fromEntries(Object.entries(item?.attributes || {}).map(([k, v]) => [k, String(v ?? '')])))
  const set = (k: string) => (v: string) => { camposForm.limpiar(k); setForm(f => ({ ...f, [k]: v })) }
  const { data: deClase } = useCamposDeClase()
  const etiquetaDeCampo = useEtiquetaDeCampo()
  const campos = deClase?.clases[form.ci_type] ?? []

  const camposForm = useErroresDeCampo()
  const msgForm = (k: string) => camposForm.de(k) ? <div className="u-field-error">{camposForm.de(k)}</div> : null
  const { mutate, isPending } = useMutation({
    onMutate: () => camposForm.limpiar(),
    mutationFn: (): Promise<unknown> => {
      // Se envían solo los atributos de la clase elegida y con valor: cambiar
      // de clase no arrastra los de la anterior.
      const propios = Object.fromEntries(campos.map(c => [c.key, attrs[c.key]]).filter(([, v]) => v))
      const vacio = (v: string) => v.trim() || null
      const d = { ...form, ci_class: form.ci_class || null, description: vacio(form.description), ip_address: vacio(form.ip_address),
        hostname: vacio(form.hostname), version: vacio(form.version), attributes: propios }
      return isEdit ? cmdbApi.sdUpdate(item.id, d) : cmdbApi.sdCreate(d)
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['cmdb-items'] }); onClose() },
    onError: (e: unknown) => { if (!camposForm.recoger(e)) toast.error(extractErr(e, t('cmdb.save_error'))) },
  })

  const etiqueta = useEtiqueta()
  const id = (k: string) => `ci-form-${k}`
  return (
    <Modal open onClose={onClose} title={isEdit ? t('cmdb.edit_ci') : t('cmdb.new_ci')}>
      <div className="u-stack-14">
        <div className="cmdb-grid cmdb-grid--wide">
          <div>
            <Input label={t('cmdb.ci_name')} id={id('name')} value={form.name} onChange={e => set('name')(e.target.value)} />{msgForm('name')}
          </div>
          <div>
            <Select label={t('cmdb.ci_type')} placeholder={false} id={id('type')} value={form.ci_class ? `clase:${form.ci_class}` : form.ci_type}
              onChange={e => {
                const v = e.target.value
                const propia = v.startsWith('clase:') ? (propias?.classes ?? []).find(c => c.key === v.slice(6)) : null
                setForm(f => propia ? { ...f, ci_class: propia.key, ci_type: propia.base_type } : { ...f, ci_class: '', ci_type: v })
              }}>
              {CI_TYPES.map(c => <option key={c} value={c}>{etiqueta('type_', c)}</option>)}
              {(propias?.classes ?? []).filter(c => c.is_active || c.key === form.ci_class).map(c => <option key={c.id} value={`clase:${c.key}`}>{c.label}</option>)}
            </Select>{msgForm('ci_type')}
          </div>
        </div>
        <div className="cmdb-grid">
          <div>
            <Select label={t('cmdb.status')} placeholder={false} id={id('status')} value={form.status} onChange={e => set('status')(e.target.value)}>
              {Object.keys(STATUS_COLOR).map(v => <option key={v} value={v}>{etiqueta('st_', v)}</option>)}
            </Select>{msgForm('status')}
          </div>
          <div>
            <Select label={t('cmdb.environment')} placeholder={false} id={id('env')} value={form.environment} onChange={e => set('environment')(e.target.value)}>
              {Object.keys(ENV_COLOR).map(v => <option key={v} value={v}>{etiqueta('env_', v)}</option>)}
            </Select>{msgForm('environment')}
          </div>
          <div>
            <Select label={t('cmdb.criticality')} placeholder={false} id={id('crit')} value={form.criticality} onChange={e => set('criticality')(e.target.value)}>
              {CRITICALITIES.map(v => <option key={v} value={v}>{etiqueta('crit_', v)}</option>)}
            </Select>{msgForm('criticality')}
          </div>
        </div>
        <div className="cmdb-grid">
          {(['hostname','ip_address','version'] as const).map(k => (
            <div key={k}>
              <Input label={t(`cmdb.f_${k}`)} id={id(k)} value={form[k]} onChange={e => set(k)(e.target.value)} />{msgForm(k)}
            </div>
          ))}
        </div>
        <div>
          <div className="cmdb-section-title cmdb-section-title--mb10">
            <IconoCi tipo={form.ci_type} size={14} /> {t('cmdb.class_fields', { type: etiqueta('type_', form.ci_type) })}
          </div>
          <div className="cmdb-grid cmdb-grid--wide cmdb-grid--gap10">
            {campos.map(c => (
              <div key={c.key}>
                <label id={`${id(c.key)}-et`} className="cmdb-label" htmlFor={id(c.key)}>{etiquetaDeCampo(c)}</label>
                {c.field_type === 'date'
                  ? <DateInput id={id(c.key)} aria-labelledby={`${id(c.key)}-et`} className="cmdb-input" value={attrs[c.key] ?? ''}
                    onChange={e => setAttrs(a => ({ ...a, [c.key]: e.target.value }))} />
                  : <Input id={id(c.key)} aria-labelledby={`${id(c.key)}-et`} type={c.field_type || 'text'} value={attrs[c.key] ?? ''}
                    onChange={e => setAttrs(a => ({ ...a, [c.key]: e.target.value }))} />}
              </div>
            ))}
          </div>
        </div>
        <div>
          <Textarea label={t('cmdb.descripcion')} id={id('descr')} value={form.description} onChange={e => set('description')(e.target.value)} />{msgForm('description')}
        </div>
        <div className="cmdb-form-actions">
          <Button variant="secondary" onClick={onClose}>{t('cmdb.cancel')}</Button>
          <Button onClick={() => mutate()} disabled={isPending || !form.name.trim()} loading={isPending}>
            {isEdit ? t('cmdb.save') : t('cmdb.create')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
