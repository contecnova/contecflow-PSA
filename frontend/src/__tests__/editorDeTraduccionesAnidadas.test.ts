// 16-11-2026: Ajustes → Idiomas → «Textos de la aplicación» se caía con
// «Objects are not valid as a React child»: los diccionarios anidan textos
// (`almint.criterio.todos`) y el editor suponía dos niveles. Ahora lista las
// hojas de texto con su ruta, y los textos personalizados se mezclan en
// profundidad (editar uno no borra a sus hermanos).
import { describe, expect, it } from 'vitest'
import { getAllKeys } from '../i18n/appTranslations.mjs'
import es from '../i18n/langs/es.mjs'

describe('editor de traducciones con textos anidados', () => {
  it('solo devuelve textos, con la ruta completa dentro del módulo', () => {
    const claves = getAllKeys({ m: { a: 'A', sub: { b: 'B', otra: { c: 'C' } } } })
    expect(claves.map(k => k.full_key)).toEqual(['m.a', 'm.sub.b', 'm.sub.otra.c'])
    expect(claves.every(k => typeof k.base_es === 'string')).toBe(true)
  })

  it('ninguna clave del castellano es un objeto', () => {
    for (const k of getAllKeys(es)) expect(typeof k.base_es, k.full_key).toBe('string')
  })
})
