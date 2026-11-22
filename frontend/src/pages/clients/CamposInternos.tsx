/**
 * Ficha del cliente (22-11-2026, clientes internos): campo «Tipo» y, si es
 * interno, subtipo, estructura (departamento, área, centro de coste, empresa
 * del grupo), responsable de negocio y finanzas internas (modo, método de
 * coste, tabla de tarifas interna, margen de transferencia y cuenta ERP).
 *
 * Los selectores salen de `GET /internal-clients/options`. El formulario es de
 * textos; `datosInternos` (pages/internos/logica.ts) lo pasa a la carga útil.
 * Ver docs/CLIENTES_INTERNOS.md §2 y §11.
 */
import { Input, Select } from '../../components/ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useOpcionesInternas } from '../internos/comunes'
import { METODOS_DE_COSTE, MODOS_FINANCIEROS, SUBTIPOS, etiquetaInterna } from '../internos/logica'
import type { Traductor } from '../internos/logica'

type Props = {
  idBase: string
  form: Record<string, string>
  onCampo: (clave: string, valor: string) => void
  errorDe: (clave: string) => string | undefined
}

export function CamposInternos({ idBase, form, onCampo, errorDe }: Props): JSX.Element {
  const t = useAppT() as unknown as Traductor
  const interno = form.kind === 'interno'
  const op = useOpcionesInternas(interno)
  const sel = (clave: string, etiqueta: string, opciones: { value: string; label: string }[], vacio = true) => (
    <Select id={`${idBase}-${clave}`} label={etiqueta} value={form[clave] ?? ''} placeholder={vacio ? t('internos.sin_asignar') : false}
      onChange={e => onCampo(clave, e.target.value)} error={errorDe(clave)} options={opciones} />
  )
  return (
    <div className="cli-seccion" role="group" aria-labelledby={`${idBase}-tipo`}>
      <div id={`${idBase}-tipo`} className="cli-seccion__titulo">{t('internos.seccion_tipo')}</div>
      <div className="cli-form-grid">
        {sel('kind', t('internos.campo_tipo'), [
          { value: 'externo', label: t('internos.tipo_externo') },
          { value: 'interno', label: t('internos.tipo_interno') },
        ], false)}
        {interno && sel('internal_type', t('internos.campo_subtipo'), SUBTIPOS.map(s => ({ value: s, label: etiquetaInterna(t, 'subtipo_', s) })), false)}
      </div>
      {interno && (
        <>
          <div className="cli-seccion__titulo">{t('internos.seccion_estructura')}</div>
          <div className="cli-form-grid">
            {sel('department_id', t('internos.campo_departamento'), op.departments.map(d => ({ value: d.id, label: d.name })))}
            {sel('area_id', t('internos.campo_area'), op.areas.map(d => ({ value: d.id, label: d.name })))}
            {sel('cost_center_id', t('internos.campo_centro_coste'), op.cost_centers.map(d => ({ value: d.id, label: d.code ? `${d.code} · ${d.name}` : d.name })))}
            {sel('group_organization_id', t('internos.campo_empresa_grupo'), op.organizations.map(d => ({ value: d.id, label: d.name })))}
            {sel('business_owner_id', t('internos.campo_responsable'), op.users.map(u => ({ value: u.id, label: u.full_name })))}
          </div>
          <div className="cli-seccion__titulo">{t('internos.seccion_finanzas')}</div>
          <div className="cli-form-grid">
            {sel('finance_mode', t('internos.campo_modo'), MODOS_FINANCIEROS.map(m => ({ value: m, label: etiquetaInterna(t, 'modo_', m) })), false)}
            {sel('cost_method', t('internos.campo_metodo'), METODOS_DE_COSTE.map(m => ({ value: m, label: etiquetaInterna(t, 'metodo_', m) })), false)}
            {form.cost_method === 'tarifa_interna' && sel('internal_rate_table_id', t('internos.campo_tarifas'), op.rate_tables.map(d => ({ value: d.id, label: d.name })))}
            {form.finance_mode === 'intercompania' && (
              <Input id={`${idBase}-transfer_markup_pct`} label={t('internos.campo_margen')} type="number" step="0.01" min={0}
                value={form.transfer_markup_pct ?? ''} onChange={e => onCampo('transfer_markup_pct', e.target.value)} error={errorDe('transfer_markup_pct')} />
            )}
            <Input id={`${idBase}-erp_account`} label={t('internos.campo_cuenta_erp')} value={form.erp_account ?? ''}
              hint={form.finance_mode === 'chargeback' ? t('internos.campo_cuenta_erp_ayuda') : undefined}
              onChange={e => onCampo('erp_account', e.target.value)} error={errorDe('erp_account')} />
          </div>
        </>
      )}
    </div>
  )
}
