// Pestañas de agentes y clases de la CMDB. 23-11-2026: troceado de CMDBPage sin cambio de comportamiento.
import { useState } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr, fmtDateTime } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { cmdbApi } from '../services/api'
import { Button, Spinner, EmptyState, IconButton, Select, TablaSimple, Input } from '../components/ui'
import { ArrowDown, ArrowUp, Bot, Plus, Trash2 } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import { POLL_LIVE_MS } from '../constants/timings'
import { type CI, CI_TYPES, type Campo, chip, useCamposDeClase, useEtiqueta, useEtiquetaDeCampo } from './CMDBComun'

// ── CMDB Agents on-prem tab ──────────────────────────────────────────────────
type Agente = { id: string; name: string; os_type?: string; is_active: boolean; last_checkin_at?: string; last_hostname?: string; ci_id?: string; token_prefix?: string }

export function CMDBAgentsTab({ items }: { items: CI[] }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [agentName, setAgentName] = useState('')
  const [osType, setOsType] = useState('linux')
  const [newToken, setNewToken] = useState<string | null>(null)

  const { data: agents = [], isLoading } = useQuery<Agente[]>({
    queryKey: ['cmdb-agents'],
    queryFn: () => cmdbApi.agents().then(r => r.data ?? []),
    refetchInterval: POLL_LIVE_MS,
  })
  const nombreCI = (id?: string) => items.find(i => i.id === id)?.name

  const { mutate: registerAgent, isPending } = useMutation({
    mutationFn: () => cmdbApi.registerAgent({ name: agentName.trim(), os_type: osType }),
    onSuccess: (res) => {
      toast.success(t('cmdb.agent_registered'))
      setNewToken(res.data?.token ?? null)
      setAgentName('')
      qc.invalidateQueries({ queryKey: ['cmdb-agents'] })
    },
    onError: e => toast.error(extractErr(e, t('cmdb.agent_register_error'))),
  })

  const { mutate: revokeAgent } = useMutation({
    mutationFn: (id: string) => cmdbApi.deleteAgent(id),
    onSuccess: () => { toast.success(t('cmdb.agent_revoked')); qc.invalidateQueries({ queryKey: ['cmdb-agents'] }) },
    onError: e => toast.error(extractErr(e, t('cmdb.agent_revoke_error'))),
  })

  return (
    <div className="cmdb-agents">
      <div className="cmdb-panel">
        <div className="cmdb-card-title">
          {t('cmdb.registrar_nuevo_agente_on_prem')}
        </div>
        <div className="cmdb-agent-form">
          <Input label={t('cmdb.nombre_del_agente')} id="agent-name" value={agentName} onChange={e => setAgentName(e.target.value)} placeholder={t('cmdb.agent_name_ph')} />
          <Select label={t('cmdb.platform')} placeholder={false} id="agent-os" value={osType} onChange={e => setOsType(e.target.value)}>
              <option value="linux">{t('cmdb.os_linux')}</option>
              <option value="windows">{t('cmdb.os_windows')}</option>
            </Select>
          <Button onClick={() => registerAgent()} loading={isPending} disabled={!agentName.trim()}>{t('cmdb.register')}</Button>
        </div>

        {newToken && (
          <div className="cmdb-token" role="status">
            <div className="cmdb-token__title">
              {t('cmdb.token_de_registro_usalo_una_sola_vez')}
            </div>
            <code className="ds-codigo cmdb-token__value">
              {newToken}
            </code>
            <div className="cmdb-token__hint">
              {t('cmdb.ejecuta_el_agente_con')} <code className="ds-codigo u-mono">CMDB_TOKEN={newToken} ./cmdb-agent</code>
            </div>
            <div className="cmdb-mt10"><Button variant="ghost" size="sm" onClick={() => setNewToken(null)}>{t('cmdb.hide_token')}</Button></div>
          </div>
        )}
      </div>

      {/* `cmdb-panel--scroll` lleva `position: relative`: el texto oculto de la
          cabecera es absoluto y, sin eso, ensanchaba la página en móvil. */}
      <div className="cmdb-panel cmdb-panel--scroll">
        <div className="cmdb-card-title">
          {t('cmdb.registered_agents', { n: agents.length })}
        </div>
        {isLoading ? <Spinner /> : agents.length === 0 ? (
          <EmptyState icon={<Bot size={28} />} title={t('cmdb.no_hay_agentes_registrados_registra_el_primero')} />
        ) : (
          <TablaSimple claseTabla="cmdb-table">
            <thead>
              <tr className="u-border-b">
                <th className="cmdb-th">{t('cmdb.nombre_del_agente')}</th>
                <th className="cmdb-th">{t('cmdb.platform')}</th>
                <th className="cmdb-th">{t('cmdb.status')}</th>
                <th className="cmdb-th">{t('cmdb.last_checkin')}</th>
                <th className="cmdb-th">{t('cmdb.its_ci')}</th>
                <th className="cmdb-th"><span className="u-sr-only">{t('cmdb.actions')}</span></th>
              </tr>
            </thead>
            <tbody>
              {agents.map(ag => (
                <tr key={ag.id} className="u-border-b">
                  <td className="cmdb-td cmdb-td--strong">{ag.name}</td>
                  <td className="cmdb-td">{ag.os_type || '—'}</td>
                  <td className="cmdb-td">
                    <span className="cmdb-chip" style={chip(ag.is_active ? 'var(--success)' : 'var(--text-2)')}>
                      {ag.is_active ? t('cmdb.agent_active') : t('cmdb.agent_revoked_state')}
                    </span>
                  </td>
                  <td className="cmdb-td cmdb-td--sm">
                    {ag.last_checkin_at ? fmtDateTime(ag.last_checkin_at) : t('cmdb.never')}
                  </td>
                  <td className="cmdb-td">{nombreCI(ag.ci_id) || ag.last_hostname || '—'}</td>
                  <td className="cmdb-td">
                    {ag.is_active && (
                      <IconButton variante="caja" tono="peligro" ariaLabel={t('cmdb.revoke_agent')}
                        onClick={() => openConfirmGlobal({ message: t('cmdb.revoke_agent_q', { name: ag.name }), onConfirm: () => revokeAgent(ag.id), danger: true })}><Trash2 size={14} /></IconButton>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </TablaSimple>
        )}
      </div>
    </div>
  )
}

// ── Clases: los datos propios de cada clase, por organización ────────────────
export function ClasesTab() {
  const t = useAppT()
  const etiqueta = useEtiqueta()
  const etiquetaDeCampo = useEtiquetaDeCampo()
  const toast = useToast()
  const qc = useQueryClient()
  const { data } = useCamposDeClase()
  const [clase, setClase] = useState('server')
  const [filas, setFilas] = useState<Campo[] | null>(null)
  const actuales = filas ?? data?.clases[clase] ?? []
  const cambiar = (i: number, cambio: Partial<Campo>) =>
    setFilas(actuales.map((f, j) => (j === i ? { ...f, ...cambio } : f)))
  const mover = (i: number, d: number) => {
    const otra = [...actuales]; const [f] = otra.splice(i, 1); otra.splice(i + d, 0, f); setFilas(otra)
  }
  const { mutate: guardar, isPending } = useMutation({
    mutationFn: () => cmdbApi.saveClassFields(clase, actuales.map(f => ({ ...f, label: f.label || null }))),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['cmdb-class-fields'] }); setFilas(null); toast.success(t('cmdb.classes_saved')) },
    onError: e => toast.error(extractErr(e, t('cmdb.save_error'))),
  })

  return (
    <div className="cmdb-panel cmdb-panel--stack">
      <p className="cmdb-help">
        {t('cmdb.classes_help')} {data?.por_defecto ? t('cmdb.classes_factory') : ''}
      </p>
      <Select label={t('cmdb.ci_type')} placeholder={false} id="clase-ci" value={clase} onChange={e => { setClase(e.target.value); setFilas(null) }}>
          {CI_TYPES.map(c => <option key={c} value={c}>{etiqueta('type_', c)}</option>)}
        </Select>
      {actuales.length === 0 && <div className="u-text2-sm">{t('cmdb.classes_empty')}</div>}
      {actuales.map((f, i) => (
        <div key={i} className="cmdb-class-row">
          <Input aria-label={t('cmdb.classes_key')} value={f.key} onChange={e => cambiar(i, { key: e.target.value })} inputClassName="ds-codigo cmdb-input cmdb-input--mono ds-campo-codigo" />
          <Input aria-label={t('cmdb.classes_label')} value={f.label ?? ''} placeholder={etiquetaDeCampo({ ...f, label: null })} onChange={e => cambiar(i, { label: e.target.value })} inputClassName="cmdb-input" />
          <Select suelto placeholder={false} aria-label={t('cmdb.classes_type')} className="cmdb-input" value={f.field_type} onChange={e => cambiar(i, { field_type: e.target.value })}>
            {['text', 'number', 'date'].map(ft => <option key={ft} value={ft}>{t(`cmdb.classes_type_${ft}`)}</option>)}
          </Select>
          <div className="cmdb-class-row__actions">
            <IconButton disabled={i === 0} onClick={() => mover(i, -1)} ariaLabel={t('cmdb.classes_up')}><ArrowUp size={14} /></IconButton>
            <IconButton disabled={i === actuales.length - 1} onClick={() => mover(i, 1)} ariaLabel={t('cmdb.classes_down')}><ArrowDown size={14} /></IconButton>
            <IconButton variante="caja" tono="peligro"
              onClick={() => setFilas(actuales.filter((_, j) => j !== i))} ariaLabel={t('cmdb.classes_remove')}><Trash2 size={14} /></IconButton>
          </div>
        </div>
      ))}
      <div className="u-wrap-10">
        <Button variant="secondary" icon={<Plus size={14} />} onClick={() => setFilas([...actuales, { key: '', label: '', field_type: 'text' }])}>{t('cmdb.classes_add')}</Button>
        <Button onClick={() => guardar()} loading={isPending} disabled={filas === null || isPending}>{t('cmdb.save')}</Button>
      </div>
    </div>
  )
}

/** Lo que se enseña en la columna de red: host, IP y el atributo que más dice de la clase. */
export function Red({ item }: { item: CI }) {
  const a = item.attributes || {}
  const extra = a.os || a.db_engine || a.url || a.image || a.cloud_provider || a.region
  return (
    <>
      {item.hostname && <div className="ds-codigo cmdb-net-host">{item.hostname}{a.port ? `:${a.port}` : ''}</div>}
      {item.ip_address && <div className="u-text2-mono-xs">{item.ip_address}</div>}
      {extra && <div className="cmdb-net-extra" title={String(extra)}>{String(extra)}</div>}
      {!item.hostname && !item.ip_address && !extra && '—'}
    </>
  )
}
