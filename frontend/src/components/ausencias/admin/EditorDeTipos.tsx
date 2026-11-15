/**
 * Tipos de ausencia (tarea #25): nombre por idioma, color, icono, saldo y
 * unidad, visibilidad, flujo por defecto, sustituto, datos de salud y los
 * documentos que pide cada tipo con su plazo, recordatorio, repetición y
 * escalado. Todo con controles: nadie escribe JSON.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, Umbrella } from 'lucide-react'
import { ausenciasApi } from '../../../services/api/ausencias'
import { approvalsApi } from '../../../services/api'
import type {
  DestinatarioDeAviso, PlazoDesde, RequisitoDocumental, TipoDeAusencia, TipoDeAusenciaIn, TipoDeDocumento,
} from '../../../services/api/tipos-ausencias'
import { Button, EmptyState, Modal, Spinner } from '../../ui'
import { confirmar } from '../../../context/ConfirmContext'
import { useToast } from '../../../context/ToastContext'
import { SelectorDeEntidad, useOpciones } from '../../politicas/comun'
import IconoDeAusencia, { ICONOS_DE_AUSENCIA } from '../IconoDeAusencia'
import { AvisoDeError, colorPorDefecto, Casilla, Muestra, NombresPorIdioma, errorDe, nombreEn, useT } from './comun'

const tipoNuevo = (): TipoDeAusenciaIn => ({
  clave: '', nombre: '', nombres: {}, color: colorPorDefecto(), icono: 'umbrella', descuenta_saldo: false, saldo: null,
  cupo_anual: null, unidad: 'dias', visibilidad: 'equipo', workflow_id: null, requiere_aprobacion: true,
  requiere_sustituto: false, datos_especiales: false, activo: true, orden: 100, requisitos: [],
})
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
                <button type="button" className={`ausadm-item${t.activo ? '' : ' ausadm-item--inactivo'}`}
                  onClick={() => setAbierto({ id: t.id, datos: aEntrada(t) })}>
                  <Muestra color={t.color} className="ausadm-muestra--icono"><IconoDeAusencia icono={t.icono} /></Muestra>
                  <span className="ausadm-item-nombre">{nombreEn(t, lang)} <span className="ausadm-ayuda">({t.clave})</span></span>
                  <span className="ausadm-chips">
                    {t.descuenta_saldo && <span className="ausadm-chip">{ta(`saldo_${t.saldo}`)}</span>}
                    <span className="ausadm-chip">{ta(`unidad_${t.unidad}`)}</span>
                    <span className="ausadm-chip">{ta(`visibilidad_${t.visibilidad}`)}</span>
                    {t.datos_especiales && <span className="ausadm-chip ausadm-chip--aviso">{ta('datos_especiales_corto')}</span>}
                    {t.requisitos.length > 0 && <span className="ausadm-chip">{ta('n_documentos', { n: t.requisitos.length })}</span>}
                    {t.de_sistema && <span className="ausadm-chip">{ta('de_sistema')}</span>}
                    {!t.activo && <span className="ausadm-chip">{ta('inactivo')}</span>}
                  </span>
                </button>
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
  return { ...resto, requisitos: t.requisitos.map(r => ({ ...r })) }
}

function FormularioDeTipo({ id, inicial, deSistema, onCerrar }: {
  id: string | null; inicial: TipoDeAusenciaIn; deSistema: boolean; onCerrar: () => void
}) {
  const { ta } = useT()
  const qc = useQueryClient()
  const toast = useToast()
  const [d, setD] = useState<TipoDeAusenciaIn>(inicial)
  const cambiar = (c: Partial<TipoDeAusenciaIn>) => setD(x => ({ ...x, ...c }))
  const flujos = useQuery({
    queryKey: ['ausencias', 'flujos-leave'],
    queryFn: () => approvalsApi.listWorkflows({ entity_type: 'leave' }).then(r => (r.data ?? []).filter(w => w.entity_type === 'leave')),
  })
  const documentos = useQuery({ queryKey: ['ausencias', 'documentos'], queryFn: () => ausenciasApi.documentos() })
  const refrescar = () => qc.invalidateQueries({ queryKey: ['ausencias'] })
  const guardar = useMutation({
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
            <input aria-label={ta('clave')} className="ausadm-campo" required pattern="[a-z0-9_]{2,50}" value={d.clave} disabled={deSistema}
              aria-describedby="ausadm-clave-ayuda" onChange={e => cambiar({ clave: e.target.value.toLowerCase() })} />
            <span id="ausadm-clave-ayuda" className="ausadm-ayuda">{ta('clave_ayuda')}</span>
          </label>
          <label className="ausadm-campo-con-etiqueta">
            <span className="ausadm-etiqueta">{ta('nombre_principal')}</span>
            <input aria-label={ta('nombre_principal')} className="ausadm-campo" value={d.nombre} onChange={e => cambiar({ nombre: e.target.value })} />
          </label>
        </div>
        <NombresPorIdioma valor={d.nombres} onChange={nombres => cambiar({ nombres })} />
        <div className="ausadm-grid-2">
          <label className="ausadm-campo-con-etiqueta">
            <span className="ausadm-etiqueta">{ta('color')}</span>
            <input aria-label={ta('color')} type="color" className="ausadm-color" value={d.color} onChange={e => cambiar({ color: e.target.value })} />
          </label>
          <fieldset className="ausadm-fieldset">
            <legend className="ausadm-etiqueta">{ta('icono')}</legend>
            <div className="ausadm-iconos" role="radiogroup" aria-label={ta('icono')}>
              {Object.keys(ICONOS_DE_AUSENCIA).map(nombre => (
                <button key={nombre} type="button" role="radio" aria-checked={d.icono === nombre}
                  className="ausadm-icono" aria-label={ta(`icono_${nombre}`)} title={ta(`icono_${nombre}`)}
                  onClick={() => cambiar({ icono: nombre })}><IconoDeAusencia icono={nombre} /></button>
              ))}
            </div>
          </fieldset>
        </div>
        <div className="ausadm-grid-2">
          <label className="ausadm-campo-con-etiqueta">
            <span className="ausadm-etiqueta">{ta('unidad')}</span>
            <select className="ausadm-campo" value={d.unidad} onChange={e => cambiar({ unidad: e.target.value as TipoDeAusenciaIn['unidad'] })}>
              {(['dias', 'medios_dias', 'horas'] as const).map(u => <option key={u} value={u}>{ta(`unidad_${u}`)}</option>)}
            </select>
          </label>
          <label className="ausadm-campo-con-etiqueta">
            <span className="ausadm-etiqueta">{ta('visibilidad')}</span>
            <select className="ausadm-campo" value={d.visibilidad} aria-describedby="ausadm-vis-ayuda"
              onChange={e => cambiar({ visibilidad: e.target.value as TipoDeAusenciaIn['visibilidad'] })}>
              {(['todos', 'equipo', 'privada'] as const).map(v => <option key={v} value={v}>{ta(`visibilidad_${v}`)}</option>)}
            </select>
            <span id="ausadm-vis-ayuda" className="ausadm-ayuda">{ta(`visibilidad_${d.visibilidad}_ayuda`)}</span>
          </label>
        </div>
        <fieldset className="ausadm-fieldset">
          <legend className="ausadm-etiqueta">{ta('saldo')}</legend>
          <Casilla etiqueta={ta('descuenta_saldo')} valor={d.descuenta_saldo}
            onChange={v => cambiar({ descuenta_saldo: v, saldo: v ? (d.saldo ?? 'vacaciones') : null })} />
          {d.descuenta_saldo && (
            <div className="ausadm-fila">
              <select className="ausadm-campo" aria-label={ta('que_saldo')} value={d.saldo ?? 'vacaciones'}
                onChange={e => cambiar({ saldo: e.target.value as 'vacaciones' | 'propio' })}>
                <option value="vacaciones">{ta('saldo_vacaciones')}</option>
                <option value="propio">{ta('saldo_propio')}</option>
              </select>
              {d.saldo === 'propio' && (
                <label className="ausadm-fila">
                  <span className="ausadm-ayuda">{ta('cupo_anual', { unidad: ta(`unidad_${d.unidad}`) })}</span>
                  <input aria-label={ta('cupo_anual', { unidad: ta(`unidad_${d.unidad}`) })} type="number" min={0} step="0.5" className="ausadm-campo ausadm-campo--corto" required
                    value={d.cupo_anual ?? ''} onChange={e => cambiar({ cupo_anual: e.target.value === '' ? null : Number(e.target.value) })} />
                </label>
              )}
            </div>
          )}
        </fieldset>
        <fieldset className="ausadm-fieldset">
          <legend className="ausadm-etiqueta">{ta('aprobacion')}</legend>
          <Casilla etiqueta={ta('requiere_aprobacion')} ayuda={ta('requiere_aprobacion_ayuda')} valor={d.requiere_aprobacion}
            onChange={v => cambiar({ requiere_aprobacion: v })} />
          <label className="ausadm-campo-con-etiqueta">
            <span className="ausadm-etiqueta">{ta('flujo_por_defecto')}</span>
            <select className="ausadm-campo" value={d.workflow_id ?? ''} onChange={e => cambiar({ workflow_id: e.target.value || null })}>
              <option value="">{ta('flujo_segun_condiciones')}</option>
              {(flujos.data ?? []).map(w => <option key={w.id} value={w.id}>{w.name}{w.is_active ? '' : ` (${ta('inactivo')})`}</option>)}
            </select>
          </label>
          <Casilla etiqueta={ta('requiere_sustituto')} valor={d.requiere_sustituto} onChange={v => cambiar({ requiere_sustituto: v })} />
          <Casilla etiqueta={ta('datos_especiales')} ayuda={ta('datos_especiales_ayuda')} valor={d.datos_especiales}
            onChange={v => cambiar({ datos_especiales: v })} />
          <Casilla etiqueta={ta('activo')} valor={d.activo} onChange={v => cambiar({ activo: v })} />
        </fieldset>
        <Requisitos valor={d.requisitos} documentos={documentos.data ?? []} onChange={requisitos => cambiar({ requisitos })} />
        <AvisoDeError error={guardar.error} defecto={ta('error_guardar')} />
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
    <fieldset className="ausadm-fieldset">
      <legend className="ausadm-etiqueta">{ta('documentos_que_pide')}</legend>
      {valor.length === 0 && <p className="ausadm-ayuda">{ta('sin_requisitos')}</p>}
      {valor.map((r, i) => (
        <div key={i} className="ausadm-tarjeta" role="group" aria-label={ta('requisito_n', { n: i + 1 })}>
          <div className="ausadm-fila">
            <select className="ausadm-campo" aria-label={ta('tipo_de_documento')} value={r.tipo_de_documento_id}
              onChange={e => cambiar(i, { tipo_de_documento_id: e.target.value })}>
              <option value="">{ta('elige')}</option>
              {documentos.map(dd => <option key={dd.id} value={dd.id}>{nombreEn(dd, lang)}</option>)}
            </select>
            <Casilla etiqueta={ta('obligatorio')} valor={r.obligatorio} onChange={v => cambiar(i, { obligatorio: v })} />
            <Button size="xs" variant="ghost" icon={<Trash2 size={13} />} title={ta('quitar')}
              onClick={() => onChange(valor.filter((_, j) => j !== i))}><span className="u-sr-only">{ta('quitar')}</span></Button>
          </div>
          <div className="ausadm-fila">
            <span className="ausadm-ayuda">{ta('plazo')}</span>
            <input type="number" min={0} className="ausadm-campo ausadm-campo--corto" aria-label={ta('plazo_dias')}
              value={r.plazo_dias} onChange={e => cambiar(i, { plazo_dias: Number(e.target.value) || 0 })} />
            <span className="ausadm-ayuda">{ta('dias_desde')}</span>
            <select className="ausadm-campo" aria-label={ta('plazo_desde')} value={r.plazo_desde}
              onChange={e => cambiar(i, { plazo_desde: e.target.value as PlazoDesde })}>
              {PLAZOS.map(p => <option key={p} value={p}>{ta(`desde_${p}`)}</option>)}
            </select>
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
          <select className="ausadm-campo" aria-label={ta('destinatario')} value={d.tipo}
            onChange={e => cambiar(i, { tipo: e.target.value as DestinatarioDeAviso['tipo'], valor: null })}>
            {DESTINOS.map(x => <option key={x} value={x}>{t(`pol.dest_${x}`)}</option>)}
          </select>
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
