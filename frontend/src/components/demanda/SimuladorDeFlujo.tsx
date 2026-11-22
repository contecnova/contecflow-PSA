/**
 * Simulador del flujo de demanda (22-11-2026): se prueban datos de la ficha y
 * una decisión por fase, y `POST /demand/flows/simulate` devuelve el recorrido
 * (fases saltadas por condición, puertas, final y avisos). No crea nada.
 */
import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Play } from 'lucide-react'
import { Button, Input, Select, StatusBadge } from '../ui'
import { demandaApi, type DefinicionDeFlujo, type SimulacionDeFlujo } from '../../services/api/demanda'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { etiquetaDe, opcionesDe } from './comunes'
import { valorParaGuardar } from './utilDemanda'
import './demanda.css'

export default function SimuladorDeFlujo({ def }: { def: DefinicionDeFlujo }) {
  const t = useAppT()
  const toast = useToast()
  const [datos, setDatos] = useState<Record<string, string>>({})
  const [decisiones, setDecisiones] = useState<Record<string, string>>({})
  const [res, setRes] = useState<SimulacionDeFlujo | null>(null)
  const simular = useMutation({
    mutationFn: () => {
      const data: Record<string, unknown> = {}
      for (const c of def.fields) if ((datos[c.key] ?? '') !== '') data[c.key] = valorParaGuardar(c.type, datos[c.key])
      const dec: Record<string, string> = {}
      for (const [k, v] of Object.entries(decisiones)) if (v) dec[k] = v
      return demandaApi.simular(def, data, dec)
    },
    onSuccess: setRes,
    onError: (e: unknown) => toast.error(extractErr(e, t('demanda.error'))),
  })
  return (
    <div className="dem-editor">
      <p className="plan-muted">{t('demanda.cfg_simulador_ayuda')}</p>
      {def.fields.length > 0 && (
        <div className="dem-bloque">
          <div className="dem-bloque__titulo">{t('demanda.cfg_datos_prueba')}</div>
          <div className="dem-rejilla">
            {def.fields.map(c => c.type === 'select' ? (
              <Select key={c.key} label={c.label.es || c.key} value={datos[c.key] ?? ''} onChange={e => setDatos(d => ({ ...d, [c.key]: e.target.value }))}
                options={(c.options || []).map(o => ({ value: o.value, label: o.label.es || o.value }))} />
            ) : c.type === 'boolean' ? (
              <Select key={c.key} label={c.label.es || c.key} value={datos[c.key] ?? ''} onChange={e => setDatos(d => ({ ...d, [c.key]: e.target.value }))}
                options={[{ value: 'true', label: t('demanda.si') }, { value: 'false', label: t('demanda.no') }]} />
            ) : (
              <Input key={c.key} label={c.label.es || c.key} type={c.type === 'number' || c.type === 'money' ? 'number' : 'text'} value={datos[c.key] ?? ''}
                onChange={e => setDatos(d => ({ ...d, [c.key]: e.target.value }))} />
            ))}
          </div>
        </div>
      )}
      {def.phases.length > 0 && (
        <div className="dem-bloque">
          <div className="dem-bloque__titulo">{t('demanda.cfg_decision_por_fase')}</div>
          <div className="dem-rejilla">
            {def.phases.filter(f => f.kind !== 'gate').map(f => (
              <Select key={f.key} label={f.name.es || f.key} placeholder={t('demanda.cfg_aprobar_por_defecto')} value={decisiones[f.key] ?? ''}
                onChange={e => setDecisiones(d => ({ ...d, [f.key]: e.target.value }))} options={opcionesDe(t, 'dec', f.decisions)} />
            ))}
          </div>
        </div>
      )}
      <div className="dem-acciones"><Button icon={<Play size={13} />} loading={simular.isPending} onClick={() => simular.mutate()}>{t('demanda.cfg_simular')}</Button></div>
      {res && (
        <div className="dem-bloque">
          <div className="dem-bloque__titulo">{t('demanda.cfg_recorrido')}</div>
          {res.errors.length > 0 && <ul className="dem-errores">{res.errors.map((e, i) => <li key={i}><span className="u-mono dem-mono">{e.path}</span> — {etiquetaDe(t, 'err', e.code)}</li>)}</ul>}
          {res.path.map((p, i) => (
            <div key={i} className="dem-sim-paso">
              <span className="u-mono dem-mono">{i + 1}.</span><strong>{p.name || p.phase}</strong>
              <StatusBadge kind={p.skipped ? 'neutral' : 'info'}>{p.skipped ? t('demanda.cfg_saltada') : etiquetaDe(t, 'kind', p.kind)}</StatusBadge>
              {p.decision && <span className="plan-muted">{etiquetaDe(t, 'dec', p.decision)}</span>}
              {p.reasons?.length > 0 && <span className="plan-muted">{p.reasons.join('; ')}</span>}
            </div>
          ))}
          {res.end && <div><StatusBadge kind={res.end.endsWith('approved') ? 'success' : 'danger'}>{etiquetaDe(t, 'fin', res.end.replace('end:', ''))}</StatusBadge></div>}
          {res.warnings?.length > 0 && <ul className="dem-errores">{res.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>}
        </div>
      )}
    </div>
  )
}
