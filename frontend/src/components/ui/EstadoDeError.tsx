/**
 * EstadoDeError — lo que se pinta cuando una carga falla (auditoría 22-11-2026,
 * A9 del 04: 118 errores tragados se veían como «sin datos»).
 *
 * Uso con react-query: `if (q.isError) return <EstadoDeError error={q.error} onReintentar={() => q.refetch()} />`.
 * El texto sale de `mensajeDeError` (códigos del servidor traducidos, 422
 * resumidos) en el idioma de quien mira (operador o portal: `useTextosUiGlobales`).
 */
import { AlertTriangle, RotateCcw } from 'lucide-react'
import { EmptyState, Button } from './index'
import { useTextoUi, useTextosUiGlobales } from './useTextoUi'
import { mensajeDeError } from '../../utils/mensajeDeError'

export interface EstadoDeErrorProps {
  /** El error de la consulta o de la llamada. */
  error: unknown
  /** Si se indica, botón «Reintentar». */
  onReintentar?: () => void
  /** Título; por defecto «No se pudieron cargar los datos». */
  titulo?: string
}

export default function EstadoDeError({ error, onReintentar, titulo }: EstadoDeErrorProps) {
  const t = useTextoUi()
  const { errorDelServidor } = useTextosUiGlobales()
  const detalle = mensajeDeError(error, errorDelServidor, t('toast.load_error'))
  return (
    <div role="alert">
      <EmptyState
        svgIcon={<AlertTriangle size={28} strokeWidth={1.5} aria-hidden />}
        title={titulo || t('toast.load_error')}
        description={detalle !== (titulo || t('toast.load_error')) ? detalle : ''}
        action={onReintentar ? (
          <Button variant="secondary" icon={<RotateCcw size={14} aria-hidden />} onClick={onReintentar}>
            {t('uikit.reintentar')}
          </Button>
        ) : null}
      />
    </div>
  )
}
