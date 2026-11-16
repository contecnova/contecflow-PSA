/**
 * Piezas comunes de licencias y hardware, fases 1 y 3 (16-11-2026): iconos de
 * los catálogos, traducción de errores y códigos del backend, el selector de
 * titular (persona, proyecto, departamento, cliente o equipo), el estado de
 * una asignación y el editor del checklist de las actas.
 */
import { useQuery } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import {
  AppWindow, Building2, Cloud, Cpu, FileText, Gift, HardDrive, Infinity as InfinityIcon, KeyRound, Laptop, Layers,
  LifeBuoy, Monitor, MousePointer2, Network, Package, Printer, RefreshCw, Repeat, Server, ShoppingCart, Smartphone,
  Tablet, Timer, User, Users, Wrench, Briefcase, Landmark, Radio, Boxes,
} from 'lucide-react'
import { StatusBadge } from '../ui'
import type { StatusBadgeKind } from '../ui/StatusBadge'
import { UserSelect, ProjectSelect, ClientSelect, AssetSelect } from '../ui/EntitySelect'
import { settingsApi } from '../../services/settingsApi'
import { extractErr } from '../../utils/helpers'
import { STALE_REFERENCE_DATA_MS } from '../../constants/timings'
import type { FilaDeChecklist, TipoDeTitular } from '../../services/api/alm'
import './almFases.css'

export type Traductor = (clave: string, segundo?: string | Record<string, unknown>) => string

const I = 16

/** Icono de cada tipo de licencia (lucide; nunca emojis). */
export const ICONO_LICENCIA: Record<string, ReactNode> = {
  perpetual: <InfinityIcon size={I} />, subscription: <RefreshCw size={I} />, concurrent: <Users size={I} />,
  named: <User size={I} />, device: <Laptop size={I} />, trial: <Timer size={I} />, free: <Gift size={I} />,
  oem: <Cpu size={I} />, volume: <Boxes size={I} />,
}
export const ICONO_ACTIVO: Record<string, ReactNode> = {
  laptop: <Laptop size={I} />, desktop: <Monitor size={I} />, server: <Server size={I} />, mobile: <Smartphone size={I} />,
  tablet: <Tablet size={I} />, network: <Network size={I} />, printer: <Printer size={I} />, monitor: <Monitor size={I} />,
  peripheral: <MousePointer2 size={I} />, vm: <Cloud size={I} />, other: <Package size={I} />,
}
export const ICONO_PROVEEDOR: Record<string, ReactNode> = {
  software: <AppWindow size={I} />, hardware: <HardDrive size={I} />, saas: <Cloud size={I} />, cloud: <Cloud size={I} />,
  telecom: <Radio size={I} />, consulting: <Briefcase size={I} />, other: <Package size={I} />,
}
export const ICONO_CONTRATO: Record<string, ReactNode> = {
  purchase: <ShoppingCart size={I} />, subscription: <Repeat size={I} />, maintenance: <Wrench size={I} />,
  support: <LifeBuoy size={I} />, lease: <FileText size={I} />, enterprise: <Landmark size={I} />,
}
export const ICONO_TITULAR: Record<TipoDeTitular, ReactNode> = {
  user: <User size={14} />, project: <Layers size={14} />, department: <Building2 size={14} />,
  client: <Briefcase size={14} />, asset: <Laptop size={14} />,
}
export const ICONO_LICENCIA_DEFECTO = <KeyRound size={I} />

export const METRICAS = ['named_user', 'device', 'concurrent', 'volume', 'site'] as const
export const TIPOS_DE_TITULAR: TipoDeTitular[] = ['user', 'project', 'department', 'client', 'asset']

/** Mensaje de un error del backend. Los códigos `alm_*` (con `:campo` opcional) se traducen. */
export function errorAlm(t: Traductor, e: unknown): string {
  const detalle = extractErr(e, '')
  if (detalle.startsWith('alm_')) {
    const [codigo, campo] = detalle.split(':')
    const texto = t(`alm.err_${codigo.slice(4)}`, t('alm.err_generic'))
    return campo ? `${texto} (${campo})` : texto
  }
  return detalle || t('alm.err_generic')
}

const TONO_ASIGNACION: Record<string, StatusBadgeKind> = {
  pending: 'warning', active: 'success', ended: 'neutral', rejected: 'danger', cancelled: 'neutral',
  pending_signature: 'warning', signed: 'success', unsigned: 'neutral', void: 'neutral',
  matched: 'success', discrepancy: 'danger', accepted: 'info',
}

/** Pastilla de estado de una asignación, un acta o una factura (`alm.st_<código>`). */
export function EstadoAlm({ t, codigo, vencido }: { t: Traductor; codigo: string; vencido?: boolean }) {
  if (vencido) return <StatusBadge kind="danger" caps={false}>{t('alm.st_overdue')}</StatusBadge>
  return <StatusBadge kind={TONO_ASIGNACION[codigo] ?? 'neutral'} caps={false}>{t(`alm.st_${codigo}`, codigo)}</StatusBadge>
}

/** Texto de un evento del historial (`alm.ev_<código>`). */
export const textoDeEvento = (t: Traductor, codigo: string) => t(`alm.ev_${codigo}`, codigo)

/** Texto del tipo de titular (`alm.holder_<tipo>`). */
export const textoDeTitular = (t: Traductor, tipo?: string | null) => (tipo ? t(`alm.holder_${tipo}`, tipo) : '—')

/** Elemento del checklist: los códigos conocidos se traducen; los añadidos a mano se enseñan tal cual. */
export const textoDeChecklist = (t: Traductor, item: string) => t(`alm.chk_${item}`, item)

export function useDepartamentos() {
  return useQuery({
    queryKey: ['departments'],
    queryFn: () => settingsApi.getDepartments().then(r => r.data ?? []),
    staleTime: STALE_REFERENCE_DATA_MS,
  })
}

/** Elige un titular: primero el tipo y después quién. */
export function SelectorDeTitular({
  t, tipo, id, onChange, tipos = TIPOS_DE_TITULAR, idBase,
}: {
  t: Traductor
  tipo: TipoDeTitular
  id: string
  onChange: (tipo: TipoDeTitular, id: string) => void
  tipos?: TipoDeTitular[]
  idBase: string
}) {
  const deps = useDepartamentos()
  return (
    <div className="almf-titular">
      <div className="almf-titular__tipos" role="radiogroup" aria-label={t('alm.holder_type')}>
        {tipos.map(k => (
          <button key={k} type="button" role="radio" aria-checked={tipo === k}
            className={`almf-chip${tipo === k ? ' almf-chip--on' : ''}`} onClick={() => onChange(k, '')}>
            {ICONO_TITULAR[k]}<span>{textoDeTitular(t, k)}</span>
          </button>
        ))}
      </div>
      <div className="almf-titular__quien">
        <label className="alm-label" htmlFor={`${idBase}-quien`}>{t('alm.holder_who')}</label>
        {tipo === 'user' && <UserSelect value={id} onChange={v => onChange('user', v)} className="alm-input" placeholder={t('alm.holder_pick_user')} />}
        {tipo === 'project' && <ProjectSelect value={id} onChange={v => onChange('project', v)} placeholder={t('alm.holder_pick_project')} />}
        {tipo === 'client' && <ClientSelect id={`${idBase}-quien`} value={id} onChange={v => onChange('client', v)} className="alm-input" placeholder={t('alm.holder_pick_client')} />}
        {tipo === 'asset' && <AssetSelect value={id} onChange={v => onChange('asset', v)} placeholder={t('alm.holder_pick_asset')} />}
        {tipo === 'department' && (
          <select id={`${idBase}-quien`} className="alm-input" value={id} onChange={e => onChange('department', e.target.value)}>
            <option value="">{t('alm.holder_pick_department')}</option>
            {(deps.data ?? []).filter(d => d.is_active).map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        )}
      </div>
    </div>
  )
}

/** El checklist de entrega o devolución: cada elemento, si está y una nota. */
export function EditorDeChecklist({ t, filas, onChange }: { t: Traductor; filas: FilaDeChecklist[]; onChange: (f: FilaDeChecklist[]) => void }) {
  if (!filas.length) return <p className="alm-hint">{t('alm.checklist_empty')}</p>
  const cambiar = (i: number, cambio: Partial<FilaDeChecklist>) =>
    onChange(filas.map((f, j) => (j === i ? { ...f, ...cambio } : f)))
  return (
    <ul className="almf-checklist" aria-label={t('alm.checklist')}>
      {filas.map((f, i) => (
        <li key={f.item} className="almf-checklist__fila">
          <label className="almf-checklist__item">
            <input type="checkbox" checked={f.ok} onChange={e => cambiar(i, { ok: e.target.checked })} />
            <span>{textoDeChecklist(t, f.item)}</span>
          </label>
          <input className="alm-input almf-checklist__nota" value={f.note ?? ''} placeholder={t('alm.checklist_note')}
            aria-label={`${t('alm.checklist_note')} — ${textoDeChecklist(t, f.item)}`}
            onChange={e => cambiar(i, { note: e.target.value })} />
        </li>
      ))}
    </ul>
  )
}

/** Fila «etiqueta: valor» de las fichas. */
export function Dato({ etiqueta, children }: { etiqueta: ReactNode; children: ReactNode }) {
  return (
    <div className="almf-dato">
      <dt>{etiqueta}</dt>
      <dd>{children ?? '—'}</dd>
    </div>
  )
}

/** Hoy en formato `YYYY-MM-DD` (fecha local). */
export function hoyIso(desplazamientoDias = 0): string {
  const d = new Date()
  d.setDate(d.getDate() + desplazamientoDias)
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const dia = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${m}-${dia}`
}
