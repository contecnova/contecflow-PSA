/**
 * Constructor visual de condiciones: grupos «todas / alguna» anidados (y
 * negables) con condiciones tipadas del catálogo del dominio. El valor se
 * escribe con el control de su tipo (`EntradaDeValor`).
 */
import { Plus, Trash2, FolderPlus } from 'lucide-react'
import type {
  CampoDeDominio, CondicionSimple, DominioDePoliticas, GrupoDeCondiciones, NodoDeCondicion, Operador,
  ReferenciaDeValor, ValorDeCondicion,
} from '../../services/api/tipos-politicas'
import { Button, Select, Checkbox } from '../ui'
import { EntradaDeValor, useOpciones, useTextos } from './comun'
import { Input } from '../ui'

const MAX_PROFUNDIDAD = 8
/** Operadores con dos valores: «entre» y, en un periodo, «solapa con» / «no solapa con» (rev. 167). */
const DOS_VALORES: Operador[] = ['between', 'overlaps', 'not_overlaps']

export function grupoVacio(op: 'and' | 'or' = 'and'): GrupoDeCondiciones {
  return { tipo: 'grupo', op, hijos: [] }
}

function condicionNueva(dominio: DominioDePoliticas): CondicionSimple {
  const campo = dominio.campos[0]
  return { tipo: 'condicion', campo: campo.clave, operador: campo.operadores[0], valor: null }
}

export default function ConstructorDeCondiciones({ dominio, valor, onChange }: {
  dominio: DominioDePoliticas; valor: GrupoDeCondiciones | null; onChange: (g: GrupoDeCondiciones) => void
}) {
  return <Grupo dominio={dominio} grupo={valor ?? grupoVacio()} onChange={onChange} profundidad={0} />
}

function Grupo({ dominio, grupo, onChange, onQuitar, profundidad }: {
  dominio: DominioDePoliticas; grupo: GrupoDeCondiciones; onChange: (g: GrupoDeCondiciones) => void
  onQuitar?: () => void; profundidad: number
}) {
  const { t } = useTextos()
  const cambiarHijo = (i: number, n: NodoDeCondicion) => onChange({ ...grupo, hijos: grupo.hijos.map((h, j) => (j === i ? n : h)) })
  const quitarHijo = (i: number) => onChange({ ...grupo, hijos: grupo.hijos.filter((_, j) => j !== i) })
  const conector = grupo.op === 'and' ? t('pol.y') : t('pol.o')
  return (
    <div className={`pol-grupo${grupo.op === 'or' ? ' pol-grupo--o' : ''}${grupo.negar ? ' pol-grupo--negado' : ''}`}
      role="group" aria-label={t('pol.grupo_de_condiciones')}>
      <div className="pol-grupo-cabecera">
        <Checkbox className="pol-chip" label={t('pol.no_se_cumple')} checked={!!grupo.negar} onChange={m => onChange({ ...grupo, negar: m })} />
        <Select suelto className="pol-campo" aria-label={t('pol.modo_del_grupo')} value={grupo.op}
          onChange={e => onChange({ ...grupo, op: e.target.value as 'and' | 'or' })} placeholder={false}>
          <option value="and">{t('pol.todas')}</option>
          <option value="or">{t('pol.alguna')}</option>
        </Select>
        <span className="pol-ayuda">{grupo.hijos.length === 0 ? t('pol.grupo_vacio') : t('pol.de_estas_condiciones')}</span>
        {onQuitar && <Button size="xs" variant="ghost" icon={<Trash2 size={13} />} onClick={onQuitar} title={t('pol.quitar_grupo')}>{t('pol.quitar_grupo')}</Button>}
      </div>
      {grupo.hijos.map((h, i) => (
        <div key={i}>
          {i > 0 && <span className="pol-conector">{conector}</span>}
          {h.tipo === 'grupo'
            ? <Grupo dominio={dominio} grupo={h} profundidad={profundidad + 1} onChange={n => cambiarHijo(i, n)} onQuitar={() => quitarHijo(i)} />
            : <Condicion dominio={dominio} condicion={h} onChange={n => cambiarHijo(i, n)} onQuitar={() => quitarHijo(i)} />}
        </div>
      ))}
      <div className="pol-fila">
        <Button size="xs" variant="secondary" icon={<Plus size={13} />}
          onClick={() => onChange({ ...grupo, hijos: [...grupo.hijos, condicionNueva(dominio)] })}>{t('pol.anadir_condicion')}</Button>
        {profundidad < MAX_PROFUNDIDAD - 1 && (
          <Button size="xs" variant="ghost" icon={<FolderPlus size={13} />}
            onClick={() => onChange({ ...grupo, hijos: [...grupo.hijos, grupoVacio(grupo.op === 'and' ? 'or' : 'and')] })}>{t('pol.anadir_grupo')}</Button>
        )}
      </div>
    </div>
  )
}

function Condicion({ dominio, condicion, onChange, onQuitar }: {
  dominio: DominioDePoliticas; condicion: CondicionSimple; onChange: (c: CondicionSimple) => void; onQuitar: () => void
}) {
  const { t, etiquetaDeCampo } = useTextos()
  const opciones = useOpciones().data
  const campo = dominio.campos.find(c => c.clave === condicion.campo) ?? dominio.campos[0]
  const etiqueta = etiquetaDeCampo(dominio.clave, campo)
  const cambiarCampo = (clave: string) => {
    const nuevo = dominio.campos.find(c => c.clave === clave) as CampoDeDominio
    onChange({ tipo: 'condicion', campo: clave, operador: nuevo.operadores[0], valor: null })
  }
  const cambiarOperador = (op: Operador) => {
    const lista = ['in', 'not_in', 'weekday_in', 'weekday_not_in'].includes(op)
    onChange({ ...condicion, operador: op, valor: lista ? [] : op === 'pct_over' ? 0 : condicion.valor,
      valor2: DOS_VALORES.includes(op) ? condicion.valor2 ?? null : undefined,
      referencia: op === 'pct_over' ? condicion.referencia ?? { tipo: 'tabla' } : undefined })
  }
  const sinValor = condicion.operador === 'empty' || condicion.operador === 'not_empty'
  return (
    <div className="pol-condicion" role="group" aria-label={t('pol.condicion_sobre', { campo: etiqueta })}>
      <Select suelto className="pol-campo pol-campo--medio" aria-label={t('pol.campo')} value={campo.clave} onChange={e => cambiarCampo(e.target.value)} placeholder={false}>
        {dominio.campos.map(c => <option key={c.clave} value={c.clave}>{etiquetaDeCampo(dominio.clave, c)}</option>)}
      </Select>
      <Select suelto className="pol-campo pol-campo--medio" aria-label={t('pol.operador')} value={condicion.operador}
        onChange={e => cambiarOperador(e.target.value as Operador)} placeholder={false}>
        {campo.operadores.map(o => <option key={o} value={o}>{t(`pol.op_${o}`)}</option>)}
      </Select>
      {condicion.operador === 'pct_over' ? (
        <>
          <Input type="number" min={0} step="1" aria-label={t('pol.porcentaje')} value={(condicion.valor as number) ?? 0} onChange={e => onChange({ ...condicion, valor: Number(e.target.value) })} className="pol-campo--corto" />
          <span className="pol-ayuda">{t('pol.pct_sobre')}</span>
          <SelectorDeReferencia dominio={dominio} campo={campo} valor={condicion.referencia}
            onChange={r => onChange({ ...condicion, referencia: r })} />
        </>
      ) : !sinValor && (
        <>
          <EntradaDeValor dominio={dominio.clave} campo={campo} operador={condicion.operador} valor={condicion.valor}
            onChange={(v: ValorDeCondicion) => onChange({ ...condicion, valor: v })} opciones={opciones} etiqueta={t('pol.valor_de', { campo: etiqueta })} />
          {DOS_VALORES.includes(condicion.operador) && (
            <>
              <span className="pol-ayuda">{t('pol.y_minus')}</span>
              <EntradaDeValor dominio={dominio.clave} campo={campo} operador="eq" valor={condicion.valor2}
                onChange={(v: ValorDeCondicion) => onChange({ ...condicion, valor2: v })} opciones={opciones} etiqueta={t('pol.hasta_de', { campo: etiqueta })} />
            </>
          )}
        </>
      )}
      <Button size="xs" variant="ghost" icon={<Trash2 size={13} />} onClick={onQuitar} title={t('pol.quitar_condicion')}>
        <span className="u-sr-only">{t('pol.quitar_condicion')}</span>
      </Button>
    </div>
  )
}

/** Referencia de un porcentaje: una tabla (por país/ciudad/categoría), un valor fijo u otro campo. */
export function SelectorDeReferencia({ dominio, campo, valor, onChange }: {
  dominio: DominioDePoliticas; campo: CampoDeDominio; valor: ReferenciaDeValor | undefined; onChange: (r: ReferenciaDeValor) => void
}) {
  const { t, etiquetaDeCampo } = useTextos()
  const opciones = useOpciones().data
  const ref = valor ?? { tipo: 'tabla' as const }
  const tablas = (opciones?.tablas ?? []).filter(x => !x.dominio || x.dominio === dominio.clave)
  return (
    <span className="pol-fila">
      <Select suelto className="pol-campo" aria-label={t('pol.tipo_de_referencia')} value={ref.tipo}
        onChange={e => onChange({ tipo: e.target.value as ReferenciaDeValor['tipo'] })} placeholder={false}>
        <option value="tabla">{t('pol.ref_tabla')}</option>
        <option value="valor">{t('pol.ref_valor')}</option>
        <option value="campo">{t('pol.ref_campo')}</option>
      </Select>
      {ref.tipo === 'tabla' && (
        <Select suelto className="pol-campo pol-campo--medio" aria-label={t('pol.tabla_de_referencia')} value={ref.tabla_id ?? ''}
          onChange={e => onChange({ tipo: 'tabla', tabla_id: e.target.value })} placeholder={tablas.length ? t('pol.elige_tabla') : t('pol.sin_tablas')}>
          {tablas.map(x => <option key={x.id} value={x.id}>{x.nombre}</option>)}
        </Select>
      )}
      {ref.tipo === 'valor' && (
        <EntradaDeValor dominio={dominio.clave} campo={campo} operador="eq" valor={ref.valor} opciones={opciones}
          onChange={v => onChange({ tipo: 'valor', valor: v })} etiqueta={t('pol.valor_de_referencia')} />
      )}
      {ref.tipo === 'campo' && (
        <Select suelto className="pol-campo pol-campo--medio" aria-label={t('pol.campo_de_referencia')} value={ref.campo ?? ''}
          onChange={e => onChange({ tipo: 'campo', campo: e.target.value })} placeholder={t('pol.elige')}>
          {dominio.campos.filter(c => c.tipo === campo.tipo && c.clave !== campo.clave)
            .map(c => <option key={c.clave} value={c.clave}>{etiquetaDeCampo(dominio.clave, c)}</option>)}
        </Select>
      )}
    </span>
  )
}
