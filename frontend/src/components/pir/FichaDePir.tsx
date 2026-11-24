/**
 * Ficha de una PIR (migración 206, docs/PIR.md): el formulario guiado por la plantilla.
 *
 * Bloques: datos (responsable, fecha, participantes), criterios de éxito (sí / no /
 * parcial con comentario), resultado global y objetivos, preguntas de la plantilla,
 * incidencias provocadas (tickets) y marcha atrás, KPIs antes/después, en proyectos
 * beneficios conseguidos frente a previstos y satisfacción de los interesados, acciones
 * de mejora (nacen como tareas) y lecciones aprendidas (van al módulo de lecciones).
 * El pie lleva el flujo: guardar, enviar, aprobar, devolver, cerrar, reabrir, descartar
 * y borrar, según lo que el servidor dice que puedo (`permisos`). Con la segregación de
 * la empresa activada, quien implantó o gestionó no ve «Aprobar» y se le explica.
 */
import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle, BarChart3, CheckCircle2, ClipboardList, Lightbulb, ListChecks, Plus, RotateCcw, Send, ShieldAlert,
  Trash2, Undo2, Users, X, XCircle,
} from 'lucide-react'
import {
  Button, Buscador, Checkbox, DateInput, IconButton, Input, Modal, Segmentado, SelectRico, Spinner, StatusBadge,
  Switch, Textarea,
} from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { useAuth } from '../../context/AuthContext'
import { confirmar, pedirTexto } from '../../context/ConfirmContext'
import { extractErr, fmtDate, fmtDateTime } from '../../utils/helpers'
import { useListaDeUsuarios } from '../../hooks/useListas'
import { ticketsApi, leccionesApi } from '../../services/api'
import { CLAVES_PIR, pirApi } from '../../services/api/pir'
import type {
  BeneficioPir, CambiosPir, CriterioPir, CumplimientoPir, KpiPir, PirDetalle, PreguntaPir, ResultadoPir, SatisfaccionPir,
} from '../../services/api/pir'
import { EstadoDePir, OrigenDePir, RESULTADOS_PIR } from './comun'
import './Pir.css'

type Formulario = Required<Pick<CambiosPir, 'criterios' | 'preguntas' | 'kpis' | 'satisfaccion'>> & {
  objetivos_cumplidos: CumplimientoPir | null; resultado: ResultadoPir | null; resumen: string
  hubo_marcha_atras: boolean | null; marcha_atras_detalle: string; fecha_prevista: string
  responsable_id: string; participantes: string[]; incidencias: string[]; beneficios: BeneficioPir[]
}

const CUMPLE: CumplimientoPir[] = ['si', 'parcial', 'no']
const numero = (v: string): number | null => (v.trim() === '' || Number.isNaN(Number(v)) ? null : Number(v))

function desde(p: PirDetalle): Formulario {
  return {
    criterios: p.criterios, preguntas: p.preguntas, kpis: p.kpis, satisfaccion: p.satisfaccion,
    objetivos_cumplidos: p.objetivos_cumplidos, resultado: p.resultado, resumen: p.resumen ?? '',
    hubo_marcha_atras: p.hubo_marcha_atras, marcha_atras_detalle: p.marcha_atras_detalle ?? '',
    fecha_prevista: p.fecha_prevista ?? '', responsable_id: p.responsable_id ?? '', participantes: p.participantes,
    incidencias: p.incidencias.map(i => i.id), beneficios: p.beneficios.map(b => ({ ...b, actualizar: false })),
  }
}

export default function FichaDePir({ id, onClose }: { id: string; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { puede } = useAuth()
  const { data: pir, isLoading } = useQuery({ queryKey: CLAVES_PIR.detalle(id), queryFn: () => pirApi.detalle(id) })
  const { data: usuarios = [] } = useListaDeUsuarios()
  const [form, setForm] = useState<Formulario | null>(null)
  const [cambiado, setCambiado] = useState(false)
  useEffect(() => { if (pir) { setForm(desde(pir)); setCambiado(false) } }, [pir])

  const opcionesUsuario = useMemo(() => usuarios.map(u => ({ valor: u.id, etiqueta: u.full_name || u.id })), [usuarios])
  const nombreDe = (uid: string) => opcionesUsuario.find(o => o.valor === uid)?.etiqueta ?? uid

  const refrescar = (p?: PirDetalle) => {
    if (p) qc.setQueryData(CLAVES_PIR.detalle(id), p)
    void qc.invalidateQueries({ queryKey: CLAVES_PIR.todo })
  }
  const accion = useMutation({
    mutationFn: (f: () => Promise<PirDetalle | { ok: boolean }>) => f(),
    onSuccess: r => { refrescar('id' in r ? r as PirDetalle : undefined); toast.success(t('pir.hecho')) },
    onError: e => toast.error(extractErr(e)),
  })

  if (isLoading || !pir || !form) {
    return <Modal open title={t('pir.ficha')} onClose={onClose} size="xl" avisarSinGuardar={false}><Spinner /></Modal>
  }
  const p = pir.permisos
  const editable = !!p?.editar
  const gestiona = puede('pir.gestionar')
  const set = <K extends keyof Formulario>(k: K, v: Formulario[K]) => { setForm(f => (f ? { ...f, [k]: v } : f)); setCambiado(true) }
  const cambios = (): CambiosPir => {
    const datos: CambiosPir = {
      criterios: form.criterios, preguntas: form.preguntas, kpis: form.kpis, satisfaccion: form.satisfaccion,
      objetivos_cumplidos: form.objetivos_cumplidos, resultado: form.resultado, resumen: form.resumen,
      hubo_marcha_atras: form.hubo_marcha_atras, marcha_atras_detalle: form.marcha_atras_detalle,
      participantes: form.participantes, incidencias: form.incidencias,
    }
    if (pir.origen_tipo === 'project') datos.beneficios = form.beneficios
    if (form.fecha_prevista && form.fecha_prevista !== pir.fecha_prevista) datos.fecha_prevista = form.fecha_prevista
    if (form.responsable_id && form.responsable_id !== pir.responsable_id) datos.responsable_id = form.responsable_id
    return datos
  }
  const guardar = () => accion.mutate(() => pirApi.guardar(id, cambios()))
  const enviar = () => accion.mutate(async () => {
    if (cambiado) await pirApi.guardar(id, cambios())
    return pirApi.enviar(id)
  })
  const conMotivo = async (titulo: string, f: (m: string) => Promise<PirDetalle>) => {
    const m = await pedirTexto({ title: titulo, message: titulo, label: t('pir.motivo'), required: true, multiline: true })
    if (m && m.trim()) accion.mutate(() => f(m.trim()))
  }

  return (
    <Modal open title={`${pir.codigo} · ${pir.titulo}`} onClose={onClose} size="xl" cambiosSinGuardar={cambiado}
      subtitle={<span className="pir-insignia"><EstadoDePir pir={pir} /> <OrigenDePir pir={pir} /></span>}>
      <div className="pir-ficha">
        {pir.vencida && (
          <div role="status" className="pir-aviso pir-aviso--peligro"><AlertTriangle size={14} aria-hidden />
            {t('pir.aviso_vencida', { fecha: fmtDate(pir.fecha_prevista) })}</div>
        )}
        {p?.segregacion && (
          <div role="note" className="pir-aviso pir-aviso--info"><ShieldAlert size={14} aria-hidden />{t('pir.aviso_segregacion')}</div>
        )}
        {pir.comentario_aprobacion && pir.estado === 'en_curso' && (
          <div role="note" className="pir-aviso pir-aviso--info"><Undo2 size={14} aria-hidden />
            {t('pir.devuelta_con', { comentario: pir.comentario_aprobacion })}</div>
        )}

        {/* Datos */}
        <section className="pir-bloque" aria-labelledby={`${id}-datos`}>
          <h3 id={`${id}-datos`} className="pir-bloque__titulo"><ClipboardList size={16} aria-hidden />{t('pir.datos')}</h3>
          <div className="pir-rejilla">
            <div className="u-stack-6"><span className="pir-apagado">{t('pir.obligatoria')}</span>
              <span>{pir.obligatorio ? t('pir.si') : t('pir.no')}</span></div>
            <div className="u-stack-6"><span className="pir-apagado">{t('pir.motivo_label')}</span>
              <span>{t(`pir.motivo_${pir.motivo}`)}</span></div>
            {gestiona && editable ? (
              <>
                <div className="u-stack-6">
                  <DateInput label={t('pir.fecha_prevista')} value={form.fecha_prevista} onChange={e => set('fecha_prevista', e.target.value)} /></div>
                <SelectRico label={t('pir.responsable')} valor={form.responsable_id} onChange={v => set('responsable_id', v)}
                  opciones={opcionesUsuario} />
              </>
            ) : (
              <>
                <div className="u-stack-6"><span className="pir-apagado">{t('pir.fecha_prevista')}</span><span>{fmtDate(pir.fecha_prevista)}</span></div>
                <div className="u-stack-6"><span className="pir-apagado">{t('pir.responsable')}</span><span>{pir.responsable || '—'}</span></div>
              </>
            )}
            <div className="u-stack-6"><span className="pir-apagado">{t('pir.fecha_real')}</span><span>{fmtDate(pir.fecha_real)}</span></div>
          </div>
          <div className="u-stack-6">
            <span className="pir-apagado"><Users size={13} aria-hidden /> {t('pir.participantes')}</span>
            <ul className="pir-lista-simple">
              {form.participantes.map(u => (
                <li key={u}>{nombreDe(u)}{editable && (
                  <IconButton variante="caja" tamano="xs" tono="peligro" ariaLabel={t('pir.quitar_participante', { nombre: nombreDe(u) })}
                    onClick={() => set('participantes', form.participantes.filter(x => x !== u))}><X /></IconButton>)}</li>
              ))}
            </ul>
            {editable && (
              <SelectRico aria-label={t('pir.anadir_participante')} valor="" placeholder={t('pir.anadir_participante')}
                onChange={v => v && !form.participantes.includes(v) && set('participantes', [...form.participantes, v])}
                opciones={opcionesUsuario.filter(o => !form.participantes.includes(o.valor))} />
            )}
          </div>
        </section>

        {/* Criterios */}
        <section className="pir-bloque" aria-labelledby={`${id}-crit`}>
          <h3 id={`${id}-crit`} className="pir-bloque__titulo"><ListChecks size={16} aria-hidden />{t('pir.criterios')}</h3>
          {form.criterios.map((c, i) => (
            <Criterio key={c.clave} c={c} editable={editable}
              onChange={nuevo => set('criterios', form.criterios.map((x, j) => (j === i ? nuevo : x)))} />
          ))}
        </section>

        {/* Resultado */}
        <section className="pir-bloque" aria-labelledby={`${id}-res`}>
          <h3 id={`${id}-res`} className="pir-bloque__titulo"><CheckCircle2 size={16} aria-hidden />{t('pir.resultado_global')}</h3>
          <div className="pir-rejilla">
            <div className="u-stack-6"><span className="pir-apagado">{t('pir.objetivos_cumplidos')}</span>
              <Segmentado aria-label={t('pir.objetivos_cumplidos')} valor={form.objetivos_cumplidos ?? ''}
                onChange={v => editable && set('objetivos_cumplidos', v as CumplimientoPir)}
                opciones={CUMPLE.map(v => ({ valor: v, etiqueta: t(`pir.cumple_${v}`), disabled: !editable }))} /></div>
            <div className="u-stack-6"><span className="pir-apagado">{t('pir.resultado')}</span>
              <Segmentado aria-label={t('pir.resultado')} valor={form.resultado ?? ''}
                onChange={v => editable && set('resultado', v as ResultadoPir)}
                opciones={RESULTADOS_PIR.map(v => ({ valor: v, etiqueta: t(`pir.resultado_${v}`), disabled: !editable }))} /></div>
          </div>
          {pir.origen_tipo === 'change' && (
            <div className="u-stack-8">
              <Switch checked={!!form.hubo_marcha_atras} disabled={!editable} onChange={v => set('hubo_marcha_atras', v)}
                label={t('pir.hubo_marcha_atras')} ayuda={form.hubo_marcha_atras === null ? t('pir.marcha_atras_sin_decir') : undefined} />
              {form.hubo_marcha_atras && (
                <Textarea label={t('pir.marcha_atras_detalle')} value={form.marcha_atras_detalle} disabled={!editable}
                  onChange={e => set('marcha_atras_detalle', e.target.value)} rows={2} />
              )}
            </div>
          )}
          <Textarea label={t('pir.resumen')} value={form.resumen} disabled={!editable} rows={3}
            onChange={e => set('resumen', e.target.value)} />
          {pir.cuenta_en_modelo && <p className="pir-apagado">{t('pir.cuenta_en_modelo')}</p>}
        </section>

        {/* Preguntas */}
        {form.preguntas.length > 0 && (
          <section className="pir-bloque" aria-labelledby={`${id}-preg`}>
            <h3 id={`${id}-preg`} className="pir-bloque__titulo"><ClipboardList size={16} aria-hidden />{t('pir.preguntas')}</h3>
            {form.preguntas.map((q, i) => (
              <Textarea key={q.clave} label={q.texto} value={q.respuesta} disabled={!editable} rows={2}
                onChange={e => set('preguntas', form.preguntas.map((x, j): PreguntaPir => (j === i ? { ...x, respuesta: e.target.value } : x)))} />
            ))}
          </section>
        )}

        {/* Incidencias */}
        <Incidencias pir={pir} ids={form.incidencias} editable={editable} onChange={v => set('incidencias', v)} />

        {/* KPIs */}
        <Kpis kpis={form.kpis} editable={editable} onChange={v => set('kpis', v)} idBase={id} />

        {/* Beneficios y satisfacción (proyectos) */}
        {pir.origen_tipo === 'project' && (
          <Beneficios beneficios={form.beneficios} editable={editable} onChange={v => set('beneficios', v)} idBase={id} />
        )}
        <Satisfaccion filas={form.satisfaccion} media={pir.satisfaccion_media} editable={editable}
          onChange={v => set('satisfaccion', v)} idBase={id} />

        {/* Acciones y lecciones */}
        <Acciones pir={pir} puede={!!p?.acciones} opcionesUsuario={opcionesUsuario} onHecho={refrescar} />
        <Lecciones pir={pir} onHecho={refrescar} />

        {(pir.enviado_en || pir.aprobado_en || pir.cerrado_en) && (
          <p className="pir-apagado">
            {[pir.enviado_en && t('pir.enviada_por', { quien: pir.enviado_por ?? '—', cuando: fmtDateTime(pir.enviado_en) }),
              pir.aprobado_en && t('pir.aprobada_por', { quien: pir.aprobado_por ?? '—', cuando: fmtDateTime(pir.aprobado_en) }),
              pir.cerrado_en && t('pir.cerrada_por', { quien: pir.cerrado_por ?? '—', cuando: fmtDateTime(pir.cerrado_en) })]
              .filter(Boolean).join(' · ')}
          </p>
        )}

        <div className="pir-acciones-pie">
          {p?.borrar && (
            <Button variant="danger" icon={<Trash2 size={14} />} disabled={accion.isPending}
              onClick={async () => {
                if (await confirmar({ message: t('pir.borrar_confirmar', { codigo: pir.codigo }), danger: true })) {
                  accion.mutate(() => pirApi.borrar(id), { onSuccess: onClose })
                }
              }}>{t('pir.borrar')}</Button>
          )}
          {p?.descartar && (
            <Button variant="secondary" icon={<XCircle size={14} />} disabled={accion.isPending}
              onClick={() => conMotivo(t('pir.descartar'), m => pirApi.descartar(id, m))}>{t('pir.descartar')}</Button>
          )}
          {p?.reabrir && (
            <Button variant="secondary" icon={<RotateCcw size={14} />} disabled={accion.isPending}
              onClick={() => conMotivo(t('pir.reabrir'), m => pirApi.reabrir(id, m))}>{t('pir.reabrir')}</Button>
          )}
          {p?.devolver && (
            <Button variant="secondary" icon={<Undo2 size={14} />} disabled={accion.isPending}
              onClick={() => conMotivo(t('pir.devolver'), m => pirApi.devolver(id, m))}>{t('pir.devolver')}</Button>
          )}
          {editable && <Button variant="secondary" onClick={guardar} loading={accion.isPending} disabled={!cambiado}>{t('pir.guardar')}</Button>}
          {p?.enviar && <Button icon={<Send size={14} />} onClick={enviar} loading={accion.isPending}>{t('pir.enviar')}</Button>}
          {p?.aprobar && (
            <Button icon={<CheckCircle2 size={14} />} disabled={accion.isPending}
              onClick={async () => {
                const c = await pedirTexto({ title: t('pir.aprobar'), message: t('pir.aprobar_confirmar', { codigo: pir.codigo }), label: t('pir.comentario'), multiline: true })
                if (c !== null) accion.mutate(() => pirApi.aprobar(id, c || undefined))
              }}>{t('pir.aprobar')}</Button>
          )}
          {p?.cerrar && <Button icon={<CheckCircle2 size={14} />} onClick={() => accion.mutate(() => pirApi.cerrar(id))} loading={accion.isPending}>{t('pir.cerrar')}</Button>}
        </div>
      </div>
    </Modal>
  )
}

function Criterio({ c, editable, onChange }: { c: CriterioPir; editable: boolean; onChange: (c: CriterioPir) => void }) {
  const t = useAppT()
  return (
    <div className="pir-criterio">
      <span>{c.texto}</span>
      <Segmentado aria-label={c.texto} valor={c.resultado ?? ''} onChange={v => editable && onChange({ ...c, resultado: v as CumplimientoPir })}
        opciones={CUMPLE.map(v => ({ valor: v, etiqueta: t(`pir.cumple_${v}`), disabled: !editable }))} />
      <Input aria-label={t('pir.comentario_de', { criterio: c.texto })} value={c.comentario} disabled={!editable}
        placeholder={t('pir.comentario')} onChange={e => onChange({ ...c, comentario: e.target.value })} />
    </div>
  )
}

function Incidencias({ pir, ids, editable, onChange }: { pir: PirDetalle; ids: string[]; editable: boolean; onChange: (v: string[]) => void }) {
  const t = useAppT()
  const [q, setQ] = useState('')
  const conocidas = new Map(pir.incidencias.map(i => [i.id, i]))
  const { data: encontrados = [] } = useQuery({
    queryKey: ['pir', 'tickets', q], enabled: editable && q.trim().length >= 2,
    queryFn: () => ticketsApi.list({ search: q.trim(), page_size: 8 }).then(r => (Array.isArray(r.data) ? r.data : [])),
  })
  const [vistos, setVistos] = useState<Record<string, { number?: string | null; title?: string | null }>>({})
  const etiqueta = (tid: string) => {
    const i = conocidas.get(tid) ?? vistos[tid]
    return i ? [i.number, i.title].filter(Boolean).join(' · ') : tid
  }
  return (
    <section className="pir-bloque" aria-label={t('pir.incidencias')}>
      <h3 className="pir-bloque__titulo"><AlertTriangle size={16} aria-hidden />{t('pir.incidencias')}</h3>
      {ids.length === 0 ? <p className="pir-apagado">{t('pir.sin_incidencias')}</p> : (
        <ul className="pir-lista-simple">
          {ids.map(tid => (
            <li key={tid}>{etiqueta(tid)}{editable && (
              <IconButton variante="caja" tamano="xs" tono="peligro" ariaLabel={t('pir.quitar_incidencia', { ticket: etiqueta(tid) })}
                onClick={() => onChange(ids.filter(x => x !== tid))}><X /></IconButton>)}</li>
          ))}
        </ul>
      )}
      {editable && (
        <div className="u-stack-6">
          <Buscador value={q} onChange={setQ} retardo={300} placeholder={t('pir.buscar_ticket')} />
          {encontrados.filter(tk => !ids.includes(String(tk.id))).map(tk => (
            <Button key={tk.id} variant="ghost" size="sm" icon={<Plus size={12} />}
              onClick={() => { setVistos(v => ({ ...v, [String(tk.id)]: { number: tk.number, title: tk.title } })); onChange([...ids, String(tk.id)]) }}>
              {[tk.number, tk.title].filter(Boolean).join(' · ')}
            </Button>
          ))}
        </div>
      )}
    </section>
  )
}

function Kpis({ kpis, editable, onChange, idBase }: { kpis: KpiPir[]; editable: boolean; onChange: (v: KpiPir[]) => void; idBase: string }) {
  const t = useAppT()
  const fila = (i: number, k: Partial<KpiPir>) => onChange(kpis.map((x, j) => (j === i ? { ...x, ...k } : x)))
  return (
    <section className="pir-bloque" aria-labelledby={`${idBase}-kpi`}>
      <h3 id={`${idBase}-kpi`} className="pir-bloque__titulo"><BarChart3 size={16} aria-hidden />{t('pir.kpis')}</h3>
      {kpis.length === 0 && <p className="pir-apagado">{t('pir.sin_kpis')}</p>}
      {kpis.map((k, i) => (
        <div key={i} className="pir-fila-editable">
          <Input label={t('pir.kpi_nombre')} value={k.nombre} disabled={!editable} onChange={e => fila(i, { nombre: e.target.value })} />
          <Input label={t('pir.kpi_unidad')} value={k.unidad} disabled={!editable} onChange={e => fila(i, { unidad: e.target.value })} />
          <Input label={t('pir.kpi_antes')} type="number" value={k.antes ?? ''} disabled={!editable} onChange={e => fila(i, { antes: numero(e.target.value) })} />
          <Input label={t('pir.kpi_despues')} type="number" value={k.despues ?? ''} disabled={!editable} onChange={e => fila(i, { despues: numero(e.target.value) })} />
          <Input label={t('pir.kpi_objetivo')} type="number" value={k.objetivo ?? ''} disabled={!editable} onChange={e => fila(i, { objetivo: numero(e.target.value) })} />
          {editable && <IconButton variante="caja" tono="peligro" ariaLabel={t('pir.quitar_kpi', { nombre: k.nombre })}
            onClick={() => onChange(kpis.filter((_x, j) => j !== i))}><Trash2 /></IconButton>}
        </div>
      ))}
      {editable && <div><Button variant="ghost" size="sm" icon={<Plus size={12} />}
        onClick={() => onChange([...kpis, { nombre: '', unidad: '', antes: null, despues: null, objetivo: null }])}>{t('pir.anadir_kpi')}</Button></div>}
    </section>
  )
}

function Beneficios({ beneficios, editable, onChange, idBase }: { beneficios: BeneficioPir[]; editable: boolean; onChange: (v: BeneficioPir[]) => void; idBase: string }) {
  const t = useAppT()
  const fila = (i: number, b: Partial<BeneficioPir>) => onChange(beneficios.map((x, j) => (j === i ? { ...x, ...b } : x)))
  return (
    <section className="pir-bloque" aria-labelledby={`${idBase}-ben`}>
      <h3 id={`${idBase}-ben`} className="pir-bloque__titulo"><BarChart3 size={16} aria-hidden />{t('pir.beneficios')}</h3>
      <p className="pir-apagado">{t('pir.beneficios_ayuda')}</p>
      {beneficios.length === 0 && <p className="pir-apagado">{t('pir.sin_beneficios')}</p>}
      {beneficios.map((b, i) => (
        <div key={b.benefit_id ?? i} className="u-stack-6">
          <div className="pir-fila-editable">
            <Input label={t('pir.beneficio')} value={b.nombre} disabled={!editable || !!b.benefit_id} onChange={e => fila(i, { nombre: e.target.value })} />
            <Input label={`${t('pir.previsto')}${b.unidad ? ` (${b.unidad})` : ''}`} type="number" value={b.previsto ?? ''}
              disabled={!editable || !!b.benefit_id} onChange={e => fila(i, { previsto: numero(e.target.value) })} />
            <Input label={`${t('pir.conseguido')}${b.unidad ? ` (${b.unidad})` : ''}`} type="number" value={b.conseguido ?? ''}
              disabled={!editable} onChange={e => fila(i, { conseguido: numero(e.target.value) })} />
            <Input label={t('pir.comentario')} value={b.comentario} disabled={!editable} onChange={e => fila(i, { comentario: e.target.value })} />
            {editable && !b.benefit_id && <IconButton variante="caja" tono="peligro" ariaLabel={t('pir.quitar_beneficio', { nombre: b.nombre })}
              onClick={() => onChange(beneficios.filter((_x, j) => j !== i))}><Trash2 /></IconButton>}
          </div>
          {editable && b.benefit_id && (
            <Checkbox checked={!!b.actualizar} onChange={v => fila(i, { actualizar: v })} label={t('pir.actualizar_beneficio')} />
          )}
        </div>
      ))}
      {editable && <div><Button variant="ghost" size="sm" icon={<Plus size={12} />}
        onClick={() => onChange([...beneficios, { benefit_id: null, nombre: '', previsto: null, conseguido: null, comentario: '' }])}>{t('pir.anadir_beneficio')}</Button></div>}
    </section>
  )
}

function Satisfaccion({ filas, media, editable, onChange, idBase }: { filas: SatisfaccionPir[]; media: number | null; editable: boolean; onChange: (v: SatisfaccionPir[]) => void; idBase: string }) {
  const t = useAppT()
  const fila = (i: number, s: Partial<SatisfaccionPir>) => onChange(filas.map((x, j) => (j === i ? { ...x, ...s } : x)))
  return (
    <section className="pir-bloque" aria-labelledby={`${idBase}-sat`}>
      <h3 id={`${idBase}-sat`} className="pir-bloque__titulo"><Users size={16} aria-hidden />{t('pir.satisfaccion')}
        {media !== null && <StatusBadge kind="info">{t('pir.media', { media })}</StatusBadge>}</h3>
      {filas.length === 0 && <p className="pir-apagado">{t('pir.sin_satisfaccion')}</p>}
      {filas.map((s, i) => (
        <div key={i} className="pir-fila-editable">
          <Input label={t('pir.interesado')} value={s.interesado} disabled={!editable} onChange={e => fila(i, { interesado: e.target.value })} />
          <Input label={t('pir.rol')} value={s.rol} disabled={!editable} onChange={e => fila(i, { rol: e.target.value })} />
          <Input label={t('pir.puntuacion')} type="number" min={1} max={5} value={s.puntuacion ?? ''} disabled={!editable}
            onChange={e => fila(i, { puntuacion: numero(e.target.value) })} />
          <Input label={t('pir.comentario')} value={s.comentario} disabled={!editable} onChange={e => fila(i, { comentario: e.target.value })} />
          {editable && <IconButton variante="caja" tono="peligro" ariaLabel={t('pir.quitar_interesado', { nombre: s.interesado })}
            onClick={() => onChange(filas.filter((_x, j) => j !== i))}><Trash2 /></IconButton>}
        </div>
      ))}
      {editable && <div><Button variant="ghost" size="sm" icon={<Plus size={12} />}
        onClick={() => onChange([...filas, { interesado: '', rol: '', puntuacion: null, comentario: '' }])}>{t('pir.anadir_interesado')}</Button></div>}
    </section>
  )
}

function Acciones({ pir, puede, opcionesUsuario, onHecho }: {
  pir: PirDetalle; puede: boolean; opcionesUsuario: { valor: string; etiqueta: string }[]; onHecho: () => void
}) {
  const t = useAppT()
  const toast = useToast()
  const [nueva, setNueva] = useState({ descripcion: '', responsable_id: '', fecha_limite: '' })
  const crear = useMutation({
    mutationFn: () => pirApi.crearAccion(pir.id, { descripcion: nueva.descripcion.trim(), responsable_id: nueva.responsable_id || null, fecha_limite: nueva.fecha_limite || null }),
    onSuccess: r => {
      setNueva({ descripcion: '', responsable_id: '', fecha_limite: '' })
      if (r.sin_tarea) toast.warning(t('pir.accion_sin_tarea'))
      else toast.success(t('pir.accion_creada', { tarea: r.accion.task_code ?? '' }))
      onHecho()
    },
    onError: e => toast.error(extractErr(e)),
  })
  const editar = useMutation({
    mutationFn: ({ aid, estado }: { aid: string; estado: 'hecha' | 'descartada' | 'abierta' }) => pirApi.editarAccion(pir.id, aid, { estado }),
    onSuccess: () => onHecho(),
    onError: e => toast.error(extractErr(e)),
  })
  return (
    <section className="pir-bloque" aria-label={t('pir.acciones')}>
      <h3 className="pir-bloque__titulo"><ListChecks size={16} aria-hidden />{t('pir.acciones')}</h3>
      {pir.acciones.length === 0 ? <p className="pir-apagado">{t('pir.sin_acciones')}</p> : (
        <ul className="pir-lista-simple">
          {pir.acciones.map(a => (
            <li key={a.id}>
              <StatusBadge kind={a.estado === 'hecha' ? 'success' : a.vencida ? 'danger' : 'neutral'}>{t(`pir.accion_${a.estado}`)}</StatusBadge>
              <span>{a.descripcion}</span>
              <span className="pir-apagado">{[a.responsable, a.fecha_limite && fmtDate(a.fecha_limite), a.task_code].filter(Boolean).join(' · ')}</span>
              {puede && a.estado === 'abierta' && (
                <Button size="xs" variant="ghost" onClick={() => editar.mutate({ aid: a.id, estado: 'hecha' })}>{t('pir.marcar_hecha')}</Button>
              )}
            </li>
          ))}
        </ul>
      )}
      {puede && pir.estado !== 'descartado' && (
        <div className="pir-fila-editable">
          <Input label={t('pir.accion_descripcion')} value={nueva.descripcion} onChange={e => setNueva(n => ({ ...n, descripcion: e.target.value }))} />
          <SelectRico label={t('pir.responsable')} valor={nueva.responsable_id} onChange={v => setNueva(n => ({ ...n, responsable_id: v }))}
            opciones={[{ valor: '', etiqueta: t('pir.sin_responsable') }, ...opcionesUsuario]} />
          <div className="u-stack-6">
            <DateInput label={t('pir.fecha_limite')} value={nueva.fecha_limite} onChange={e => setNueva(n => ({ ...n, fecha_limite: e.target.value }))} /></div>
          <Button icon={<Plus size={14} />} disabled={nueva.descripcion.trim().length < 3} loading={crear.isPending}
            onClick={() => crear.mutate()}>{t('pir.anadir_accion')}</Button>
        </div>
      )}
    </section>
  )
}

function Lecciones({ pir, onHecho }: { pir: PirDetalle; onHecho: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const [abierta, setAbierta] = useState(false)
  const [f, setF] = useState({ titulo: '', categoria: '', que_paso: '', recomendacion: '', tipo: 'evitar' as 'evitar' | 'repetir' })
  const { data: config } = useQuery({ queryKey: ['lecciones', 'config'], queryFn: () => leccionesApi.config(), enabled: abierta })
  const categorias: string[] = config?.categorias ?? []
  const crear = useMutation({
    mutationFn: () => pirApi.crearLeccion(pir.id, { ...f, categoria: f.categoria || categorias[0] || '' }),
    onSuccess: r => { toast.success(t('pir.leccion_creada', { codigo: r.codigo })); setAbierta(false); onHecho() },
    onError: e => toast.error(extractErr(e)),
  })
  return (
    <section className="pir-bloque" aria-label={t('pir.lecciones')}>
      <h3 className="pir-bloque__titulo"><Lightbulb size={16} aria-hidden />{t('pir.lecciones')}</h3>
      {pir.lecciones.length === 0 ? <p className="pir-apagado">{t('pir.sin_lecciones')}</p> : (
        <ul className="pir-lista-simple">
          {pir.lecciones.map(l => <li key={l.id}><span>{l.codigo}</span><span>{l.titulo}</span><StatusBadge kind="neutral">{l.estado}</StatusBadge></li>)}
        </ul>
      )}
      {!abierta ? (
        <div><Button variant="ghost" size="sm" icon={<Plus size={12} />} onClick={() => setAbierta(true)}>{t('pir.anadir_leccion')}</Button></div>
      ) : (
        <div className="u-stack-8">
          <div className="pir-rejilla">
            <Input label={t('pir.leccion_titulo')} value={f.titulo} onChange={e => setF(x => ({ ...x, titulo: e.target.value }))} />
            <SelectRico label={t('pir.leccion_categoria')} valor={f.categoria || categorias[0] || ''} onChange={v => setF(x => ({ ...x, categoria: v }))}
              opciones={categorias.map(c => ({ valor: c, etiqueta: c }))} />
            <div className="u-stack-6"><span className="pir-apagado">{t('pir.leccion_tipo')}</span>
              <Segmentado aria-label={t('pir.leccion_tipo')} valor={f.tipo} onChange={v => setF(x => ({ ...x, tipo: v as 'evitar' | 'repetir' }))}
                opciones={[{ valor: 'evitar', etiqueta: t('pir.leccion_evitar') }, { valor: 'repetir', etiqueta: t('pir.leccion_repetir') }]} /></div>
          </div>
          <Textarea label={t('pir.leccion_que_paso')} value={f.que_paso} rows={2} onChange={e => setF(x => ({ ...x, que_paso: e.target.value }))} />
          <Textarea label={t('pir.leccion_recomendacion')} value={f.recomendacion} rows={2} onChange={e => setF(x => ({ ...x, recomendacion: e.target.value }))} />
          <div className="pir-acciones-pie">
            <Button variant="secondary" onClick={() => setAbierta(false)}>{t('pir.cancelar')}</Button>
            <Button icon={<Lightbulb size={14} />} loading={crear.isPending}
              disabled={!f.titulo.trim() || !f.que_paso.trim() || !f.recomendacion.trim() || !(f.categoria || categorias[0])}
              onClick={() => crear.mutate()}>{t('pir.crear_leccion')}</Button>
          </div>
        </div>
      )}
    </section>
  )
}
