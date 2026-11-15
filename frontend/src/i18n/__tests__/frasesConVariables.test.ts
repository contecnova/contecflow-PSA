// Frases con datos: una sola clave con {variables} por frase, en los 3 idiomas.
//
// Antes se montaban concatenando `t()` con números y valores en medio
// ("Tienes" + n + "acciones"), lo que fija el orden de palabras del español y
// rompe el inglés y el chino. Estas claves llevan la frase entera para que cada
// idioma coloque los datos donde le corresponde (Segunda auditoría 2026-11).
import { describe, expect, it } from 'vitest'
import en from '../langs/en.mjs'
import es from '../langs/es.mjs'
import zh from '../langs/zh.mjs'

type Arbol = { [k: string]: string | Arbol }
const DICC: Record<string, Arbol> = { es: es as Arbol, en: en as Arbol, zh: zh as Arbol }

const CLAVES_CON_VARIABLES = [
  'bigdpr.dsr_vencida_uno',
  'bigdpr.dsr_vencidas_otros',
  'governedconversations.resumen',
  'client_portal.uat_detail_cases_summary',
  'client_portal.uat_issues_summary',
  'datagovernance.mostrar_inactivas_con_activas',
  'datagovernance.mostrar_inactivas_con_ambas',
  'pagina_docs.paso_x_de_y',
  'pagina_docs.documentos_uno_filtrado',
  'pagina_docs.documentos_otros_filtrado',
  'pagina_ent.sincronizados_con_error',
  'pagina_imput.periodo_resumen',
  'jira_integration.sync_resumen',
  'jira_integration.push_resumen',
  'pagina_orgs.baja_pedida_fecha',
  'orgchart.aprobacion_con_aprobador',
  'orgchart.aprobacion_sin_aprobador',
  'pagina_perf.faltan_respuestas',
  'pagina_perf.oculto_umbral',
  'pagina_perf.ciclo_resumen',
  'prevision_recursos_ui.tendencia_semanas',
  'autoresolution.resumen_ejecucion',
  'incidentassignment.resumen',
  'voiceagent.transcripcion_turnos',
  'metricsdashboard.service_desk_ultimos_dias',
  'settingsadvanced.mostrando_200_de_n',
  'settingsadvanced.claves_de_total',
  'settingsadvanced.nivel_root_uvicorn',
  'sprint_planning.plan_meta',
  'sprints.backlog_titulo',
  'team_dashboard.trainings_sub',
  'team_dashboard.okrs_sub',
  'team_dashboard.trainings_gauge_sub',
  'timesheets.semana_rango',
  'timesheets.semana_del_fecha',
  'usercosts.resumen_meta',
  'usercosts.n_horas_ano',
  'work_dashboard.hours_target_sub',
  'ai.provider_resumen',
  'automations.pause_rule_aria',
  'automations.activate_rule_aria',
  'automations.delete_action_aria',
  'resource_scheduler.person_tooltip',
  'resource_scheduler.cell_tooltip',
  'cmdbtopologygraph.resumen_grafo',
  'biquerybuilder.mostrando_200_de_n',
  'voicecommand.audio_grabado_kb',
  'rcawizardmodal.paso_x_de_y',
  'smartschedulemodal.n_de_total_seleccionadas',
  'aihub.diagnostico_resumen',
  'chat.anade_miembros_minimo',
  'chat.anade_miembros_opcional',
  'pagina_perf.pares_seleccionados',
  'portaladvanced.base_iva',
  'portaldashboard.acciones_pendientes',
  'ratecards.copia_con_incremento',
  'reportes_ui.elige_entre_metricas',
  'reports.metricas_en_categorias',
  'sprint_planning.resultado_meta',
]

function valor(arbol: Arbol, clave: string): string | undefined {
  const v = clave.split('.').reduce<unknown>((a, p) => (a as Arbol | undefined)?.[p], arbol)
  return typeof v === 'string' ? v : undefined
}
const variables = (s: string) => [...new Set([...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]))].sort()

describe('frases con variables en una sola clave', () => {
  for (const clave of CLAVES_CON_VARIABLES) {
    it(`${clave} existe en es/en/zh con las mismas variables`, () => {
      const es_ = valor(DICC.es, clave)
      expect(es_, `falta ${clave} en es`).toBeTruthy()
      const vars = variables(es_ as string)
      expect(vars.length, `${clave} debe llevar al menos una variable`).toBeGreaterThan(0)
      for (const idioma of ['en', 'zh']) {
        const v = valor(DICC[idioma], clave)
        expect(v, `falta ${clave} en ${idioma}`).toBeTruthy()
        expect(variables(v as string), `variables de ${clave} en ${idioma}`).toEqual(vars)
      }
    })
  }

  it('el inglés y el chino no heredan el orden del español (no son copia literal)', () => {
    const iguales = CLAVES_CON_VARIABLES.filter(
      (k) => valor(DICC.en, k) === valor(DICC.es, k) || valor(DICC.zh, k) === valor(DICC.es, k),
    )
    // Solo se admite la frase técnica idéntica en todos los idiomas.
    expect(iguales).toEqual(['settingsadvanced.nivel_root_uvicorn'])
  })
})
