/**
 * «Resumen» de horas extra (18-11-2026, responsables): GET /overtime/summary
 * agrupado por persona, equipo, departamento o proyecto; cifras de cabecera,
 * consumo frente a los límites de las reglas publicadas (≥80 % atención,
 * ≥100 % excedido) y frente al presupuesto. Debajo, las horas imputadas fuera
 * de horario sin autorizar (GET /overtime/unauthorized).
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, BarChart3, CheckCircle2, Clock, Hourglass, ShieldAlert, Wallet } from 'lucide-react'
import { horasExtraApi, type AgruparPor, type FilaResumenHe, type SinAutorizarHe } from '../../services/api/horas-extra'
import { BarraDeFiltros, KpiCard, LoadBar, Section, Segmentado, SelectorDePeriodo, StatusBadge, Tabla, type ColumnaTabla } from '../ui'
import { usePeriodo } from '../../hooks/usePeriodo'
import { SIN_HORA } from '../../utils/periodo'
import { fmtNumber } from '../../utils/helpers'
import { nivelDeConsumo, nivelDeFila, pctDeLimite, pctDePresupuesto, totalesDeResumen } from './logica'
import { AvisoDeError, TONO_DE_NIVEL, fecha, horas, useTh, type Th } from './comun'

const AGRUPACIONES: AgruparPor[] = ['persona', 'equipo', 'departamento', 'proyecto']

export default function ResumenHorasExtra({ onAbrir }: { onAbrir: (id: string) => void }) {
  const { th } = useTh()
  const periodo = usePeriodo({ defecto: 'anio', granularidades: SIN_HORA, prefijo: 'her_' })
  const [agrupar, setAgrupar] = useState<AgruparPor>('persona')
  const q = useQuery({
    queryKey: ['horas-extra', 'resumen', periodo.fechas, agrupar],
    queryFn: () => horasExtraApi.resumen({ ...periodo.fechas, agrupar }),
  })
  const filas = q.data?.filas ?? []
  const tot = totalesDeResumen(filas)
  const columnas: Array<ColumnaTabla<FilaResumenHe>> = [
    { key: 'etiqueta', label: th(`agrupar_${agrupar}`), cabeceraDeFila: true, valorOrden: f => f.etiqueta },
    { key: 'peticiones', label: th('peticiones'), alinear: 'derecha' },
    { key: 'horas_pedidas', label: th('horas_pedidas'), alinear: 'derecha', render: (_, f) => horas(f.horas_pedidas), valorOrden: f => f.horas_pedidas },
    { key: 'horas_aprobadas', label: th('aprobadas'), alinear: 'derecha', render: (_, f) => horas(f.horas_aprobadas), valorOrden: f => f.horas_aprobadas },
    { key: 'horas_pendientes', label: th('pendientes'), alinear: 'derecha', render: (_, f) => horas(f.horas_pendientes), valorOrden: f => f.horas_pendientes },
    { key: 'horas_rechazadas', label: th('rechazadas'), alinear: 'derecha', render: (_, f) => horas(f.horas_rechazadas), valorOrden: f => f.horas_rechazadas },
    { key: 'horas_reales', label: th('reales'), alinear: 'derecha', render: (_, f) => horas(f.horas_reales), valorOrden: f => f.horas_reales },
    { key: 'horas_sin_autorizar', label: th('sin_autorizar'), alinear: 'derecha', valorOrden: f => f.horas_sin_autorizar,
      render: (_, f) => <span className={f.horas_sin_autorizar > 0 ? 'hext-negativo' : ''}>{horas(f.horas_sin_autorizar)}</span> },
    { key: 'horas_pago', label: th('compensacion_pago'), alinear: 'derecha', render: (_, f) => horas(f.horas_pago), valorOrden: f => f.horas_pago },
    { key: 'horas_bolsa', label: th('compensacion_bolsa'), alinear: 'derecha', render: (_, f) => horas(f.horas_bolsa), valorOrden: f => f.horas_bolsa },
    { key: 'horas_ponderadas_pago', label: th('a_pagar'), alinear: 'derecha', render: (_, f) => horas(f.horas_ponderadas_pago), valorOrden: f => f.horas_ponderadas_pago },
    { key: 'presupuesto', label: th('presupuesto'), valorOrden: f => pctDePresupuesto(f.presupuesto) ?? -1, render: (_, f) => <Presupuesto f={f} th={th} /> },
    { key: 'limites', label: th('limites'), valorOrden: f => Math.max(0, ...f.limites.map(pctDeLimite)), render: (_, f) => <Limites f={f} th={th} /> },
    { key: 'nivel', label: th('nivel'), valorOrden: f => ['ok', 'atencion', 'excedido'].indexOf(nivelDeFila(f)), render: (_, f) => {
      const n = nivelDeFila(f)
      return <StatusBadge kind={TONO_DE_NIVEL[n]}>{th(`nivel_${n}`)}</StatusBadge>
    } },
  ]
  return (
    <div className="hext-panel">
      <BarraDeFiltros>
        <SelectorDePeriodo {...periodo.selector} sinGranularidad />
        <Segmentado aria-label={th('agrupar_por')} valor={agrupar} onChange={v => setAgrupar(v as AgruparPor)}
          opciones={AGRUPACIONES.map(a => ({ valor: a, etiqueta: th(`agrupar_${a}`) }))} />
      </BarraDeFiltros>
      {q.isError && <AvisoDeError error={q.error} />}
      <div className="ds-grid-stats">
        <KpiCard icon={<Clock size={16} />} label={th('horas_pedidas')} value={horas(tot.pedidas)} />
        <KpiCard icon={<CheckCircle2 size={16} />} label={th('aprobadas')} value={horas(tot.aprobadas)} accent />
        <KpiCard icon={<Hourglass size={16} />} label={th('pendientes')} value={horas(tot.pendientes)} warning={tot.pendientes > 0} />
        <KpiCard icon={<BarChart3 size={16} />} label={th('reales')} value={horas(tot.reales)} />
        <KpiCard icon={<ShieldAlert size={16} />} label={th('sin_autorizar')} value={horas(tot.sin_autorizar)} danger={tot.sin_autorizar > 0} />
        <KpiCard icon={<Wallet size={16} />} label={th('a_pagar')} value={horas(tot.a_pagar)} sub={th('a_pagar_ayuda')} />
      </div>
      <Tabla etiqueta={th('tab_resumen')} filas={filas} columnas={columnas} claveDeFila={f => f.clave} ordenable
        ordenInicial={{ col: 'horas_pedidas', dir: 'desc' }} cargando={q.isLoading}
        vacio={{ icono: <BarChart3 size={28} />, titulo: th('resumen_vacio') }} />
      {q.data && (
        <Section title={th('limites_publicados')} subtitle={th('limites_publicados_ayuda')}>
          {q.data.limites_publicados.length === 0 ? <p className="hext-ayuda">{th('sin_limites')}</p> : (
            <ul className="hext-lista">
              {q.data.limites_publicados.map((l, i) => (
                <li key={i}>
                  {th(`campo_${l.campo}`)} ≤ {horas(l.umbral)} · {l.politica} · {l.regla} · <StatusBadge kind={l.efecto === 'block' ? 'danger' : 'warning'}>{th(`efecto_${l.efecto}`)}</StatusBadge>
                </li>
              ))}
            </ul>
          )}
        </Section>
      )}
      <SinAutorizar desde={periodo.fechas.desde} hasta={periodo.fechas.hasta} onAbrir={onAbrir} />
    </div>
  )
}

function Presupuesto({ f, th }: { f: FilaResumenHe; th: Th }) {
  const pct = pctDePresupuesto(f.presupuesto)
  if (!f.presupuesto || pct === null) return <>—</>
  const n = nivelDeConsumo(pct)
  return (
    <div className="hext-consumo">
      <LoadBar value={pct} max={100} label={th('consumo_pct', { pct: fmtNumber(pct, 0) })} />
      <span className="hext-fila">
        <StatusBadge kind={TONO_DE_NIVEL[n]}>{fmtNumber(pct, 0)} %</StatusBadge>
        {th('restantes_de', { restantes: horas(f.presupuesto.restantes), total: horas(f.presupuesto.horas) })}
      </span>
    </div>
  )
}

function Limites({ f, th }: { f: FilaResumenHe; th: Th }) {
  if (!f.limites.length) return <>—</>
  return (
    <div className="hext-limites">
      {f.limites.map((l, i) => {
        const pct = pctDeLimite(l)
        const n = nivelDeConsumo(pct)
        return (
          <div key={i} className="hext-consumo" title={`${l.politica} · ${th(`efecto_${l.efecto}`)}`}>
            <span className="hext-fila">
              <StatusBadge kind={TONO_DE_NIVEL[n]}>{fmtNumber(pct, 0)} %</StatusBadge>
              {th(`campo_${l.campo}`)}: {horas(l.consumo)} / {horas(l.umbral)}
              {n === 'excedido' && <AlertTriangle size={12} aria-hidden />}
            </span>
            <LoadBar value={pct} max={100} label={th('consumo_pct', { pct: fmtNumber(pct, 0) })} />
          </div>
        )
      })}
    </div>
  )
}

function SinAutorizar({ desde, hasta, onAbrir }: { desde: string; hasta: string; onAbrir: (id: string) => void }) {
  const { th } = useTh()
  const q = useQuery({ queryKey: ['horas-extra', 'sin-autorizar', desde, hasta], queryFn: () => horasExtraApi.sinAutorizar({ desde, hasta }) })
  const filas = q.data ?? []
  const columnas: Array<ColumnaTabla<SinAutorizarHe>> = [
    { key: 'persona', label: th('persona'), cabeceraDeFila: true, valorOrden: x => x.persona },
    { key: 'fecha', label: th('fecha'), render: (_, x) => fecha(x.fecha), valorOrden: x => x.fecha },
    { key: 'horario', label: th('horario_del_dia'), alinear: 'derecha', render: (_, x) => horas(x.horario) },
    { key: 'imputado', label: th('imputado'), alinear: 'derecha', render: (_, x) => horas(x.imputado) },
    { key: 'autorizadas', label: th('autorizadas'), alinear: 'derecha', render: (_, x) => horas(x.autorizadas) },
    { key: 'pendientes', label: th('pendientes'), alinear: 'derecha', render: (_, x) => horas(x.pendientes) },
    { key: 'sin_autorizar', label: th('sin_autorizar'), alinear: 'derecha', valorOrden: x => x.sin_autorizar,
      render: (_, x) => <span className="hext-negativo">{horas(x.sin_autorizar)}</span>,
      pie: horas(filas.reduce((s, x) => s + x.sin_autorizar, 0)) },
  ]
  return (
    <Section title={th('sin_autorizar_titulo')} subtitle={th('sin_autorizar_ayuda')}>
      {q.isError && <AvisoDeError error={q.error} />}
      <Tabla etiqueta={th('sin_autorizar_titulo')} filas={filas} columnas={columnas} claveDeFila={x => `${x.user_id}-${x.fecha}`}
        ordenable ordenInicial={{ col: 'fecha', dir: 'desc' }} cargando={q.isLoading}
        onFila={x => { if (x.peticion_id) onAbrir(x.peticion_id) }}
        vacio={{ icono: <CheckCircle2 size={28} />, titulo: th('sin_autorizar_vacio') }} />
    </Section>
  )
}
