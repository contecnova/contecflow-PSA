/**
 * Costes de licencias y equipos (fase 3): coste por titular y día del periodo,
 * agrupado por titular, proyecto, centro de coste, cliente, recurso o tipo;
 * lo ocioso (comprado sin asignar) aparte; y lo refacturable a clientes con su
 * margen (`ALM_REBILL_MARKUP_PCT`).
 */
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Coins, PackageX, Receipt, Wallet } from 'lucide-react'
import { DataTable, EmptyState, KpiCard, Section, SelectorDePeriodo, Spinner, Tabs, Select } from '../../components/ui'
import type { ColumnaDeTabla } from '../../components/ui'
import { usePeriodo } from '../../hooks/usePeriodo'
import { SIN_HORA, codigoDeErrorDePeriodo } from '../../utils/periodo'
import { useAppT } from '../../i18n/AppLangContext'
import { almApi } from '../../services/api/alm'
import type { Agrupacion, LineaDeCoste } from '../../services/api/alm'
import { fmtCurrency } from '../../utils/helpers'
import { errorAlm, textoDeTitular } from '../../components/alm/almFases'

const AGRUPACIONES: Agrupacion[] = ['holder', 'project', 'cost_center', 'client', 'resource', 'kind']

export default function CostesTab() {
  const t = useAppT()
  // Periodo libre (16-11-2026): antes dos campos de fecha propios (mes en curso por defecto).
  // Coste por día de calendario: sin hora; no es serie, sin agrupación.
  const periodo = usePeriodo({ defecto: 'mes', granularidades: SIN_HORA, prefijo: 'cost_' })
  const [agrupar, setAgrupar] = useState<Agrupacion>('holder')
  const [vista, setVista] = useState('groups')
  const costes = useQuery({
    queryKey: ['alm-costs', periodo.params, agrupar],
    queryFn: () => almApi.costes({ ...periodo.params, group_by: agrupar }),
  })
  const refa = useQuery({
    queryKey: ['alm-costs', 'rebill', periodo.params],
    queryFn: () => almApi.refacturable({ ...periodo.params }),
    enabled: vista === 'rebill',
  })
  const textoDeError = (e: unknown) => {
    const ep = codigoDeErrorDePeriodo(e)
    return ep ? t(`periodo_err.${ep.motivo}`, ep.params) : errorAlm(t, e)
  }
  const r = costes.data
  const moneda = r?.currency
  const nombreDeGrupo = (clave: string, nombre: string | null) => {
    if (nombre) return nombre
    if (clave === 'idle') return t('alm.cost_idle')
    if (clave === 'none') return t('alm.cost_unassigned')
    if (agrupar === 'kind') return t(`alm.cost_kind_${clave}`, clave)
    return clave
  }
  const columnas: ColumnaDeTabla<LineaDeCoste>[] = [
    { key: 'resource_name', label: t('alm.resource') },
    { key: 'kind', label: t('alm.cost_kind'), render: (_v, l) => t(`alm.cost_kind_${l.kind}`, l.kind) },
    { key: 'holder_name', label: t('alm.holder'), render: (_v, l) => l.kind === 'idle' ? t('alm.cost_idle')
      : `${l.holder_name ?? '—'} (${textoDeTitular(t, l.holder_type)})` },
    { key: 'project_name', label: t('alm.charge_project'), render: (_v, l) => l.project_name ?? '—' },
    { key: 'cost_center_name', label: t('alm.charge_cost_center'), render: (_v, l) => l.cost_center_name ?? '—' },
    { key: 'client_name', label: t('alm.charge_client'), render: (_v, l) => l.client_name ?? '—' },
    { key: 'days', label: t('alm.days') },
    { key: 'amount', label: t('alm.amount'), render: (_v, l) => <span className="almf-importe">{fmtCurrency(l.amount, l.currency)}</span> },
  ]
  return (
    <div>
      <div className="almf-filtros">
        <div className="almf-filtro">
          <SelectorDePeriodo {...periodo.selector} sinGranularidad />
        </div>
        <div className="almf-filtro">
          <label className="alm-label" htmlFor="almc-agr">{t('alm.group_by')}</label>
          <Select suelto placeholder={false} id="almc-agr" className="alm-input" value={agrupar} onChange={e => setAgrupar(e.target.value as Agrupacion)}>
            {AGRUPACIONES.map(a => <option key={a} value={a}>{t(`alm.group_${a}`)}</option>)}
          </Select>
        </div>
      </div>
      <p className="alm-hint">{t('alm.costs_hint')}</p>
      {costes.isLoading ? <Spinner /> : costes.isError ? <EmptyState title={textoDeError(costes.error)} /> : r && (
        <>
          <div className="ds-grid-stats almf-kpis">
            <KpiCard icon={<Wallet size={16} />} label={t('alm.cost_total')} value={fmtCurrency(r.total, moneda)} accent />
            <KpiCard icon={<PackageX size={16} />} label={t('alm.cost_idle')} value={fmtCurrency(r.idle, moneda)}
              sub={r.total ? t('alm.cost_idle_pct', { pct: Math.round((r.idle / r.total) * 100) }) : undefined} warning={r.idle > 0} />
            <KpiCard icon={<Receipt size={16} />} label={t('alm.cost_rebillable')} value={fmtCurrency(r.rebillable, moneda)} />
          </div>
          <Tabs active={vista} onChange={setVista} ariaLabel={t('alm.tab_costs')} items={[
            { id: 'groups', label: t('alm.cost_groups'), count: r.groups.length },
            { id: 'lines', label: t('alm.cost_lines'), count: r.lines.length },
            { id: 'rebill', label: t('alm.cost_rebill_report') },
          ]} />
          {vista === 'groups' && (r.groups.length === 0 ? <EmptyState svgIcon={<Coins size={32} />} title={t('alm.costs_empty')} /> : (
            <div className="almf-grupos">
              {r.groups.map(g => (
                <div key={g.key} className="almf-grupo">
                  <span className="almf-grupo__nombre">{nombreDeGrupo(g.key, g.name)}</span>
                  <strong className="almf-importe">{fmtCurrency(g.amount, moneda)}</strong>
                  <div className="almf-barra" aria-hidden="true">
                    <div className="almf-barra__relleno" style={{ '--almf-pct': `${r.total ? (g.amount / r.total) * 100 : 0}%` } as CSSProperties} />
                  </div>
                  <span className="almf-grupo__sub">
                    {t('alm.cost_group_lines', { n: g.lines })}{g.idle > 0 ? ` · ${t('alm.cost_idle')}: ${fmtCurrency(g.idle, moneda)}` : ''}
                  </span>
                </div>
              ))}
            </div>
          ))}
          {vista === 'lines' && <div className="almf-tabla-scroll"><DataTable columns={columnas} data={r.lines} pageSize={25} /></div>}
          {vista === 'rebill' && (refa.isLoading ? <Spinner /> : refa.data && (
            <Section title={t('alm.cost_rebill_report')}
              subtitle={t('alm.cost_rebill_markup', { pct: refa.data.markup_pct })}>
              {refa.data.clients.length === 0 ? <EmptyState icon={<Receipt size={28} />} title={t('alm.cost_rebill_empty')} /> : (
                <div className="almf-grupos">
                  {refa.data.clients.map(c => (
                    <div key={c.client_id} className="almf-grupo">
                      <span className="almf-grupo__nombre">{c.client_name ?? c.client_id}</span>
                      <strong className="almf-importe">{fmtCurrency(c.amount_to_bill, refa.data?.currency)}</strong>
                      <span className="almf-grupo__sub">{t('alm.cost_rebill_cost', { amount: fmtCurrency(c.cost, refa.data?.currency), n: c.lines.length })}</span>
                    </div>
                  ))}
                  <div className="almf-grupo">
                    <span className="almf-grupo__nombre">{t('alm.cost_rebill_total')}</span>
                    <strong className="almf-importe">{fmtCurrency(refa.data.total_to_bill, refa.data.currency)}</strong>
                  </div>
                </div>
              )}
            </Section>
          ))}
        </>
      )}
    </div>
  )
}
