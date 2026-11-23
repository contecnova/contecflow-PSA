/**
 * Editor del menú lateral (23-11-2026, «menú personalizable»).
 *
 * Lo usan el modo «Personalizar menú» del propio menú (cada persona, con las
 * categorías y pestañas que su rol permite) y Configuración › «Menú por defecto»
 * (el administrador, para cada rol, con todo el menú).
 *
 * - Categorías: se reordenan arrastrando (ratón) o con «Subir»/«Bajar»
 *   (teclado y pantallas táctiles); cada movimiento se anuncia en `aria-live`.
 * - Pestañas: casilla para ocultarla o mostrarla y «Subir»/«Bajar» (sin
 *   arrastre: decisión documentada en docs/CONFIGURACION.md).
 * - Los cambios se entregan al momento (`onChange`): quien lo usa decide si
 *   guarda ya (menú personal) o con un botón (menú por defecto).
 */
import { useEffect, useRef, useState, type DragEvent } from 'react'
import { ChevronDown, ChevronUp, ChevronRight, GripVertical } from 'lucide-react'
import { Checkbox, IconButton } from '../ui'
import { useAppLang } from '../../i18n/AppLangContext'
import {
  categoriasOrdenadas, estaOculta, moverCategoria, moverPestana, pestanasOrdenadas, alternarOculta,
  type PreferenciaDeMenu,
} from '../../permisos/menuPersonal'
import { getGroupLabel, getNavLabel, type NavGroupConfig, type TFn } from './menuLateral'
import './EditorDeMenu.css'

export interface EditorDeMenuProps {
  /** Categorías que se pueden personalizar (para una persona, ya filtradas por permisos). */
  grupos: NavGroupConfig[]
  valor: PreferenciaDeMenu | null
  onChange: (p: PreferenciaDeMenu) => void
  /** Prefijo de los ids (dos editores en la misma página). */
  idBase?: string
}

export default function EditorDeMenu({ grupos, valor, onChange, idBase = 'editor-menu' }: EditorDeMenuProps) {
  const { t } = useAppLang()
  const tNav = t as unknown as TFn
  const [abierta, setAbierta] = useState<string | null>(null)
  const [anuncio, setAnuncio] = useState('')
  const [arrastrando, setArrastrando] = useState<number | null>(null)
  const [sobre, setSobre] = useState<number | null>(null)
  const [enfocar, setEnfocar] = useState<string | null>(null)
  const raiz = useRef<HTMLDivElement | null>(null)

  const categorias = categoriasOrdenadas(grupos.filter(g => g.items.some(i => !i.divider && i.to)), valor)
  const ids = categorias.map(g => g.id || '')

  // Tras mover con el teclado, el foco sigue en el botón del elemento movido
  // (si quedó desactivado en un extremo, en su compañero).
  useEffect(() => {
    if (!enfocar || !raiz.current) return
    const [clave, dir] = enfocar.split('|')
    const sel = (d: string) => raiz.current?.querySelector<HTMLButtonElement>(`[data-enfoque="${CSS.escape(`${clave}|${d}`)}"]`)
    const boton = sel(dir)
    if (boton && !boton.disabled) boton.focus()
    else sel(dir === 'subir' ? 'bajar' : 'subir')?.focus()
    setEnfocar(null)
  }, [enfocar, valor])

  const nombreDe = (g: NavGroupConfig) => getGroupLabel(g, tNav)

  const moverCat = (desde: number, hasta: number, dir?: 'subir' | 'bajar') => {
    if (hasta < 0 || hasta >= ids.length || desde === hasta) return
    onChange(moverCategoria(valor, ids, desde, hasta))
    setAnuncio(t('menu_personal.movida', { nombre: nombreDe(categorias[desde]), pos: String(hasta + 1), total: String(ids.length) }))
    if (dir) setEnfocar(`${ids[desde]}|${dir}`)
  }

  const soltar = (e: DragEvent<HTMLLIElement>, hasta: number) => {
    e.preventDefault()
    if (arrastrando !== null) moverCat(arrastrando, hasta)
    setArrastrando(null); setSobre(null)
  }

  return (
    <div className="editor-menu" ref={raiz}>
      <p className="editor-menu__ayuda">{t('menu_personal.ayuda')}</p>
      <div className="u-sr-only" aria-live="polite" role="status">{anuncio}</div>
      <ol className="editor-menu__lista" aria-label={t('menu_personal.categorias')}>
        {categorias.map((g, i) => {
          const gid = g.id || ''
          const nombre = nombreDe(g)
          const pestanas = pestanasOrdenadas(g, valor)
          const rutas = pestanas.map(p => p.to || '')
          const visibles = pestanas.filter(p => !estaOculta(valor, gid, p.to || '')).length
          const desplegada = abierta === gid
          const idLista = `${idBase}-${gid}`
          return (
            <li key={gid}
              className={['editor-menu__cat', arrastrando === i ? 'editor-menu__cat--arrastrando' : '', sobre === i && arrastrando !== i ? 'editor-menu__cat--sobre' : ''].filter(Boolean).join(' ')}
              draggable
              onDragStart={e => { setArrastrando(i); e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', gid) }}
              onDragOver={e => { if (arrastrando !== null) { e.preventDefault(); setSobre(i) } }}
              onDragLeave={() => setSobre(s => (s === i ? null : s))}
              onDrop={e => soltar(e, i)}
              onDragEnd={() => { setArrastrando(null); setSobre(null) }}
            >
              <div className="editor-menu__fila">
                <span className="editor-menu__asa" title={t('menu_personal.arrastrar')} aria-hidden><GripVertical size={14} /></span>
                <span className="editor-menu__icono" aria-hidden>{g.icon}</span>
                <span className="editor-menu__nombre">{nombre}</span>
                <span className="editor-menu__cuenta">{t('menu_personal.visibles', { n: String(visibles), total: String(pestanas.length) })}</span>
                <IconButton ariaLabel={t('menu_personal.subir', { nombre })} disabled={i === 0} data-enfoque={`${gid}|subir`}
                  className="editor-menu__mover" onClick={() => moverCat(i, i - 1, 'subir')}><ChevronUp size={14} /></IconButton>
                <IconButton ariaLabel={t('menu_personal.bajar', { nombre })} disabled={i === categorias.length - 1} data-enfoque={`${gid}|bajar`}
                  className="editor-menu__mover" onClick={() => moverCat(i, i + 1, 'bajar')}><ChevronDown size={14} /></IconButton>
                <IconButton ariaLabel={t('menu_personal.pestanas', { nombre })} aria-expanded={desplegada} aria-controls={idLista}
                  className="editor-menu__mover" onClick={() => setAbierta(a => (a === gid ? null : gid))}>
                  <ChevronRight size={14} className={desplegada ? 'editor-menu__flecha--abierta' : 'editor-menu__flecha'} />
                </IconButton>
              </div>
              {desplegada && (
                <ul className="editor-menu__pestanas" id={idLista} aria-label={t('menu_personal.pestanas', { nombre })}>
                  {pestanas.map((p, j) => {
                    const ruta = p.to || ''
                    const etiqueta = getNavLabel(ruta, p.label, tNav)
                    const oculta = estaOculta(valor, gid, ruta)
                    const moverP = (hasta: number, dir: 'subir' | 'bajar') => {
                      onChange(moverPestana(valor, gid, rutas, j, hasta))
                      setAnuncio(t('menu_personal.movida', { nombre: etiqueta, pos: String(hasta + 1), total: String(rutas.length) }))
                      setEnfocar(`${gid}${ruta}|${dir}`)
                    }
                    return (
                      <li key={ruta} className={`editor-menu__pestana${oculta ? ' editor-menu__pestana--oculta' : ''}`}>
                        <Checkbox checked={!oculta} label={etiqueta} className="editor-menu__casilla"
                          onChange={() => {
                            onChange(alternarOculta(valor, gid, ruta))
                            setAnuncio(t(oculta ? 'menu_personal.mostrada' : 'menu_personal.ocultada', { nombre: etiqueta }))
                          }} />
                        <IconButton ariaLabel={t('menu_personal.subir', { nombre: etiqueta })} disabled={j === 0} data-enfoque={`${gid}${ruta}|subir`}
                          className="editor-menu__mover" onClick={() => moverP(j - 1, 'subir')}><ChevronUp size={13} /></IconButton>
                        <IconButton ariaLabel={t('menu_personal.bajar', { nombre: etiqueta })} disabled={j === pestanas.length - 1} data-enfoque={`${gid}${ruta}|bajar`}
                          className="editor-menu__mover" onClick={() => moverP(j + 1, 'bajar')}><ChevronDown size={13} /></IconButton>
                      </li>
                    )
                  })}
                </ul>
              )}
            </li>
          )
        })}
      </ol>
    </div>
  )
}
