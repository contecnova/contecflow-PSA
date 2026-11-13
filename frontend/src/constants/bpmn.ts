/**
 * `targetNamespace` de los diagramas BPMN que genera la aplicación.
 *
 * Barrido 2026-11: el frontend escribía `http://contecflow.io/bpmn` y el backend
 * (`bpmn_process_service.BPMN_TARGET_NAMESPACE`) `http://contecflow/bpmn`. Se usa
 * el del backend. Es solo una etiqueta del documento: no cambia cómo se lee ni
 * se ejecuta un diagrama, y los ya guardados se abren igual. Los espacios de
 * nombres `xmlns:bpmn`/`bpmndi`/`dc`/`di` son los de la especificación OMG
 * BPMN 2.0 y ya coincidían.
 */
export const BPMN_TARGET_NAMESPACE = 'http://contecflow/bpmn'
