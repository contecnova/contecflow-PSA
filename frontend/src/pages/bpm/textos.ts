/**
 * Textos de BPM construidos con códigos del backend (`app/services/bpmn_engine.py`).
 *
 * Revisión BPM 2026-11-16: la pantalla mostraba tal cual el tipo de elemento
 * (`userTask`), el rol de la calle (`team_lead`) y los motivos de fallo, que el
 * motor escribe en castellano. Ahora el backend manda códigos y aquí se
 * traducen; si un código no tiene texto (backend más nuevo que el frontend) se
 * muestra el texto legible del backend o el propio código, nunca la clave.
 * `tests/test_bpm_i18n_codigos.py` exige un texto por código en los tres idiomas.
 */
import type { InstanciaBpmn, ProblemaBpmn } from '../../services/api/tipos-documentos'

type Traducir = (k: string, p?: Record<string, unknown>) => string

function traducirO(t: Traducir, clave: string, alternativa: string, params?: Record<string, unknown>): string {
  const texto = t(clave, params)
  return texto && texto !== clave ? texto : alternativa
}

/** Un problema que impide ejecutar un diagrama (`bpm.problema_<code>`). */
export function textoProblema(t: Traducir, p: ProblemaBpmn): string {
  return traducirO(t, `bpm.problema_${p.code}`, p.detail, { element: p.element ?? '', extra: p.extra ?? '' })
}

/** El motivo del fallo de una instancia (`bpm.error_<code>`). */
export function textoErrorDeInstancia(t: Traducir, inst: Pick<InstanciaBpmn, 'error' | 'error_code' | 'error_params'>): string | null {
  if (!inst.error && !inst.error_code) return null
  if (!inst.error_code) return inst.error
  return traducirO(t, `bpm.error_${inst.error_code}`, inst.error || inst.error_code, inst.error_params ?? undefined)
}

/** Tipo de elemento BPMN (`bpm.tipo_<elementType>`). */
export function textoTipo(t: Traducir, tipo: string): string {
  return traducirO(t, `bpm.tipo_${tipo}`, tipo)
}

/** Rol que exige la calle del diagrama (`bpm.rol_<rol>`); sin rol, «cualquiera». */
export function textoRol(t: Traducir, rol: string | null | undefined): string {
  return rol ? traducirO(t, `bpm.rol_${rol}`, rol) : t('bpm.rol_cualquiera')
}

/** Estado de una instancia o de un paso (`bpm.estado_<estado>`). */
export function textoEstado(t: Traducir, estado: string): string {
  return traducirO(t, `bpm.estado_${estado}`, estado)
}

/** Variables escritas una por línea (`nombre=valor`): booleanos y números con su tipo. */
export function leerVariables(texto: string): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  texto.split('\n').map(l => l.trim()).filter(Boolean).forEach(l => {
    const i = l.indexOf('=')
    if (i <= 0) return
    const k = l.slice(0, i).trim()
    const raw = l.slice(i + 1).trim()
    if (raw === 'true' || raw === 'false') out[k] = raw === 'true'
    else if (raw !== '' && !Number.isNaN(Number(raw))) out[k] = Number(raw)
    else out[k] = raw
  })
  return out
}
