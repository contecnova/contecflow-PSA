/**
 * «Todas mis tareas y etiquetas»: las casillas pendientes y las etiquetas de
 * todos los cuadernos que la persona puede leer (los suyos y lo compartido con
 * ella). Se usa en Mi cuaderno, en la bandeja de entrada y en «Mi día».
 * Marcar una casilla aquí la marca también en su página.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { CheckSquare, NotebookPen } from 'lucide-react'
import { Checkbox, EmptyState, Pulsable, Segmentado, Select, Spinner } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr, fmtDate } from '../../utils/helpers'
import { cuadernoApi, CLAVES_CUADERNO } from '../../services/api/cuaderno'
import type { ElementoDeCuaderno, Etiqueta } from '../../services/api/cuaderno'
import { IconoDeEtiqueta, nombreDeEtiqueta } from './comun'

type Vista = 'todo' | 'done' | 'tag'

export default function TodasMisTareas({ compacto = false, limite }: { compacto?: boolean; limite?: number }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [vista, setVista] = useState<Vista>('todo')
  const [etiqueta, setEtiqueta] = useState('')
  const filtro = vista === 'tag' ? { kind: 'tag' as const, status: 'all' as const, tag: etiqueta || undefined }
    : { kind: 'todo' as const, status: vista === 'done' ? 'done' as const : 'open' as const }
  const { data: items = [], isLoading } = useQuery({ queryKey: CLAVES_CUADERNO.elementos(filtro), queryFn: () => cuadernoApi.elementos(filtro) })
  const { data: etiquetas = [] } = useQuery<Etiqueta[]>({ queryKey: ['cuaderno', 'etiquetas'], queryFn: cuadernoApi.etiquetas, staleTime: 300_000 })
  const marcar = useMutation({
    mutationFn: ({ id, v }: { id: string; v: boolean }) => cuadernoApi.marcar(id, v),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['cuaderno', 'elementos'] }) },
    onError: e => toast.error(extractErr(e)),
  })
  const abrir = (x: ElementoDeCuaderno) => navigate(`/notebook?page=${x.page_id}`)
  const lista = limite ? items.slice(0, limite) : items

  return (
    <div className={`cdn-tareas${compacto ? ' cdn-tareas--compacto' : ''}`}>
      {!compacto && (
        <div className="cdn-tareas__filtros">
          <Segmentado aria-label={t('cuaderno.tareas_vista')} valor={vista} onChange={v => setVista(v as Vista)} opciones={[
            { valor: 'todo', etiqueta: t('cuaderno.pendientes') }, { valor: 'done', etiqueta: t('cuaderno.hechas') },
            { valor: 'tag', etiqueta: t('cuaderno.etiquetas') },
          ]} />
          {vista === 'tag' && (
            <Select suelto tamano="sm" value={etiqueta} onChange={e => setEtiqueta(e.target.value)} aria-label={t('cuaderno.etiqueta')}
              options={[{ value: '', label: t('cuaderno.todas_las_etiquetas') }, ...etiquetas.map(e => ({ value: e.key, label: nombreDeEtiqueta(t, e, e.key) }))]} placeholder={false} />
          )}
        </div>
      )}
      {isLoading ? <Spinner /> : lista.length === 0 ? (
        <EmptyState icon={vista === 'tag' ? <NotebookPen size={28} /> : <CheckSquare size={28} />}
          title={vista === 'tag' ? t('cuaderno.sin_etiquetas') : t('cuaderno.sin_tareas')} description={t('cuaderno.sin_tareas_ayuda')} />
      ) : (
        <ul className="cdn-lista">
          {lista.map(x => {
            const e = etiquetas.find(y => y.key === x.tag_key)
            const vencida = x.due_date && !x.checked && x.due_date < new Date().toISOString().slice(0, 10)
            return (
              <li key={x.id} className="cdn-lista__fila">
                {x.kind === 'todo'
                  ? <Checkbox checked={x.checked} aria-label={x.text || t('cuaderno.casilla')} onChange={v => marcar.mutate({ id: x.id, v })} />
                  : <span className={`cdn-etiqueta cdn-color--${e?.color || 'gray'}`}><IconoDeEtiqueta icono={e?.icon} /><span>{nombreDeEtiqueta(t, e, x.tag_key || '')}</span></span>}
                <Pulsable className="cdn-lista__texto" onClick={() => abrir(x)}>
                  <span className={x.checked ? 'cdn-tachado' : undefined}>{x.text || t('cuaderno.sin_texto')}</span>
                  <span className="cdn-lista__sub">{[x.notebook_title, x.page_title || t('cuaderno.sin_titulo')].filter(Boolean).join(' › ')}</span>
                </Pulsable>
                {x.due_date && <span className={`cdn-fecha${vencida ? ' cdn-fecha--vencida' : ''}`}>{fmtDate(x.due_date)}</span>}
              </li>
            )
          })}
        </ul>
      )}
      {compacto && items.length > (limite || 0) && limite && (
        <Pulsable className="cdn-arbol__nueva" onClick={() => navigate('/notebook?tab=tasks')}>{t('cuaderno.ver_todas', { n: items.length })}</Pulsable>
      )}
    </div>
  )
}
