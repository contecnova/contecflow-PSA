/**
 * Compartir un cuaderno entero o una sección con personas, equipos o
 * departamentos, en lectura o edición. Solo el dueño. Cada cambio queda en la
 * auditoría del servidor; la persona recibe un aviso.
 *
 * 23-11-2026: también con los agentes de código del propio dueño (MCP, solo
 * lectura; docs/integraciones/MCP.md). Privado por defecto; la empresa tiene
 * que tener encendido Mi cuaderno por MCP (si no, el servidor lo dice).
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Trash2 } from 'lucide-react'
import { Button, FormField, IconButton, Modal, Segmentado, Select, Spinner, Switch, UserSelect } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { useAuth } from '../../context/AuthContext'
import { confirmar } from '../../context/ConfirmContext'
import { extractErr } from '../../utils/helpers'
import { cuadernoApi, CLAVES_CUADERNO } from '../../services/api/cuaderno'
import type { Arbol, Cuaderno } from '../../services/api/cuaderno'

type Destino = 'user' | 'team' | 'department'

export default function ModalCompartir({ cuaderno, seccionId, permitido, onClose }: {
  cuaderno: Cuaderno; seccionId?: string | null; permitido: Arbol['features']['sharing']; onClose: () => void
}) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { user } = useAuth()
  const claveLista = ['cuaderno', 'shares', cuaderno.id]
  const { data: lista = [], isLoading } = useQuery({ queryKey: claveLista, queryFn: () => cuadernoApi.comparticiones(cuaderno.id) })
  const { data: destinos } = useQuery({ queryKey: ['cuaderno', 'destinos'], queryFn: () => cuadernoApi.destinos() })
  const tipos = (['user', 'team', 'department'] as Destino[]).filter(x => permitido[{ user: 'users', team: 'teams', department: 'departments' }[x] as keyof typeof permitido])
  const [tipo, setTipo] = useState<Destino>(tipos[0] ?? 'user')
  const [destino, setDestino] = useState('')
  const [permiso, setPermiso] = useState<'read' | 'edit'>('read')
  const [alcance, setAlcance] = useState<string>(seccionId || '')

  const refrescar = () => { void qc.invalidateQueries({ queryKey: claveLista }); void qc.invalidateQueries({ queryKey: CLAVES_CUADERNO.arbol }) }
  const anadir = useMutation({
    mutationFn: () => cuadernoApi.compartir(cuaderno.id, { target_type: tipo, target_id: destino, permission: permiso, section_id: alcance || null }),
    onSuccess: () => { setDestino(''); refrescar(); toast.success(t('cuaderno.compartido')) },
    onError: e => toast.error(extractErr(e)),
  })
  const cambiar = useMutation({
    mutationFn: ({ id, p }: { id: string; p: 'read' | 'edit' }) => cuadernoApi.cambiarPermiso(id, p),
    onSuccess: refrescar, onError: e => toast.error(extractErr(e)),
  })
  const quitar = useMutation({
    mutationFn: (id: string) => cuadernoApi.dejarDeCompartir(id),
    onSuccess: refrescar, onError: e => toast.error(extractErr(e)),
  })
  const conAgentes = lista.find(s => s.target_type === 'agents' && !s.section_id)
  const agentes = useMutation({
    mutationFn: (activar: boolean) => activar
      ? cuadernoApi.compartir(cuaderno.id, { target_type: 'agents', target_id: 'me', permission: 'read', section_id: null })
      : cuadernoApi.dejarDeCompartir(conAgentes?.id ?? ''),
    onSuccess: refrescar, onError: e => toast.error(extractErr(e)),
  })

  const opcionesDeGrupo = (tipo === 'team' ? destinos?.teams : destinos?.departments) ?? []
  const nombreDeSeccion = (id: string | null) => cuaderno.sections.find(s => s.id === id)?.title
  return (
    <Modal open onClose={onClose} title={t('cuaderno.compartir_titulo', { cuaderno: cuaderno.title })} size="lg" avisarSinGuardar={false}>
      <div className="cdn-form">
        <p className="cdn-ayuda">{t('cuaderno.compartir_ayuda')}</p>
        {tipos.length === 0 ? <p className="cdn-ayuda">{t('cuaderno.compartir_desactivado')}</p> : (
          <>
            <Segmentado aria-label={t('cuaderno.compartir_con')} valor={tipo} onChange={v => { setTipo(v as Destino); setDestino('') }}
              opciones={tipos.map(x => ({ valor: x, etiqueta: t(`cuaderno.destino_${x}`) }))} />
            <div className="cdn-form__fila">
              <FormField label={t(`cuaderno.destino_${tipo}`)}>
                {tipo === 'user'
                  ? <UserSelect value={destino} onChange={id => setDestino(id)} filterFn={u => u.id !== user?.id} />
                  : <Select value={destino} onChange={e => setDestino(e.target.value)}
                      options={opcionesDeGrupo.map(g => ({ value: g, label: g }))} aria-label={t(`cuaderno.destino_${tipo}`)} />}
              </FormField>
              <FormField label={t('cuaderno.compartir_alcance')}>
                <Select value={alcance} onChange={e => setAlcance(e.target.value)} placeholder={false} aria-label={t('cuaderno.compartir_alcance')}
                  options={[{ value: '', label: t('cuaderno.cuaderno_entero') }, ...cuaderno.sections.map(s => ({ value: s.id, label: t('cuaderno.solo_seccion', { seccion: s.title }) }))]} />
              </FormField>
              <FormField label={t('cuaderno.permiso')}>
                <Select value={permiso} onChange={e => setPermiso(e.target.value as 'read' | 'edit')} placeholder={false} aria-label={t('cuaderno.permiso')}
                  options={[{ value: 'read', label: t('cuaderno.permiso_read') }, { value: 'edit', label: t('cuaderno.permiso_edit') }]} />
              </FormField>
            </div>
            <div className="cdn-form__acciones">
              <Button onClick={() => anadir.mutate()} disabled={!destino} loading={anadir.isPending}>{t('cuaderno.compartir')}</Button>
            </div>
          </>
        )}
        {!cuaderno.is_quick && (
          <Switch checked={!!conAgentes} disabled={agentes.isPending || isLoading}
            onChange={v => agentes.mutate(v)} label={t('cuaderno.agentes_compartir')} ayuda={t('cuaderno.agentes_ayuda')} />
        )}
        <h3 className="ds-eyebrow">{t('cuaderno.compartido_con')}</h3>
        {isLoading ? <Spinner /> : lista.length === 0 ? <p className="cdn-ayuda">{t('cuaderno.sin_compartir')}</p> : (
          <ul className="cdn-lista">
            {lista.map(s => (
              <li key={s.id} className="cdn-lista__fila">
                <span className="cdn-lista__texto">
                  <strong>{s.target_type === 'agents' ? t('cuaderno.destino_agents') : s.target_name}</strong>
                  {s.target_type !== 'agents' && <> · {t(`cuaderno.destino_${s.target_type}`)}</>}
                  {s.section_id ? ` · ${t('cuaderno.solo_seccion', { seccion: nombreDeSeccion(s.section_id) || '—' })}` : ''}
                </span>
                {s.target_type === 'agents' ? <span>{t('cuaderno.permiso_read')}</span> : (
                  <Select suelto tamano="sm" value={s.permission} placeholder={false} aria-label={t('cuaderno.permiso')}
                    onChange={e => cambiar.mutate({ id: s.id, p: e.target.value as 'read' | 'edit' })}
                    options={[{ value: 'read', label: t('cuaderno.permiso_read') }, { value: 'edit', label: t('cuaderno.permiso_edit') }]} />
                )}
                <IconButton ariaLabel={t('cuaderno.dejar_de_compartir')} className="cdn-boton"
                  onClick={async () => { if (await confirmar({ message: t('cuaderno.dejar_de_compartir_confirmar', { nombre: s.target_type === 'agents' ? t('cuaderno.destino_agents') : s.target_name }), danger: true })) quitar.mutate(s.id) }}>
                  <Trash2 size={14} />
                </IconButton>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Modal>
  )
}
