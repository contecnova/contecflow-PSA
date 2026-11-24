/**
 * Papelera del cuaderno: lo borrado (cuadernos, secciones, páginas) se puede
 * restaurar o borrar del todo. Se vacía sola pasados los días de la
 * configuración; lo que está bajo bloqueo legal no se borra.
 */
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { RotateCcw, Trash2 } from 'lucide-react'
import { Button, EmptyState, IconButton, Modal, Spinner } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { confirmar } from '../../context/ConfirmContext'
import { extractErr, fmtDateTime } from '../../utils/helpers'
import { cuadernoApi, CLAVES_CUADERNO } from '../../services/api/cuaderno'

export default function ModalPapelera({ onClose }: { onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { data = [], isLoading } = useQuery({ queryKey: CLAVES_CUADERNO.papelera, queryFn: cuadernoApi.papelera })
  const refrescar = () => Promise.all([qc.invalidateQueries({ queryKey: CLAVES_CUADERNO.papelera }), qc.invalidateQueries({ queryKey: CLAVES_CUADERNO.arbol })])
  const hacer = async (f: () => Promise<unknown>, ok: string) => {
    try { await f(); await refrescar(); toast.success(ok) } catch (e) { toast.error(extractErr(e)) }
  }
  return (
    <Modal open onClose={onClose} title={t('cuaderno.papelera')} size="lg" avisarSinGuardar={false}>
      <div className="cdn-form">
        <p className="cdn-ayuda">{t('cuaderno.papelera_ayuda')}</p>
        {isLoading ? <Spinner /> : data.length === 0 ? <EmptyState icon={<Trash2 size={28} />} title={t('cuaderno.papelera_vacia')} /> : (
          <ul className="cdn-lista">
            {data.map(x => (
              <li key={`${x.kind}:${x.id}`} className="cdn-lista__fila">
                <span className="cdn-lista__texto">
                  <strong>{x.title || t('cuaderno.sin_titulo')}</strong>
                  <span className="cdn-lista__sub">{t(`cuaderno.tipo_${x.kind}`)} · {fmtDateTime(x.deleted_at)}</span>
                </span>
                <IconButton ariaLabel={t('cuaderno.restaurar')} className="cdn-boton" onClick={() => { void hacer(() => cuadernoApi.restaurar(x.kind, x.id), t('cuaderno.restaurado')) }}>
                  <RotateCcw size={14} />
                </IconButton>
                <IconButton ariaLabel={t('cuaderno.borrar_definitivo')} className="cdn-boton" onClick={async () => {
                  if (await confirmar({ message: t('cuaderno.borrar_definitivo_confirmar', { nombre: x.title || t('cuaderno.sin_titulo') }), danger: true }))
                    await hacer(() => cuadernoApi.purgar(x.kind, x.id), t('cuaderno.borrado'))
                }}><Trash2 size={14} /></IconButton>
              </li>
            ))}
          </ul>
        )}
        <div className="cdn-form__acciones">
          {data.length > 0 && (
            <Button variant="danger" onClick={async () => {
              if (await confirmar({ message: t('cuaderno.vaciar_confirmar'), danger: true })) await hacer(() => cuadernoApi.vaciarPapelera(), t('cuaderno.papelera_vaciada'))
            }}>{t('cuaderno.vaciar_papelera')}</Button>
          )}
          <Button variant="secondary" onClick={onClose}>{t('common.close')}</Button>
        </div>
      </div>
    </Modal>
  )
}
