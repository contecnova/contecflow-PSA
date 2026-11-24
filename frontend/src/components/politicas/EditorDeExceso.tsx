/**
 * Bandas por porcentaje de exceso sobre una referencia (p. ej. la tabla de
 * dietas de la ciudad del gasto): «hasta +20 % → +1 nivel; más → +2 niveles».
 * La barra muestra las bandas a escala; cada banda tiene sus resultados.
 */
import type { CSSProperties } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import type { BandaDeExceso, DominioDePoliticas, Exceso } from '../../services/api/tipos-politicas'
import { Button, Select } from '../ui'
import { SelectorDeReferencia } from './ConstructorDeCondiciones'
import EditorDeResultados from './EditorDeResultados'
import { useTextos } from './comun'
import { Input } from '../ui'

export default function EditorDeExceso({ dominio, valor, onChange }: {
  dominio: DominioDePoliticas; valor: Exceso | null; onChange: (e: Exceso | null) => void
}) {
  const { t, etiquetaDeCampo } = useTextos()
  const medibles = dominio.campos.filter(c => c.tipo === 'importe' || c.tipo === 'numero')
  if (!valor) {
    return (
      <Button size="xs" variant="secondary" icon={<Plus size={13} />} disabled={!medibles.length}
        onClick={() => onChange({ campo: medibles[0].clave, referencia: { tipo: 'tabla' },
          bandas: [{ desde: 0, hasta: 20, resultados: [{ tipo: 'add_approval_levels', niveles: 1 }] },
                   { desde: 20, hasta: null, resultados: [{ tipo: 'add_approval_levels', niveles: 2 }] }] })}>
        {t('pol.anadir_bandas')}
      </Button>
    )
  }
  const campo = medibles.find(c => c.clave === valor.campo) ?? medibles[0]
  const bandas = [...valor.bandas].sort((a, b) => a.desde - b.desde)
  const techo = Math.max(100, ...bandas.map(b => (b.hasta ?? b.desde + 50)))
  const cambiarBanda = (i: number, b: BandaDeExceso) => onChange({ ...valor, bandas: bandas.map((x, j) => (j === i ? b : x)) })
  const anadir = () => {
    const ultima = bandas[bandas.length - 1]
    const desde = ultima ? (ultima.hasta ?? ultima.desde + 20) : 0
    const previas = ultima && ultima.hasta === null ? bandas.map((b, j) => (j === bandas.length - 1 ? { ...b, hasta: desde } : b)) : bandas
    onChange({ ...valor, bandas: [...previas, { desde, hasta: null, resultados: [] }] })
  }
  return (
    <div className="u-stack-10">
      <div className="pol-fila">
        <span className="pol-ayuda">{t('pol.exceso_de')}</span>
        <Select suelto className="pol-campo pol-campo--medio" aria-label={t('pol.campo_medido')} value={campo.clave}
          onChange={e => onChange({ ...valor, campo: e.target.value })} placeholder={false}>
          {medibles.map(c => <option key={c.clave} value={c.clave}>{etiquetaDeCampo(dominio.clave, c)}</option>)}
        </Select>
        <span className="pol-ayuda">{t('pol.sobre')}</span>
        <SelectorDeReferencia dominio={dominio} campo={campo} valor={valor.referencia} onChange={r => onChange({ ...valor, referencia: r })} />
        <Button size="xs" variant="ghost" icon={<Trash2 size={13} />} onClick={() => onChange(null)}>{t('pol.quitar_bandas')}</Button>
      </div>
      <div className="pol-bandas-barra" role="img" aria-label={t('pol.bandas_resumen', { n: bandas.length })}>
        {bandas.map((b, i) => {
          const izq = (b.desde / techo) * 100
          const ancho = (((b.hasta ?? techo) - b.desde) / techo) * 100
          return (
            <div key={i} className={`pol-banda-segmento pol-banda-segmento--${Math.min(i, 3)}`} style={{ '--pol-izq': `${izq}%`, '--pol-ancho': `${ancho}%` } as CSSProperties}>
              {b.hasta === null ? `> ${b.desde} %` : `${b.desde}–${b.hasta} %`}
            </div>
          )
        })}
      </div>
      <div className="pol-bandas-escala" aria-hidden><span>0 %</span><span>{Math.round(techo / 2)} %</span><span>{techo} %</span></div>
      {bandas.map((b, i) => (
        <div key={i} className="pol-tarjeta" role="group" aria-label={t('pol.banda_n', { n: i + 1 })}>
          <div className="pol-fila">
            <span className="pol-subtitulo">{t('pol.banda_n', { n: i + 1 })}</span>
            <div className="pol-fila">
              <Input label={t('pol.mas_de')} type="number" min={0} aria-label={t('pol.desde_pct')} value={b.desde} onChange={e => cambiarBanda(i, { ...b, desde: Number(e.target.value) })} /> %
            </div>
            <div className="pol-fila">
              <Input label={t('pol.hasta_incluido')} type="number" min={0} aria-label={t('pol.hasta_pct')} value={b.hasta ?? ''} placeholder={t('pol.sin_techo')} onChange={e => cambiarBanda(i, { ...b, hasta: e.target.value === '' ? null : Number(e.target.value) })} /> %
            </div>
            <Button size="xs" variant="ghost" icon={<Trash2 size={13} />} onClick={() => onChange({ ...valor, bandas: bandas.filter((_, j) => j !== i) })}
              title={t('pol.quitar_banda')}><span className="u-sr-only">{t('pol.quitar_banda')}</span></Button>
          </div>
          <EditorDeResultados dominio={dominio} valor={b.resultados} onChange={r => cambiarBanda(i, { ...b, resultados: r })}
            titulo={t('pol.banda_n', { n: i + 1 })} />
        </div>
      ))}
      <Button size="xs" variant="secondary" icon={<Plus size={13} />} onClick={anadir}>{t('pol.anadir_banda')}</Button>
    </div>
  )
}
