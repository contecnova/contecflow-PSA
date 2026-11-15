/**
 * Resultados graduados de una regla (o de una banda de exceso): aviso,
 * justificación, justificante, niveles o pasos de aprobación, avisos a
 * personas por canal, bloqueo, fijar un campo, etiqueta, auto-aprobar.
 */
import { Plus, Trash2 } from 'lucide-react'
import type {
  Canal, Destinatario, DominioDePoliticas, ParametroDeResultado, PasoAnadido, Resultado, ResultadoPropio, TipoDeAprobador,
  TipoDeDestinatario, TipoDeResultado,
} from '../../services/api/tipos-politicas'
import { Button } from '../ui'
import { EntradaDeValor, ListaDeValores, SelectorDeEntidad, useCatalogo, useOpciones, useTextos } from './comun'

/** Un resultado propio del dominio (rev. 167, p. ej. el cupo de ausencias) con los valores por defecto de sus parámetros. */
function nuevoPropio(propio: ResultadoPropio): Resultado {
  const r: Resultado = { tipo: propio.clave }
  for (const p of propio.parametros) {
    r[p.clave] = p.tipo === 'clave' ? crypto.randomUUID() : structuredClone(p.defecto ?? null)
  }
  return r
}

function nuevo(tipo: TipoDeResultado | string, dominio?: DominioDePoliticas): Resultado {
  const propio = dominio?.resultados_propios?.find(x => x.clave === tipo)
  if (propio) return nuevoPropio(propio)
  switch (tipo) {
    case 'add_approval_levels': return { tipo, niveles: 1, pasos: [] }
    case 'notify': return { tipo, destinatarios: [{ tipo: 'responsable' }], canales: ['app'], mensaje: '' }
    case 'require_attachment': return { tipo, tipos_de_documento: [], mensaje: '' }
    case 'tag': return { tipo, etiqueta: '' }
    case 'set_field': return { tipo, campo: '', valor: null }
    default: return { tipo, mensaje: '' }
  }
}

/** Los tipos de resultado que se ofrecen en este dominio (los del motor y los propios). */
function tiposDe(dominio: DominioDePoliticas, todos: TipoDeResultado[], anidado: boolean): string[] {
  const motor = todos.filter(x => x !== 'waitlist' || dominio.admite_lista_de_espera)
  return anidado ? motor : [...motor, ...(dominio.resultados_propios ?? []).map(p => p.clave)]
}

export default function EditorDeResultados({ dominio, valor, onChange, titulo, anidado = false }: {
  dominio: DominioDePoliticas; valor: Resultado[]; onChange: (r: Resultado[]) => void; titulo?: string
  /** Dentro de un resultado propio (p. ej. «si el cupo está lleno»): solo los del motor. */
  anidado?: boolean
}) {
  const { t } = useTextos()
  const catalogo = useCatalogo().data
  const cambiar = (i: number, r: Resultado) => onChange(valor.map((x, j) => (j === i ? r : x)))
  return (
    <div role="group" aria-label={titulo ?? t('pol.resultados')}>
      {valor.length === 0 && <p className="pol-ayuda">{t('pol.sin_resultados')}</p>}
      {valor.map((r, i) => (
        <div key={i} className="pol-resultado">
          <select className="pol-campo" aria-label={t('pol.tipo_de_resultado')} value={r.tipo}
            onChange={e => cambiar(i, nuevo(e.target.value, dominio))}>
            {tiposDe(dominio, catalogo?.resultados ?? [], anidado).map(x => <option key={x} value={x}>{t(`pol.res_${x}`)}</option>)}
          </select>
          <DatosDeResultado dominio={dominio} r={r} onChange={n => cambiar(i, n)} />
          <Button size="xs" variant="ghost" icon={<Trash2 size={13} />} onClick={() => onChange(valor.filter((_, j) => j !== i))}
            title={t('pol.quitar_resultado')}><span className="u-sr-only">{t('pol.quitar_resultado')}</span></Button>
        </div>
      ))}
      <Button size="xs" variant="secondary" icon={<Plus size={13} />} onClick={() => onChange([...valor, nuevo('warn')])}>
        {t('pol.anadir_resultado')}
      </Button>
    </div>
  )
}

function Mensaje({ r, onChange, obligatorio = false }: { r: Resultado; onChange: (r: Resultado) => void; obligatorio?: boolean }) {
  const { t } = useTextos()
  return (
    <input className="pol-campo pol-campo--ancho" aria-label={t('pol.mensaje')} aria-required={obligatorio}
      placeholder={obligatorio ? t('pol.mensaje_obligatorio') : t('pol.mensaje_opcional')}
      value={r.mensaje ?? ''} onChange={e => onChange({ ...r, mensaje: e.target.value })} />
  )
}

function DatosDeResultado({ dominio, r, onChange }: { dominio: DominioDePoliticas; r: Resultado; onChange: (r: Resultado) => void }) {
  const { t, etiquetaDeCampo } = useTextos()
  const opciones = useOpciones().data
  const catalogo = useCatalogo().data
  switch (r.tipo) {
    case 'waitlist':
      return <Mensaje r={r} onChange={onChange} />
    case 'allow':
    case 'auto_approve':
      return <span className="pol-ayuda">{t(`pol.ayuda_${r.tipo}`)}</span>
    case 'warn':
    case 'require_justification':
      return <Mensaje r={r} onChange={onChange} />
    case 'block':
      return <Mensaje r={r} onChange={onChange} obligatorio />
    case 'require_attachment':
      return (
        <div className="pol-fila">
          <ListaDeValores valores={r.tipos_de_documento ?? []} onChange={v => onChange({ ...r, tipos_de_documento: v })}
            opciones={opciones?.tipos_de_documento ?? []} etiqueta={t('pol.tipos_de_documento')} />
          <Mensaje r={r} onChange={onChange} />
        </div>
      )
    case 'tag':
      return <input className="pol-campo pol-campo--medio" aria-label={t('pol.etiqueta')} value={r.etiqueta ?? ''}
        onChange={e => onChange({ ...r, etiqueta: e.target.value })} />
    case 'set_field': {
      const asignables = dominio.campos.filter(c => c.asignable)
      const campo = asignables.find(c => c.clave === r.campo)
      return (
        <div className="pol-fila">
          <select className="pol-campo pol-campo--medio" aria-label={t('pol.campo_a_fijar')} value={r.campo ?? ''}
            onChange={e => onChange({ ...r, campo: e.target.value, valor: null })}>
            <option value="">{asignables.length ? t('pol.elige') : t('pol.sin_campos_asignables')}</option>
            {asignables.map(c => <option key={c.clave} value={c.clave}>{etiquetaDeCampo(dominio.clave, c)}</option>)}
          </select>
          {campo && <EntradaDeValor dominio={dominio.clave} campo={campo} operador="eq" valor={r.valor} opciones={opciones}
            onChange={v => onChange({ ...r, valor: v })} etiqueta={t('pol.nuevo_valor')} />}
        </div>
      )
    }
    case 'add_approval_levels':
      return (
        <div className="u-stack-10">
          <label className="pol-fila">
            <span className="pol-ayuda">{t('pol.niveles_jerarquicos')}</span>
            <input type="number" min={0} max={catalogo?.max_niveles ?? 10} className="pol-campo pol-campo--corto"
              aria-label={t('pol.niveles')} value={r.niveles ?? 0} onChange={e => onChange({ ...r, niveles: Number(e.target.value) || null })} />
          </label>
          <PasosConcretos pasos={r.pasos ?? []} onChange={p => onChange({ ...r, pasos: p })} />
        </div>
      )
    case 'notify':
      return (
        <div className="u-stack-10">
          <Destinatarios valor={r.destinatarios ?? []} onChange={d => onChange({ ...r, destinatarios: d })} />
          <div className="pol-fila" role="group" aria-label={t('pol.canales')}>
            {(catalogo?.canales ?? []).map((c: Canal) => (
              <label key={c} className="pol-chip">
                <input type="checkbox" checked={(r.canales ?? []).includes(c)}
                  onChange={e => onChange({ ...r, canales: e.target.checked ? [...(r.canales ?? []), c] : (r.canales ?? []).filter(x => x !== c) })} />
                {t(`pol.canal_${c}`)}
              </label>
            ))}
          </div>
          <Mensaje r={r} onChange={onChange} />
        </div>
      )
    default: {
      const propio = dominio.resultados_propios?.find(x => x.clave === r.tipo)
      return propio ? <DatosPropios dominio={dominio} propio={propio} r={r} onChange={onChange} /> : null
    }
  }
}

/** Los parámetros de un resultado propio del dominio, cada uno con su control (nadie escribe JSON). */
function DatosPropios({ dominio, propio, r, onChange }: {
  dominio: DominioDePoliticas; propio: ResultadoPropio; r: Resultado; onChange: (r: Resultado) => void
}) {
  const { t } = useTextos()
  const visibles = propio.parametros.filter(p => p.tipo !== 'clave'
    && (!p.visible_si || p.visible_si.valores.includes(String(r[p.visible_si.parametro] ?? ''))))
  return (
    <div className="u-stack-10" role="group" aria-label={t(`pol.res_${propio.clave}`)}>
      <span className="pol-ayuda">{t(`pol.ayuda_res_${propio.clave}`)}</span>
      {visibles.map(p => (
        <Parametro key={p.clave} dominio={dominio} propio={propio.clave} p={p} valor={r[p.clave]}
          onChange={v => onChange({ ...r, [p.clave]: v })} />
      ))}
    </div>
  )
}

function Parametro({ dominio, propio, p, valor, onChange }: {
  dominio: DominioDePoliticas; propio: string; p: ParametroDeResultado; valor: unknown; onChange: (v: unknown) => void
}) {
  const { t } = useTextos()
  const opciones = useOpciones().data
  const catalogo = useCatalogo().data
  const etiqueta = t(`pol.par_${propio}_${p.clave}`)
  switch (p.tipo) {
    case 'numero':
      return (
        <label className="pol-fila"><span className="pol-ayuda">{etiqueta}</span>
          <input type="number" min={p.minimo ?? undefined} className="pol-campo pol-campo--corto" aria-label={etiqueta}
            value={(valor as number | null) ?? ''} onChange={e => onChange(e.target.value === '' ? null : Number(e.target.value))} />
        </label>
      )
    case 'booleano':
      return (
        <label className="pol-fila pol-chip">
          <input type="checkbox" checked={Boolean(valor)} onChange={e => onChange(e.target.checked)} />{etiqueta}
        </label>
      )
    case 'enum':
      return (
        <label className="pol-fila"><span className="pol-ayuda">{etiqueta}</span>
          <select className="pol-campo pol-campo--medio" aria-label={etiqueta} value={String(valor ?? '')} onChange={e => onChange(e.target.value)}>
            {p.opciones.map(o => <option key={o.valor} value={o.valor}>{t(`pol.par_${propio}_${p.clave}_${o.valor}`)}</option>)}
          </select>
        </label>
      )
    case 'entidad':
      return (
        <span className="pol-fila"><span className="pol-ayuda">{etiqueta}</span>
          <SelectorDeEntidad clase={p.entidad ?? 'grupo'} valor={valor as string} opciones={opciones} onChange={onChange} etiqueta={etiqueta} />
        </span>
      )
    case 'resultados':
      return (
        <fieldset className="pol-anidado">
          <legend className="pol-ayuda">{etiqueta}</legend>
          <EditorDeResultados dominio={dominio} valor={(valor as Resultado[]) ?? []} onChange={onChange} titulo={etiqueta} anidado />
        </fieldset>
      )
    case 'destinatarios':
      return (
        <fieldset className="pol-anidado">
          <legend className="pol-ayuda">{etiqueta}</legend>
          <Destinatarios valor={(valor as Destinatario[]) ?? []} onChange={onChange} />
        </fieldset>
      )
    case 'canales': {
      const lista = (valor as Canal[]) ?? []
      return (
        <div className="pol-fila" role="group" aria-label={etiqueta}>
          <span className="pol-ayuda">{etiqueta}</span>
          {(catalogo?.canales ?? []).map((c: Canal) => (
            <label key={c} className="pol-chip">
              <input type="checkbox" checked={lista.includes(c)}
                onChange={e => onChange(e.target.checked ? [...lista, c] : lista.filter(x => x !== c))} />
              {t(`pol.canal_${c}`)}
            </label>
          ))}
        </div>
      )
    }
    default:
      return <input className="pol-campo pol-campo--medio" aria-label={etiqueta} value={String(valor ?? '')} onChange={e => onChange(e.target.value)} />
  }
}

export function SelectorDeAprobador({ paso, onChange }: { paso: PasoAnadido; onChange: (p: PasoAnadido) => void }) {
  const { t } = useTextos()
  const opciones = useOpciones().data
  const catalogo = useCatalogo().data
  return (
    <span className="pol-fila">
      <select className="pol-campo pol-campo--medio" aria-label={t('pol.quien_aprueba')} value={paso.approver_type}
        onChange={e => onChange({ ...paso, approver_type: e.target.value as TipoDeAprobador, approver_role: null, approver_user_id: null,
          approver_department: null, approver_group_id: null, approver_level: e.target.value === 'manager_level' ? 2 : null })}>
        {(catalogo?.tipos_de_aprobador ?? []).map(x => <option key={x} value={x}>{t(`pol.aprobador_${x}`)}</option>)}
      </select>
      {paso.approver_type === 'role' && <SelectorDeEntidad clase="rol" valor={paso.approver_role} opciones={opciones}
        onChange={v => onChange({ ...paso, approver_role: v })} etiqueta={t('pol.rol')} />}
      {paso.approver_type === 'user' && <SelectorDeEntidad clase="usuario" valor={paso.approver_user_id} opciones={opciones}
        onChange={v => onChange({ ...paso, approver_user_id: v })} etiqueta={t('pol.persona')} />}
      {paso.approver_type === 'any_in_department' && <SelectorDeEntidad clase="departamento" valor={paso.approver_department} opciones={opciones}
        onChange={v => onChange({ ...paso, approver_department: v })} etiqueta={t('pol.departamento')} />}
      {paso.approver_type === 'group' && <SelectorDeEntidad clase="grupo" valor={paso.approver_group_id} opciones={opciones}
        onChange={v => onChange({ ...paso, approver_group_id: v })} etiqueta={t('pol.grupo')} />}
      {paso.approver_type === 'manager_level' && (
        <input type="number" min={1} max={10} className="pol-campo pol-campo--corto" aria-label={t('pol.nivel')}
          value={paso.approver_level ?? 2} onChange={e => onChange({ ...paso, approver_level: Number(e.target.value) })} />
      )}
    </span>
  )
}

function PasosConcretos({ pasos, onChange }: { pasos: PasoAnadido[]; onChange: (p: PasoAnadido[]) => void }) {
  const { t } = useTextos()
  const cambiar = (i: number, p: PasoAnadido) => onChange(pasos.map((x, j) => (j === i ? p : x)))
  return (
    <div role="group" aria-label={t('pol.pasos_concretos')}>
      <span className="pol-ayuda">{t('pol.pasos_concretos')}</span>
      {pasos.map((p, i) => (
        <div key={i} className="pol-fila">
          <input className="pol-campo pol-campo--medio" aria-label={t('pol.nombre_del_paso')} value={p.nombre ?? ''}
            placeholder={t('pol.nombre_del_paso')} onChange={e => cambiar(i, { ...p, nombre: e.target.value })} />
          <SelectorDeAprobador paso={p} onChange={n => cambiar(i, n)} />
          <label className="pol-fila"><span className="pol-ayuda">{t('pol.quorum')}</span>
            <input type="number" min={1} className="pol-campo pol-campo--corto" aria-label={t('pol.quorum')}
              value={p.required_approvals ?? 1} onChange={e => cambiar(i, { ...p, required_approvals: Number(e.target.value) || 1 })} />
          </label>
          <Button size="xs" variant="ghost" icon={<Trash2 size={13} />} onClick={() => onChange(pasos.filter((_, j) => j !== i))}
            title={t('pol.quitar_paso')}><span className="u-sr-only">{t('pol.quitar_paso')}</span></Button>
        </div>
      ))}
      <Button size="xs" variant="ghost" icon={<Plus size={13} />}
        onClick={() => onChange([...pasos, { approver_type: 'role', approver_role: null, required_approvals: 1 }])}>{t('pol.anadir_paso')}</Button>
    </div>
  )
}

function Destinatarios({ valor, onChange }: { valor: Destinatario[]; onChange: (d: Destinatario[]) => void }) {
  const { t } = useTextos()
  const opciones = useOpciones().data
  const catalogo = useCatalogo().data
  const cambiar = (i: number, d: Destinatario) => onChange(valor.map((x, j) => (j === i ? d : x)))
  const clase = { persona: 'usuario', rol: 'rol', grupo: 'grupo', departamento: 'departamento' } as const
  return (
    <div role="group" aria-label={t('pol.destinatarios')}>
      {valor.map((d, i) => (
        <div key={i} className="pol-fila">
          <select className="pol-campo pol-campo--medio" aria-label={t('pol.destinatario')} value={d.tipo}
            onChange={e => cambiar(i, { tipo: e.target.value as TipoDeDestinatario, valor: null })}>
            {(catalogo?.destinatarios ?? []).map(x => <option key={x} value={x}>{t(`pol.dest_${x}`)}</option>)}
          </select>
          {d.tipo in clase && (
            <SelectorDeEntidad clase={clase[d.tipo as keyof typeof clase]} valor={d.valor} opciones={opciones}
              onChange={v => cambiar(i, { ...d, valor: v })} etiqueta={t(`pol.dest_${d.tipo}`)} />
          )}
          <Button size="xs" variant="ghost" icon={<Trash2 size={13} />} onClick={() => onChange(valor.filter((_, j) => j !== i))}
            title={t('pol.quitar_destinatario')}><span className="u-sr-only">{t('pol.quitar_destinatario')}</span></Button>
        </div>
      ))}
      <Button size="xs" variant="ghost" icon={<Plus size={13} />} onClick={() => onChange([...valor, { tipo: 'rol', valor: null }])}>
        {t('pol.anadir_destinatario')}
      </Button>
    </div>
  )
}
