/**
 * Tipos de ausencia (tarea #25): nombre por idioma, color, icono, saldo y
 * unidad, visibilidad, flujo por defecto, sustituto, datos de salud y los
 * documentos que pide cada tipo con su plazo, recordatorio, repetición y
 * escalado. Todo con controles: nadie escribe JSON.
 *
 * Rev. 180: modos de petición (días, medio día, horas), retribuido, saldo
 * «bolsa de horas», periodo del saldo y mes de inicio, arrastre máximo y su
 * caducidad, caducidad de los apuntes, prorrateo por alta, tabla de referencia
 * del derecho (tablas numéricas de Políticas) y reglas de la bolsa.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, Umbrella } from 'lucide-react'
import { ausenciasApi } from '../../../services/api/ausencias'
import { approvalsApi } from '../../../services/api'
import type {
  DestinatarioDeAviso, ModoDePeticion, PeriodoDeSaldo, PlazoDesde, ReglasDeBolsa, RequisitoDocumental, Saldo, TipoDeAusencia,
  TipoDeAusenciaIn, TipoDeDocumento,
} from '../../../services/api/tipos-ausencias'
import { Button, EmptyState, Modal, Spinner, Select, Pulsable, IconButton , useErroresDeCampo, Input } from '../../ui'
import { confirmar } from '../../../context/ConfirmContext'
import { useToast } from '../../../context/ToastContext'
import { SelectorDeEntidad, useOpciones } from '../../politicas/comun'
import IconoDeAusencia, { ICONOS_DE_AUSENCIA } from '../IconoDeAusencia'
import { AvisoDeError, ErrorDeCampo, hayDeCampo, colorPorDefecto, Casilla, Muestra, NombresPorIdioma, errorDe, nombreEn, useT } from './comun'

const tipoNuevo = (): TipoDeAusenciaIn => ({
  clave: '', nombre: '', nombres: {}, color: colorPorDefecto(), icono: 'umbrella', descuenta_saldo: false, saldo: null,
  cupo_anual: null, unidad: 'dias', visibilidad: 'equipo', workflow_id: null, requiere_aprobacion: true,
  requiere_sustituto: false, datos_especiales: false, activo: true, orden: 100, requisitos: [],
  modos: ['dias', 'medio_dia'], retribuido: true, periodo_saldo: 'anual', inicio_periodo_mes: 1, arrastre_max: null,
  arrastre_caduca_meses: null, caduca_meses: null, prorratear_alta: false, derecho_tabla_id: null, bolsa: null,
})
/** Reglas neutras de una bolsa nueva: cada hora de más cuenta una hora, sin umbral ni topes. */
const bolsaNueva = (): ReglasDeBolsa => ({
  factor: 1, factor_festivo: 1, factor_no_laborable: 1, umbral_minutos: 0, tope_diario: null, tope_periodo: null, solo_aprobadas: true,
  solo_horas_extra: false,
})
const MODOS: ModoDePeticion[] = ['dias', 'medio_dia', 'horas']
const SALDOS: Saldo[] = ['vacaciones', 'propio', 'bolsa']
const PERIODOS: PeriodoDeSaldo[] = ['anual', 'semestral', 'trimestral', 'mensual', 'sin_periodo']
const MESES = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
/** Un número opcional de un input (vacío = null). */
const numOpcional = (v: string): number | null => (v === '' ? null : Number(v))
const PLAZOS: PlazoDesde[] = ['solicitud', 'inicio', 'fin']
const DESTINOS: DestinatarioDeAviso['tipo'][] = ['responsable', 'rol', 'persona', 'departamento', 'grupo', 'solicitante']
const CLASE = { persona: 'usuario', rol: 'rol', departamento: 'departamento', grupo: 'grupo' } as const

export default function EditorDeTipos() {
  const { ta, lang } = useT()
  const [abierto, setAbierto] = useState<{ id: string | null; datos: TipoDeAusenciaIn } | null>(null)
  const q = useQuery({ queryKey: ['ausencias', 'tipos', 'todos'], queryFn: () => ausenciasApi.tipos(true) })
  if (q.isLoading) return <Spinner label={ta('cargando')} />
  if (q.isError) return <AvisoDeError error={q.error} defecto={ta('error_cargar')} />
  const tipos = q.data ?? []
  return (
    <section aria-labelledby="ausadm-tipos-titulo">
      <div className="ausadm-cabecera">
        <h2 id="ausadm-tipos-titulo" className="ausadm-titulo">{ta('tipos_titulo')}</h2>
        <Button icon={<Plus size={14} />} onClick={() => setAbierto({ id: null, datos: tipoNuevo() })}>{ta('nuevo_tipo')}</Button>
      </div>
      <p className="ausadm-ayuda">{ta('tipos_ayuda')}</p>
      {tipos.length === 0
        ? <EmptyState svgIcon={<Umbrella size={26} />} title={ta('sin_tipos')} ctaLabel={ta('nuevo_tipo')}
            onCta={() => setAbierto({ id: null, datos: tipoNuevo() })} />
        : (
          <ul className="ausadm-lista">
            {tipos.map(t => (
              <li key={t.id}>
                <Pulsable className={`ausadm-item${t.activo ? '' : ' ausadm-item--inactivo'}`}
                  onClick={() => setAbierto({ id: t.id, datos: aEntrada(t) })}>
                  <Muestra color={t.color} className="ausadm-muestra--icono"><IconoDeAusencia icono={t.icono} /></Muestra>
                  <span className="ausadm-item-nombre">{nombreEn(t, lang)} <span className="ausadm-ayuda">({t.clave})</span></span>
                  <span className="ausadm-chips">
                    {t.descuenta_saldo && <span className="ausadm-chip">{ta(`saldo_${t.saldo}`)}</span>}
                    <span className="ausadm-chip">{ta(`unidad_${t.unidad}`)}</span>
                    {(t.modos ?? []).map(m => <span key={m} className="ausadm-chip">{ta(`modo_${m}`)}</span>)}
                    {t.retribuido === false && <span className="ausadm-chip">{ta('no_retribuido')}</span>}
                    <span className="ausadm-chip">{ta(`visibilidad_${t.visibilidad}`)}</span>
                    {t.datos_especiales && <span className="ausadm-chip ausadm-chip--aviso">{ta('datos_especiales_corto')}</span>}
                    {t.requisitos.length > 0 && <span className="ausadm-chip">{ta('n_documentos', { n: t.requisitos.length })}</span>}
                    {t.de_sistema && <span className="ausadm-chip">{ta('de_sistema')}</span>}
                    {!t.activo && <span className="ausadm-chip">{ta('inactivo')}</span>}
                  </span>
                </Pulsable>
              </li>
            ))}
          </ul>
        )}
      {abierto && <FormularioDeTipo key={abierto.id ?? 'nuevo'} id={abierto.id} inicial={abierto.datos}
        deSistema={tipos.find(t => t.id === abierto.id)?.de_sistema ?? false} onCerrar={() => setAbierto(null)} />}
    </section>
  )
}

function aEntrada(t: TipoDeAusencia): TipoDeAusenciaIn {
  const { id: _id, de_sistema: _s, ...resto } = t
  const base = tipoNuevo()
  return {
    ...resto, requisitos: t.requisitos.map(r => ({ ...r })),
    // Tipos de antes de la rev. 180 sin estos campos: los valores neutros.
    modos: t.modos?.length ? [...t.modos] : base.modos, retribuido: t.retribuido ?? base.retribuido,
    periodo_saldo: t.periodo_saldo ?? base.periodo_saldo, inicio_periodo_mes: t.inicio_periodo_mes ?? base.inicio_periodo_mes,
    arrastre_max: t.arrastre_max ?? null, arrastre_caduca_meses: t.arrastre_caduca_meses ?? null, caduca_meses: t.caduca_meses ?? null,
    prorratear_alta: t.prorratear_alta ?? false, derecho_tabla_id: t.derecho_tabla_id ?? null, bolsa: t.bolsa ? { ...t.bolsa } : null,
  }
}

function FormularioDeTipo({ id, inicial, deSistema, onCerrar }: {
  id: string | null; inicial: TipoDeAusenciaIn; deSistema: boolean; onCerrar: () => void
}) {
  const { ta } = useT()
  const qc = useQueryClient()
  const toast = useToast()
  const [d, setD] = useState<TipoDeAusenciaIn>(inicial)
  const campos = useErroresDeCampo()
  const cambiar = (c: Partial<TipoDeAusenciaIn>) => { Object.keys(c).forEach(k => campos.limpiar(k)); setD(x => ({ ...x, ...c })) }
  const flujos = useQuery({
    queryKey: ['ausencias', 'flujos-leave'],
    queryFn: () => approvalsApi.listWorkflows({ entity_type: 'leave' }).then(r => (r.data ?? []).filter(w => w.entity_type === 'leave')),
  })
  const documentos = useQuery({ queryKey: ['ausencias', 'documentos'], queryFn: () => ausenciasApi.documentos() })
  const opciones = useOpciones().data
  // Tablas de referencia numéricas de Políticas (de ausencias o de cualquier dominio) para el derecho.
  const tablas = (opciones?.tablas ?? []).filter(x => x.tipo_de_valor === 'numero' && (!x.dominio || x.dominio === 'ausencias'))
  const refrescar = () => qc.invalidateQueries({ queryKey: ['ausencias'] })
  const guardar = useMutation({
    onMutate: () => campos.limpiar(),
    onError: e => { campos.recoger(e) },
    mutationFn: () => (id ? ausenciasApi.guardarTipo(id, d) : ausenciasApi.crearTipo(d)),
    onSuccess: () => { toast.success(ta('guardado')); refrescar(); onCerrar() },
  })
  const borrar = useMutation({
    mutationFn: () => ausenciasApi.borrarTipo(id as string),
    onSuccess: r => { toast.success(r.desactivado ? ta('desactivado_en_uso') : ta('borrado')); refrescar(); onCerrar() },
    onError: e => toast.error(errorDe(e, ta('error_guardar')).mensaje),
  })
  return (
    <Modal open onClose={onCerrar} title={id ? ta('editar_tipo') : ta('nuevo_tipo')} size="lg">
      <form className="ausadm-form" onSubmit={e => { e.preventDefault(); guardar.mutate() }}>
        <div className="ausadm-grid-2">
          <label className="ausadm-campo-con-etiqueta">
            <span className="ausadm-etiqueta">{ta('clave')}</span>
            <Input aria-label={ta('clave')} required pattern="[a-z0-9_]{2,50}" value={d.clave} disabled={deSistema} aria-describedby="ausadm-clave-ayuda" onChange={e => cambiar({ clave: e.target.value.toLowerCase() })} inputClassName="ausadm-campo" />
            <span id="ausadm-clave-ayuda" className="ausadm-ayuda">{ta('clave_ayuda')}</span>
            <ErrorDeCampo texto={campos.de('clave')} />
          </label>
          <label className="ausadm-campo-con-etiqueta">
            <span className="ausadm-etiqueta">{ta('nombre_principal')}</span>
            <Input aria-label={ta('nombre_principal')} value={d.nombre} onChange={e => cambiar({ nombre: e.target.value })} inputClassName="ausadm-campo" />
            <ErrorDeCampo texto={campos.de('nombre')} />
          </label>
        </div>
        <NombresPorIdioma valor={d.nombres} onChange={nombres => cambiar({ nombres })} />
        <div className="ausadm-grid-2">
          <label className="ausadm-campo-con-etiqueta">
            <span className="ausadm-etiqueta">{ta('color')}</span>
            <input aria-label={ta('color')} type="color" className="ausadm-color" value={d.color} onChange={e => cambiar({ color: e.target.value })} />
          </label>
          <fieldset className="ds-grupo-opciones ausadm-fieldset">
            <legend className="ausadm-etiqueta">{ta('icono')}</legend>
            <div className="ausadm-iconos" role="radiogroup" aria-label={ta('icono')}>
              {Object.keys(ICONOS_DE_AUSENCIA).map(nombre => (
                <IconButton key={nombre} role="radio" aria-checked={d.icono === nombre}
                  className="ausadm-icono" ariaLabel={ta(`icono_${nombre}`)} title={ta(`icono_${nombre}`)}
                  onClick={() => cambiar({ icono: nombre })}><IconoDeAusencia icono={nombre} /></IconButton>
              ))}
            </div>
          </fieldset>
        </div>
        <div className="ausadm-grid-2">
          <label className="ausadm-campo-con-etiqueta">
            <span className="ausadm-etiqueta">{ta('unidad')}</span>
            <Select suelto className="ausadm-campo" value={d.unidad} onChange={e => cambiar({ unidad: e.target.value as TipoDeAusenciaIn['unidad'] })} placeholder={false}>
              {(['dias', 'medios_dias', 'horas'] as const).map(u => <option key={u} value={u}>{ta(`unidad_${u}`)}</option>)}
            </Select>
          </label>
          <label className="ausadm-campo-con-etiqueta">
            <span className="ausadm-etiqueta">{ta('visibilidad')}</span>
            <Select suelto className="ausadm-campo" value={d.visibilidad} aria-describedby="ausadm-vis-ayuda"
              onChange={e => cambiar({ visibilidad: e.target.value as TipoDeAusenciaIn['visibilidad'] })} placeholder={false}>
              {(['todos', 'equipo', 'privada'] as const).map(v => <option key={v} value={v}>{ta(`visibilidad_${v}`)}</option>)}
            </Select>
            <span id="ausadm-vis-ayuda" className="ausadm-ayuda">{ta(`visibilidad_${d.visibilidad}_ayuda`)}</span>
          </label>
        </div>
        <fieldset className="ds-grupo-opciones ausadm-fieldset">
          <legend className="ausadm-etiqueta">{ta('modos_de_peticion')}</legend>
          <div className="ausadm-fila">
            {MODOS.map(m => (
              <Casilla key={m} etiqueta={ta(`modo_${m}`)} valor={d.modos.includes(m)}
                onChange={v => cambiar({ modos: v ? MODOS.filter(x => x === m || d.modos.includes(x)) : d.modos.filter(x => x !== m) })} />
            ))}
          </div>
          <span className="ausadm-ayuda">{d.modos.length ? ta('modos_ayuda') : ta('modos_vacio')}</span>
          <Casilla etiqueta={ta('retribuido')} ayuda={ta('retribuido_ayuda')} valor={d.retribuido} onChange={v => cambiar({ retribuido: v })} />
        </fieldset>
        <fieldset className="ds-grupo-opciones ausadm-fieldset">
          <legend className="ausadm-etiqueta">{ta('saldo')}</legend>
          <Casilla etiqueta={ta('descuenta_saldo')} valor={d.descuenta_saldo}
            onChange={v => cambiar({ descuenta_saldo: v, saldo: v ? (d.saldo ?? 'vacaciones') : null })} />
          {d.descuenta_saldo && (
            <>
              <div className="ausadm-fila">
                <Select suelto className="ausadm-campo" aria-label={ta('que_saldo')} value={d.saldo ?? 'vacaciones'}
                  onChange={e => { const s = e.target.value as Saldo; cambiar({ saldo: s, bolsa: s === 'bolsa' ? (d.bolsa ?? bolsaNueva()) : null }) }} placeholder={false}>
                  {SALDOS.map(s => <option key={s} value={s}>{ta(`saldo_${s}`)}</option>)}
                </Select>
                {d.saldo === 'propio' && (
                  <label className="ausadm-fila">
                    <span className="ausadm-ayuda">{ta('cupo_anual', { unidad: ta(`unidad_${d.unidad}`) })}</span>
                    <input aria-label={ta('cupo_anual', { unidad: ta(`unidad_${d.unidad}`) })} type="number" min={0} step="0.5" className="ausadm-campo ausadm-campo--corto"
                      required={!d.derecho_tabla_id}
                      value={d.cupo_anual ?? ''} onChange={e => cambiar({ cupo_anual: numOpcional(e.target.value) })} />
                    <ErrorDeCampo texto={campos.de('cupo_anual')} />
                  </label>
                )}
              </div>
              <span className="ausadm-ayuda">{ta(`saldo_${d.saldo ?? 'vacaciones'}_ayuda`)}</span>
              <div className="ausadm-grid-2">
                <label className="ausadm-campo-con-etiqueta">
                  <span className="ausadm-etiqueta">{ta('periodo_saldo')}</span>
                  <Select suelto className="ausadm-campo" value={d.periodo_saldo} placeholder={false}
                    onChange={e => cambiar({ periodo_saldo: e.target.value as PeriodoDeSaldo })}>
                    {PERIODOS.map(x => <option key={x} value={x}>{ta(`periodo_${x}`)}</option>)}
                  </Select>
                </label>
                {d.periodo_saldo !== 'sin_periodo' && d.periodo_saldo !== 'mensual' && (
                  <label className="ausadm-campo-con-etiqueta">
                    <span className="ausadm-etiqueta">{ta('inicio_periodo_mes')}</span>
                    <Select suelto className="ausadm-campo" value={String(d.inicio_periodo_mes)} placeholder={false}
                      onChange={e => cambiar({ inicio_periodo_mes: Number(e.target.value) })}>
                      {MESES.map(m => <option key={m} value={m}>{ta(`mes_${m}`)}</option>)}
                    </Select>
                  </label>
                )}
                {d.saldo !== 'bolsa' && (
                  <label className="ausadm-campo-con-etiqueta">
                    <span className="ausadm-etiqueta">{ta('derecho_tabla')}</span>
                    <Select suelto className="ausadm-campo" value={d.derecho_tabla_id ?? ''} aria-describedby="ausadm-tabla-ayuda"
                      onChange={e => cambiar({ derecho_tabla_id: e.target.value || null })} placeholder={tablas.length ? ta('sin_tabla') : ta('no_hay_tablas')}>
                      {tablas.map(x => <option key={x.id} value={x.id}>{x.nombre}</option>)}
                    </Select>
                    <span id="ausadm-tabla-ayuda" className="ausadm-ayuda">{ta('derecho_tabla_ayuda')}</span>
                  </label>
                )}
                <label className="ausadm-campo-con-etiqueta">
                  <span className="ausadm-etiqueta">{ta('arrastre_max', { unidad: ta(`unidad_${d.unidad}`) })}</span>
                  <Input aria-label={ta('arrastre_max', { unidad: ta(`unidad_${d.unidad}`) })} type="number" min={0} step="0.5" value={d.arrastre_max ?? ''} placeholder={ta('sin_arrastre')} onChange={e => cambiar({ arrastre_max: numOpcional(e.target.value) })} inputClassName="ausadm-campo ausadm-campo--corto" />
                </label>
                {d.arrastre_max != null && d.arrastre_max > 0 && (
                  <label className="ausadm-campo-con-etiqueta">
                    <span className="ausadm-etiqueta">{ta('arrastre_caduca_meses')}</span>
                    <Input aria-label={ta('arrastre_caduca_meses')} type="number" min={0} step={1} value={d.arrastre_caduca_meses ?? ''} placeholder={ta('no_caduca')} onChange={e => cambiar({ arrastre_caduca_meses: numOpcional(e.target.value) })} inputClassName="ausadm-campo ausadm-campo--corto" />
                  </label>
                )}
                <label className="ausadm-campo-con-etiqueta">
                  <span className="ausadm-etiqueta">{ta('caduca_meses')}</span>
                  <Input aria-label={ta('caduca_meses')} type="number" min={0} step={1} value={d.caduca_meses ?? ''} placeholder={ta('no_caduca')} aria-describedby="ausadm-caduca-ayuda" onChange={e => cambiar({ caduca_meses: numOpcional(e.target.value) })} inputClassName="ausadm-campo ausadm-campo--corto" />
                  <span id="ausadm-caduca-ayuda" className="ausadm-ayuda">{ta('caduca_meses_ayuda')}</span>
                </label>
              </div>
              {d.saldo !== 'bolsa' && (
                <Casilla etiqueta={ta('prorratear_alta')} ayuda={ta('prorratear_alta_ayuda')} valor={d.prorratear_alta}
                  onChange={v => cambiar({ prorratear_alta: v })} />
              )}
              {d.saldo === 'bolsa' && <ReglasDeLaBolsa valor={d.bolsa ?? bolsaNueva()} onChange={bolsa => cambiar({ bolsa })} />}
            </>
          )}
        </fieldset>
        <fieldset className="ds-grupo-opciones ausadm-fieldset">
          <legend className="ausadm-etiqueta">{ta('aprobacion')}</legend>
          <Casilla etiqueta={ta('requiere_aprobacion')} ayuda={ta('requiere_aprobacion_ayuda')} valor={d.requiere_aprobacion}
            onChange={v => cambiar({ requiere_aprobacion: v })} />
          <label className="ausadm-campo-con-etiqueta">
            <span className="ausadm-etiqueta">{ta('flujo_por_defecto')}</span>
            <Select suelto className="ausadm-campo" value={d.workflow_id ?? ''} onChange={e => cambiar({ workflow_id: e.target.value || null })} placeholder={ta('flujo_segun_condiciones')}>
              {(flujos.data ?? []).map(w => <option key={w.id} value={w.id}>{w.name}{w.is_active ? '' : ` (${ta('inactivo')})`}</option>)}
            </Select>
          </label>
          <Casilla etiqueta={ta('requiere_sustituto')} valor={d.requiere_sustituto} onChange={v => cambiar({ requiere_sustituto: v })} />
          <Casilla etiqueta={ta('datos_especiales')} ayuda={ta('datos_especiales_ayuda')} valor={d.datos_especiales}
            onChange={v => cambiar({ datos_especiales: v })} />
          <Casilla etiqueta={ta('activo')} valor={d.activo} onChange={v => cambiar({ activo: v })} />
        </fieldset>
        <Requisitos valor={d.requisitos} documentos={documentos.data ?? []} onChange={requisitos => cambiar({ requisitos })} />
        <AvisoDeError error={hayDeCampo(campos) ? null : guardar.error} defecto={ta('error_guardar')} />
        <div className="ausadm-acciones">
          {id && <Button variant="danger" icon={<Trash2 size={14} />} loading={borrar.isPending}
            onClick={async () => { if (await confirmar({ title: ta('borrar'), danger: true, message: ta('borrar_tipo_confirmar') })) borrar.mutate() }}>
            {ta('borrar')}</Button>}
          <Button variant="secondary" onClick={onCerrar}>{ta('cancelar')}</Button>
          <Button type="submit" loading={guardar.isPending}>{ta('guardar')}</Button>
        </div>
      </form>
    </Modal>
  )
}

/** Cómo se acumulan las horas de más en la bolsa (desde las imputaciones). */
function ReglasDeLaBolsa({ valor, onChange }: { valor: ReglasDeBolsa; onChange: (b: ReglasDeBolsa) => void }) {
  const { ta } = useT()
  const poner = (c: Partial<ReglasDeBolsa>) => onChange({ ...valor, ...c })
  const numero = (clave: 'factor' | 'factor_festivo' | 'factor_no_laborable') => (
    <label className="ausadm-campo-con-etiqueta">
      <span className="ausadm-etiqueta">{ta(`bolsa_${clave}`)}</span>
      <Input aria-label={ta(`bolsa_${clave}`)} type="number" min={0} step="0.25" required value={valor[clave]} onChange={e => poner({ [clave]: Math.max(0, Number(e.target.value) || 0) } as Partial<ReglasDeBolsa>)} inputClassName="ausadm-campo ausadm-campo--corto" />
    </label>
  )
  const opcional = (clave: 'tope_diario' | 'tope_periodo') => (
    <label className="ausadm-campo-con-etiqueta">
      <span className="ausadm-etiqueta">{ta(`bolsa_${clave}`)}</span>
      <Input aria-label={ta(`bolsa_${clave}`)} type="number" min={0} step="0.5" value={valor[clave] ?? ''} placeholder={ta('sin_tope')} onChange={e => poner({ [clave]: numOpcional(e.target.value) } as Partial<ReglasDeBolsa>)} inputClassName="ausadm-campo ausadm-campo--corto" />
    </label>
  )
  return (
    <div className="ausadm-tarjeta" role="group" aria-label={ta('bolsa_reglas')}>
      <span className="ausadm-etiqueta">{ta('bolsa_reglas')}</span>
      <span className="ausadm-ayuda">{ta('bolsa_reglas_ayuda')}</span>
      <div className="ausadm-grid-3">
        {numero('factor')}
        {numero('factor_festivo')}
        {numero('factor_no_laborable')}
        <label className="ausadm-campo-con-etiqueta">
          <span className="ausadm-etiqueta">{ta('bolsa_umbral_minutos')}</span>
          <Input aria-label={ta('bolsa_umbral_minutos')} type="number" min={0} step={5} value={valor.umbral_minutos} onChange={e => poner({ umbral_minutos: Math.max(0, Number(e.target.value) || 0) })} inputClassName="ausadm-campo ausadm-campo--corto" />
        </label>
        {opcional('tope_diario')}
        {opcional('tope_periodo')}
      </div>
      <Casilla etiqueta={ta('bolsa_solo_aprobadas')} ayuda={ta('bolsa_solo_aprobadas_ayuda')} valor={valor.solo_aprobadas}
        onChange={v => poner({ solo_aprobadas: v })} />
      <Casilla etiqueta={ta('bolsa_solo_horas_extra')} ayuda={ta('bolsa_solo_horas_extra_ayuda')} valor={valor.solo_horas_extra ?? false}
        onChange={v => poner({ solo_horas_extra: v })} />
    </div>
  )
}

function Requisitos({ valor, documentos, onChange }: {
  valor: RequisitoDocumental[]; documentos: TipoDeDocumento[]; onChange: (r: RequisitoDocumental[]) => void
}) {
  const { ta, lang } = useT()
  const cambiar = (i: number, c: Partial<RequisitoDocumental>) => onChange(valor.map((r, j) => (j === i ? { ...r, ...c } : r)))
  const nuevo = (): RequisitoDocumental => ({
    tipo_de_documento_id: documentos[0]?.id ?? '', obligatorio: true, plazo_dias: 3, plazo_desde: 'inicio',
    repetir_cada_dias: null, recordar_dias_antes: 1, escalar_dias_despues: null, escalar_a: [{ tipo: 'responsable' }],
  })
  return (
    <fieldset className="ds-grupo-opciones ausadm-fieldset">
      <legend className="ausadm-etiqueta">{ta('documentos_que_pide')}</legend>
      {valor.length === 0 && <p className="ausadm-ayuda">{ta('sin_requisitos')}</p>}
      {valor.map((r, i) => (
        <div key={i} className="ausadm-tarjeta" role="group" aria-label={ta('requisito_n', { n: i + 1 })}>
          <div className="ausadm-fila">
            <Select suelto className="ausadm-campo" aria-label={ta('tipo_de_documento')} value={r.tipo_de_documento_id}
              onChange={e => cambiar(i, { tipo_de_documento_id: e.target.value })} placeholder={ta('elige')}>
              {documentos.map(dd => <option key={dd.id} value={dd.id}>{nombreEn(dd, lang)}</option>)}
            </Select>
            <Casilla etiqueta={ta('obligatorio')} valor={r.obligatorio} onChange={v => cambiar(i, { obligatorio: v })} />
            <Button size="xs" variant="ghost" icon={<Trash2 size={13} />} title={ta('quitar')}
              onClick={() => onChange(valor.filter((_, j) => j !== i))}><span className="u-sr-only">{ta('quitar')}</span></Button>
          </div>
          <div className="ausadm-fila">
            <span className="ausadm-ayuda">{ta('plazo')}</span>
            <input type="number" min={0} className="ausadm-campo ausadm-campo--corto" aria-label={ta('plazo_dias')}
              value={r.plazo_dias} onChange={e => cambiar(i, { plazo_dias: Number(e.target.value) || 0 })} />
            <span className="ausadm-ayuda">{ta('dias_desde')}</span>
            <Select suelto className="ausadm-campo" aria-label={ta('plazo_desde')} value={r.plazo_desde}
              onChange={e => cambiar(i, { plazo_desde: e.target.value as PlazoDesde })} placeholder={false}>
              {PLAZOS.map(p => <option key={p} value={p}>{ta(`desde_${p}`)}</option>)}
            </Select>
          </div>
          <div className="ausadm-fila">
            <Casilla etiqueta={ta('repetir')} valor={r.repetir_cada_dias != null}
              onChange={v => cambiar(i, { repetir_cada_dias: v ? 7 : null })} />
            {r.repetir_cada_dias != null && (
              <label className="ausadm-fila"><span className="ausadm-ayuda">{ta('cada_n_dias')}</span>
                <input type="number" min={1} className="ausadm-campo ausadm-campo--corto" aria-label={ta('cada_n_dias')}
                  value={r.repetir_cada_dias} onChange={e => cambiar(i, { repetir_cada_dias: Math.max(1, Number(e.target.value) || 1) })} />
              </label>
            )}
            <label className="ausadm-fila"><span className="ausadm-ayuda">{ta('recordar_antes')}</span>
              <input type="number" min={0} className="ausadm-campo ausadm-campo--corto" aria-label={ta('recordar_antes')}
                value={r.recordar_dias_antes} onChange={e => cambiar(i, { recordar_dias_antes: Number(e.target.value) || 0 })} />
            </label>
          </div>
          <div className="ausadm-fila">
            <Casilla etiqueta={ta('escalar')} valor={r.escalar_dias_despues != null}
              onChange={v => cambiar(i, { escalar_dias_despues: v ? 1 : null })} />
            {r.escalar_dias_despues != null && (
              <>
                <label className="ausadm-fila"><span className="ausadm-ayuda">{ta('escalar_tras')}</span>
                  <input type="number" min={0} className="ausadm-campo ausadm-campo--corto" aria-label={ta('escalar_tras')}
                    value={r.escalar_dias_despues} onChange={e => cambiar(i, { escalar_dias_despues: Number(e.target.value) || 0 })} />
                </label>
                <Destinatarios valor={r.escalar_a} onChange={escalar_a => cambiar(i, { escalar_a })} />
              </>
            )}
          </div>
        </div>
      ))}
      <Button size="xs" variant="secondary" icon={<Plus size={13} />} disabled={!documentos.length}
        onClick={() => onChange([...valor, nuevo()])}>{ta('anadir_documento')}</Button>
      {!documentos.length && <p className="ausadm-ayuda">{ta('crea_tipos_de_documento')}</p>}
    </fieldset>
  )
}

export function Destinatarios({ valor, onChange }: { valor: DestinatarioDeAviso[]; onChange: (d: DestinatarioDeAviso[]) => void }) {
  const { t, ta } = useT()
  const opciones = useOpciones().data
  const cambiar = (i: number, d: DestinatarioDeAviso) => onChange(valor.map((x, j) => (j === i ? d : x)))
  return (
    <div role="group" aria-label={ta('escalar_a')} className="ausadm-destinatarios">
      <span className="ausadm-ayuda">{ta('escalar_a')}</span>
      {valor.map((d, i) => (
        <span key={i} className="ausadm-fila">
          <Select suelto className="ausadm-campo" aria-label={ta('destinatario')} value={d.tipo}
            onChange={e => cambiar(i, { tipo: e.target.value as DestinatarioDeAviso['tipo'], valor: null })} placeholder={false}>
            {DESTINOS.map(x => <option key={x} value={x}>{t(`pol.dest_${x}`)}</option>)}
          </Select>
          {d.tipo in CLASE && <SelectorDeEntidad clase={CLASE[d.tipo as keyof typeof CLASE]} valor={d.valor} opciones={opciones}
            onChange={v => cambiar(i, { ...d, valor: v })} etiqueta={t(`pol.dest_${d.tipo}`)} />}
          <Button size="xs" variant="ghost" icon={<Trash2 size={13} />} title={ta('quitar')}
            onClick={() => onChange(valor.filter((_, j) => j !== i))}><span className="u-sr-only">{ta('quitar')}</span></Button>
        </span>
      ))}
      <Button size="xs" variant="ghost" icon={<Plus size={13} />} onClick={() => onChange([...valor, { tipo: 'rol', valor: 'hr' }])}>
        {ta('anadir_destinatario')}</Button>
    </div>
  )
}
