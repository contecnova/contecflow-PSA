/**
 * DataExplorerPage — Exploración interactiva de datos.
 * Pregunta en lenguaje natural (NL→SQL), narrativa IA, query builder visual
 * y panel de query SQL avanzado. Antes vivía en /bi tab "explore".
 */
import PageShell from '../components/layout/PageShell'
import PageHeader from '../components/layout/PageHeader'
import { Search } from 'lucide-react'
import { useAppLang } from '../i18n/AppLangContext'
import NarrativeCard from '../components/bi/NarrativeCard'
import AskDataWidget from '../components/bi/AskDataWidget'
import VisualQueryBuilderWidget from '../components/bi/VisualQueryBuilderWidget'
import BiQueryBuilderPanel from '../components/bi/BiQueryBuilderPanel'
import EstadoDelAlmacen from '../components/bi/EstadoDelAlmacen'
import './DataExplorerPage.css'

export default function DataExplorerPage(): JSX.Element {
  const { lang, t } = useAppLang()

  return (
    <PageShell className="dxp-page">
      <PageHeader
        icon={<Search size={18} />}
        title={t('nav.data_explorer')}
        subtitle={t('dataexplorer.subtitle')}
        showListExport={false}
      />

      <div className="u-stack-20">
        <EstadoDelAlmacen />
        <div className="dxp-widgets">
          <NarrativeCard lang={lang} />
          <AskDataWidget />
          <VisualQueryBuilderWidget />
        </div>

        <BiQueryBuilderPanel />
      </div>
    </PageShell>
  )
}
