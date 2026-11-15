/**
 * Simulador: la política (tal como está en el editor, aunque no esté guardada)
 * contra las últimas N entidades del dominio o un rango de fechas. Sin efectos.
 */
import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Play } from 'lucide-react'
import { politicasApi } from '../../services/api'
import type { DocumentoDePolitica, ExplicacionDePolitica, Huella, Simulacion } from '../../services/api/tipos-politicas'
import { Button, EmptyState, KpiCard, Spinner } from '../ui'
import DateInput from '../ui/DateInput'
import { extractErr } from '../../utils/helpers'
import { textoDeValor, useTextos } from './comun'

export default function Simulador({ documento }: { documento: DocumentoDePolitica & { id?: string; familia_id?: string } }) {
  const { t } = useTextos()
  const [modo, setModo] = useState<'ultimos' | 'rango'>('ultimos')
  const [ultimos, setUltimos] = useState<number | ''>('')
  const [desde, setDesde] = useState('')
  const [hasta, setHasta] = useState('')
  const [soloCambios, setSoloCambios] = useState(true)
  const sim = useMutation({
    mutationFn: () => politicasApi.simular({
      documento, ...(modo === 'ultimos' ? (ultimos ? { ultimos: Number(ultimos) } : {}) : { desde: desde || undefined, hasta: hasta || undefined }),
    }),
  })
  return (
    <div className="u-stack-14">
      <p className="pol-ayuda">{t('pol.simulador_ayuda')}</p>
      <div className="pol-fila" role="group" aria-label={t('pol.que_simular')}>
        <label className="pol-chip"><input type="radio" name="modo-sim" checked={modo === 'ultimos'} onChange={() => setModo('ultimos')} />{t('pol.ultimos')}</label>
        {modo === 'ultimos' && <input type="number" min={1} className="pol-campo pol-campo--corto" aria-label={t('pol.cuantos')}
          placeholder={t('pol.por_defecto')} value={ultimos} onChange={e => setUltimos(e.target.value ? Number(e.target.value) : '')} />}
        <label className="pol-chip"><input type="radio" name="modo-sim" checked={modo === 'rango'} onChange={() => setModo('rango')} />{t('pol.rango')}</label>
        {modo === 'rango' && <>
          <DateInput className="pol-campo" aria-label={t('pol.desde')} value={desde} onChange={e => setDesde(e.target.value)} />
          <DateInput className="pol-campo" aria-label={t('pol.hasta')} value={hasta} onChange={e => setHasta(e.target.value)} />
        </>}
        <Button icon={<Play size={14} />} onClick={() => sim.mutate()} loading={sim.isPending}>{t('pol.simular')}</Button>
      </div>
      {sim.isPending && <Spinner label={t('pol.simulando')} />}
      {sim.isError && <div role="alert" className="pol-error">{extractErr(sim.error, t('pol.error_simular'))}</div>}
      {sim.data && <Resultados s={sim.data} soloCambios={soloCambios} setSoloCambios={setSoloCambios} />}
    </div>
  )
}

function Resultados({ s, soloCambios, setSoloCambios }: { s: Simulacion; soloCambios: boolean; setSoloCambios: (v: boolean) => void }) {
  const { t } = useTextos()
  const c = s.resumen_de_cambios
  const items = soloCambios ? s.items.filter(i => i.cambia) : s.items
  return (
    <div aria-live="polite">
      <div className="pol-kpis">
        <KpiCard label={t('pol.evaluadas')} value={s.evaluadas} sub={s.evaluadas >= s.tope ? t('pol.tope_alcanzado', { n: s.tope }) : undefined} />
        <KpiCard label={t('pol.cambian')} value={s.cambian} accent />
        <KpiCard label={t('pol.mas_aprobacion')} value={c.mas_aprobacion} warning={c.mas_aprobacion > 0} />
        <KpiCard label={t('pol.menos_aprobacion')} value={c.menos_aprobacion} />
        <KpiCard label={t('pol.nuevos_bloqueos')} value={c.nuevos_bloqueos} danger={c.nuevos_bloqueos > 0} />
        <KpiCard label={t('pol.auto_aprobadas')} value={c.auto_aprobadas} />
      </div>
      <label className="pol-chip"><input type="checkbox" checked={soloCambios} onChange={e => setSoloCambios(e.target.checked)} />{t('pol.solo_cambios')}</label>
      {items.length === 0 ? <EmptyState title={s.evaluadas ? t('pol.nada_cambia') : t('pol.sin_historicos')} /> : (
        <div role="table" aria-label={t('pol.resultados_simulacion')} className="pol-mt">
          <div role="row" className="pol-diff pol-ayuda">
            <span role="columnheader">{t('pol.entidad')}</span><span role="columnheader">{t('pol.hoy')}</span><span role="columnheader">{t('pol.con_esta_politica')}</span>
          </div>
          {items.map(i => (
            <div key={i.entidad_id} role="row" className={`pol-diff${i.cambia ? ' pol-diff--cambia' : ''}`}>
              <span role="cell">{i.resumen} <span className="pol-ayuda">{i.fecha}</span>
                {i.explicacion && <Explicacion politicas={i.explicacion} />}</span>
              <span role="cell"><HuellaVisible h={i.antes} /></span>
              <span role="cell"><HuellaVisible h={i.despues} /></span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function HuellaVisible({ h }: { h: Huella }) {
  const { t } = useTextos()
  return (
    <span className="pol-fila">
      <span className={`pol-chip pol-chip--${h.decision}`}>{t(`pol.decision_${h.decision}`)}</span>
      {(h.niveles + h.pasos) > 0 && <span className="pol-chip">{t('pol.n_niveles', { n: h.niveles + h.pasos })}</span>}
      {h.avisos > 0 && <span className="pol-chip">{t('pol.n_avisos', { n: h.avisos })}</span>}
      {h.requisitos.map(r => <span key={r} className="pol-chip">{t(`pol.res_${r}`)}</span>)}
      {h.etiquetas.map(e => <span key={e} className="pol-chip">#{e}</span>)}
    </span>
  )
}

/** Por qué: cada política que aplicó, sus reglas y la traza de cada condición. */
export function Explicacion({ politicas }: { politicas: ExplicacionDePolitica[] }) {
  const { t, pais } = useTextos()
  const aplicadas = politicas.filter(p => p.aplica && p.reglas.some(r => r.cumple !== false))
  if (!aplicadas.length) return null
  return (
    <details>
      <summary className="pol-ayuda">{t('pol.por_que')}</summary>
      {aplicadas.map(p => (
        <div key={p.politica_id}>
          <strong>{p.politica}</strong> <span className="pol-ayuda">v{p.version}</span>
          {p.reglas.filter(r => r.cumple !== false).map(r => (
            <ul key={r.regla_id} className="pol-traza" aria-label={r.regla}>
              <li><em>{r.regla}</em>{r.exceso?.exceso_pct !== undefined && ` · ${t('pol.exceso_pct', { pct: r.exceso.exceso_pct })}`}</li>
              {r.traza.map((x, k) => (
                <li key={k} data-cumple={String(x.cumple)}>
                  {x.etiqueta} {t(`pol.op_${x.operador}`)} {textoDeValor(x.esperado, pais)} → {textoDeValor(x.convertido ?? x.real, pais)}
                  {x.nota && ` (${x.nota})`}
                </li>
              ))}
            </ul>
          ))}
        </div>
      ))}
    </details>
  )
}
