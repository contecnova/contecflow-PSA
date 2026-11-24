/**
 * Lista de PIR con filtros (migración 206, docs/PIR.md): buscador, ámbito, estado
 * (incluye «vencida» y «pendiente»), resultado y «solo obligatorias». La usan la página
 * `/pir`, la sección PIR del cambio y del proyecto. Las vencidas salen marcadas y se
 * avisa arriba de cuántas hay.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, ClipboardCheck } from 'lucide-react'
import { Buscador, Checkbox, FiltrosDeLista, Segmentado, SelectRico, Tabla } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { fmtDate } from '../../utils/helpers'
import { CLAVES_PIR, pirApi } from '../../services/api/pir'
import type { FiltrosPir, OrigenPir, Pir } from '../../services/api/pir'
import { ESTADOS_PIR, EstadoDePir, OrigenDePir, RESULTADOS_PIR, ResultadoDePir } from './comun'
import './Pir.css'

export interface ListaDePirProps {
  /** Fija el origen (ficha del cambio o del proyecto): no se muestra el filtro de ámbito. */
  origenTipo?: OrigenPir
  origenId?: string
  soloMias?: boolean
  onAbrir: (id: string) => void
}

export default function ListaDePir({ origenTipo, origenId, soloMias, onAbrir }: ListaDePirProps) {
  const t = useAppT()
  const [q, setQ] = useState('')
  const [ambito, setAmbito] = useState<string>(origenTipo ?? 'todos')
  const [estado, setEstado] = useState('')
  const [resultado, setResultado] = useState('')
  const [obligatorias, setObligatorias] = useState(false)
  const filtros: FiltrosPir = {
    q: q || undefined, origen_tipo: origenTipo ?? (ambito === 'todos' ? undefined : ambito as OrigenPir),
    origen_id: origenId, estado: estado || undefined, resultado: resultado || undefined,
    solo_mias: soloMias || undefined, solo_obligatorias: obligatorias || undefined, page_size: 200,
  }
  const { data, isLoading } = useQuery({ queryKey: CLAVES_PIR.lista(filtros), queryFn: () => pirApi.listar(filtros) })
  const filas = data?.items ?? []
  const vencidas = filas.filter(p => p.vencida).length

  return (
    <div className="u-stack-12">
      <FiltrosDeLista
        aria-label={t('pir.filtros')}
        buscador={<Buscador value={q} onChange={setQ} retardo={300} placeholder={t('pir.buscar')} />}
        segmentado={origenTipo ? undefined : (
          <Segmentado aria-label={t('pir.ambito')} valor={ambito} onChange={setAmbito} opciones={[
            { valor: 'todos', etiqueta: t('pir.todos') },
            { valor: 'change', etiqueta: t('pir.origen_change') },
            { valor: 'project', etiqueta: t('pir.origen_project') },
          ]} />
        )}>
        <SelectRico aria-label={t('pir.estado')} valor={estado} onChange={setEstado} opciones={[
          { valor: '', etiqueta: t('pir.todos_los_estados') },
          { valor: 'pendiente', etiqueta: t('pir.estado_pendiente') },
          { valor: 'vencido', etiqueta: t('pir.estado_vencido') },
          ...ESTADOS_PIR.map(e => ({ valor: e, etiqueta: t(`pir.estado_${e}`) })),
        ]} />
        <SelectRico aria-label={t('pir.resultado')} valor={resultado} onChange={setResultado} opciones={[
          { valor: '', etiqueta: t('pir.todos_los_resultados') },
          ...RESULTADOS_PIR.map(r => ({ valor: r, etiqueta: t(`pir.resultado_${r}`) })),
        ]} />
      </FiltrosDeLista>
      <Checkbox checked={obligatorias} onChange={v => setObligatorias(v)} label={t('pir.solo_obligatorias')} />
      {vencidas > 0 && (
        <div role="status" className="pir-aviso pir-aviso--peligro">
          <AlertTriangle size={14} aria-hidden />{t('pir.aviso_vencidas', { n: vencidas })}
        </div>
      )}
      <Tabla<Pir>
        etiqueta={t('pir.lista')}
        filas={filas}
        cargando={isLoading}
        ordenable
        onFila={p => onAbrir(p.id)}
        claseDeFila={p => (p.vencida ? 'pir-fila--vencida' : undefined)}
        vacio={{ icono: <ClipboardCheck size={28} />, titulo: t('pir.vacio'), descripcion: t('pir.vacio_desc') }}
        columnas={[
          { key: 'codigo', label: t('pir.codigo'), cabeceraDeFila: true },
          { key: 'titulo', label: t('pir.titulo'), render: (_v, p) => (
            <div className="pir-celda"><span>{p.titulo}</span>{!origenId && <OrigenDePir pir={p} />}</div>) },
          { key: 'estado', label: t('pir.estado'), render: (_v, p) => <EstadoDePir pir={p} /> },
          { key: 'obligatorio', label: t('pir.obligatoria'), render: (_v, p) => (p.obligatorio ? t('pir.si') : t('pir.no')) },
          { key: 'fecha_prevista', label: t('pir.fecha_prevista'), render: (_v, p) => fmtDate(p.fecha_prevista) },
          { key: 'responsable', label: t('pir.responsable'), render: (_v, p) => p.responsable || '—' },
          { key: 'resultado', label: t('pir.resultado'), render: (_v, p) => <ResultadoDePir resultado={p.resultado} /> },
        ]}
      />
    </div>
  )
}
