import { useCallback, useMemo, useState } from 'react'
import { useTextoUi } from './useTextoUi'
import { erroresPorCampo } from '../../utils/erroresDeValidacion'

/**
 * useErroresDeCampo — los errores de validación del servidor junto a cada campo
 * (17-11-2026).
 *
 *   const campos = useErroresDeCampo()
 *   useMutation({ ..., onMutate: campos.limpiar, onError: e => { if (!campos.recoger(e)) toast.error(extractErr(e, '…')) } })
 *   <Input label="Nombre" error={campos.de('name')} onChange={e => { campos.limpiar('name'); … }} />
 *
 * `recoger(e)` lee un 422 de validación (`code: 'validacion'`) y devuelve true
 * si había errores de campo (el formulario ya los enseña; no hace falta aviso).
 * Los textos salen traducidos con el traductor del kit: el de operador
 * (es/en/zh) o, dentro del portal, el del portal (8 idiomas).
 *
 * `alias` traduce nombres del servidor a los del formulario
 * (`{ client_id: 'cliente' }`) cuando no coinciden.
 */
export function useErroresDeCampo(alias: Record<string, string> = {}) {
  const t = useTextoUi()
  const [errores, setErrores] = useState<Record<string, string>>({})
  const claveAlias = JSON.stringify(alias)

  const recoger = useCallback((e: unknown): boolean => {
    const porCampo = erroresPorCampo(e, t)
    if (!porCampo) { setErrores({}); return false }
    const mapa: Record<string, string> = JSON.parse(claveAlias)
    const salida: Record<string, string> = {}
    for (const [campo, texto] of Object.entries(porCampo)) {
      const destino = mapa[campo] ?? campo
      if (!(destino in salida)) salida[destino] = texto
    }
    setErrores(salida)
    // Solo cuenta como «de campo» si alguno tiene nombre (un error del cuerpo entero va al aviso).
    return Object.keys(salida).some(k => k !== '')
  }, [t, claveAlias])

  const limpiar = useCallback((campo?: unknown) => {
    setErrores(prev => {
      if (typeof campo !== 'string') return Object.keys(prev).length ? {} : prev
      if (!(campo in prev)) return prev
      const { [campo]: _quitado, ...resto } = prev
      return resto
    })
  }, [])

  const de = useCallback((campo: string): string | undefined => errores[campo], [errores])

  return useMemo(() => ({
    errores, de, recoger, limpiar, hay: Object.keys(errores).length > 0,
    /** Para quien gestiona sus propios errores locales: fija los del servidor. */
    fijar: setErrores,
  }), [errores, de, recoger, limpiar])
}

export type ErroresDeCampo = ReturnType<typeof useErroresDeCampo>
