
import { lazy, Suspense, useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Spinner, Tabs, Page } from '../components/ui'
import {
  Layers,
  Building2,
  FileText,
  Key,
  Monitor,
  Coins,
  CalendarClock,
  History,
  FolderKanban,
  LayoutDashboard,
  ArrowLeftRight,
  HandCoins,
  FileSignature,
  Receipt,
  Activity,
  Scale,
} from 'lucide-react'
import FichaLicencia from '../components/alm/FichaLicencia'
import FichaActivo from '../components/alm/FichaActivo'
import AsignacionesTab, { HistorialPorTitularTab } from './alm/AsignacionesTab'
import CostesTab from './alm/CostesTab'
import RenovacionesTab from './alm/RenovacionesTab'
import ConciliacionTab from './alm/ConciliacionTab'
import ActasTab from './alm/ActasTab'
import { useAppT } from '../i18n/AppLangContext'
import { ALMDashboard } from './alm/PanelAlm'
import { VendorsTab } from './alm/ProveedoresAlm'
import { ContractsTab } from './alm/ContratosAlm'
import { LicensesTab } from './alm/LicenciasAlm'
import { AssetsTab } from './alm/ActivosAlm'
import { ComplianceTab, CostCentersTab } from './alm/CentrosYCumplimiento'
import './ALMPage.css'

// ── Main Page ──────────────────────────────────────────────────────────────────
// Uso real (fase 2): su pestaña vive en pages/alm/uso y se carga al abrirla.
const UsoRealTab = lazy(() => import('./alm/uso/UsoRealTab'))

/** Pestañas por grupo: catálogo, quién tiene qué, dinero y uso real. */
const GRUPOS_DE_PESTANAS: { id: string; tabs: { id: string; icon: ReactNode }[] }[] = [
  { id: 'inventory', tabs: [
    { id: 'dashboard', icon: <LayoutDashboard size={14} /> }, { id: 'licenses', icon: <Key size={14} /> },
    { id: 'assets', icon: <Monitor size={14} /> }, { id: 'vendors', icon: <Building2 size={14} /> },
    { id: 'contracts', icon: <FileText size={14} /> },
  ] },
  { id: 'holders', tabs: [
    { id: 'assignments', icon: <ArrowLeftRight size={14} /> }, { id: 'loans', icon: <HandCoins size={14} /> },
    { id: 'acts', icon: <FileSignature size={14} /> }, { id: 'history', icon: <History size={14} /> },
  ] },
  { id: 'money', tabs: [
    { id: 'costs', icon: <Coins size={14} /> }, { id: 'renewals', icon: <CalendarClock size={14} /> },
    { id: 'reconciliation', icon: <Receipt size={14} /> }, { id: 'cost', icon: <FolderKanban size={14} /> },
    { id: 'compliance', icon: <Scale size={14} /> },
  ] },
  { id: 'usage', tabs: [{ id: 'usage', icon: <Activity size={14} /> }] },
]

const TODAS = GRUPOS_DE_PESTANAS.flatMap(g => g.tabs.map(x => x.id))

export default function ALMPage(): JSX.Element {
  const t = useAppT()
  const [params, setParams] = useSearchParams()
  const pedida = params.get('tab') ?? 'dashboard'
  const tab = TODAS.includes(pedida) ? pedida : 'dashboard'
  const setTab = (id: string) => setParams(p => { const n = new URLSearchParams(p); n.set('tab', id); return n }, { replace: true })
  const grupo = GRUPOS_DE_PESTANAS.find(g => g.tabs.some(x => x.id === tab)) ?? GRUPOS_DE_PESTANAS[0]
  const [fichaDeAsignacion, setFichaDeAsignacion] = useState<{ tipo: 'license' | 'asset'; id: string } | null>(null)

  return (
    <Page
      icon={<Layers size={18} />}
      title={t('nav.alm')}
      subtitle={t('alm.subtitle')}
    >
      <Tabs
        items={GRUPOS_DE_PESTANAS.map(g => ({ id: g.id, label: t(`alm.group_tab_${g.id}`) }))}
        active={grupo.id}
        onChange={id => setTab(GRUPOS_DE_PESTANAS.find(g => g.id === id)?.tabs[0].id ?? 'dashboard')}
        ariaLabel={t('alm.tablist_groups_aria')}
        className="alm-tabs"
      />
      {/* Un grupo de una sola pestaña (Uso real) no lleva segunda barra. */}
      {grupo.tabs.length > 1 && (
        <Tabs
          items={grupo.tabs.map(x => ({ id: x.id, label: t(`alm.tab_${x.id}`), icon: x.icon }))}
          active={tab}
          onChange={setTab}
          ariaLabel={t('alm.tablist_aria')}
          className="alm-tabs"
        />
      )}

      {/* Tabs no pone id a sus botones: el panel se nombra con la etiqueta de la pestaña. */}
      <div id={`alm-panel-${tab}`} role="tabpanel" aria-label={t(`alm.tab_${tab}`)}>
        {tab === 'dashboard'  && <ALMDashboard onNavigate={setTab} />}
        {tab === 'vendors'    && <VendorsTab />}
        {tab === 'contracts'  && <ContractsTab />}
        {tab === 'licenses'   && <LicensesTab />}
        {tab === 'assets'     && <AssetsTab />}
        {tab === 'assignments' && <AsignacionesTab onAbrir={a => setFichaDeAsignacion(a.resource_type === 'license' ? { tipo: 'license', id: a.license_id ?? '' } : { tipo: 'asset', id: a.asset_id ?? '' })} />}
        {tab === 'loans'      && <AsignacionesTab soloPrestamos onAbrir={a => setFichaDeAsignacion({ tipo: 'asset', id: a.asset_id ?? '' })} />}
        {tab === 'acts'       && <ActasTab />}
        {tab === 'history'    && <HistorialPorTitularTab />}
        {tab === 'costs'      && <CostesTab />}
        {tab === 'renewals'   && <RenovacionesTab />}
        {tab === 'reconciliation' && <ConciliacionTab />}
        {tab === 'cost'       && <CostCentersTab />}
        {tab === 'compliance' && <ComplianceTab />}
        {tab === 'usage' && <Suspense fallback={<Spinner />}><UsoRealTab /></Suspense>}
      </div>
      {fichaDeAsignacion?.tipo === 'license' && <FichaLicencia licenseId={fichaDeAsignacion.id} onClose={() => setFichaDeAsignacion(null)} />}
      {fichaDeAsignacion?.tipo === 'asset' && <FichaActivo assetId={fichaDeAsignacion.id} onClose={() => setFichaDeAsignacion(null)} />}
    </Page>
  )
}
