/**
 * Dibujo a mano alzada o con lápiz (Pointer Events: ratón, dedo o lápiz con
 * presión). Se guardan los trazos (JSON) y el servidor genera el SVG; se puede
 * volver a abrir y seguir dibujando.
 */
import { useEffect, useRef, useState } from 'react'
import type { PointerEvent as EventoDePuntero } from 'react'
import { Eraser, Trash2, Undo2 } from 'lucide-react'
import { Button, IconButton, Modal, Segmentado } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import type { Dibujo, Trazo } from '../../services/api/cuaderno'

const ANCHO = 900
const ALTO = 520
/** Color del trazo → token del tema (el SVG final lo pinta el servidor con colores fijos). */
const COLORES: Record<string, string> = {
  ink: '--text-1', blue: '--accent', red: '--danger', green: '--success', amber: '--warning',
}
const GROSORES = ['2', '4', '8']

function pintar(ctx: CanvasRenderingContext2D, trazos: Trazo[], estilo: CSSStyleDeclaration) {
  ctx.clearRect(0, 0, ANCHO, ALTO)
  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'
  for (const t of trazos) {
    const token = t.erase ? '--surface-1' : (COLORES[t.color] || '--text-1')
    ctx.strokeStyle = estilo.getPropertyValue(token).trim() || (t.erase ? 'white' : 'black')
    ctx.lineWidth = t.width
    ctx.beginPath()
    t.points.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)))
    if (t.points.length === 1) ctx.lineTo(t.points[0][0] + 0.1, t.points[0][1])
    ctx.stroke()
  }
}

export default function ModalDibujo({ inicial, onClose, onGuardar, guardando }: {
  inicial?: Dibujo | null; onClose: () => void; onGuardar: (d: Dibujo) => void; guardando?: boolean
}) {
  const t = useAppT()
  const lienzo = useRef<HTMLCanvasElement>(null)
  const [trazos, setTrazos] = useState<Trazo[]>(inicial?.strokes ?? [])
  const actual = useRef<Trazo | null>(null)
  const [color, setColor] = useState('ink')
  const [grosor, setGrosor] = useState('4')
  const [goma, setGoma] = useState(false)

  useEffect(() => {
    const c = lienzo.current?.getContext('2d')
    if (c && lienzo.current) pintar(c, actual.current ? [...trazos, actual.current] : trazos, getComputedStyle(lienzo.current))
  }, [trazos])

  const punto = (e: EventoDePuntero<HTMLCanvasElement>): [number, number] => {
    const r = e.currentTarget.getBoundingClientRect()
    return [Math.round(((e.clientX - r.left) / r.width) * ANCHO * 10) / 10, Math.round(((e.clientY - r.top) / r.height) * ALTO * 10) / 10]
  }
  const empezar = (e: EventoDePuntero<HTMLCanvasElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId)
    const presion = e.pointerType === 'pen' && e.pressure > 0 ? 0.5 + e.pressure : 1
    actual.current = { color, width: Math.min(60, Number(grosor) * presion * (goma ? 4 : 1)), points: [punto(e)], erase: goma }
  }
  const mover = (e: EventoDePuntero<HTMLCanvasElement>) => {
    if (!actual.current || actual.current.points.length >= 5000) return
    actual.current.points.push(punto(e))
    const c = lienzo.current?.getContext('2d')
    if (c && lienzo.current) pintar(c, [...trazos, actual.current], getComputedStyle(lienzo.current))
  }
  const terminar = () => {
    if (!actual.current) return
    const t0 = actual.current
    actual.current = null
    setTrazos(ts => [...ts, t0].slice(-2000))
  }

  return (
    <Modal open onClose={onClose} title={t('cuaderno.dibujo_titulo')} size="xl" cambiosSinGuardar={trazos.length > (inicial?.strokes.length ?? 0)}>
      <div className="cdn-dibujo">
        <div className="cdn-dibujo__barra">
          <Segmentado aria-label={t('cuaderno.dibujo_color')} valor={goma ? '' : color}
            onChange={v => { setColor(v); setGoma(false) }}
            opciones={Object.keys(COLORES).map(k => ({ valor: k, etiqueta: <span className={`cdn-muestra cdn-muestra--${k}`} />, 'aria-label': t(`cuaderno.color_${k}`) }))} />
          <Segmentado aria-label={t('cuaderno.dibujo_grosor')} valor={grosor} onChange={setGrosor}
            opciones={GROSORES.map(g => ({ valor: g, etiqueta: `${g}px` }))} />
          <IconButton ariaLabel={t('cuaderno.dibujo_goma')} aria-pressed={goma} onClick={() => setGoma(g => !g)} className="cdn-boton"><Eraser size={14} /></IconButton>
          <IconButton ariaLabel={t('cuaderno.deshacer')} onClick={() => setTrazos(ts => ts.slice(0, -1))} disabled={!trazos.length} className="cdn-boton"><Undo2 size={14} /></IconButton>
          <IconButton ariaLabel={t('cuaderno.dibujo_borrar_todo')} onClick={() => setTrazos([])} disabled={!trazos.length} className="cdn-boton"><Trash2 size={14} /></IconButton>
        </div>
        <canvas ref={lienzo} width={ANCHO} height={ALTO} className="cdn-dibujo__lienzo" role="img" aria-label={t('cuaderno.dibujo_lienzo')}
          onPointerDown={empezar} onPointerMove={mover} onPointerUp={terminar} onPointerCancel={terminar} onPointerLeave={terminar} />
        <div className="cdn-form__acciones">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => onGuardar({ width: ANCHO, height: ALTO, strokes: trazos })} loading={guardando} disabled={!trazos.length}>
            {t('common.save')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
