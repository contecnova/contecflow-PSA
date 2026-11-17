import { createContext, createElement, useContext, useEffect, useMemo, useRef, useSyncExternalStore } from 'react'
import type { ReactNode } from 'react'
import { useAppLang } from '../../i18n/AppLangContext'
import { traducirSinHook } from '../../i18n/traducirSinHook'
import { idiomaActivo } from '../../utils/helpers'

type Traducir = (clave: string, params?: Record<string, string | number>) => string

/**
 * Textos de interfaz del kit (16-11-2026).
 *
 * El kit (Spinner, Modal, DataTable, Pagination, Confirm…) y el aviso global
 * (`ToastContext`) no saben si están dentro del portal de clientes. Por
 * defecto usan el traductor de operador (es/en/zh, `useAppLang`); el portal
 * envuelve su árbol con `TextosDeInterfazProvider` y les da el suyo (8
 * idiomas). Las claves son las mismas (`uikit.*`, `pagination.*`, `toast.*`,
 * `common.*`…): están en `i18n/langs/*.mjs` y en `i18n/portal/*.ts`.
 */
/** Texto de un error del servidor con código estable (`code` + `params`), o
 *  null si ese traductor no tiene el código (se enseña el `detail`). */
export type TraductorDeCodigos = (codigo: string, params?: Record<string, unknown> | null) => string | null

export interface TextosDeInterfaz {
  t: Traducir
  lang: string
  /** Solo el portal: los errores del servidor con código, en su idioma. */
  errorDelServidor?: TraductorDeCodigos
}

export const TextosDeInterfazContext = createContext<TextosDeInterfaz | null>(null)

// ── Lo que ven los globales (montados por encima del portal) ────────────────
// `ToastProvider` vive en la raíz, por encima de cualquier proveedor de textos:
// no puede leer el contexto. Cada `TextosDeInterfazProvider` montado se apunta
// aquí y manda el último que se montó (en la práctica solo hay uno: el portal).
const pila: { valor: TextosDeInterfaz }[] = []
const oyentes = new Set<() => void>()
let version = 0
const avisar = () => { version += 1; oyentes.forEach(o => o()) }
const instantanea = () => version
const suscribir = (o: () => void) => { oyentes.add(o); return () => { oyentes.delete(o) } }
const actual = (): TextosDeInterfaz | null => pila.length ? pila[pila.length - 1].valor : null

/** Da a su árbol (y a los globales mientras esté montado) otro traductor de interfaz. */
export function TextosDeInterfazProvider({ t, lang, errorDelServidor, children }: TextosDeInterfaz & { children?: ReactNode }) {
  const valor: TextosDeInterfaz = { t, lang, errorDelServidor }
  const entrada = useRef({ valor })
  // Que los globales lean siempre el último `t` (con las personalizaciones del
  // administrador) sin re-renderizarlos en cada pintado del portal.
  entrada.current.valor = valor
  useEffect(() => {
    const e = entrada.current
    pila.push(e)
    avisar()
    return () => {
      const i = pila.indexOf(e)
      if (i >= 0) pila.splice(i, 1)
      avisar()
    }
  }, [])
  // Cambio de idioma: los globales se vuelven a pintar.
  useEffect(() => { avisar() }, [lang])
  return createElement(TextosDeInterfazContext.Provider, { value: valor }, children)
}

function useTraductorDeOperador(): { t: Traducir; lang: string } {
  try {
    const ctx = useAppLang()
    const t = ctx?.t
    const lang = ctx?.lang
    return {
      t: typeof t === 'function' ? t : traducirSinHook,
      lang: typeof lang === 'string' && lang ? lang : idiomaActivo(),
    }
  } catch {
    return { t: traducirSinHook, lang: idiomaActivo() }
  }
}

/**
 * `t()` para las primitivas del kit (Spinner, Modal, DataTable, ColVisibility…).
 *
 * Primero, el traductor del `TextosDeInterfazProvider` que las envuelva (el
 * portal). Si no hay, el de operador: se pintan en todas partes, también en
 * tests y árboles montados sin `AppLangProvider`; `useAppLang()` lanza ahí a
 * propósito y se cae a `traducirSinHook`, que lee el idioma guardado y los
 * diccionarios ya cargados.
 *
 * Se pasa por `useAppLang()` (y no por `useContext(AppLangContext)`) para que
 * los tests que simulan ese módulo con `vi.mock` sigan sirviendo. El orden de
 * hooks no cambia: siempre `useContext` del proveedor de textos y después
 * `useAppLang`.
 */
export function useTextoUi(): Traducir {
  const propio = useContext(TextosDeInterfazContext)
  const operador = useTraductorDeOperador()
  return propio ? propio.t : operador.t
}

/**
 * Idioma activo para las primitivas del kit (selector de fecha): el del
 * proveedor de textos si lo hay, si no el de operador o el guardado.
 */
export function useIdiomaUi(): string {
  const propio = useContext(TextosDeInterfazContext)
  const operador = useTraductorDeOperador()
  return propio ? propio.lang : operador.lang
}

/**
 * Traductores para los componentes **globales** montados por encima de todo
 * (`ToastProvider`): los del último `TextosDeInterfazProvider` montado (el
 * portal, mientras esté en pantalla) o, si no hay, el de operador (que no
 * traduce códigos de error: el operador lee el `detail`).
 */
export function useTextosUiGlobales(): { t: Traducir; errorDelServidor: TraductorDeCodigos } {
  // Se re-renderiza cuando se monta o desmonta un proveedor o cambia su idioma;
  // el `t` se lee en el momento de traducir (el portal lo renueva en cada pintado).
  const v = useSyncExternalStore(suscribir, instantanea, instantanea)
  const operador = useTraductorDeOperador().t
  return useMemo(() => ({
    t: (clave: string, params?: Record<string, string | number>) => {
      const montado = actual()
      return montado ? montado.t(clave, params) : operador(clave, params)
    },
    errorDelServidor: (codigo: string, params?: Record<string, unknown> | null) =>
      actual()?.errorDelServidor?.(codigo, params) ?? null,
  }), [operador, v])  // eslint-disable-line react-hooks/exhaustive-deps
}

/** Solo tests: vacía la pila de proveedores. */
export function _reiniciarTextosDeInterfaz(): void {
  pila.length = 0
  avisar()
}

/**
 * Sustituye los `{param}` que el traductor haya dejado sin rellenar (el de
 * respaldo, `traducirSinHook`, no interpola: pasa en pruebas y en árboles sin
 * `AppLangProvider`).
 */
export function conParametros(texto: string, params: Record<string, string | number>): string {
  return texto.replace(/\{(\w+)\}/g, (m, k: string) => (k in params ? String(params[k]) : m))
}
