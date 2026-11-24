/**
 * «Certificaciones» (`/certificaciones`, grupo Cumplimiento; migración 212, docs/CERTIFICACIONES.md).
 *
 * El punto de control del cumplimiento, como Licencias: el programa se elige en el selector de
 * contexto y las pestañas son panel, programas, declaración de aplicabilidad, matriz cruzada,
 * evidencias, auditorías (hallazgos y CAPA), auditores y empresas colaboradoras, certificados,
 * NIS2, proveedores críticos y biblioteca. `?tab=` abre una pestaña (enlace de los avisos) y
 * `?programa=` el programa.
 */
import { useEffect, useRef } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import {
  Award, BookOpen, ClipboardList, FileCheck2, Grid3x3, LayoutDashboard, ListChecks, Search, ShieldCheck, Siren, Truck,
  Users,
} from 'lucide-react'
import { Page, SelectRico, SelectorDeContexto, Tabs } from '../components/ui'
import { useAppLang, useAppT } from '../i18n/AppLangContext'
import { CLAVES_CERT, certApi } from '../services/api/certificaciones'
import PanelCert from '../components/certificaciones/PanelCert'
import ProgramasCert from '../components/certificaciones/ProgramasCert'
import AplicabilidadCert from '../components/certificaciones/AplicabilidadCert'
import MatrizCert from '../components/certificaciones/MatrizCert'
import EvidenciasCert from '../components/certificaciones/EvidenciasCert'
import AuditoriasCert from '../components/certificaciones/AuditoriasCert'
import ExternosCert from '../components/certificaciones/ExternosCert'
import CertificadosCert from '../components/certificaciones/CertificadosCert'
import Nis2Cert from '../components/certificaciones/Nis2Cert'
import ProveedoresCert from '../components/certificaciones/ProveedoresCert'
import CatalogoCert from '../components/certificaciones/CatalogoCert'

const PESTANAS = ['panel', 'programas', 'aplicabilidad', 'matriz', 'evidencias', 'auditorias', 'externos', 'certificados',
  'nis2', 'proveedores', 'catalogo'] as const
type Pestana = typeof PESTANAS[number]

const ICONOS: Record<Pestana, JSX.Element> = {
  panel: <LayoutDashboard size={14} />, programas: <ClipboardList size={14} />, aplicabilidad: <ListChecks size={14} />,
  matriz: <Grid3x3 size={14} />, evidencias: <FileCheck2 size={14} />, auditorias: <Search size={14} />,
  externos: <Users size={14} />, certificados: <Award size={14} />, nis2: <Siren size={14} />, proveedores: <Truck size={14} />,
  catalogo: <BookOpen size={14} />,
}

export default function CertificacionesPage(): JSX.Element {
  const t = useAppT()
  // 24-11-2026 (barrido de traducciones): el servidor devuelve la biblioteca en el idioma
  // de la interfaz (`X-Idioma`); al cambiar de idioma se vuelve a pedir lo que hay en caché.
  const { lang } = useAppLang()
  const qc = useQueryClient()
  const idiomaAnterior = useRef(lang)
  useEffect(() => {
    if (idiomaAnterior.current === lang) return
    idiomaAnterior.current = lang
    qc.invalidateQueries({ queryKey: CLAVES_CERT.todo })
  }, [lang, qc])
  const [params, setParams] = useSearchParams()
  const pedida = params.get('tab') as Pestana | null
  const tab: Pestana = pedida && PESTANAS.includes(pedida) ? pedida : 'panel'
  const { data: programas = [] } = useQuery({ queryKey: CLAVES_CERT.programas, queryFn: certApi.programas })
  const programaId = params.get('programa') ?? (programas.length === 1 ? programas[0].id : '')
  const cambiar = (clave: string, valor: string | null) => {
    const sig = new URLSearchParams(params)
    if (valor) sig.set(clave, valor)
    else sig.delete(clave)
    setParams(sig, { replace: true })
  }
  const props = { programaId }
  return (
    <Page icon={<ShieldCheck size={18} />} title={t('nav.certificaciones')} subtitle={t('cert.subtitulo')}>
      <SelectorDeContexto>
        <SelectRico label={t('cert.programa')} valor={programaId} onChange={v => cambiar('programa', v || null)} opciones={[
          { valor: '', etiqueta: t('cert.todos_los_programas') },
          ...programas.map(p => ({ valor: p.id, etiqueta: `${p.codigo} · ${p.nombre}` }))]} />
      </SelectorDeContexto>
      <Tabs ariaLabel={t('nav.certificaciones')} active={tab} onChange={id => cambiar('tab', id)}
        items={PESTANAS.map(p => ({ id: p, label: t(`cert.tab_${p}`), icon: ICONOS[p] }))} />
      {tab === 'panel' && <PanelCert {...props} />}
      {tab === 'programas' && <ProgramasCert onElegir={id => { const sig = new URLSearchParams(params); sig.set('programa', id);
        sig.set('tab', 'aplicabilidad'); setParams(sig, { replace: true }) }} />}
      {tab === 'aplicabilidad' && <AplicabilidadCert {...props} />}
      {tab === 'matriz' && <MatrizCert {...props} />}
      {tab === 'evidencias' && <EvidenciasCert {...props} />}
      {tab === 'auditorias' && <AuditoriasCert {...props} />}
      {tab === 'externos' && <ExternosCert {...props} />}
      {tab === 'certificados' && <CertificadosCert {...props} />}
      {tab === 'nis2' && <Nis2Cert {...props} />}
      {tab === 'proveedores' && <ProveedoresCert {...props} />}
      {tab === 'catalogo' && <CatalogoCert />}
    </Page>
  )
}
