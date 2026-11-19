/**
 * «Gestión» de horas extra (18-11-2026, admin/RRHH/PM/responsables):
 * GET /overtime con filtros y periodo, tabla con totales; una fila abre el
 * ciclo completo. Sub-vista «Para nómina» (admin/RRHH): GET /overtime/payroll
 * con exportación CSV.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlarmClockPlus, Download, ListChecks, Wallet } from 'lucide-react'
import {
  horasExtraApi, COMPENSACIONES_HE, ESTADOS_HE, ORIGENES_HE, TIPOS_HE, type FiltrosHe, type LineaDeNomina, type PeticionHe,
} from '../../services/api/horas-extra'
import {
  BarraDeFiltros, Button, Input, ProjectSelect, Segmentado, Select, SelectorDePeriodo, Tabla, UserSelect, type ColumnaTabla,
} from '../ui'
import { useAuth } from '../../context/AuthContext'
import { usePeriodo } from '../../hooks/usePeriodo'
import { SIN_HORA } from '../../utils/periodo'
import { aCsv } from './logica'
import { AvisoDeError, EstadoHeBadge, fecha, fechaHora, franja, horas, useTh } from './comun'

export default function GestionHorasExtra({ onAbrir }: { onAbrir: (id: string) => void }) {
  const { th } = useTh()
  const { puede } = useAuth()
  const nomina = puede('horas_extra.config')
  const [vista, setVista] = useState('peticiones')
  return (
    <div className="hext-panel">
      {nomina && (
        <Segmentado aria-label={th('vista')} valor={vista} onChange={setVista} opciones={[
          { valor: 'peticiones', etiqueta: th('vista_peticiones'), icon: <ListChecks size={14} /> },
          { valor: 'nomina', etiqueta: th('vista_nomina'), icon: <Wallet size={14} /> },
        ]} />
      )}
      {vista === 'nomina' && nomina ? <ParaNomina /> : <Peticiones onAbrir={onAbrir} />}
    </div>
  )
}

const VACIOS: FiltrosHe = { estado: '', origen: '', tipo: '', compensacion: '', user_id: '', project_id: '', equipo: '', departamento: '' }

function Peticiones({ onAbrir }: { onAbrir: (id: string) => void }) {
  const { th } = useTh()
  const periodo = usePeriodo({ defecto: 'mes', granularidades: SIN_HORA, prefijo: 'heg_' })
  const [f, setF] = useState<FiltrosHe>(VACIOS)
  const poner = (c: Partial<FiltrosHe>) => setF(x => ({ ...x, ...c }))
  const hayFiltros = Object.values(f).some(Boolean)
  const q = useQuery({
    queryKey: ['horas-extra', 'lista', periodo.fechas, f],
    queryFn: () => horasExtraApi.listar({ ...periodo.fechas, ...f }),
  })
  const t = q.data?.totales
  const columnas: Array<ColumnaTabla<PeticionHe>> = [
    { key: 'persona', label: th('persona'), cabeceraDeFila: true, valorOrden: p => p.persona, pie: t ? th('total_peticiones', { n: t.peticiones }) : undefined },
    { key: 'fecha', label: th('fecha'), render: (_, p) => fecha(p.fecha), valorOrden: p => p.fecha },
    { key: 'tipo', label: th('tipo'), render: (_, p) => th(`tipo_${p.tipo}`) },
    { key: 'origen', label: th('origen'), render: (_, p) => th(`origen_${p.origen}`) },
    { key: 'franja', label: th('franja'), render: (_, p) => franja(p), sortable: false },
    { key: 'proyecto', label: th('proyecto'), render: (_, p) => p.proyecto ?? '—' },
    { key: 'horas', label: th('horas'), alinear: 'derecha', render: (_, p) => horas(p.horas), pie: t ? horas(t.horas) : undefined },
    { key: 'horas_autorizadas', label: th('autorizadas'), alinear: 'derecha', render: (_, p) => horas(p.horas_autorizadas), pie: t ? horas(t.autorizadas) : undefined },
    { key: 'horas_reales', label: th('reales'), alinear: 'derecha', render: (_, p) => horas(p.horas_reales) },
    { key: 'compensacion', label: th('compensacion'), render: (_, p) => th(`compensacion_${p.compensacion}`) },
    { key: 'horas_ponderadas', label: th('horas_ponderadas'), alinear: 'derecha', render: (_, p) => horas(p.horas_ponderadas),
      pie: t ? th('a_pagar_pie', { n: horas(t.ponderadas_pago) }) : undefined },
    { key: 'estado', label: th('estado'), render: (_, p) => <EstadoHeBadge p={p} />, valorOrden: p => p.estado,
      pie: t ? th('pendientes_pie', { n: horas(t.pendientes) }) : undefined },
  ]
  const opciones = (lista: string[], prefijo: string) => lista.map(x => ({ value: x, label: th(`${prefijo}_${x}`) }))
  return (
    <>
      <BarraDeFiltros acciones={hayFiltros ? <Button variant="link" onClick={() => setF(VACIOS)}>{th('limpiar_filtros')}</Button> : undefined}>
        <SelectorDePeriodo {...periodo.selector} sinGranularidad />
        <Select suelto aria-label={th('estado')} value={f.estado} placeholder={th('todos_los_estados')} onChange={e => poner({ estado: e.target.value })}
          options={opciones(ESTADOS_HE, 'estado')} />
        <Select suelto aria-label={th('origen')} value={f.origen} placeholder={th('todos_los_origenes')} onChange={e => poner({ origen: e.target.value })}
          options={opciones(ORIGENES_HE, 'origen')} />
        <Select suelto aria-label={th('tipo')} value={f.tipo} placeholder={th('todos_los_tipos')} onChange={e => poner({ tipo: e.target.value })}
          options={opciones(TIPOS_HE, 'tipo')} />
        <Select suelto aria-label={th('compensacion')} value={f.compensacion} placeholder={th('todas_las_compensaciones')}
          onChange={e => poner({ compensacion: e.target.value })} options={opciones(COMPENSACIONES_HE, 'compensacion')} />
        <UserSelect value={f.user_id} placeholder={th('todas_las_personas')} onChange={id => poner({ user_id: id })} />
        <ProjectSelect value={f.project_id} placeholder={th('todos_los_proyectos')} onChange={id => poner({ project_id: id })} />
        <Input aria-label={th('equipo')} placeholder={th('equipo')} value={f.equipo} onChange={e => poner({ equipo: e.target.value })} />
        <Input aria-label={th('departamento')} placeholder={th('departamento')} value={f.departamento} onChange={e => poner({ departamento: e.target.value })} />
      </BarraDeFiltros>
      {q.isError && <AvisoDeError error={q.error} />}
      <Tabla etiqueta={th('tab_gestion')} filas={q.data?.items ?? []} columnas={columnas} claveDeFila={p => p.id}
        ordenable ordenInicial={{ col: 'fecha', dir: 'desc' }} cargando={q.isLoading} onFila={p => onAbrir(p.id)} cabeceraFija
        vacio={{ icono: <AlarmClockPlus size={28} />, titulo: th('sin_resultados'), descripcion: th('sin_resultados_texto') }} />
    </>
  )
}

function ParaNomina() {
  const { th } = useTh()
  const periodo = usePeriodo({ defecto: 'mes', granularidades: SIN_HORA, prefijo: 'hen_' })
  const [liquidadas, setLiquidadas] = useState('')
  const q = useQuery({
    queryKey: ['horas-extra', 'nomina', periodo.fechas, liquidadas],
    queryFn: () => horasExtraApi.nomina({ ...periodo.fechas, liquidadas: liquidadas === '' ? null : liquidadas === 'si' }),
  })
  const filas = q.data ?? []
  const totalPonderadas = filas.reduce((s, l) => s + l.horas_ponderadas, 0)
  const columnas: Array<ColumnaTabla<LineaDeNomina>> = [
    { key: 'persona', label: th('persona'), cabeceraDeFila: true, valorOrden: l => l.persona },
    { key: 'fecha', label: th('fecha'), render: (_, l) => fecha(l.fecha), valorOrden: l => l.fecha },
    { key: 'tipo', label: th('tipo'), render: (_, l) => th(`tipo_${l.tipo}`) },
    { key: 'horas_autorizadas', label: th('autorizadas'), alinear: 'derecha', render: (_, l) => horas(l.horas_autorizadas) },
    { key: 'horas_reales', label: th('reales'), alinear: 'derecha', render: (_, l) => horas(l.horas_reales) },
    { key: 'factor', label: th('factor'), alinear: 'derecha', render: (_, l) => `×${l.factor}` },
    { key: 'horas_ponderadas', label: th('horas_ponderadas'), alinear: 'derecha', render: (_, l) => horas(l.horas_ponderadas), pie: horas(totalPonderadas) },
    { key: 'liquidacion', label: th('liquidacion'), render: (_, l) => (l.liquidacion ? `${l.liquidacion.referencia} · ${fechaHora(l.liquidacion.en)}` : th('sin_liquidar')) },
  ]
  const exportar = () => {
    const csv = aCsv(
      [th('persona'), th('fecha'), th('tipo'), th('autorizadas'), th('reales'), th('factor'), th('horas_ponderadas'), th('referencia'), th('liquidada_en')],
      filas.map(l => [l.persona, l.fecha, th(`tipo_${l.tipo}`), l.horas_autorizadas, l.horas_reales, l.factor, l.horas_ponderadas,
        l.liquidacion?.referencia ?? '', l.liquidacion?.en ?? '']),
    )
    const url = URL.createObjectURL(new Blob(['﻿', csv], { type: 'text/csv;charset=utf-8;' }))
    const a = document.createElement('a')
    a.href = url
    a.download = `horas_extra_nomina_${periodo.fechas.desde}_${periodo.fechas.hasta}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }
  return (
    <>
      <BarraDeFiltros acciones={<Button variant="secondary" icon={<Download size={14} />} disabled={!filas.length} onClick={exportar}>{th('exportar_csv')}</Button>}>
        <SelectorDePeriodo {...periodo.selector} sinGranularidad />
        <Select suelto aria-label={th('liquidacion')} value={liquidadas} placeholder={false} onChange={e => setLiquidadas(e.target.value)}
          options={[{ value: '', label: th('todas') }, { value: 'no', label: th('sin_liquidar') }, { value: 'si', label: th('liquidadas') }]} />
      </BarraDeFiltros>
      <p className="hext-ayuda">{th('nomina_ayuda')}</p>
      {q.isError && <AvisoDeError error={q.error} />}
      <Tabla etiqueta={th('vista_nomina')} filas={filas} columnas={columnas} claveDeFila={l => l.id} ordenable
        ordenInicial={{ col: 'fecha', dir: 'asc' }} cargando={q.isLoading}
        vacio={{ icono: <Wallet size={28} />, titulo: th('nomina_vacia') }} />
    </>
  )
}
