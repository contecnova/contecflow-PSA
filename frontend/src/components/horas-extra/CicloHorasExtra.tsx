/**
 * Ciclo completo de una petición de horas extra (18-11-2026), en un panel
 * lateral: GET /overtime/{id} → petición, línea de tiempo, evaluaciones de las
 * reglas (qué políticas y reglas encajaron), aprobación (pasos, decisiones,
 * escalados), el día (horario, imputado, exceso real frente a autorizado), sus
 * imputaciones y la compensación (bolsa o pago y su liquidación). «Liquidar»
 * (POST /overtime/{id}/settle) para admin y RRHH en aprobadas que se pagan.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Minus, Receipt, X } from 'lucide-react'
import { horasExtraApi, type DetalleHe, type EvaluacionHe } from '../../services/api/horas-extra'
import { Button, Drawer, IconButton, Spinner, StatusBadge, Tabla, type ColumnaTabla } from '../ui'
import { useAuth } from '../../context/AuthContext'
import { pedirTexto } from '../../context/ConfirmContext'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { lineaPorDia, paresDeDatos } from './logica'
import {
  Aviso, AvisoDeError, Datos, EstadoHeBadge, fecha, fechaHora, franja, horas, textoDeTramos, useTh, type Th,
} from './comun'

export default function CicloHorasExtra({ id, onCerrar }: { id: string | null; onCerrar: () => void }) {
  const { th } = useTh()
  const q = useQuery({ queryKey: ['horas-extra', 'detalle', id], queryFn: () => horasExtraApi.detalle(id as string), enabled: Boolean(id) })
  if (!id) return null
  return (
    <Drawer open onClose={onCerrar} ariaLabel={th('ciclo_completo')} width={640} variant="borde">
      <div className="hext-ciclo">
        <div className="hext-ciclo-cabecera">
          <h2 className="hext-ciclo-titulo">{th('ciclo_completo')}</h2>
          <IconButton ariaLabel={th('cerrar')} onClick={onCerrar}><X size={16} /></IconButton>
        </div>
        {q.isLoading && <Spinner label={th('cargando')} />}
        {q.isError && <AvisoDeError error={q.error} />}
        {q.data && <Contenido d={q.data} th={th} />}
      </div>
    </Drawer>
  )
}

function Contenido({ d, th }: { d: DetalleHe; th: Th }) {
  const p = d.peticion
  const qc = useQueryClient()
  const toast = useToast()
  const { hasRole } = useAuth()
  const liquidar = useMutation({
    mutationFn: (referencia: string) => horasExtraApi.liquidar(p.id, referencia),
    onSuccess: () => { toast.success(th('liquidada_ok')); qc.invalidateQueries({ queryKey: ['horas-extra'] }) },
    onError: e => toast.error(extractErr(e, th('error'))),
  })
  const puedeLiquidar = d.puede_gestionar && hasRole('admin', 'hr') && p.estado === 'aprobada'
    && p.compensacion === 'pago' && !p.liquidacion && !d.compensacion.liquidacion
  const pedirLiquidar = async () => {
    const ref = await pedirTexto({ title: th('liquidar'), message: th('liquidar_texto'), label: th('referencia'), required: true })
    if (ref?.trim()) liquidar.mutate(ref.trim())
  }
  const autorizadasDia = d.dia.autorizadas_del_dia
  const exceso = d.dia.exceso_real
  const columnasImp: Array<ColumnaTabla<DetalleHe['imputaciones'][number]>> = [
    { key: 'proyecto', label: th('proyecto'), render: (_, i) => i.proyecto ?? '—' },
    { key: 'horas', label: th('horas'), alinear: 'derecha', render: (_, i) => horas(i.horas) },
    { key: 'descripcion', label: th('descripcion'), render: (_, i) => i.descripcion ?? '—' },
    { key: 'aprobada', label: th('aprobada'), render: (_, i) => (i.aprobada ? th('si') : th('no')) },
  ]
  return (
    <>
      <section>
        <div className="hext-fila hext-fila--ancha">
          <strong>{p.persona}</strong><EstadoHeBadge p={p} />
          {p.en_aprobacion && <StatusBadge kind="accent">{th('en_aprobacion')}</StatusBadge>}
        </div>
        <Datos filas={[
          [th('fecha'), fecha(p.fecha)],
          [th('tipo'), th(`tipo_${p.tipo}`)],
          [th('clase_dia'), th(`clase_${p.clase_dia}`)],
          [th('origen'), th(`origen_${p.origen}`)],
          [th('franja'), franja(p)],
          [th('horas_pedidas'), horas(p.horas)],
          [th('autorizadas'), horas(p.horas_autorizadas)],
          [th('reales'), horas(p.horas_reales)],
          p.proyecto && [th('proyecto'), p.proyecto],
          p.ticket_id && [th('ticket'), p.ticket_id],
          p.sustituto && [th('sustituto'), p.sustituto],
          p.solicitante_id !== p.user_id && [th('pedida_por'), p.solicitante],
          p.motivo && [th('motivo'), p.motivo],
          p.decidido_por && [th('decidida_por'), `${p.decidido_por} · ${fechaHora(p.decidido_en)}`],
          p.motivo_rechazo && [th('motivo_rechazo'), p.motivo_rechazo],
        ]} />
        {p.avisos.map(a => <Aviso key={a} tono="aviso">{a}</Aviso>)}
        {p.bloqueos.map(a => <Aviso key={a} tono="bloqueo">{a}</Aviso>)}
      </section>

      <section>
        <h3 className="hext-subtitulo">{th('linea_de_tiempo')}</h3>
        {d.linea_de_tiempo.length === 0 ? <p className="hext-ayuda">{th('sin_eventos')}</p> : (
          <ol className="hext-linea">
            {lineaPorDia(d.linea_de_tiempo).map(g => (
              <li key={g.dia}>
                <p className="hext-linea-dia">{fecha(g.dia)}</p>
                <ol className="hext-lista">
                  {g.eventos.map((e, i) => (
                    <li key={i} className="hext-evento">
                      <span>{th(`evento_${e.tipo}`)}</span>
                      <span className="hext-evento-meta">{fechaHora(e.cuando)}{e.quien ? ` · ${e.quien}` : ''}</span>
                      {paresDeDatos(e.datos).map(([k, v]) => <span key={k} className="hext-evento-meta">{k}: {v}</span>)}
                    </li>
                  ))}
                </ol>
              </li>
            ))}
          </ol>
        )}
      </section>

      <section>
        <h3 className="hext-subtitulo">{th('evaluaciones')}</h3>
        {d.evaluaciones.length === 0 ? <p className="hext-ayuda">{th('sin_evaluaciones')}</p>
          : d.evaluaciones.map((ev, i) => <Evaluacion key={i} ev={ev} th={th} />)}
      </section>

      <section>
        <h3 className="hext-subtitulo">{th('aprobacion')}</h3>
        {!d.aprobacion ? <p className="hext-ayuda">{th('aprobacion_sin_flujo')}</p> : (
          <>
            <Datos filas={[[th('estado'), d.aprobacion.estado], d.aprobacion.paso_actual !== null && [th('paso_actual'), String(d.aprobacion.paso_actual)]]} />
            <ol className="hext-pasos">
              {d.aprobacion.pasos.map(s => (
                <li key={s.orden} className={s.orden === d.aprobacion?.paso_actual ? 'hext-paso--actual' : ''}>
                  {s.nombre} · {s.aprobador}{s.rol ? ` (${s.rol})` : ''}
                </li>
              ))}
            </ol>
            {d.aprobacion.decisiones.length > 0 && (
              <ul className="hext-lista">
                {d.aprobacion.decisiones.map((x, i) => (
                  <li key={i}>
                    {th('decision_de_paso', { paso: x.orden, decision: x.decision, quien: x.quien ?? '—' })} · {fechaHora(x.cuando)}
                    {x.nota ? ` · ${x.nota}` : ''}
                  </li>
                ))}
              </ul>
            )}
            {d.aprobacion.escalados.length > 0 && (
              <>
                <h4 className="hext-subtitulo">{th('escalados')}</h4>
                <ul className="hext-lista">
                  {d.aprobacion.escalados.map((x, i) => (
                    <li key={i}>{x.accion}{x.paso !== null ? ` · ${th('paso', { paso: x.paso })}` : ''} · {fechaHora(x.cuando)}{x.nota ? ` · ${x.nota}` : ''}</li>
                  ))}
                </ul>
              </>
            )}
          </>
        )}
      </section>

      <section>
        <h3 className="hext-subtitulo">{th('el_dia')}</h3>
        <Datos filas={[
          [th('horario_del_dia'), `${horas(d.dia.horario_horas)} · ${textoDeTramos(d.dia.tramos)}`],
          d.dia.festivo && [th('festivo'), d.dia.festivo],
          [th('imputado'), horas(d.dia.imputado)],
          [th('exceso_real'), horas(exceso)],
          [th('autorizadas_del_dia'), horas(autorizadasDia)],
        ]} />
        {exceso > autorizadasDia && <Aviso tono="aviso">{th('exceso_sin_cubrir', { n: horas(exceso - autorizadasDia) })}</Aviso>}
        <Tabla etiqueta={th('imputaciones_del_dia')} filas={d.imputaciones} columnas={columnasImp} claveDeFila={i => i.id} densidad="compacta"
          vacio={{ titulo: th('sin_imputaciones') }} />
      </section>

      <section>
        <h3 className="hext-subtitulo">{th('compensacion')}</h3>
        <Datos filas={[
          [th('compensacion'), th(`compensacion_${d.compensacion.tipo}`)],
          [th('horas_ponderadas'), horas(d.compensacion.horas_ponderadas)],
          d.compensacion.movimiento_bolsa && [th('movimiento_bolsa'),
            `${horas(d.compensacion.movimiento_bolsa.cantidad)} · ${fecha(d.compensacion.movimiento_bolsa.fecha)}`],
          d.compensacion.liquidacion && [th('liquidacion'),
            `${d.compensacion.liquidacion.referencia} · ${fechaHora(d.compensacion.liquidacion.en)}${d.compensacion.liquidacion.por ? ` · ${d.compensacion.liquidacion.por}` : ''}`],
        ]} />
        {puedeLiquidar && (
          <Button icon={<Receipt size={14} />} loading={liquidar.isPending} onClick={pedirLiquidar}>{th('liquidar')}</Button>
        )}
      </section>
    </>
  )
}

function Evaluacion({ ev, th }: { ev: EvaluacionHe; th: Th }) {
  const politicas = ev.explicacion ?? []
  return (
    <details className="hext-tarjeta">
      <summary>
        {th('momento', { momento: th(`momento_${ev.momento}`) })} · {th(`decision_${ev.decision}`)} · {fechaHora(ev.created_at)}
      </summary>
      {politicas.length === 0 && <p className="hext-ayuda">{th('sin_politicas')}</p>}
      {politicas.map((pol, i) => (
        <div key={i}>
          <p className={`hext-regla ${pol.aplica ? 'hext-regla--cumple' : 'hext-regla--no'}`}>
            {pol.aplica ? <Check size={13} aria-hidden /> : <Minus size={13} aria-hidden />}
            <strong>{pol.politica}</strong> · {pol.aplica ? th('aplica') : th('no_aplica')}
          </p>
          <ul className="hext-lista">
            {pol.reglas.map((r, j) => {
              const extra = paresDeDatos(Object.fromEntries(Object.entries(r).filter(([k]) => k !== 'regla' && k !== 'cumple')))
              return (
                <li key={j} className={`hext-regla ${r.cumple ? 'hext-regla--cumple' : 'hext-regla--no'}`}>
                  {r.cumple ? <Check size={13} aria-hidden /> : <X size={13} aria-hidden />}
                  <span>{r.regla} · {r.cumple ? th('encaja') : th('no_encaja')}
                    {extra.length > 0 && <span className="hext-evento-meta"> · {extra.map(([k, v]) => `${k}: ${v}`).join(' · ')}</span>}
                  </span>
                </li>
              )
            })}
          </ul>
        </div>
      ))}
    </details>
  )
}
