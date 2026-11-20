/**
 * Tablas compartidas de la CMDB de software (19-11-2026): instancias (máquina,
 * IP, entorno, puertos, TLS, ciclo de vida) y hallazgos (prioridad, CVSS, EPSS,
 * semáforo de SLA, producto y «dentro de»). Las usan las pestañas y la ficha.
 */
import { useAppT } from '../../../i18n/AppLangContext'
import type { Hallazgo, InstanciaSw } from '../../../services/api/cmdbSoftware'
import { StatusBadge, TablaSimple, Button } from '../../ui'
import { CicloBadge, ESTADO_KIND, PosibleBadge, Semaforo, SeveridadBadge, VersionTexto, useEtiquetaSw } from './comun'

/** Instancias: máquina, IP, entorno, puertos, TLS y ciclo de vida. */
export function TablaInstancias({ instancias, conProducto, onAbrir }: { instancias: InstanciaSw[]; conProducto?: boolean; onAbrir?: (i: InstanciaSw) => void }) {
  const t = useAppT()
  const e = useEtiquetaSw()
  return (
    <TablaSimple etiqueta={t('sw.instancias')}>
      <thead><tr>
        {conProducto && <th>{t('sw.software')}</th>}
        <th>{t('sw.version')}</th><th>{t('sw.maquina')}</th><th>{t('sw.ip')}</th><th>{t('sw.entorno')}</th>
        <th>{t('sw.puertos')}</th><th>{t('sw.tls')}</th><th>{t('sw.exposicion')}</th><th>{t('sw.ciclo_vida')}</th><th className="sw-num">{t('sw.col_hallazgos')}</th>
      </tr></thead>
      <tbody>
        {instancias.map(i => {
          const tls = i.config_summary?.tls_protocols
          return (
            <tr key={i.id}>
              {conProducto && <td>{onAbrir ? <Button variant="link" className="sw-enlace" onClick={() => onAbrir(i)}>{i.product_name ?? i.name}</Button> : (i.product_name ?? i.name)}
                {i.name && i.name !== i.product_name && <div className="u-text3-xs">{i.name}</div>}</td>}
              <td className="u-mono">{onAbrir && !conProducto ? <Button variant="link" className="sw-enlace" onClick={() => onAbrir(i)}><VersionTexto v={i.version} /></Button> : <VersionTexto v={i.version} />}</td>
              <td>{i.ci_name ?? '—'}{i.ci_hostname && <div className="u-text3-xs u-mono">{i.ci_hostname}</div>}</td>
              <td className="u-mono">{i.ci_ip ?? '—'}</td>
              <td>{e('entorno', i.environment)}</td>
              <td className="u-mono">{(i.ports ?? []).join(', ') || '—'}</td>
              <td className="u-mono">{tls ? (Array.isArray(tls) ? tls.join(' ') : String(tls)) : '—'}</td>
              <td><StatusBadge kind={i.exposure === 'internet' ? 'warning' : 'neutral'} caps={false}>{e('expo', i.exposure)}</StatusBadge></td>
              <td><CicloBadge c={i.lifecycle} fecha={i.eol_date} />{!i.lifecycle && <span className="u-text3-xs">{t('sw.con_soporte')}</span>}</td>
              <td className="sw-num">{i.open_findings ?? 0} {i.worst_severity && <SeveridadBadge s={i.worst_severity} />}</td>
            </tr>
          )
        })}
      </tbody>
    </TablaSimple>
  )
}

/** Lista de hallazgos: prioridad, CVSS, EPSS, semáforo de SLA, dónde. */
export function TablaHallazgos({ hallazgos, onAbrir }: { hallazgos: Hallazgo[]; onAbrir: (h: Hallazgo) => void }) {
  const t = useAppT()
  const e = useEtiquetaSw()
  return (
    <TablaSimple etiqueta={t('sw.hallazgos')}>
      <thead><tr>
        <th className="sw-num">{t('sw.prioridad')}</th><th>{t('sw.aviso')}</th><th>{t('sw.severidad')}</th>
        <th className="sw-num">CVSS</th><th className="sw-num">EPSS</th><th>{t('sw.sla')}</th>
        <th>{t('sw.software')}</th><th>{t('sw.maquina')}</th><th>{t('sw.estado')}</th>
      </tr></thead>
      <tbody>
        {hallazgos.map(h => (
          <tr key={h.id}>
            <td className="sw-num u-600">{h.priority_score != null ? Math.round(h.priority_score) : '—'}</td>
            <td>
              <Button variant="link" className="sw-enlace u-mono" onClick={() => onAbrir(h)}>{h.vuln_id ?? '—'}</Button>
              {h.kev && <> <StatusBadge kind="danger" caps={false} title={t('sw.kev_ayuda')}>KEV</StatusBadge></>}
              {h.title && <div className="u-text3-xs sw-recorte" title={h.title}>{h.title}</div>}
            </td>
            <td><SeveridadBadge s={h.severity} /> <PosibleBadge posible={h.possible} /></td>
            <td className="sw-num">{h.cvss_score != null ? h.cvss_score.toFixed(1) : '—'}</td>
            <td className="sw-num">{h.epss_score != null ? `${(h.epss_score * 100).toFixed(1)} %` : '—'}</td>
            <td><Semaforo h={h} /></td>
            <td>
              <div>{h.product_name ?? '—'} <span className="u-text3-xs"><VersionTexto v={h.affected_version} /></span></div>
              {h.fixed_version && <div className="u-text3-xs">{t('sw.corregido_en')}: <span className="u-mono">{h.fixed_version}</span></div>}
              {h.parent_product_name && <div className="u-text3-xs">{t('sw.dentro_de', { nombre: `${h.parent_product_name} ${h.parent_version ?? ''}`.trim() })}</div>}
            </td>
            <td>{h.ci_name ?? h.instance_name ?? '—'}{h.environment && <div className="u-text3-xs">{e('entorno', h.environment)}{h.exposure ? ` · ${e('expo', h.exposure)}` : ''}</div>}</td>
            <td><StatusBadge kind={ESTADO_KIND[h.status] ?? 'neutral'} caps={false}>{e('estado', h.status)}</StatusBadge></td>
          </tr>
        ))}
      </tbody>
    </TablaSimple>
  )
}
