/**
 * services/api/ausencias.ts — ausencias gobernadas por reglas (tarea #25).
 * El interceptor de `_core` ya desenvuelve `{ data, meta }`: `r.data` es el contenido.
 */
import api from './_core'
import type {
  AccesoEspecial, AjusteDeSaldoIn, AsignacionDeJornada, AsignacionDeJornadaIn, AusenciaServida, CambioDeTurno, Cobertura,
  Cuadrante, DetalleDeAusencia, DocumentoDeAusencia, EjemplosCargados, ElementoDeBandeja, FichaLaboral, FichaLaboralIn,
  Festivo, FestivoIn, FiltroDeHorario, HorarioEfectivo, Jornada, JornadaIn, MovimientoDeSaldo, PeticionDeAusencia,
  RecalculoDeBolsa, RequisitoDeAusencia, Rotacion, RotacionIn, SaldoDeAusencia, SaldosDePersona, TipoDeAusencia,
  TipoDeAusenciaIn, TipoDeDocumento, TipoDeDocumentoIn, Turno, TurnoIn, VistaPreviaDeAusencia,
} from './tipos-ausencias'

const D = <T,>(p: Promise<{ data: unknown }>) => p.then(r => r.data as T)
export interface RangoDeFechas { desde?: string; hasta?: string; equipo?: string; departamento?: string }
type Borrado = { eliminado?: boolean; desactivado?: boolean }
/** Listas como `user_ids=a&user_ids=b` (lo que espera FastAPI), no `user_ids[]=a`. */
const REPETIR = { paramsSerializer: { indexes: null } } as const

export const ausenciasApi = {
  tipos: (incluirInactivos = false) => D<TipoDeAusencia[]>(api.get('/absences/types', { params: { incluir_inactivos: incluirInactivos } })),
  crearTipo: (t: TipoDeAusenciaIn) => D<TipoDeAusencia>(api.post('/absences/types', t)),
  guardarTipo: (id: string, t: TipoDeAusenciaIn) => D<TipoDeAusencia>(api.put(`/absences/types/${id}`, t)),
  borrarTipo: (id: string) => D<Borrado>(api.delete(`/absences/types/${id}`)),
  documentos: (incluirInactivos = false) =>
    D<TipoDeDocumento[]>(api.get('/absences/document-types', { params: { incluir_inactivos: incluirInactivos } })),
  crearDocumento: (d: TipoDeDocumentoIn) => D<TipoDeDocumento>(api.post('/absences/document-types', d)),
  guardarDocumento: (id: string, d: TipoDeDocumentoIn) => D<TipoDeDocumento>(api.put(`/absences/document-types/${id}`, d)),
  borrarDocumento: (id: string) => D<Borrado>(api.delete(`/absences/document-types/${id}`)),
  accesos: () => D<AccesoEspecial[]>(api.get('/absences/special-access')),
  concederAcceso: (userId: string) => D<AccesoEspecial[]>(api.post('/absences/special-access', { user_id: userId })),
  retirarAcceso: (userId: string) => D<AccesoEspecial[]>(api.delete(`/absences/special-access/${userId}`)),
  turnos: (incluirInactivos = false) => D<Turno[]>(api.get('/absences/shifts', { params: { incluir_inactivos: incluirInactivos } })),
  crearTurno: (t: TurnoIn) => D<Turno>(api.post('/absences/shifts', t)),
  guardarTurno: (id: string, t: TurnoIn) => D<Turno>(api.put(`/absences/shifts/${id}`, t)),
  borrarTurno: (id: string) => D<Borrado>(api.delete(`/absences/shifts/${id}`)),
  rotaciones: () => D<Rotacion[]>(api.get('/absences/rotations')),
  crearRotacion: (r: RotacionIn) => D<Rotacion>(api.post('/absences/rotations', r)),
  guardarRotacion: (id: string, r: RotacionIn) => D<Rotacion>(api.put(`/absences/rotations/${id}`, r)),
  borrarRotacion: (id: string) => D<{ ok: boolean }>(api.delete(`/absences/rotations/${id}`)),
  cuadrante: (p: RangoDeFechas) => D<Cuadrante>(api.get('/absences/roster', { params: p })),
  cambiarCuadrante: (cambios: CambioDeTurno[]) => D<{ cambios: number }>(api.put('/absences/roster', { cambios })),
  cobertura: (p: RangoDeFechas) => D<Cobertura>(api.get('/absences/coverage', { params: p })),
  vistaPrevia: (p: PeticionDeAusencia) => D<VistaPreviaDeAusencia>(api.post('/absences/preview', p)),
  pedir: (p: PeticionDeAusencia) => D<AusenciaServida>(api.post('/absences/my', p)),
  editar: (id: string, p: PeticionDeAusencia) => D<AusenciaServida>(api.patch(`/absences/my/${id}`, p)),
  cancelar: (id: string) => D<{ ok: boolean }>(api.delete(`/absences/my/${id}`)),
  mias: () => D<AusenciaServida[]>(api.get('/absences/my')),
  delEquipo: (mes: string) => D<AusenciaServida[]>(api.get('/absences/team', { params: { month: mes } })),
  saldos: (fecha?: string) => D<SaldoDeAusencia[]>(api.get('/absences/my/balances', { params: fecha ? { fecha } : {} })),
  // ── Rev. 180: horario efectivo, jornadas, ficha laboral, saldos por persona, bolsa y festivos ──
  horario: (f: FiltroDeHorario) => D<HorarioEfectivo>(api.get('/absences/effective-schedule', { params: f, ...REPETIR })),
  miHorario: (desde: string, hasta: string) => D<HorarioEfectivo>(api.get('/absences/my/schedule', { params: { desde, hasta } })),
  jornadas: (incluirInactivas = false) =>
    D<Jornada[]>(api.get('/absences/work-schedules', { params: { incluir_inactivas: incluirInactivas } })),
  crearJornada: (j: JornadaIn) => D<Jornada>(api.post('/absences/work-schedules', j)),
  guardarJornada: (id: string, j: JornadaIn) => D<Jornada>(api.put(`/absences/work-schedules/${id}`, j)),
  borrarJornada: (id: string) => D<Borrado>(api.delete(`/absences/work-schedules/${id}`)),
  crearAsignacion: (a: AsignacionDeJornadaIn) => D<AsignacionDeJornada>(api.post('/absences/work-schedule-assignments', a)),
  guardarAsignacion: (id: string, a: AsignacionDeJornadaIn) =>
    D<AsignacionDeJornada>(api.put(`/absences/work-schedule-assignments/${id}`, a)),
  borrarAsignacion: (id: string) => D<{ ok: boolean }>(api.delete(`/absences/work-schedule-assignments/${id}`)),
  fichas: () => D<FichaLaboral[]>(api.get('/absences/work-profiles')),
  guardarFicha: (userId: string, f: Partial<FichaLaboralIn>) => D<FichaLaboral>(api.put(`/absences/work-profiles/${userId}`, f)),
  saldosDePersonas: (p: { fecha?: string; equipo?: string; departamento?: string; user_ids?: string[] } = {}) =>
    D<SaldosDePersona[]>(api.get('/absences/balances', { params: p, ...REPETIR })),
  movimientos: (userId: string, saldoClave?: string) =>
    D<MovimientoDeSaldo[]>(api.get(`/absences/balances/${userId}/movements`, { params: saldoClave ? { saldo_clave: saldoClave } : {} })),
  ajustarSaldo: (a: AjusteDeSaldoIn) => D<MovimientoDeSaldo>(api.post('/absences/balance-adjustments', a)),
  quitarAjuste: (id: string) => D<{ ok: boolean }>(api.delete(`/absences/balance-adjustments/${id}`)),
  recalcularBolsa: (desde: string, hasta: string, userIds?: string[]) =>
    D<RecalculoDeBolsa>(api.post('/absences/hour-bank/recalculate', { desde, hasta, user_ids: userIds?.length ? userIds : null })),
  festivos: () => D<Festivo[]>(api.get('/settings/holidays')),
  crearFestivo: (f: FestivoIn) => D<Festivo>(api.post('/settings/holidays', f)),
  guardarFestivo: (id: string, f: FestivoIn) => D<Festivo>(api.patch(`/settings/holidays/${id}`, f)),
  borrarFestivo: (id: string) => D<unknown>(api.delete(`/settings/holidays/${id}`)),
  bandeja: () => D<ElementoDeBandeja[]>(api.get('/absences/inbox')),
  decidir: (id: string, aprobada: boolean, nota?: string) =>
    D<{ status: string }>(api.post(`/absences/${id}/review`, { approved: aprobada, rejection_reason: nota || null })),
  detalle: (id: string) => D<DetalleDeAusencia>(api.get(`/absences/${id}/detail`)),
  subirDocumento: (id: string, tipoId: string, fichero: File, sustituyeA?: string | null, nota?: string) => {
    const fd = new FormData()
    fd.append('file', fichero)
    fd.append('tipo_id', tipoId)
    if (sustituyeA) fd.append('sustituye_a', sustituyeA)
    if (nota) fd.append('nota', nota)
    return D<DocumentoDeAusencia>(api.post(`/absences/${id}/documents`, fd))
  },
  abrirDocumento: (id: string, docId: string, accion: 'view' | 'download') =>
    D<{ url: string; nombre: string; accion: string }>(api.get(`/absences/${id}/documents/${docId}/open`, { params: { accion } })),
  pedirDocumento: (id: string, tipoId: string, vence: string, nota?: string) =>
    D<RequisitoDeAusencia>(api.post(`/absences/${id}/document-requests`, { tipo_id: tipoId, vence, nota: nota || null })),
  dispensar: (id: string, requisitoId: string, nota?: string) =>
    D<RequisitoDeAusencia>(api.post(`/absences/${id}/document-requests/${requisitoId}/waive`, { nota: nota || null })),
  ampliar: (id: string, fin: string, nota?: string) =>
    D<DetalleDeAusencia>(api.post(`/absences/${id}/extend`, { end_date: fin, nota: nota || null })),
  darPlaza: (id: string) => D<DetalleDeAusencia>(api.post(`/absences/${id}/promote`)),
  cargarEjemplos: () => D<EjemplosCargados>(api.post('/absences/examples')),
}
