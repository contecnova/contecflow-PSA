/**
 * «Por aprobar» (18-11-2026): GET /overtime/inbox. Cada petición con su
 * contexto (acumulados, presupuesto, descanso, días seguidos) y la decisión:
 * aprobar con horas autorizadas (por defecto las pedidas) o rechazar con nota
 * → POST /overtime/{id}/review. Indica si va por flujo (paso) o sin flujo.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Inbox, X } from 'lucide-react'
import { horasExtraApi, type ElementoBandejaHe } from '../../services/api/horas-extra'
import { Button, Chip, EmptyState, Input, Pulsable, Spinner } from '../ui'
import { useToast } from '../../context/ToastContext'
import { Aviso, AvisoDeError, Datos, fecha, franja, horas, useTh } from './comun'

export default function BandejaHorasExtra({ onAbrir }: { onAbrir: (id: string) => void }) {
  const { th } = useTh()
  const q = useQuery({ queryKey: ['horas-extra', 'bandeja'], queryFn: horasExtraApi.bandeja })
  if (q.isLoading) return <Spinner label={th('cargando')} />
  if (q.isError) return <AvisoDeError error={q.error} />
  if (!q.data?.length) return <EmptyState svgIcon={<Inbox size={26} />} title={th('bandeja_vacia')} description={th('bandeja_vacia_texto')} />
  return <ul className="hext-bandeja hext-panel">{q.data.map(x => <Elemento key={x.peticion.id} x={x} onAbrir={onAbrir} />)}</ul>
}

function Elemento({ x, onAbrir }: { x: ElementoBandejaHe; onAbrir: (id: string) => void }) {
  const { th } = useTh()
  const qc = useQueryClient()
  const toast = useToast()
  const p = x.peticion
  const [nota, setNota] = useState('')
  const [autorizadas, setAutorizadas] = useState(String(p.horas))
  const n = Number(autorizadas.replace(',', '.'))
  const autorizadasValidas = autorizadas.trim() !== '' && Number.isFinite(n) && n >= 0 && n <= p.horas
  const decidir = useMutation({
    mutationFn: (aprobado: boolean) => horasExtraApi.revisar(p.id, aprobado, nota, aprobado ? n : null),
    onSuccess: (_, aprobado) => {
      toast.success(aprobado ? th('aprobada_ok') : th('rechazada_ok'))
      qc.invalidateQueries({ queryKey: ['horas-extra'] })
    },
  })
  const c = x.contexto
  return (
    <li className="hext-tarjeta">
      <header className="hext-tarjeta-cabecera">
        <Pulsable className="hext-enlace" onClick={() => onAbrir(p.id)}>{p.persona}</Pulsable>
        <span>{fecha(p.fecha)} · {franja(p)} · {horas(p.horas)}</span>
        <Chip>{th(`tipo_${p.tipo}`)}</Chip>
        <Chip>{th(`origen_${p.origen}`)}</Chip>
        <Chip>{th(`compensacion_${p.compensacion}`)}</Chip>
        {x.sin_flujo ? <Chip>{th('sin_flujo')}</Chip> : x.paso && <Chip activo>{th('paso', { paso: x.paso })}</Chip>}
      </header>
      {p.motivo && <p className="hext-ayuda">{p.motivo}</p>}
      <Datos filas={[
        p.proyecto && [th('proyecto'), p.proyecto],
        p.sustituto && [th('sustituto'), p.sustituto],
        p.solicitante_id !== p.user_id && [th('pedida_por'), p.solicitante],
        [th('acum_dia'), horas(c.acumulados.dia)],
        [th('acum_semana'), horas(c.acumulados.semana)],
        [th('acum_mes'), horas(c.acumulados.mes)],
        [th('acum_anio'), horas(c.acumulados.anio)],
        [th('acum_anio_pago'), horas(c.acumulados.anio_pago)],
        c.presupuesto_restante !== null && [th('presupuesto_restante'),
          <span key="p" className={c.presupuesto_restante < 0 ? 'hext-negativo' : ''}>{horas(c.presupuesto_restante)}</span>],
        c.descanso_horas !== null && [th('descanso'), horas(c.descanso_horas)],
        [th('dias_seguidos'), String(c.dias_seguidos)],
      ]} />
      {p.avisos.map(a => <Aviso key={a} tono="aviso">{a}</Aviso>)}
      {p.bloqueos.map(a => <Aviso key={a} tono="bloqueo">{a}</Aviso>)}
      <div className="hext-decidir">
        <Input className="hext-decidir-horas" label={th('horas_autorizadas')} inputMode="decimal" value={autorizadas}
          onChange={e => setAutorizadas(e.target.value)}
          error={autorizadasValidas ? undefined : th('autorizadas_rango', { n: horas(p.horas) })} />
        <Input className="hext-decidir-nota" label={th('nota')} placeholder={th('nota_ayuda')} value={nota} maxLength={1000}
          onChange={e => setNota(e.target.value)} />
        <Button size="md" icon={<Check size={14} />} disabled={!autorizadasValidas || !p.puede_revisar}
          loading={decidir.isPending && decidir.variables === true} onClick={() => decidir.mutate(true)}>{th('aprobar')}</Button>
        <Button size="md" variant="danger" icon={<X size={14} />} disabled={!p.puede_revisar}
          loading={decidir.isPending && decidir.variables === false} onClick={() => decidir.mutate(false)}>{th('rechazar')}</Button>
      </div>
      {!p.puede_revisar && <p className="hext-ayuda">{th('no_puedes_revisar')}</p>}
      <AvisoDeError error={decidir.error} />
    </li>
  )
}
