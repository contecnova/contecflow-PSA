/**
 * Sección «Del ticket al PR» de Configuración (`/settings/ticket-a-pr`, capacidad
 * `ticket_pr.config`; migración 203, docs/integraciones/TICKET_A_PR.md).
 *
 * - Estado: encender o apagar el módulo (apagado por defecto) y uso de hoy.
 * - Motor y modelo: OpenCode con su imagen y versión FIJADA; proveedor de IA de la
 *   empresa (o uno elegido) y modelo.
 * - Credenciales Git cifradas (GitHub App o token de proyecto de GitLab): se
 *   escriben, nunca se leen en claro.
 * - Repositorios permitidos por proyecto (rama base y orden de tests).
 * - Seguridad: ficheros protegidos, salida extra, órdenes de shell permitidas,
 *   tests, aprobación del plan por otra persona y tipo de cambio.
 * - Límites, plantillas de instrucción, prueba de conexión real y coste por proyecto.
 */
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { GitPullRequest, KeyRound, ListChecks, PlugZap, Shield, Trash2, Wallet } from 'lucide-react'
import { Button, Card, IconButton, Input, Select, Spinner, StatusBadge, Switch, TablaSimple, Textarea } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { confirmar } from '../../context/ConfirmContext'
import { extractErr, fmtNumber } from '../../utils/helpers'
import { aiProvidersApi, projectsApi } from '../../services/api'
import { SELECTOR_LIST_SIZE } from '../../constants/pagination'
import { CLAVES_TICKET_A_PR, ticketAPrApi } from '../../services/api/ticketAPr'
import type { ConfigTicketAPr as Config, LimitesTicketAPr, PruebaTicketAPr, VistaDeConfigTicketAPr } from '../../services/api/ticketAPr'

const lineas = (texto: string): string[] => texto.split('\n').map(x => x.trim()).filter(Boolean)
const LIMITES: (keyof LimitesTicketAPr)[] = ['max_runs_per_day', 'max_cost_per_day_usd', 'max_concurrent', 'plan_timeout_min',
  'build_timeout_min', 'cpus', 'memory_mb', 'max_changed_files', 'max_diff_kb', 'max_repo_mb']

function useGuardar() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (c: Partial<Config> & { enabled?: boolean }) => ticketAPrApi.cambiarConfig(c),
    onSuccess: () => { toast.success(t('ticket_pr.guardado')); void qc.invalidateQueries({ queryKey: CLAVES_TICKET_A_PR.config }) },
    onError: e => toast.error(extractErr(e)),
  })
}

function Estado({ vista }: { vista: VistaDeConfigTicketAPr }) {
  const t = useAppT()
  const guardar = useGuardar()
  return (
    <Card>
      <h3 className="u-row-center-8"><GitPullRequest size={16} aria-hidden />{t('ticket_pr.config_estado')}
        <StatusBadge kind={vista.enabled ? 'success' : 'neutral'}>{vista.enabled ? t('ticket_pr.encendido') : t('ticket_pr.apagado')}</StatusBadge>
      </h3>
      <div className="u-stack-12">
        <p className="u-text2-sm">{t('ticket_pr.config_intro')}</p>
        <Switch checked={vista.enabled} onChange={v => guardar.mutate({ enabled: v })} label={t('ticket_pr.modulo_encendido')}
          ayuda={t('ticket_pr.modulo_encendido_ayuda')} />
        <p className="u-text2-sm">{t('ticket_pr.uso_hoy', { runs: vista.usage_today.runs, coste: fmtNumber(vista.usage_today.cost_usd, 4), activas: vista.usage_today.active })}</p>
      </div>
    </Card>
  )
}

function MotorYModelo({ cfg }: { cfg: Config }) {
  const t = useAppT()
  const guardar = useGuardar()
  const { data: proveedores = [] } = useQuery<{ id: string; name: string }[]>({
    queryKey: ['ai-providers'], queryFn: () => aiProvidersApi.list().then(r => (r.data ?? []) as unknown as { id: string; name: string }[]),
  })
  const [b, setB] = useState(cfg)
  useEffect(() => { setB(cfg) }, [cfg])
  return (
    <Card>
      <h3 className="u-row-center-8"><PlugZap size={16} aria-hidden />{t('ticket_pr.motor_titulo')}</h3>
      <div className="u-stack-12">
        <div className="u-wrap-8">
          <Select label={t('ticket_pr.motor')} value={b.engine} placeholder={false} onChange={e => setB({ ...b, engine: e.target.value })}
            options={[{ value: 'opencode', label: 'OpenCode' }]} />
          <Input label={t('ticket_pr.imagen')} value={b.engine_image} maxLength={250} onChange={e => setB({ ...b, engine_image: e.target.value })} />
          <Input label={t('ticket_pr.version')} value={b.engine_version} maxLength={128} hint={t('ticket_pr.version_ayuda')}
            onChange={e => setB({ ...b, engine_version: e.target.value })} />
        </div>
        <div className="u-wrap-8">
          <Select label={t('ticket_pr.proveedor_ia')} value={b.ai_provider_id ?? ''} placeholder={false}
            onChange={e => setB({ ...b, ai_provider_id: e.target.value || null })}
            options={[{ value: '', label: t('ticket_pr.proveedor_por_defecto') }, ...proveedores.map(p => ({ value: p.id, label: p.name }))]} />
          <Input label={t('ticket_pr.modelo')} value={b.model ?? ''} maxLength={120} hint={t('ticket_pr.modelo_ayuda')}
            onChange={e => setB({ ...b, model: e.target.value || null })} />
        </div>
        <div className="u-actions-8">
          <Button loading={guardar.isPending} onClick={() => guardar.mutate({ engine: b.engine, engine_image: b.engine_image,
            engine_version: b.engine_version, ai_provider_id: b.ai_provider_id, model: b.model })}>{t('ticket_pr.guardar')}</Button>
        </div>
      </div>
    </Card>
  )
}

function Credenciales({ vista }: { vista: VistaDeConfigTicketAPr }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [valores, setValores] = useState<Record<string, string>>({})
  const guardar = useMutation({
    mutationFn: async () => {
      for (const [clave, valor] of Object.entries(valores)) await ticketAPrApi.guardarCredencial(clave, valor)
    },
    onSuccess: () => { setValores({}); toast.success(t('ticket_pr.guardado')); void qc.invalidateQueries({ queryKey: CLAVES_TICKET_A_PR.config }) },
    onError: e => toast.error(extractErr(e)),
  })
  return (
    <Card>
      <h3 className="u-row-center-8"><KeyRound size={16} aria-hidden />{t('ticket_pr.credenciales_titulo')}</h3>
      <div className="u-stack-12">
        <p className="u-text2-sm">{t('ticket_pr.credenciales_intro')}</p>
        {vista.credentials.items.map(c => (
          c.key === 'github_private_key'
            ? <Textarea key={c.key} label={t(`ticket_pr.cred_${c.key}`)} rows={4} value={valores[c.key] ?? ''}
                placeholder={c.configured ? t('ticket_pr.configurado') : ''} onChange={e => setValores({ ...valores, [c.key]: e.target.value })} />
            : <Input key={c.key} label={t(`ticket_pr.cred_${c.key}`)} type={c.is_secret ? 'password' : 'text'} autoComplete="off"
                value={valores[c.key] ?? (c.is_secret ? '' : (c.value ?? ''))} placeholder={c.is_secret && c.configured ? t('ticket_pr.configurado') : ''}
                onChange={e => setValores({ ...valores, [c.key]: e.target.value })} />
        ))}
        <div className="u-actions-8">
          <Button loading={guardar.isPending} disabled={Object.keys(valores).length === 0} onClick={() => guardar.mutate()}>{t('ticket_pr.guardar')}</Button>
        </div>
      </div>
    </Card>
  )
}

function Repositorios() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: repos = [], isLoading } = useQuery({ queryKey: CLAVES_TICKET_A_PR.repos, queryFn: ticketAPrApi.repos })
  const { data: proyectos = [] } = useQuery<{ id: string; name: string; code?: string }[]>({
    queryKey: ['ticket-pr', 'proyectos'],
    queryFn: () => projectsApi.list({ page_size: SELECTOR_LIST_SIZE, status: 'active' }).then(r => (r.data ?? []) as unknown as { id: string; name: string; code?: string }[]),
  })
  const [nuevo, setNuevo] = useState({ project_id: '', provider: 'github', repo_full_name: '', default_branch: 'main', test_command: '' })
  const refrescar = () => void qc.invalidateQueries({ queryKey: CLAVES_TICKET_A_PR.repos })
  const crear = useMutation({
    mutationFn: () => ticketAPrApi.crearRepo({ ...nuevo, test_command: nuevo.test_command || undefined }),
    onSuccess: () => { setNuevo({ ...nuevo, repo_full_name: '', test_command: '' }); refrescar() },
    onError: e => toast.error(extractErr(e)),
  })
  const quitar = useMutation({ mutationFn: (id: string) => ticketAPrApi.quitarRepo(id), onSuccess: refrescar, onError: e => toast.error(extractErr(e)) })
  const nombre = (id: string) => proyectos.find(p => p.id === id)?.name ?? id
  return (
    <Card>
      <h3 className="u-row-center-8"><ListChecks size={16} aria-hidden />{t('ticket_pr.repos_titulo')}</h3>
      <div className="u-stack-12">
        <p className="u-text2-sm">{t('ticket_pr.repos_intro')}</p>
        <div className="u-wrap-8">
          <Select label={t('ticket_pr.proyecto')} value={nuevo.project_id} onChange={e => setNuevo({ ...nuevo, project_id: e.target.value })}
            options={proyectos.map(p => ({ value: p.id, label: p.code ? `${p.code} · ${p.name}` : p.name }))} />
          <Select label={t('ticket_pr.proveedor_git')} value={nuevo.provider} placeholder={false} onChange={e => setNuevo({ ...nuevo, provider: e.target.value })}
            options={[{ value: 'github', label: 'GitHub' }, { value: 'gitlab', label: 'GitLab' }]} />
          <Input label={t('ticket_pr.repositorio')} value={nuevo.repo_full_name} maxLength={256} placeholder="owner/repo"
            onChange={e => setNuevo({ ...nuevo, repo_full_name: e.target.value })} />
          <Input label={t('ticket_pr.rama_base')} value={nuevo.default_branch} maxLength={200} onChange={e => setNuevo({ ...nuevo, default_branch: e.target.value })} />
          <Input label={t('ticket_pr.orden_tests')} value={nuevo.test_command} maxLength={500} placeholder="npm ci && npm test"
            onChange={e => setNuevo({ ...nuevo, test_command: e.target.value })} />
        </div>
        <div className="u-actions-8">
          <Button onClick={() => crear.mutate()} loading={crear.isPending} disabled={!nuevo.project_id || !nuevo.repo_full_name.trim()}>{t('ticket_pr.anadir_repo')}</Button>
        </div>
        {isLoading ? <Spinner /> : repos.filter(r => r.is_active).length === 0 ? <p className="u-text2-sm">{t('ticket_pr.sin_repos')}</p> : (
          <TablaSimple etiqueta={t('ticket_pr.repos_titulo')} densidad="compacta">
            <thead>
              <tr><th>{t('ticket_pr.proyecto')}</th><th>{t('ticket_pr.repositorio')}</th><th>{t('ticket_pr.rama_base')}</th>
                <th>{t('ticket_pr.orden_tests')}</th><th><span className="u-sr-only">{t('ticket_pr.quitar')}</span></th></tr>
            </thead>
            <tbody>
              {repos.filter(r => r.is_active).map(r => (
                <tr key={r.id}>
                  <td>{nombre(r.project_id)}</td>
                  <td><code className="u-mono">{r.provider} · {r.repo_full_name}</code></td>
                  <td>{r.default_branch}</td>
                  <td><code className="u-mono">{r.test_command || '—'}</code></td>
                  <td>
                    <IconButton variante="caja" tono="peligro" ariaLabel={t('ticket_pr.quitar')}
                      onClick={async () => { if (await confirmar({ message: t('ticket_pr.quitar_confirmar', { repo: r.repo_full_name }), danger: true })) quitar.mutate(r.id) }}>
                      <Trash2 size={14} />
                    </IconButton>
                  </td>
                </tr>
              ))}
            </tbody>
          </TablaSimple>
        )}
      </div>
    </Card>
  )
}

function Seguridad({ vista }: { vista: VistaDeConfigTicketAPr }) {
  const t = useAppT()
  const guardar = useGuardar()
  const cfg = vista.config
  const [b, setB] = useState(cfg)
  const [protegidos, setProtegidos] = useState(cfg.protected_paths.join('\n'))
  const [hosts, setHosts] = useState(cfg.extra_egress_hosts.join('\n'))
  const [bash, setBash] = useState(cfg.bash_allow.join('\n'))
  useEffect(() => {
    setB(cfg); setProtegidos(cfg.protected_paths.join('\n')); setHosts(cfg.extra_egress_hosts.join('\n')); setBash(cfg.bash_allow.join('\n'))
  }, [cfg])
  return (
    <Card>
      <h3 className="u-row-center-8"><Shield size={16} aria-hidden />{t('ticket_pr.seguridad_titulo')}</h3>
      <div className="u-stack-12">
        <p className="u-text2-sm">{t('ticket_pr.protegidos_fabrica')}: <code className="u-mono">{vista.protected_defaults.join(', ')}</code></p>
        <Textarea label={t('ticket_pr.protegidos')} rows={4} value={protegidos} hint={t('ticket_pr.protegidos_ayuda')} onChange={e => setProtegidos(e.target.value)} />
        <Textarea label={t('ticket_pr.salida_extra')} rows={3} value={hosts} hint={t('ticket_pr.salida_extra_ayuda')} onChange={e => setHosts(e.target.value)} />
        <Textarea label={t('ticket_pr.bash')} rows={3} value={bash} hint={t('ticket_pr.bash_ayuda')} onChange={e => setBash(e.target.value)} />
        <Switch checked={b.run_tests} onChange={v => setB({ ...b, run_tests: v })} label={t('ticket_pr.ejecutar_tests')} ayuda={t('ticket_pr.ejecutar_tests_ayuda')} />
        <Switch checked={b.block_on_test_failure} onChange={v => setB({ ...b, block_on_test_failure: v })} label={t('ticket_pr.bloquear_si_fallan')} />
        <Switch checked={b.plan_requires_other_person} onChange={v => setB({ ...b, plan_requires_other_person: v })}
          label={t('ticket_pr.plan_otra_persona')} ayuda={t('ticket_pr.plan_otra_persona_ayuda')} />
        <div className="u-wrap-8">
          <Select label={t('ticket_pr.tipo_de_cambio')} value={b.change_type} placeholder={false}
            onChange={e => setB({ ...b, change_type: e.target.value as Config['change_type'] })}
            options={[{ value: 'normal', label: t('ticket_pr.cambio_normal') }, { value: 'standard_if_fits', label: t('ticket_pr.cambio_estandar') }]} />
          {b.change_type === 'standard_if_fits' && (
            <Input label={t('ticket_pr.modelo_estandar')} value={b.standard_model_id ?? ''} maxLength={36}
              onChange={e => setB({ ...b, standard_model_id: e.target.value || null })} />
          )}
        </div>
        <div className="u-actions-8">
          <Button loading={guardar.isPending} onClick={() => guardar.mutate({
            protected_paths: lineas(protegidos), extra_egress_hosts: lineas(hosts), bash_allow: lineas(bash), run_tests: b.run_tests,
            block_on_test_failure: b.block_on_test_failure, plan_requires_other_person: b.plan_requires_other_person,
            change_type: b.change_type, standard_model_id: b.standard_model_id,
          })}>{t('ticket_pr.guardar')}</Button>
        </div>
      </div>
    </Card>
  )
}

function LimitesYPlantillas({ cfg }: { cfg: Config }) {
  const t = useAppT()
  const guardar = useGuardar()
  const [lim, setLim] = useState(cfg.limits)
  const [plan, setPlan] = useState(cfg.templates.plan)
  const [build, setBuild] = useState(cfg.templates.build)
  useEffect(() => { setLim(cfg.limits); setPlan(cfg.templates.plan); setBuild(cfg.templates.build) }, [cfg])
  return (
    <Card>
      <h3 className="u-row-center-8"><Wallet size={16} aria-hidden />{t('ticket_pr.limites_titulo')}</h3>
      <div className="u-stack-12">
        <div className="u-wrap-8">
          {LIMITES.map(k => (
            <Input key={k} type="number" label={t(`ticket_pr.lim_${k}`)} value={lim[k]} step={k === 'cpus' || k === 'max_cost_per_day_usd' ? 0.25 : 1}
              onChange={e => setLim({ ...lim, [k]: Number(e.target.value) })} />
          ))}
        </div>
        <Textarea label={t('ticket_pr.plantilla_plan')} rows={6} value={plan} onChange={e => setPlan(e.target.value)} hint={t('ticket_pr.plantilla_ayuda')} />
        <Textarea label={t('ticket_pr.plantilla_build')} rows={6} value={build} onChange={e => setBuild(e.target.value)} />
        <div className="u-actions-8">
          <Button loading={guardar.isPending} onClick={() => guardar.mutate({ limits: lim, templates: { plan, build } })}>{t('ticket_pr.guardar')}</Button>
        </div>
      </div>
    </Card>
  )
}

function Prueba() {
  const t = useAppT()
  const toast = useToast()
  const [r, setR] = useState<PruebaTicketAPr | null>(null)
  const probar = useMutation({ mutationFn: ticketAPrApi.probar, onSuccess: setR, onError: e => toast.error(extractErr(e)) })
  return (
    <Card>
      <h3 className="u-row-center-8"><PlugZap size={16} aria-hidden />{t('ticket_pr.prueba_titulo')}</h3>
      <div className="u-stack-12">
        <p className="u-text2-sm">{t('ticket_pr.prueba_intro')}</p>
        <div className="u-actions-8"><Button variant="secondary" loading={probar.isPending} onClick={() => probar.mutate()}>{t('ticket_pr.probar')}</Button></div>
        {r && (
          <div className="u-stack-6" role="status">
            <StatusBadge kind={r.ok ? 'success' : 'warning'}>{t(`ticket_pr.verificado_${r.verificado}`)}</StatusBadge>
            <ul className="u-stack-6">
              {Object.entries(r.comprobaciones).map(([k, v]) => (
                <li key={k} className="u-text2-sm">{t(`ticket_pr.comprobacion_${k}`)}: {v === null ? '—' : v ? t('ticket_pr.ok') : t('ticket_pr.fallo')}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Card>
  )
}

function Costes() {
  const t = useAppT()
  const { data: filas = [], isLoading } = useQuery({ queryKey: CLAVES_TICKET_A_PR.costes, queryFn: () => ticketAPrApi.costes(30) })
  return (
    <Card>
      <h3 className="u-row-center-8"><Wallet size={16} aria-hidden />{t('ticket_pr.costes_titulo')}</h3>
      {isLoading ? <Spinner /> : filas.length === 0 ? <p className="u-text2-sm">{t('ticket_pr.sin_costes')}</p> : (
        <TablaSimple etiqueta={t('ticket_pr.costes_titulo')} densidad="compacta">
          <thead><tr><th>{t('ticket_pr.proyecto')}</th><th>{t('ticket_pr.ejecuciones')}</th><th>{t('ticket_pr.coste')}</th><th>{t('ticket_pr.horas')}</th></tr></thead>
          <tbody>
            {filas.map(f => (
              <tr key={f.project_id ?? '-'}>
                <td>{f.project_name ?? '—'}</td><td>{f.runs}</td><td>{fmtNumber(f.cost_usd, 4)}</td><td>{fmtNumber(f.agent_hours, 2)}</td>
              </tr>
            ))}
          </tbody>
        </TablaSimple>
      )}
    </Card>
  )
}

export default function ConfigTicketAPr(): JSX.Element {
  const { data: vista, isLoading } = useQuery({ queryKey: CLAVES_TICKET_A_PR.config, queryFn: ticketAPrApi.config })
  if (isLoading || !vista) return <Spinner />
  return (
    <div className="u-stack-20">
      <Estado vista={vista} />
      <Prueba />
      <MotorYModelo cfg={vista.config} />
      <Credenciales vista={vista} />
      <Repositorios />
      <Seguridad vista={vista} />
      <LimitesYPlantillas cfg={vista.config} />
      <Costes />
    </div>
  )
}
