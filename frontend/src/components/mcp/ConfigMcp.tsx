/**
 * Sección «Agentes de código (MCP)» de Configuración (`/settings/mcp`, 23-11-2026).
 *
 * Conectar OpenCode, Claude Code u otro cliente MCP al servidor de la empresa
 * (`POST /api/v1/mcp`, Streamable HTTP) para trabajar desde el editor o el
 * terminal: tareas, tickets, horas, cronómetro, cambios y, si cada persona lo
 * comparte, sus notas. Guía completa: docs/integraciones/MCP.md.
 *
 * - Estado: encendido, modo de escritura, Mi cuaderno y límite por minuto. Lo
 *   cambia quien tiene `gobierno.administrar` (`PATCH /mcp/estado`); el resto lo ve.
 * - Conectar: la URL y la configuración exacta de OpenCode y Claude Code.
 * - Mis credenciales: claves de solo lectura o de lectura y escritura que solo
 *   abren MCP; la clave se ve una vez; se revocan aquí.
 * - Herramientas: las de trabajo diario, con la capacidad que piden y si quien
 *   mira puede usarlas.
 */
import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Copy, KeyRound, Plug, ShieldCheck, Trash2, Wrench } from 'lucide-react'
import { Button, Card, IconButton, Input, Select, Spinner, StatusBadge, Switch, TablaSimple } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { confirmar } from '../../context/ConfirmContext'
import { extractErr } from '../../utils/helpers'
import { UI_FEEDBACK_MS } from '../../constants/timings'
import { CLAVES_MCP, mcpApi } from '../../services/api/mcp'
import type { CredencialCreada, EstadoMcp, ModoDeEscritura } from '../../services/api/mcp'

const VARIABLE = 'CONTECFLOW_MCP_TOKEN'

/** Configuración de OpenCode (`opencode.jsonc`): servidor MCP remoto con cabecera. */
function configOpenCode(url: string): string {
  return `{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "contecflow": {
      "type": "remote",
      "url": "${url}",
      "enabled": true,
      "headers": {
        "Authorization": "Bearer {env:${VARIABLE}}"
      }
    }
  }
}`
}

/** Alta en Claude Code por la línea de órdenes (transporte HTTP). */
function comandoClaudeCode(url: string): string {
  return `claude mcp add --transport http --scope user contecflow ${url} --header "Authorization: Bearer $${VARIABLE}"`
}

/** `.mcp.json` del proyecto para Claude Code (la variable se expande al arrancar). */
function configClaudeCode(url: string): string {
  return `{
  "mcpServers": {
    "contecflow": {
      "type": "http",
      "url": "${url}",
      "headers": {
        "Authorization": "Bearer \${${VARIABLE}}"
      }
    }
  }
}`
}

function BotonCopiar({ texto }: { texto: string }) {
  const t = useAppT()
  const toast = useToast()
  const [copiado, setCopiado] = useState(false)
  const copiar = () => {
    navigator.clipboard.writeText(texto).then(
      () => { setCopiado(true); setTimeout(() => setCopiado(false), UI_FEEDBACK_MS) },
      () => toast.error(t('mcp.no_se_pudo_copiar')),
    )
  }
  return (
    <Button size="sm" variant="secondary" onClick={copiar} icon={copiado ? <Check size={14} /> : <Copy size={14} />}>
      {copiado ? t('mcp.copiado') : t('mcp.copiar')}
    </Button>
  )
}

function Bloque({ titulo, texto }: { titulo: string; texto: string }) {
  return (
    <div className="u-stack-6">
      <div className="u-row-center-8">
        <span className="ds-eyebrow u-flex1">{titulo}</span>
        <BotonCopiar texto={texto} />
      </div>
      <pre className="ds-codigo ds-codigo--bloque">{texto}</pre>
    </div>
  )
}

function Estado({ estado }: { estado: EstadoMcp }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [b, setB] = useState(estado)
  useEffect(() => { setB(estado) }, [estado])
  const guardar = useMutation({
    mutationFn: () => mcpApi.cambiarEstado({ enabled: b.enabled, write_mode: b.write_mode, notebook_enabled: b.notebook_enabled,
      rate_limit_per_minute: Number(b.rate_limit_per_minute) || 0 }),
    onSuccess: () => {
      toast.success(t('mcp.guardado'))
      void qc.invalidateQueries({ queryKey: CLAVES_MCP.estado })
      void qc.invalidateQueries({ queryKey: CLAVES_MCP.herramientas })
    },
    onError: e => toast.error(extractErr(e)),
  })
  const cambiado = b.enabled !== estado.enabled || b.write_mode !== estado.write_mode
    || b.notebook_enabled !== estado.notebook_enabled || Number(b.rate_limit_per_minute) !== estado.rate_limit_per_minute
  return (
    <Card>
      <h3 className="u-row-center-8"><Plug size={16} aria-hidden />{t('mcp.estado_titulo')}
        <StatusBadge kind={estado.enabled ? 'success' : 'neutral'}>{estado.enabled ? t('mcp.encendido') : t('mcp.apagado')}</StatusBadge>
      </h3>
      <div className="u-stack-12">
        <Switch checked={b.enabled} disabled={!estado.can_admin} onChange={v => setB({ ...b, enabled: v })}
          label={t('mcp.servidor_encendido')} ayuda={t('mcp.servidor_encendido_ayuda')} />
        <Select label={t('mcp.modo_escritura')} value={b.write_mode} disabled={!estado.can_admin} placeholder={false}
          onChange={e => setB({ ...b, write_mode: e.target.value as ModoDeEscritura })}
          hint={t('mcp.modo_escritura_ayuda')}
          options={(['off', 'approval', 'direct'] as ModoDeEscritura[]).map(m => ({ value: m, label: t(`mcp.modo_${m}`) }))} />
        <Switch checked={b.notebook_enabled} disabled={!estado.can_admin} onChange={v => setB({ ...b, notebook_enabled: v })}
          label={t('mcp.cuaderno_switch')} ayuda={t('mcp.cuaderno_ayuda')} />
        <Input type="number" label={t('mcp.limite')} hint={t('mcp.limite_ayuda')} value={b.rate_limit_per_minute}
          disabled={!estado.can_admin} min={0} max={10000}
          onChange={e => setB({ ...b, rate_limit_per_minute: Number(e.target.value) })} />
        {estado.can_admin
          ? <div className="u-actions-8"><Button onClick={() => guardar.mutate()} disabled={!cambiado} loading={guardar.isPending}>{t('mcp.guardar')}</Button></div>
          : <p className="u-text2-sm">{t('mcp.solo_admin')}</p>}
      </div>
    </Card>
  )
}

function Conectar({ url }: { url: string }) {
  const t = useAppT()
  return (
    <Card>
      <h3 className="u-row-center-8"><Plug size={16} aria-hidden />{t('mcp.conectar_titulo')}</h3>
      <div className="u-stack-14">
        <p className="u-text2-sm">{t('mcp.conectar_intro', { variable: VARIABLE })}</p>
        <Bloque titulo={t('mcp.url')} texto={url} />
        <Bloque titulo={t('mcp.opencode_titulo')} texto={configOpenCode(url)} />
        <p className="u-text2-sm">{t('mcp.opencode_ayuda', { variable: VARIABLE })}</p>
        <Bloque titulo={t('mcp.claude_cli')} texto={comandoClaudeCode(url)} />
        <Bloque titulo={t('mcp.claude_json')} texto={configClaudeCode(url)} />
        <p className="u-text2-sm">{t('mcp.claude_ayuda', { variable: VARIABLE })}</p>
      </div>
    </Card>
  )
}

function Credenciales() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: lista = [], isLoading } = useQuery({ queryKey: CLAVES_MCP.credenciales, queryFn: mcpApi.credenciales })
  const [nombre, setNombre] = useState('')
  const [alcance, setAlcance] = useState<'read' | 'write'>('read')
  const [dias, setDias] = useState(90)
  const [creada, setCreada] = useState<CredencialCreada | null>(null)
  const refrescar = () => void qc.invalidateQueries({ queryKey: CLAVES_MCP.credenciales })
  const crear = useMutation({
    mutationFn: () => mcpApi.crearCredencial({ name: nombre.trim(), scope: alcance, expires_in_days: dias }),
    onSuccess: c => { setCreada(c); setNombre(''); refrescar() },
    onError: e => toast.error(extractErr(e)),
  })
  const revocar = useMutation({
    mutationFn: (id: string) => mcpApi.revocarCredencial(id),
    onSuccess: () => { toast.success(t('mcp.revocada')); refrescar() },
    onError: e => toast.error(extractErr(e)),
  })
  return (
    <Card>
      <h3 className="u-row-center-8"><KeyRound size={16} aria-hidden />{t('mcp.credenciales_titulo')}</h3>
      <div className="u-stack-12">
        <p className="u-text2-sm">{t('mcp.credenciales_intro')}</p>
        <div className="u-wrap-8">
          <Input label={t('mcp.nombre')} value={nombre} maxLength={120} onChange={e => setNombre(e.target.value)} />
          <Select label={t('mcp.alcance')} value={alcance} placeholder={false} onChange={e => setAlcance(e.target.value as 'read' | 'write')}
            options={[{ value: 'read', label: t('mcp.alcance_read') }, { value: 'write', label: t('mcp.alcance_write') }]} />
          <Input type="number" label={t('mcp.caduca_dias')} value={dias} min={1} max={365}
            onChange={e => setDias(Math.min(365, Math.max(1, Number(e.target.value) || 1)))} />
        </div>
        <div className="u-actions-8">
          <Button onClick={() => crear.mutate()} disabled={!nombre.trim()} loading={crear.isPending}>{t('mcp.generar')}</Button>
        </div>
        {creada && (
          <div className="u-stack-6" role="status">
            <Bloque titulo={t('mcp.generada_aviso')} texto={creada.key} />
            <p className="u-text2-sm">{t('mcp.generada_variable', { variable: VARIABLE })}</p>
          </div>
        )}
        {isLoading ? <Spinner /> : lista.length === 0 ? <p className="u-text2-sm">{t('mcp.sin_credenciales')}</p> : (
          <TablaSimple etiqueta={t('mcp.credenciales_titulo')} densidad="compacta">
            <thead>
              <tr>
                <th>{t('mcp.nombre')}</th><th>{t('mcp.alcance')}</th><th>{t('mcp.prefijo')}</th>
                <th>{t('mcp.ultimo_uso')}</th><th>{t('mcp.caduca')}</th><th><span className="u-sr-only">{t('mcp.revocar')}</span></th>
              </tr>
            </thead>
            <tbody>
              {lista.map(c => (
                <tr key={c.id}>
                  <td>{c.name}</td>
                  <td>{c.scopes.includes('mcp:write') ? t('mcp.alcance_write') : t('mcp.alcance_read')}</td>
                  <td><code className="u-mono">{c.key_prefix}…</code></td>
                  <td>{c.last_used_at || t('mcp.nunca')}</td>
                  <td>{c.is_active ? (c.expires_at || '—') : <StatusBadge kind="neutral">{t('mcp.revocada')}</StatusBadge>}</td>
                  <td>
                    {c.is_active && (
                      <IconButton variante="caja" tono="peligro" ariaLabel={t('mcp.revocar')}
                        onClick={async () => { if (await confirmar({ message: t('mcp.revocar_confirmar', { nombre: c.name }), danger: true })) revocar.mutate(c.id) }}>
                        <Trash2 size={14} />
                      </IconButton>
                    )}
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

function Herramientas({ estado }: { estado: EstadoMcp }) {
  const t = useAppT()
  const { data: lista = [], isLoading } = useQuery({ queryKey: CLAVES_MCP.herramientas, queryFn: mcpApi.herramientas })
  return (
    <Card>
      <h3 className="u-row-center-8"><Wrench size={16} aria-hidden />{t('mcp.herramientas_titulo')}</h3>
      <div className="u-stack-12">
        <p className="u-text2-sm">{t('mcp.herramientas_intro')}</p>
        {estado.write_mode === 'off' && <p className="u-text2-sm">{t('mcp.escritura_apagada')}</p>}
        {isLoading ? <Spinner /> : (
          <TablaSimple etiqueta={t('mcp.herramientas_titulo')} densidad="compacta">
            <thead>
              <tr><th>{t('mcp.col_herramienta')}</th><th>{t('mcp.col_tipo')}</th><th>{t('mcp.col_capacidad')}</th><th>{t('mcp.col_estado')}</th></tr>
            </thead>
            <tbody>
              {lista.map(h => (
                <tr key={h.name}>
                  <td><code className="u-mono">{h.name}</code><div className="u-text3-xs">{h.title}</div></td>
                  <td><StatusBadge kind={h.writes ? 'warning' : 'info'}>{h.writes ? t('mcp.escritura') : t('mcp.lectura')}</StatusBadge></td>
                  <td><code className="u-mono">{h.capability || t('mcp.cualquier_sesion')}</code></td>
                  <td>{h.available
                    ? <StatusBadge kind="success">{t('mcp.disponible')}</StatusBadge>
                    : <span className="u-text2-xs">{h.reason ? t(`err_srv.${h.reason.code}`, h.reason.params) : t('mcp.no_disponible')}</span>}</td>
                </tr>
              ))}
            </tbody>
          </TablaSimple>
        )}
      </div>
    </Card>
  )
}

function Guia() {
  const t = useAppT()
  const apartado = (clave: string, n: number) => (
    <div className="u-stack-6">
      <span className="ds-eyebrow">{t(`mcp.${clave}_titulo`)}</span>
      <ul className="u-stack-6">
        {Array.from({ length: n }, (_, i) => <li key={i} className="u-text2-sm">{t(`mcp.${clave}_${i + 1}`, { variable: VARIABLE })}</li>)}
      </ul>
    </div>
  )
  return (
    <Card>
      <h3 className="u-row-center-8"><ShieldCheck size={16} aria-hidden />{t('mcp.guia_titulo')}</h3>
      <div className="u-stack-14">
        {apartado('pasos', 5)}
        {apartado('ejemplos', 5)}
        {apartado('seguridad', 6)}
        {apartado('problemas', 6)}
      </div>
    </Card>
  )
}

export default function ConfigMcp(): JSX.Element {
  const { data: estado, isLoading } = useQuery({ queryKey: CLAVES_MCP.estado, queryFn: mcpApi.estado })
  const url = useMemo(() => estado?.url || `${window.location.origin}/api/v1/mcp`, [estado?.url])
  if (isLoading || !estado) return <Spinner />
  return (
    <div className="u-stack-20">
      <Estado estado={estado} />
      <Conectar url={url} />
      <Credenciales />
      <Herramientas estado={estado} />
      <Guia />
    </div>
  )
}
