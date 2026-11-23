// Pestaña Matriz de permisos de GRC. 23-11-2026: troceado de GrcPage sin cambio de comportamiento.
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useToast } from '../context/ToastContext'
import { grcApi } from '../services/api'
import type { MatrizDePermisos as PermMatrix } from '../services/api/tipos-grc'
import { Check, Loader2, RefreshCw, RotateCcw, X } from 'lucide-react'
import { Buscador, Button, Spinner, TablaSimple } from '../components/ui'
import { extractErr } from '../utils/helpers'
import { useAppT } from '../i18n/AppLangContext'
import { ACTIONS, type Role, moduleInfo, rolesDeReserva, usePermisos } from './GrcComun'

// ── Shared style atoms ────────────────────────────────────────────────────────

// ═══════════════════════════════════════════════════════════════════════════════
// 1. MATRIZ DE PERMISOS (wired to API)
// ═══════════════════════════════════════════════════════════════════════════════

export function MatrixTab({ roles }: { roles: Role[] }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [selRole, setSelRole] = useState('all')
  const [saving, setSaving] = useState<string | null>(null)
  const [filtro, setFiltro] = useState('')

  const { data, isLoading, refetch } = usePermisos()
  const matrix: PermMatrix = data?.matrix || {}
  const acciones = data?.actions || ACTIONS
  const modulos = (data?.modules || Object.keys(Object.values(matrix)[0] || {}))
    .map(moduleInfo(t))
    .filter(m => !filtro || `${m.id} ${m.label}`.toLowerCase().includes(filtro.toLowerCase()))
  // Las columnas son los roles que la matriz gobierna (los de la API); el
  // nombre y el color salen de los roles configurados si existen.
  const rolesDeLaMatriz: Role[] = (data?.roles || roles.map(r => r.id)).map(id =>
    roles.find(r => r.id === id) || rolesDeReserva(t).find(r => r.id === id) || { id, label: id, color: 'var(--text-2)' })

  const { mutate: resetMatrix, isPending: resetting } = useMutation({
    mutationFn: () => grcApi.seedPermissions(),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['grc-permissions'] }); toast.success(t('grc.matrix_reset_success')) },
    onError: e => toast.error(extractErr(e, t('grc.error'))),
  })

  const togglePerm = async (role: string, module: string, action: string, current: boolean) => {
    const key = `${role}/${module}/${action}`
    setSaving(key)
    try {
      await grcApi.updatePermission(role, module, action, { allowed: !current })
      qc.invalidateQueries({ queryKey: ['grc-permissions'] })
    } catch (e) {
      toast.error(extractErr(e, t('grc.error_save_permission')))
    } finally {
      setSaving(null)
    }
  }

  const displayRoles = selRole === 'all' ? rolesDeLaMatriz : rolesDeLaMatriz.filter((r: Role) => r.id === selRole)

  if (isLoading) return <Spinner />

  return (
    <div>
      <div className="grc-row">
        <div className="grc-row-2">
          <span className="grc-label">{t('grc.role')}:</span>
          <Button size="sm" variant={selRole === 'all' ? 'primary' : 'secondary'} onClick={() => setSelRole('all')}>
            {t('grc.all')}
          </Button>
          {rolesDeLaMatriz.map(r => (
            <Button key={r.id} size="sm" variant={selRole === r.id ? 'primary' : 'secondary'} onClick={() => setSelRole(r.id)}>
              {r.label}
            </Button>
          ))}
        </div>
        <div className="u-row-8">
          <Buscador value={filtro} onChange={setFiltro} placeholder={t('pagina_grc.filtrar_modulos')}
            aria-label={t('pagina_grc.filtrar_modulos_2')} inputClassName="grc-page-e3" />
          <Button size="sm" variant="secondary" icon={<RefreshCw size={14} />} onClick={() => refetch()}>{t('grc.refresh')}</Button>
          <Button size="sm" variant="secondary" icon={<RotateCcw size={14} />} loading={resetting}
            onClick={() => { openConfirmGlobal({ message: t('grc.reset_confirm'), onConfirm: () => resetMatrix(), danger: true }) }}>
            {resetting ? t('grc.resetting') : t('grc.reset_to_default')}
          </Button>
        </div>
      </div>

      <div className="u-scroll-x">
        <TablaSimple claseTabla="grc-table">
          <thead>
            <tr className="grc-row-3">
              <th className="grc-th">{t('grc.module')}</th>
              {displayRoles.map(r => (
                <th key={r.id} colSpan={acciones.length}
                  className="grc-th-2 grc-page-e4" style={{ '--grc-page-color': r.color } as CSSProperties}>
                  {r.label}
                </th>
              ))}
            </tr>
            <tr className="u-border-b">
              <th aria-hidden="true" className="grc-th-3" />
              {displayRoles.map(r => acciones.map(a => (
                <th key={r.id + a} className="grc-th-4">
                  {t(`grc.action_${a}`)}
                </th>
              )))}
            </tr>
          </thead>
          <tbody>
            {modulos.map((mod, mIdx) => (
              <tr key={mod.id} className={`u-border-b ${mIdx % 2 === 0 ? 'grcpage-sx4' : 'grcpage-sx5'}`}>
                <td className={`grc-td ${mIdx % 2 === 0 ? 'grcpage-sx4' : 'grcpage-sx5'}`}>
                  {mod.label}
                </td>
                {displayRoles.map(role =>
                  acciones.map(action => {
                    const celda = matrix[role.id]?.[mod.id]?.[action];
                    const key = `${role.id}/${mod.id}/${action}`;
                    const isSaving = saving === key;
                    // Sin casilla: el módulo no tiene esa operación (nada que gobernar).
                    if (celda === undefined) return <td key={key} className="grc-td-2">—</td>;
                    const allowed = celda;
                    return (
                      <td
                        key={key}
                        className="grc-td-3"
                        onClick={() => togglePerm(role.id, mod.id, action, allowed)}
                        title={`${role.label} · ${mod.label} · ${t(`grc.action_${action}`)}: ${allowed ? t('grc.allowed') : t('grc.denied')} — ${t('grc.click_to_change')}`}
                      >
                        <span className={`grc-label-2 ${isSaving ? 'grcpage-sx6' : 'grcpage-sx7'}`}>
                          {isSaving ? <Loader2 size={14} className="grc-girando" aria-hidden />
                            : allowed ? <Check size={15} className="grc-permitido" aria-label={t('grc.allowed')} />
                            : <X size={15} className="grc-denegado" aria-label={t('grc.denied')} />}
                        </span>
                      </td>
                    );
                  })
                )}
              </tr>
            ))}
          </tbody>
        </TablaSimple>
      </div>

      <div className="grc-row-4">
        <div className="grc-row-5"><Check size={14} className="grc-permitido" aria-hidden /><span>{t('grc.allowed')}</span></div>
        <div className="grc-row-5"><X size={14} className="grc-denegado" aria-hidden /><span>{t('grc.denied')}</span></div>
        <span className="grc-label-4">{t('grc.changes_auto_saved')}</span>
      </div>
    </div>
  )
}
