// Pestañas de ajustes del portal y de facturas de la ficha de cliente. 23-11-2026: troceado de ClientsPageTabs sin cambio de comportamiento.
import { type CSSProperties, useState, useEffect, useId } from 'react'
import { Globe, Receipt, Ticket } from 'lucide-react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useToast } from '../../context/ToastContext'
import { clientExtApi, clientsApi } from '../../services/api'
import { Button, Spinner, EmptyState, Select, TablaSimple, Checkbox, Input } from '../../components/ui'
import Pagination from '../../components/ui/Pagination'
import { fmtDate, extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { useAppLang } from '../../i18n/AppLangContext'
import type { FacturaDeCliente } from '../../services/api/tipos-alm'
import { alpha } from '../../constants/theme'
import { useFormatoMoneda } from '../../hooks/useFormatoMoneda'
import { IDIOMA_POR_DEFECTO, PORTAL_LANGUAGES } from '../../i18n/portalTranslations'
import { MODULES, type PortalConfig, type PortalConfigPayload, SLA_COLOR } from './ClientsTabsComun'

export function PortalSettingsTab({ cid }: { cid: string }) {
  const idCampo = useId()
  const { t: traducir } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: cfg, isLoading } = useQuery<PortalConfig>({
    queryKey: ['client-portal-cfg', cid],
    queryFn: () => clientExtApi.portalConfig(cid).then(r => r.data),
  })
  const [modules, setModules] = useState<string[]>([])
  const [sdWithout, setSdWithout] = useState(true)
  const [slaTier, setSlaTier] = useState('')
  const [maxUsers, setMaxUsers] = useState(10)
  const [defaultLang, setDefaultLang] = useState<string>(IDIOMA_POR_DEFECTO)
  const [allowEdit, setAllowEdit] = useState(true)
  const [allowPwd, setAllowPwd] = useState(true)

  useEffect(() => {
    if (cfg) {
      setModules(cfg.enabled_modules || [])
      setSdWithout(cfg.sd_without_project ?? true)
      setSlaTier(cfg.sla_tier || '')
      setMaxUsers(cfg.max_portal_users || 10)
      setDefaultLang(cfg.default_language || IDIOMA_POR_DEFECTO)
      setAllowEdit(cfg.allow_profile_edit ?? true)
      setAllowPwd(cfg.allow_pwd_change ?? true)
    }
  }, [cfg])

  const { mutate: save, isPending: saving } = useMutation({
    mutationFn: (d: PortalConfigPayload) => clientExtApi.updatePortalConfig(cid, d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['client-portal-cfg', cid] }); toast.success(traducir('clientstabs.config_guardada')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const toggleModule = (mod: string) => setModules(m => m.includes(mod) ? m.filter(x => x !== mod) : [...m, mod])

  // 23-11-2026: los idiomas del portal salen de su catálogo único (8 idiomas).
  const languages = PORTAL_LANGUAGES

  if (isLoading) return <Spinner />
  return (
    <div className="clpata-grid-3">
      <div className="u-stack-16">
        <div className="clpata-panel5">
          <div className="clpata-box-22">{traducir('clients.modulos_del_portal')}</div>
          <div className="clpata-box-23">{traducir('clients.que_secciones_puede_ver_el_cliente_en')}</div>
          {MODULES.map(m => (
            <label key={m.id} className="clpata-row-12">
              <Checkbox checked={modules.includes(m.id)} onChange={() => toggleModule(m.id)} className="clpata-box-24" />
              <span className="clpata-txt-4" aria-hidden="true"><m.Icon size={15} /></span>
              <span className={`clpata-txt-6 ${modules.includes(m.id) ? 'clients-page-tabs-m8' : 'clients-page-tabs-m9'}`}>{traducir(`clientstabs.mod_${m.id}`)}</span>
            </label>
          ))}
        </div>

        <div className="clpata-panel5">
          <div className="clpata-box-22 clpata-ico"><Ticket size={15} aria-hidden="true" />{traducir('clientstabs.mod_support')}</div>
          <label className="clpata-row-13">
            <Checkbox aria-label={traducir('clients.acceso_sin_proyecto_vinculado')} checked={sdWithout} onChange={(_, e) => setSdWithout(e.target.checked)} className="clpata-box-25" />
            <div>
              <div className="u-base-600">{traducir('clients.acceso_sin_proyecto_vinculado')}</div>
              <div className="u-text2-xs">{traducir('clients.puede_abrir_tickets_aunque_no_tenga_proyectos')}</div>
            </div>
          </label>
        </div>
      </div>

      <div className="u-stack-16">
        <div className="clpata-panel5">
          <div className="clpata-box-22 clpata-ico"><Globe size={15} aria-hidden="true" />{traducir('clientstabs.idioma_y_sla')}</div>
          <div className="u-mb-14">
            <Select label={traducir('clients.idioma_por_defecto_del_portal')} placeholder={false} id={`${idCampo}-1`} value={defaultLang} onChange={e => setDefaultLang(e.target.value)}>
              {languages.map(l => <option key={l.code} value={l.code}>{l.label}</option>)}
            </Select>
            <div className="clpata-box-26">{traducir('clients.se_aplica_a_nuevos_usuarios_cada_usuario')}</div>
          </div>
          <div>
            <Select label={traducir('clientstabs.tier_sla')} placeholder={false} id={`${idCampo}-2`} value={slaTier} onChange={e => setSlaTier(e.target.value)}>
              <option value="">{traducir('clients.sin_tier')}</option>
              <option value="bronze">{traducir('clientstabs.sla_bronze')}</option>
              <option value="silver">{traducir('clientstabs.sla_silver')}</option>
              <option value="gold">{traducir('clientstabs.sla_gold')}</option>
              <option value="enterprise">{traducir('clientstabs.sla_enterprise')}</option>
            </Select>
            {slaTier && <div className="clpata-box-34 clients-page-tabs-e1" style={{ '--clients-page-tabs-background': alpha((SLA_COLOR[slaTier] || 'var(--text-2)'), '15'), '--clients-page-tabs-color': SLA_COLOR[slaTier] || 'var(--text-2)' } as CSSProperties}>
              {traducir('clientstabs.tier_activo')} <strong>{traducir(`clientstabs.sla_${slaTier}`).split(' — ')[0]}</strong>
            </div>}
          </div>
        </div>

        <div className="clpata-panel5">
          <div className="clpata-box-22">{traducir('clients.perfil_del_cliente')}</div>
          <div className="clpata-box-23">{traducir('clients.define_que_puede_modificar_el_cliente_desde')}</div>
          {[
            { key: 'allowEdit', val: allowEdit, set: setAllowEdit, label: traducir('clientstabs.puede_editar_perfil'), desc: traducir('clientstabs.puede_editar_perfil_desc') },
            { key: 'allowPwd', val: allowPwd, set: setAllowPwd, label: traducir('clientstabs.puede_cambiar_pwd'), desc: traducir('clientstabs.puede_cambiar_pwd_desc') },
          ].map(opt => (
            <label className={`clpata-row-15 clientsp-sx1 clients-page-tabs-e2 ${opt.val ? 'clients-page-tabs-m10' : 'clients-page-tabs-m11'}`} key={opt.key} style={{ '--clients-page-tabs-border': `1px solid ${opt.val ? 'var(--accent)' : 'var(--surface-4)'}` } as CSSProperties}>
              <Checkbox checked={opt.val} onChange={(_, e) => opt.set(e.target.checked)} className="clpata-box-27" />
              <div>
                <div className={`clpata-txt-7 ${opt.val ? 'clients-page-tabs-m12' : 'clients-page-tabs-m13'}`}>{opt.label}</div>
                <div className="u-text3-xs">{opt.desc}</div>
              </div>
            </label>
          ))}
          <div className="clpata-sp-2">
            <Input label={traducir('clients.max_usuarios_de_portal')} id={`${idCampo}-3`} type="number" min={1} max={100} value={maxUsers} onChange={e => setMaxUsers(+e.target.value)} />
          </div>
        </div>

        <Button onClick={() => save({ enabled_modules: modules, sd_without_project: sdWithout, sla_tier: slaTier || null, max_portal_users: maxUsers, default_language: defaultLang, allow_profile_edit: allowEdit, allow_pwd_change: allowPwd })} className="clientsp-sx2" loading={saving}>
          {traducir('clients.guardar_configuracion_del_portal')}
        </Button>
      </div>
    </div>
  )
}

// ── Facturas del cliente (#22) ───────────────────────────────────────────────
// GET /clients/{cid}/invoices pagina en el servidor: el total llega en `meta.total`
// (o `X-Total-Count`) y la pestana solo trae la pagina visible.
const FACTURAS_POR_PAGINA = 20

const FACTURA_ESTADOS = ['draft', 'sent', 'paid', 'overdue', 'cancelled'] as const

export function InvoicesTab({ cid }: { cid: string }) {
  const { t: traducir } = useAppLang()
  const dinero = useFormatoMoneda()
  const [page, setPage] = useState(1)

  const { data, isLoading, isError, isFetching, refetch } = useQuery({
    queryKey: ['client-invoices', cid, page],
    queryFn: () => clientsApi.invoices(cid, { page, page_size: FACTURAS_POR_PAGINA }).then(r => ({
      items: r.data,
      total: r.meta?.total ?? Number(r.headers?.['x-total-count'] ?? r.data.length),
    })),
    placeholderData: previous => previous,
  })

  const total = data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / FACTURAS_POR_PAGINA))
  // Si la pagina pedida queda fuera del total, vuelve a la ultima que existe.
  useEffect(() => { if (data && page > totalPages) setPage(totalPages) }, [data, page, totalPages])
  useEffect(() => { setPage(1) }, [cid])

  const etiquetaEstado = (st: string) => (FACTURA_ESTADOS as readonly string[]).includes(st) ? traducir(`clientstabs.fact_estado_${st}`) : st

  if (isLoading) return <Spinner />
  if (isError) {
    return (
      <div className="clifac-error" role="alert">
        <span>{traducir('clientstabs.fact_error')}</span>
        <Button variant="secondary" size="sm" onClick={() => refetch()}>{traducir('clientstabs.fact_reintentar')}</Button>
      </div>
    )
  }
  const facturas: FacturaDeCliente[] = data?.items ?? []
  if (facturas.length === 0) {
    return <EmptyState icon={<Receipt size={28} />} title={traducir('clientstabs.fact_vacio_titulo')} description={traducir('clientstabs.fact_vacio_desc')} />
  }
  return (
    <div className="clifac" aria-busy={isFetching || undefined}>
      <div className="clifac-scroll">
        <TablaSimple claseTabla="clifac-tabla">
          <thead>
            <tr>
              <th scope="col">{traducir('clientstabs.fact_numero')}</th>
              <th scope="col">{traducir('clientstabs.fact_proyecto')}</th>
              <th scope="col">{traducir('clientstabs.fact_emision')}</th>
              <th scope="col">{traducir('clientstabs.fact_vencimiento')}</th>
              <th scope="col" className="clifac-num">{traducir('clientstabs.fact_importe')}</th>
              <th scope="col">{traducir('clientstabs.fact_estado')}</th>
            </tr>
          </thead>
          <tbody>
            {facturas.map(f => (
              <tr key={f.id}>
                <td className="clifac-numero">{f.number ?? '—'}</td>
                <td>{f.project_name ?? '—'}</td>
                <td>{f.issue_date ? fmtDate(f.issue_date) : '—'}</td>
                <td>{f.due_date ? fmtDate(f.due_date) : '—'}</td>
                <td className="clifac-num">{f.total_amount == null ? '—' : dinero(f.total_amount)}</td>
                <td><span className={`clifac-estado clifac-estado--${f.status}`}>{etiquetaEstado(f.status)}</span></td>
              </tr>
            ))}
          </tbody>
        </TablaSimple>
      </div>
      <Pagination page={page} totalPages={totalPages} onChange={setPage} total={total} pageSize={FACTURAS_POR_PAGINA} maxVisible={5} />
    </div>
  )
}
