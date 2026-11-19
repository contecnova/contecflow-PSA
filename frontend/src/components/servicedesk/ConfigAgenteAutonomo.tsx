/**
 * Sección «Agente autónomo» de Configuración (`/settings/sd-agente`, 19-11-2026).
 *
 * Antes era la pestaña «Configuración» de Service desk → Herramientas → Agente
 * (AgenteAutonomoPanel). Encendido, modo sugerir/ejecutar, umbrales, playbooks
 * de serie apagados y «Pasar ahora».
 *
 * Escritura: PUT /sd/autonomous/config, `require_admin`; la sección pide
 * `sd.administrar`. Auditado (`sd_autonomous_agent`, antes y después).
 * Los playbooks, el registro y las propuestas siguen en el módulo.
 */
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Play } from 'lucide-react'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { Button, GrupoDeOpciones, Spinner, Switch } from '../ui'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import { agenteAutonomoApi } from '../../services/api/serviceDeskMercado'
import type { ConfigDelAgente } from '../../services/api/serviceDeskMercado'
import './sdMercado.css'

export default function ConfigAgenteAutonomo() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({ queryKey: ['sdm-agente-config'], queryFn: agenteAutonomoApi.config })
  const [form, setForm] = useState<ConfigDelAgente | null>(null)
  useEffect(() => { if (data) setForm(data) }, [data])
  const guardar = useMutation({
    mutationFn: (f: ConfigDelAgente) => agenteAutonomoApi.guardarConfig({
      enabled: f.enabled, mode: f.mode, resolve_threshold: f.resolve_threshold, suggest_threshold: f.suggest_threshold,
      disabled_playbooks: f.disabled_playbooks,
    }),
    onSuccess: d => { setForm(d); qc.invalidateQueries({ queryKey: ['sdm-agente-config'] }); qc.invalidateQueries({ queryKey: ['sdm-agente-playbooks'] }); toast.success(t('sd_mercado.guardado')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const pasar = useMutation({
    mutationFn: agenteAutonomoApi.pasarAhora,
    onSuccess: r => { toast.success(t('sd_mercado.pasada_hecha', { n: r.evaluated ?? 0 })); qc.invalidateQueries({ queryKey: ['sdm-agente-log'] }) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  if (isLoading || !form) return <Spinner />
  const set = (p: Partial<ConfigDelAgente>) => setForm({ ...form, ...p })
  return (
    <div className="u-stack-12">
      <div className="ds-opciones">
        <Switch checked={!!form.enabled} onChange={v => set({ enabled: v })} label={t('sd_mercado.agente_encendido')} />
      </div>
      <GrupoDeOpciones name="sdm-modo" leyenda={t('sd_mercado.modo_titulo')} valor={form.mode}
        onChange={m => set({ mode: m as typeof form.mode })}
        opciones={form.modes.map(m => ({ valor: m, titulo: etiquetaCodigo(t, 'sd_mercado.modo', m), ayuda: t(`sd_mercado.modo_desc_${m}`) }))} />
      <div className="sdm-form">
        <label className="sdm-field"><span>{t('sd_mercado.umbral_resolver')}</span>
          <input className="ds-input" type="number" min={0} max={1} step={0.05} value={form.resolve_threshold ?? ''}
            onChange={e => set({ resolve_threshold: e.target.value === '' ? null : Number(e.target.value) })} /></label>
        <label className="sdm-field"><span>{t('sd_mercado.umbral_sugerir')}</span>
          <input className="ds-input" type="number" min={0} max={1} step={0.05} value={form.suggest_threshold ?? ''}
            onChange={e => set({ suggest_threshold: e.target.value === '' ? null : Number(e.target.value) })} /></label>
      </div>
      <GrupoDeOpciones tipo="checkbox" leyenda={t('sd_mercado.de_serie_titulo')}
        valor={form.builtin_playbooks.filter(id => !form.disabled_playbooks.includes(id))}
        onChange={activos => set({ disabled_playbooks: [...form.disabled_playbooks.filter(x => !form.builtin_playbooks.includes(x)), ...form.builtin_playbooks.filter(id => !activos.includes(id))] })}
        opciones={form.builtin_playbooks.map(id => ({ valor: id, titulo: etiquetaCodigo(t, 'sd_mercado.pb', id) }))} />
      <div className="u-actions-8">
        <Button variant="secondary" icon={<Play size={14} />} onClick={() => pasar.mutate()} loading={pasar.isPending} disabled={!data?.enabled}>{t('sd_mercado.pasar_ahora')}</Button>
        <Button onClick={() => guardar.mutate(form)} loading={guardar.isPending}>{t('common.save')}</Button>
      </div>
    </div>
  )
}
