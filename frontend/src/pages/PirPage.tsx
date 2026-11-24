/**
 * «Revisiones PIR» (`/pir`, Mi trabajo; migración 206, docs/PIR.md).
 *
 * Pestañas: «Mis PIR» (las asignadas a mí y las que me tocaría aprobar), «Todas»
 * (lista con filtros: ámbito, estado —con vencidas y pendientes—, resultado,
 * obligatorias) e «Informes» (tasa de éxito y cumplimiento, con `pir.gestionar`).
 * `?id=<pir>` abre la ficha (es el enlace de los avisos).
 */
import { useSearchParams } from 'react-router-dom'
import { BarChart3, ClipboardCheck, Inbox, List } from 'lucide-react'
import { Page, Tabs } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'
import { useAuth } from '../context/AuthContext'
import BandejaPir from '../components/pir/BandejaPir'
import ListaDePir from '../components/pir/ListaDePir'
import InformesPir from '../components/pir/InformesPir'
import FichaDePir from '../components/pir/FichaDePir'

type Pestana = 'mias' | 'todas' | 'informes'

export default function PirPage(): JSX.Element {
  const t = useAppT()
  const { puede } = useAuth()
  const [params, setParams] = useSearchParams()
  const informes = puede('pir.gestionar')
  const pedida = params.get('tab') as Pestana | null
  const tab: Pestana = pedida === 'todas' || (pedida === 'informes' && informes) ? pedida : 'mias'
  const abierta = params.get('id')
  const cambiar = (clave: string, valor: string | null) => {
    const sig = new URLSearchParams(params)
    if (valor) sig.set(clave, valor)
    else sig.delete(clave)
    setParams(sig, { replace: true })
  }
  return (
    <Page icon={<ClipboardCheck size={18} />} title={t('nav.pir')} subtitle={t('pir.subtitulo')}>
      <Tabs
        ariaLabel={t('nav.pir')}
        active={tab}
        onChange={id => cambiar('tab', id)}
        items={[
          { id: 'mias', label: t('pir.mis_pir'), icon: <Inbox size={14} /> },
          { id: 'todas', label: t('pir.todas'), icon: <List size={14} /> },
          ...(informes ? [{ id: 'informes', label: t('pir.informes'), icon: <BarChart3 size={14} /> }] : []),
        ]}
      />
      {tab === 'mias' && <BandejaPir />}
      {tab === 'todas' && <ListaDePir onAbrir={id => cambiar('id', id)} />}
      {tab === 'informes' && informes && <InformesPir onAbrir={id => cambiar('id', id)} />}
      {abierta && <FichaDePir id={abierta} onClose={() => cambiar('id', null)} />}
    </Page>
  )
}
