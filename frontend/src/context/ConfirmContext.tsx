/**
 * ConfirmContext — reemplaza los confirm()/prompt() nativos del navegador con
 * un diálogo propio, no bloqueante y accesible (construido sobre `Modal`, que
 * usa `useDialogo`: trampa de foco, Esc y devolución del foco).
 *
 * Formas de uso:
 *
 * 1. Promesa (recomendada):
 *    const { confirmar, pedirTexto } = useConfirm()
 *    if (await confirmar({ message: '¿Eliminar X?', danger: true })) del(id)
 *    const motivo = await pedirTexto({ message: 'Motivo del rechazo', required: true })
 *    if (motivo !== null) rechazar(motivo)
 *
 *    Para una acción irreversible se puede exigir teclear una palabra:
 *    confirmar({ message: '…', danger: true, palabraConfirmacion: 'BORRAR' })
 *
 * 2. Callback (compatibilidad):
 *    const { openConfirm } = useConfirm()
 *    openConfirm({ message: '¿Eliminar X?', onConfirm: () => del(id) })
 *
 * 3. Sin hook (desde cualquier sitio):
 *    import { confirmar, pedirTexto, openConfirmGlobal } from '../context/ConfirmContext'
 *
 * El `confirm()`/`prompt()`/`alert()` nativos están prohibidos por ESLint en src.
 */
import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
} from 'react'
import type { ReactNode } from 'react'
import { Button, Modal } from '../components/ui'
import { useAppT } from '../hooks/useAppT'

export interface ConfirmOptions {
  title?: string
  message: ReactNode
  onConfirm?: () => void
  danger?: boolean
  /** Texto del botón de aceptar. */
  confirmLabel?: string
  /** Si se indica, el botón de aceptar no se habilita hasta teclear esta palabra. */
  palabraConfirmacion?: string
}

export interface PromptOptions {
  title?: string
  message: ReactNode
  /** Etiqueta del campo; si falta se usa el propio mensaje como nombre accesible. */
  label?: string
  defaultValue?: string
  placeholder?: string
  /** Si es true, no se puede aceptar con el campo vacío. */
  required?: boolean
  multiline?: boolean
  /** 'password' oculta lo escrito (reautenticacion antes de cambiar el 2FA). */
  inputType?: 'text' | 'number' | 'password'
  confirmLabel?: string
  danger?: boolean
}

export interface ConfirmContextValue {
  openConfirm: (opts: ConfirmOptions) => void
  /** Resuelve true si el usuario acepta, false si cancela o cierra. */
  confirmar: (opts: Omit<ConfirmOptions, 'onConfirm'>) => Promise<boolean>
  /** Resuelve el texto introducido, o null si el usuario cancela o cierra. */
  pedirTexto: (opts: PromptOptions) => Promise<string | null>
}

type Peticion =
  | { id: number; tipo: 'confirm'; opts: ConfirmOptions; resolver: (v: boolean) => void }
  | { id: number; tipo: 'prompt'; opts: PromptOptions; resolver: (v: string | null) => void }

let _siguienteId = 0

const ConfirmContext = createContext<ConfirmContextValue | null>(null)

// Referencia mutable al proveedor montado: permite llamar sin hook.
let _ref: ConfirmContextValue | null = null

/** Abre el diálogo de confirmación con callback desde cualquier lugar. */
export function openConfirmGlobal(opts: ConfirmOptions): void {
  _ref?.openConfirm(opts)
}

/** Versión sin hook de `useConfirm().confirmar`. */
export function confirmar(opts: Omit<ConfirmOptions, 'onConfirm'>): Promise<boolean> {
  if (!_ref) {
    console.warn('confirmar(): ConfirmProvider no está montado')
    return Promise.resolve(false)
  }
  return _ref.confirmar(opts)
}

/** Versión sin hook de `useConfirm().pedirTexto`. */
export function pedirTexto(opts: PromptOptions): Promise<string | null> {
  if (!_ref) {
    console.warn('pedirTexto(): ConfirmProvider no está montado')
    return Promise.resolve(null)
  }
  return _ref.pedirTexto(opts)
}

interface ConfirmProviderProps {
  children?: ReactNode
}

export function ConfirmProvider({ children }: ConfirmProviderProps) {
  const [peticion, setPeticion] = useState<Peticion | null>(null)
  const actual = useRef<Peticion | null>(null)

  const abrir = useCallback((p: Peticion) => {
    // Si ya había un diálogo abierto, se da por cancelado.
    const previa = actual.current
    if (previa) {
      if (previa.tipo === 'confirm') previa.resolver(false)
      else previa.resolver(null)
    }
    actual.current = p
    setPeticion(p)
  }, [])

  const confirmarCtx = useCallback((opts: Omit<ConfirmOptions, 'onConfirm'>) =>
    new Promise<boolean>(resolve => abrir({ id: ++_siguienteId, tipo: 'confirm', opts, resolver: resolve })), [abrir])

  const pedirTextoCtx = useCallback((opts: PromptOptions) =>
    new Promise<string | null>(resolve => abrir({ id: ++_siguienteId, tipo: 'prompt', opts, resolver: resolve })), [abrir])

  const openConfirm = useCallback((opts: ConfirmOptions) => {
    void confirmarCtx(opts).then(ok => { if (ok) opts.onConfirm?.() })
  }, [confirmarCtx])

  const value = useMemo<ConfirmContextValue>(
    () => ({ openConfirm, confirmar: confirmarCtx, pedirTexto: pedirTextoCtx }),
    [openConfirm, confirmarCtx, pedirTextoCtx],
  )

  useEffect(() => {
    _ref = value
    return () => { if (_ref === value) _ref = null }
  }, [value])

  const cerrar = useCallback((resultado: boolean | string | null) => {
    const p = actual.current
    actual.current = null
    setPeticion(null)
    if (!p) return
    if (p.tipo === 'confirm') p.resolver(resultado === true)
    else p.resolver(typeof resultado === 'string' ? resultado : null)
  }, [])

  return (
    <ConfirmContext.Provider value={value}>
      {children}
      {peticion && (
        <DialogoConfirmacion
          // Una petición nueva reinicia el estado interno (texto tecleado).
          key={peticion.id}
          peticion={peticion}
          onResultado={cerrar}
        />
      )}
    </ConfirmContext.Provider>
  )
}

function DialogoConfirmacion({ peticion, onResultado }: {
  peticion: Peticion
  onResultado: (r: boolean | string | null) => void
}) {
  const { t } = useAppT()
  const idCampo = useId()
  const idMensaje = useId()
  const { opts } = peticion
  const danger = Boolean(opts.danger)
  const inicial = peticion.tipo === 'prompt' ? (peticion.opts.defaultValue ?? '') : ''
  const [texto, setTexto] = useState(inicial)

  const titulo = opts.title || (danger ? t('confirm_modal.danger_title') : t('confirm_modal.default_title'))
  const cancelar = () => onResultado(peticion.tipo === 'confirm' ? false : null)

  let puedeAceptar = true
  if (peticion.tipo === 'confirm' && peticion.opts.palabraConfirmacion) {
    puedeAceptar = texto.trim() === peticion.opts.palabraConfirmacion
  }
  if (peticion.tipo === 'prompt' && peticion.opts.required) {
    puedeAceptar = texto.trim() !== ''
  }

  const aceptar = () => {
    if (!puedeAceptar) return
    onResultado(peticion.tipo === 'confirm' ? true : texto)
  }

  const estiloCampo = {
    background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
    borderRadius: 'var(--radius-md)', padding: '9px 13px',
    color: 'var(--text-1)', fontSize: 'var(--text-base)',
    fontFamily: 'var(--font-sans)', width: '100%',
  } as const

  const palabra = peticion.tipo === 'confirm' ? peticion.opts.palabraConfirmacion : undefined
  const necesitaCampo = peticion.tipo === 'prompt' || Boolean(palabra)
  const etiquetaCampo = peticion.tipo === 'prompt'
    ? peticion.opts.label
    : palabra ? `Escribe ${palabra} para confirmar` : undefined

  return (
    <Modal open onClose={cancelar} title={titulo} size="sm">
      <form
        onSubmit={e => { e.preventDefault(); aceptar() }}
        aria-describedby={idMensaje}
      >
        <div id={idMensaje} style={{ color: 'var(--text-2)', fontSize: 'var(--text-md)', lineHeight: 1.6, marginBottom: necesitaCampo ? 14 : 24, whiteSpace: 'pre-line' }}>
          {opts.message}
        </div>
        {necesitaCampo && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5, marginBottom: 24 }}>
            {etiquetaCampo && (
              <label htmlFor={idCampo} id={`${idCampo}-etiqueta`} style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--text-2)' }}>
                {etiquetaCampo}
              </label>
            )}
            {peticion.tipo === 'prompt' && peticion.opts.multiline ? (
              <textarea
                id={idCampo}
                aria-labelledby={etiquetaCampo ? `${idCampo}-etiqueta` : undefined}
                autoFocus
                rows={3}
                value={texto}
                placeholder={peticion.opts.placeholder}
                aria-label={etiquetaCampo ? undefined : (typeof opts.message === 'string' ? opts.message : titulo)}
                aria-required={peticion.opts.required || undefined}
                onChange={e => setTexto(e.target.value)}
                style={{ ...estiloCampo, resize: 'vertical' }}
              />
            ) : (
              <input
                id={idCampo}
                aria-labelledby={etiquetaCampo ? `${idCampo}-etiqueta` : undefined}
                autoFocus
                type={peticion.tipo === 'prompt' ? (peticion.opts.inputType ?? 'text') : 'text'}
                value={texto}
                autoComplete="off"
                placeholder={peticion.tipo === 'prompt' ? peticion.opts.placeholder : palabra}
                aria-label={etiquetaCampo ? undefined : (typeof opts.message === 'string' ? opts.message : titulo)}
                aria-required={(peticion.tipo === 'prompt' ? peticion.opts.required : true) || undefined}
                onChange={e => setTexto(e.target.value)}
                style={estiloCampo}
              />
            )}
          </div>
        )}
        <div className="u-actions-10">
          <Button variant="secondary" onClick={cancelar}>{t('common.cancel')}</Button>
          <Button type="submit" variant={danger ? 'danger' : 'primary'} disabled={!puedeAceptar}>
            {opts.confirmLabel || t('confirm_modal.default_title')}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

export function useConfirm(): ConfirmContextValue {
  const ctx = useContext(ConfirmContext)
  if (!ctx) throw new Error('useConfirm must be used within ConfirmProvider')
  return ctx
}
