/**
 * VistaDeDatos — pinta un resultado estructurado del servidor (análisis de
 * impacto, planes de un cambio, simulación…) como listas de clave y valor y
 * tablas, con las claves traducidas (`sd_mercado.campo.<clave>`). Lo que no
 * tiene traducción se ve con la clave legible, nunca cortado.
 */
import { useAppT } from '../../i18n/AppLangContext'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import './sdMercado.css'

type Valor = unknown
const legible = (k: string) => k.replace(/_/g, ' ').replace(/^\w/, c => c.toUpperCase())
const esObjeto = (v: Valor): v is Record<string, Valor> => !!v && typeof v === 'object' && !Array.isArray(v)
const esEscalar = (v: Valor) => v == null || ['string', 'number', 'boolean'].includes(typeof v)

function Escalar({ v }: { v: Valor }) {
  const t = useAppT()
  if (v == null || v === '') return <>—</>
  if (typeof v === 'boolean') return <>{t(v ? 'sd_mercado.si' : 'sd_mercado.no')}</>
  if (typeof v === 'number') return <>{Number.isInteger(v) ? v : v.toFixed(2)}</>
  return <span className="sdm-pre">{String(v)}</span>
}

export default function VistaDeDatos({ datos, nivel = 0 }: { datos: Valor; nivel?: number }) {
  const t = useAppT()
  const etiqueta = (k: string) => etiquetaCodigo(t, 'sd_mercado.campo', k, legible(k))
  if (esEscalar(datos)) return <Escalar v={datos} />
  if (Array.isArray(datos)) {
    if (datos.length === 0) return <>—</>
    if (datos.every(esEscalar)) return <span className="sdm-wrap">{datos.map(String).join(', ')}</span>
    if (datos.every(esObjeto)) {
      const columnas = Array.from(new Set(datos.flatMap(d => Object.keys(d as object)))).filter(c =>
        datos.every(d => esEscalar((d as Record<string, Valor>)[c]) || Array.isArray((d as Record<string, Valor>)[c])))
      const complejas = Array.from(new Set(datos.flatMap(d => Object.keys(d as object)))).filter(c => !columnas.includes(c))
      return (
        <div className="sdm-table-wrap">
          <table className="u-table u-table-sm">
            <thead><tr>{columnas.map(c => <th key={c}>{etiqueta(c)}</th>)}</tr></thead>
            <tbody>
              {datos.map((fila, i) => (
                <tr key={i} className="u-border-b">
                  {columnas.map(c => <td key={c} className="sdm-wrap"><VistaDeDatos datos={(fila as Record<string, Valor>)[c]} nivel={nivel + 1} /></td>)}
                </tr>
              ))}
            </tbody>
          </table>
          {complejas.length > 0 && datos.map((fila, i) => (
            <div key={`c${i}`} className="u-stack-6 u-mb-10">
              {complejas.map(c => (fila as Record<string, Valor>)[c] != null && (
                <div key={c}><div className="ds-eyebrow">{etiqueta(c)}</div><VistaDeDatos datos={(fila as Record<string, Valor>)[c]} nivel={nivel + 1} /></div>
              ))}
            </div>
          ))}
        </div>
      )
    }
    return <div className="u-stack-6">{datos.map((d, i) => <VistaDeDatos key={i} datos={d} nivel={nivel + 1} />)}</div>
  }
  const obj = datos as Record<string, Valor>
  const simples = Object.keys(obj).filter(k => esEscalar(obj[k]) || (Array.isArray(obj[k]) && (obj[k] as Valor[]).every(esEscalar)))
  const compuestos = Object.keys(obj).filter(k => !simples.includes(k))
  return (
    <div className="u-stack-10">
      {simples.length > 0 && (
        <dl className="sdm-kv">
          {simples.map(k => [<dt key={`k${k}`}>{etiqueta(k)}</dt>, <dd key={`v${k}`}><VistaDeDatos datos={obj[k]} nivel={nivel + 1} /></dd>])}
        </dl>
      )}
      {compuestos.map(k => (
        <div key={k} className="u-stack-6">
          <div className="ds-eyebrow">{etiqueta(k)}</div>
          <VistaDeDatos datos={obj[k]} nivel={nivel + 1} />
        </div>
      ))}
    </div>
  )
}
