/**
 * Icono de un tipo de ausencia (tarea #25). Los nombres son los de
 * `app/services/ausencias/catalogo.py::ICONOS`; uno desconocido sale como círculo.
 */
import {
  Baby, BookOpen, Briefcase, Calendar, Circle, Clock, Coffee, GraduationCap, Heart, Home, Plane, Shield,
  Stethoscope, Sun, Umbrella, User,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

export const ICONOS_DE_AUSENCIA: Record<string, LucideIcon> = {
  umbrella: Umbrella, sun: Sun, stethoscope: Stethoscope, user: User, graduation: GraduationCap, baby: Baby,
  circle: Circle, plane: Plane, heart: Heart, home: Home, briefcase: Briefcase, clock: Clock, calendar: Calendar,
  book: BookOpen, shield: Shield, coffee: Coffee,
}

export default function IconoDeAusencia({ icono, size = 16, etiqueta }: { icono: string | null | undefined; size?: number; etiqueta?: string }) {
  const Icono = ICONOS_DE_AUSENCIA[icono ?? ''] ?? Circle
  return etiqueta
    ? <Icono size={size} role="img" aria-label={etiqueta} />
    : <Icono size={size} aria-hidden />
}
