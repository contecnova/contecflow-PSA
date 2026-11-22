/**
 * Diseñador visual del flujo de demanda (22-11-2026): diagrama por capas en SVG
 * a partir de `POST /demand/flows/diagram`. Una fase por fila; las aristas que
 * saltan o vuelven atrás se dibujan por los lados con su etiqueta. Pulsar un
 * nodo abre esa fase en el editor.
 */
import { useEffect, useMemo, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Button, Spinner } from '../ui'
import { demandaApi, type AristaDeDiagrama, type DefinicionDeFlujo, type DiagramaDeFlujo, type NodoDeDiagrama } from '../../services/api/demanda'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { etiquetaDe } from './comunes'
import './demanda.css'

const ANCHO = 220
const ALTO = 48
const SEPARACION = 84
const X0 = 150

export default function DiagramaDeFlujoVista({ def, onAbrirFase }: { def: DefinicionDeFlujo; onAbrirFase: (clave: string) => void }) {
  const t = useAppT()
  const toast = useToast()
  const [dg, setDg] = useState<DiagramaDeFlujo | null>(null)
  const pedir = useMutation({
    mutationFn: () => demandaApi.diagrama(def),
    onSuccess: setDg,
    onError: (e: unknown) => toast.error(extractErr(e, t('demanda.error'))),
  })
  useEffect(() => { pedir.mutate() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const { nodos, indice } = useMemo(() => {
    const lista: NodoDeDiagrama[] = [...(dg?.nodes || [])]
    for (const e of dg?.edges || []) {
      for (const id of [e.from, e.to]) if (!lista.some(n => n.id === id)) lista.push({ id, label: id, kind: 'end' })
    }
    // Los finales al fondo.
    lista.sort((a, b) => Number(a.kind === 'end') - Number(b.kind === 'end'))
    return { nodos: lista, indice: new Map(lista.map((n, i) => [n.id, i])) }
  }, [dg])

  const y = (i: number) => 20 + i * SEPARACION
  const alto = y(nodos.length) + 10
  const trazado = (e: AristaDeDiagrama, k: number): { d: string; lx: number; ly: number } | null => {
    const a = indice.get(e.from), b = indice.get(e.to)
    if (a === undefined || b === undefined) return null
    if (b === a + 1) return { d: `M ${X0 + ANCHO / 2} ${y(a) + ALTO} L ${X0 + ANCHO / 2} ${y(b)}`, lx: X0 + ANCHO / 2 + 6, ly: (y(a) + ALTO + y(b)) / 2 + 4 }
    // Saltos y retornos: por la derecha (hacia atrás) o por la izquierda (hacia delante).
    const derecha = b <= a
    const x = derecha ? X0 + ANCHO + 30 + (k % 5) * 18 : X0 - 30 - (k % 5) * 18
    const xa = derecha ? X0 + ANCHO : X0
    const ya = y(a) + ALTO / 2, yb = y(b) + ALTO / 2
    return { d: `M ${xa} ${ya} C ${x} ${ya}, ${x} ${yb}, ${xa} ${yb}`, lx: x, ly: (ya + yb) / 2 }
  }
  if (pedir.isPending && !dg) return <Spinner />
  return (
    <div className="u-stack-12">
      <div className="dem-fila dem-fila--entre">
        <p className="plan-muted">{t('demanda.cfg_diagrama_ayuda')}</p>
        <Button size="sm" variant="secondary" loading={pedir.isPending} onClick={() => pedir.mutate()}>{t('demanda.cfg_actualizar_diagrama')}</Button>
      </div>
      {nodos.length === 0 ? <p className="plan-muted">{t('demanda.cfg_sin_fases')}</p> : (
        <div className="dem-diagrama">
          <svg role="img" aria-label={t('demanda.cfg_diagrama')} width={X0 + ANCHO + 220} height={alto} viewBox={`0 0 ${X0 + ANCHO + 220} ${alto}`}>
            <defs><marker id="dem-flecha" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" className="dem-dg__flecha" /></marker></defs>
            {(dg?.edges || []).map((e, k) => {
              const p = trazado(e, k)
              if (!p) return null
              return (
                <g key={k}>
                  <path d={p.d} className={`dem-dg__arista dem-dg__arista--${e.label}`} markerEnd="url(#dem-flecha)" fill="none" />
                  <text x={p.lx} y={p.ly} className="dem-dg__etiqueta">{etiquetaDe(t, 'arista', e.label)}</text>
                </g>
              )
            })}
            {nodos.map((n, i) => {
              const final = n.kind === 'end'
              return (
                <g key={n.id} className={`dem-dg__nodo${final ? ' dem-dg__nodo--final' : ''}${n.conditional ? ' dem-dg__nodo--cond' : ''}`}
                  role={final ? undefined : 'button'} tabIndex={final ? undefined : 0}
                  onClick={() => { if (!final) onAbrirFase(n.id) }}
                  onKeyDown={e => { if (!final && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); onAbrirFase(n.id) } }}>
                  <rect x={X0} y={y(i)} width={ANCHO} height={ALTO} rx={final ? 24 : 8} />
                  <text x={X0 + ANCHO / 2} y={y(i) + 20} textAnchor="middle" className="dem-dg__titulo">{final ? etiquetaDe(t, 'fin', n.id.replace('end:', '')) : n.label}</text>
                  {!final && <text x={X0 + ANCHO / 2} y={y(i) + 36} textAnchor="middle" className="dem-dg__sub">{etiquetaDe(t, 'kind', n.kind)}{n.parallel ? ` · ${t('demanda.cfg_paralelo_corto')}` : ''}{n.conditional ? ` · ${t('demanda.cfg_condicional_corto')}` : ''}{n.steps != null ? ` · ${n.steps}` : ''}</text>}
                </g>
              )
            })}
          </svg>
        </div>
      )}
    </div>
  )
}
