import { useAppT } from '../i18n/AppLangContext'
import PageHeader from '../components/layout/PageHeader'
import { Megaphone } from 'lucide-react'

export default function PipelinePage() {
  const t = useAppT()
  return (
    <div style={{ padding: 20 }}>
      <PageHeader icon={<Megaphone size={16} />} title={t('pipeline.title')} />
      <p>{t('pipeline.placeholder')}</p>
    </div>
  )
}
