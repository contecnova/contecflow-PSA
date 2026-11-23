/**
 * Sección «Git» de Configuración (`/settings/git`, 19-11-2026).
 *
 * Antes era la pestaña «Configuración» de la página Git (`/git`). Muestra, por
 * empresa, la dirección del webhook de GitHub y de GitLab, si el secreto está
 * puesto (se guarda en Credenciales → Inbound webhooks), los eventos que hay
 * que activar, los pasos y cómo se enlazan ramas y PR con tareas.
 *
 * Solo lectura: no guarda nada aquí. `GET /git/webhooks` es `require_admin_or_pm`;
 * la sección pide `proyectos.gobierno` (admin, pm), la capacidad que cubre Git.
 */
import { type ReactNode, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Check, Copy, Github, Gitlab, Link2 } from 'lucide-react'
import { gitApi } from '../../services/api'
import { Button, Card } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { UI_FEEDBACK_MS } from '../../constants/timings'
import '../../pages/GitPage.css'

export default function ConfigGit(): JSX.Element {
  const t = useAppT()
  const { data: webhooks } = useQuery({
    queryKey: ['git-webhooks'],
    queryFn: () => gitApi.webhooks().then(r => r.data),
  })
  return (
    <div className="u-stack-20">
      <ProveedorGit
        title={t('git_integration.config_github_title')}
        icon={<Github size={16} aria-hidden />}
        webhook={webhooks?.github}
        clave="github_secret"
        events={['pull_request', 'deployment_status', 'push']}
        steps={[
          t('git_integration.config_github_step1'),
          t('git_integration.config_github_step2'),
          t('git_integration.config_github_step3'),
          t('git_integration.config_github_step4'),
          t('git_integration.config_github_step5'),
        ]}
      />
      <ProveedorGit
        title={t('git_integration.config_gitlab_title')}
        icon={<Gitlab size={16} aria-hidden />}
        webhook={webhooks?.gitlab}
        clave="gitlab_secret"
        events={['merge_requests', 'deployment']}
        steps={[
          t('git_integration.config_gitlab_step1'),
          t('git_integration.config_gitlab_step2'),
          t('git_integration.config_gitlab_step3'),
          t('git_integration.config_gitlab_step4'),
        ]}
      />
      <Card>
        <h3 className="gitp-title"><Link2 size={16} aria-hidden />{t('git_integration.auto_link_title')}</h3>
        <p className="gitp-text">
          {t('git_integration.auto_link_desc')}
        </p>
        <ul className="gitp-box-2">
          <li>{t('git_integration.auto_link_code')}: <code className="gitp-box-3">PROJ-123</code> {t('git_integration.auto_link_code_desc')}</li>
          <li>{t('git_integration.auto_link_id')}: <code className="gitp-box-3">#456</code></li>
        </ul>
        <p className="gitp-text-2">
          {t('git_integration.auto_link_example')}: <code className="u-success">feature/PROJ-42-add-login</code>
        </p>
      </Card>
    </div>
  )
}

// Revisión 2026-11: cada empresa tiene su dirección y su propio secreto
// (Credenciales → Inbound webhooks); antes había uno para toda la instalación.
function ProveedorGit({ title, icon, webhook, clave, events, steps }: { title: string; icon: ReactNode; webhook?: { ruta: string; secreto: boolean }; clave: string; events: string[]; steps: string[] }) {
  const t = useAppT()
  const toast = useToast()
  const [copied, setCopied] = useState(false)
  const url = webhook ? `${window.location.origin}${webhook.ruta}` : '…'
  const copy = () => {
    navigator.clipboard.writeText(url).then(
      () => { setCopied(true); setTimeout(() => setCopied(false), UI_FEEDBACK_MS) },
      () => toast.error(t('git_integration.no_se_pudo_copiar')),
    )
  }
  return (
    <Card>
      <h3 className="gitp-title">{icon}{title}</h3>
      <div className="u-mb-12">
        <div className="ds-eyebrow gitp-box-5">{t('git_integration.webhook_url_label')}</div>
        <div className="u-row-center-8">
          <code className="gitp-card-5">{url}</code>
          <Button size="sm" variant="secondary" onClick={copy} icon={copied ? <Check size={14} /> : <Copy size={14} />}>
            {copied ? t('git_integration.copied') : t('git_integration.copy')}
          </Button>
        </div>
      </div>
      <div className="u-mb-12">
        <div className="ds-eyebrow gitp-box-5">{t('git_integration.secreto_label')}</div>
        <div className={`gitp-box-4 ${webhook?.secreto ? 'gitpage-sx5' : 'gitpage-sx6'}`}>
          {t(webhook?.secreto ? 'git_integration.secreto_puesto' : 'git_integration.secreto_falta', { clave })}
        </div>
      </div>
      <div className="u-mb-12">
        <div className="ds-eyebrow gitp-box-5">{t('git_integration.events_label')}</div>
        <div className="u-wrap-6">
          {events.map(e => (
            <span key={e} className="ds-codigo gitp-card-6">{e}</span>
          ))}
        </div>
      </div>
      <div>
        <div className="ds-eyebrow gitp-box-5">{t('git_integration.steps_label')}</div>
        <ol className="gitp-box-6">
          {steps.map((s, i) => <li key={i}>{s}</li>)}
        </ol>
      </div>
    </Card>
  )
}
