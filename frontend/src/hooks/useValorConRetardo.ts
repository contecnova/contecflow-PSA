import { useEffect, useState } from 'react'

/**
 * Devuelve `valor` solo cuando lleva `ms` milisegundos sin cambiar.
 *
 * Para búsquedas que van al servidor: escribir "ana" no lanza tres peticiones.
 */
export function useValorConRetardo<T>(valor: T, ms = 300): T {
  const [estable, setEstable] = useState(valor)
  useEffect(() => {
    const id = setTimeout(() => setEstable(valor), ms)
    return () => clearTimeout(id)
  }, [valor, ms])
  return estable
}
