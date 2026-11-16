/**
 * Icono (lucide) de cada clase de CI. Sustituye a los emojis que usaban la
 * tabla, el detalle y el grafo de topología (pasada de diseño 16-11-2026).
 */
import {
  AppWindow, Box, Cloud, Cpu, Database, Globe, HardDrive, Laptop, MapPin, Plug, Puzzle, Server, Settings,
  type LucideIcon, type LucideProps,
} from 'lucide-react'

export const CI_TYPE_LUCIDE: Record<string, LucideIcon> = {
  server: Server,
  virtual_machine: Cpu,
  application: AppWindow,
  database: Database,
  network: Globe,
  service: Settings,
  container: Box,
  cloud: Cloud,
  endpoint: Laptop,
  storage: HardDrive,
  module: Puzzle,
  integration: Plug,
  other: MapPin,
}

/** El icono de la clase `tipo` (o el genérico si no se conoce). */
export function IconoCi({ tipo, ...props }: { tipo?: string | null } & LucideProps) {
  const Icono = CI_TYPE_LUCIDE[tipo ?? ''] ?? MapPin
  return <Icono aria-hidden="true" {...props} />
}
