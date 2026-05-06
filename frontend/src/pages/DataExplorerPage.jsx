/**
 * DataExplorerPage — Exploración interactiva de datos.
 * Pregunta en lenguaje natural (NL→SQL), narrativa IA, query builder visual
 * y panel de query SQL avanzado. Antes vivía en /bi tab "explore".
 */
import PageShell from '../components/layout/PageShell'
import PageHeader from '../components/layout/PageHeader'
import { Search } from 'lucide-react'
import { useAppLang } from '../i18n/AppLangContext'
import useMediaQuery from '../hooks/useMediaQuery'
import NarrativeCard from '../components/bi/NarrativeCard'
import AskDataWidget from '../components/bi/AskDataWidget'
import VisualQueryBuilderWidget from '../components/bi/VisualQueryBuilderWidget'
import BiQueryBuilderPanel from '../components/bi/BiQueryBuilderPanel'

export default function DataExplorerPage() {
  const { lang } = useAppLang()
  const isMobile = useMediaQuery('(max-width: 900px)')

  return (
    <PageShell style={isMobile ? { paddingLeft: 14, paddingRight: 14 } : undefined}>
      <PageHeader
        icon={<Search size={18} />}
        title="Data Explorer"
        subtitle="Pregunta a tus datos en lenguaje natural y construye consultas visuales"
      showListExport={false}
      />

      <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(auto-fit, minmax(360px, 1fr))', gap: 14 }}>
          <NarrativeCard lang={lang} />
          <AskDataWidget />
          <VisualQueryBuilderWidget />
        </div>

        <BiQueryBuilderPanel />
      </div>
    </PageShell>
  )
}
