import { useState, useEffect, useRef, useMemo } from 'react'
import type { CSSProperties, RefObject } from 'react'
import { Button, Page } from '../components/ui'
import { Network, Plus, X, ChevronLeft, Edit3, Download, Search } from 'lucide-react'
import { bpmnProcessesApi, apiErrorMsg } from '../services/api'
import { useToast } from '../context/ToastContext'

// NOTE: bpmn-js (JS + CSS) is loaded dynamically inside useBpmnViewer so it
// stays out of the initial bundle (~400 KB JS + assets). See audit #43, #81.
let _bpmnCssLoaded = false
async function loadBpmnCssOnce() {
  if (_bpmnCssLoaded) return
  _bpmnCssLoaded = true
  await Promise.all([
    import('bpmn-js/dist/assets/diagram-js.css'),
    import('bpmn-js/dist/assets/bpmn-font/css/bpmn.css'),
  ])
}

// ─── BPMN XML GENERATOR ───────────────────────────────────────────────────────
const DIMS = {
  startEvent:         { w: 36,  h: 36  },
  endEvent:           { w: 36,  h: 36  },
  task:               { w: 100, h: 80  },
  userTask:           { w: 100, h: 80  },
  serviceTask:        { w: 100, h: 80  },
  scriptTask:         { w: 100, h: 80  },
  exclusiveGateway:   { w: 50,  h: 50  },
  parallelGateway:    { w: 50,  h: 50  },
  intermediateCatchEvent: { w: 36, h: 36 },
}
const COL_W  = 170
const ROW_H  = 160
const X0     = 80
const Y0     = 140

type BpmnNode = { id: string; type: string; name: string; col?: number; row?: number }
type BpmnConn = [string, string, string?, string?]
type NodePos = { cx: number; cy: number; x: number; y: number; w: number; h: number }

function xmlEsc(s: unknown): string {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')
}

function buildBpmn(pid: string, pname: string, nodes: BpmnNode[], conns: BpmnConn[]): string {
  const posOf: Record<string, NodePos> = {}
  nodes.forEach(n => {
    const d   = (DIMS as Record<string, { w: number; h: number }>)[n.type] || DIMS.task
    const cx  = X0 + (n.col ?? 0) * COL_W
    const cy  = Y0 + (n.row ?? 0) * ROW_H
    posOf[n.id] = { cx, cy, x: cx - d.w / 2, y: cy - d.h / 2, w: d.w, h: d.h }
  })

  const inc: Record<string, string[]> = {}, out: Record<string, string[]> = {}
  conns.forEach(([fr, to,, fid]) => {
    const id = fid || `f_${fr}_${to}`
    ;(out[fr] = out[fr] || []).push(id)
    ;(inc[to]  = inc[to]  || []).push(id)
  })

  const nodeXml = nodes.map(n => {
    const i = (inc[n.id] || []).map(f => `<bpmn:incoming>${f}</bpmn:incoming>`).join('')
    const o = (out[n.id] || []).map(f => `<bpmn:outgoing>${f}</bpmn:outgoing>`).join('')
    return `    <bpmn:${n.type} id="${n.id}" name="${xmlEsc(n.name)}">${i}${o}</bpmn:${n.type}>`
  }).join('\n')

  const flowXml = conns.map(([fr, to, lbl, fid]) => {
    const id   = fid || `f_${fr}_${to}`
    const attr = lbl ? ` name="${xmlEsc(lbl)}"` : ''
    return `    <bpmn:sequenceFlow id="${id}"${attr} sourceRef="${fr}" targetRef="${to}" />`
  }).join('\n')

  const shapeXml = nodes.map(n => {
    const p   = posOf[n.id]
    const gw  = n.type.includes('Gateway') ? ' isMarkerVisible="true"' : ''
    const lbx = p.cx - 50
    const lby = p.y + p.h + 4
    return `      <bpmndi:BPMNShape id="${n.id}_di" bpmnElement="${n.id}"${gw}>
        <dc:Bounds x="${p.x}" y="${p.y}" width="${p.w}" height="${p.h}" />
        <bpmndi:BPMNLabel><dc:Bounds x="${lbx}" y="${lby}" width="100" height="28" /></bpmndi:BPMNLabel>
      </bpmndi:BPMNShape>`
  }).join('\n')

  const edgeXml = conns.map(([fr, to, lbl, fid]) => {
    const id  = fid || `f_${fr}_${to}`
    const s   = posOf[fr]
    const t   = posOf[to]
    const nFr = nodes.find(n => n.id === fr)
    const nTo = nodes.find(n => n.id === to)
    const rFr = nFr?.row ?? 0
    const rTo = nTo?.row ?? 0

    let wps
    if (rFr === rTo) {
      if (s.cx <= t.cx) {
        wps = `<di:waypoint x="${s.x + s.w}" y="${s.cy}" /><di:waypoint x="${t.x}" y="${t.cy}" />`
      } else {
        // backward / loop - route above
        const loopY = Math.min(s.y, t.y) - 50
        wps = `<di:waypoint x="${s.cx}" y="${s.y}" /><di:waypoint x="${s.cx}" y="${loopY}" /><di:waypoint x="${t.cx}" y="${loopY}" /><di:waypoint x="${t.cx}" y="${t.y}" />`
      }
    } else if (rFr < rTo) {
      wps = `<di:waypoint x="${s.cx}" y="${s.y + s.h}" /><di:waypoint x="${s.cx}" y="${t.cy}" /><di:waypoint x="${t.x}" y="${t.cy}" />`
    } else {
      wps = `<di:waypoint x="${s.x + s.w}" y="${s.cy}" /><di:waypoint x="${t.cx}" y="${s.cy}" /><di:waypoint x="${t.cx}" y="${t.y + t.h}" />`
    }

    const lblEl = lbl ? `<bpmndi:BPMNLabel><dc:Bounds x="${(s.cx + t.cx) / 2 - 15}" y="${Math.min(s.cy, t.cy) - 22}" width="40" height="14" /></bpmndi:BPMNLabel>` : ''
    return `      <bpmndi:BPMNEdge id="${id}_di" bpmnElement="${id}">${wps}${lblEl}</bpmndi:BPMNEdge>`
  }).join('\n')

  return `<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
  xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
  xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"
  xmlns:di="http://www.omg.org/spec/DD/20100524/DI"
  id="Definitions_${pid}" targetNamespace="http://contecflow.io/bpmn">
  <bpmn:process id="${pid}" name="${xmlEsc(pname)}" isExecutable="false">
${nodeXml}
${flowXml}
  </bpmn:process>
  <bpmndi:BPMNDiagram id="BPMNDiagram_${pid}">
    <bpmndi:BPMNPlane id="BPMNPlane_${pid}" bpmnElement="${pid}">
${shapeXml}
${edgeXml}
    </bpmndi:BPMNPlane>
  </bpmndi:BPMNDiagram>
</bpmn:definitions>`
}

// ─── PROCESS CATALOG ─────────────────────────────────────────────────────────
const CATEGORIES = [
  { id: 'all',        label: 'Todos los procesos', color: 'var(--accent)' },
  { id: 'proyectos',  label: 'Gestión de Proyectos', color: '#3b82f6' },
  { id: 'finanzas',   label: 'Finanzas y Facturación', color: '#10b981' },
  { id: 'rrhh',       label: 'RRHH y Recursos', color: '#f59e0b' },
  { id: 'servicedesk',label: 'Service Desk / ITSM', color: '#ef4444' },
  { id: 'crm',        label: 'CRM y Ventas', color: '#8b5cf6' },
  { id: 'admin',      label: 'Administración', color: '#6b7280' },
]

const CAT_COLOR = Object.fromEntries(CATEGORIES.map(c => [c.id, c.color]))

const PROCESS_CATALOG = [
  // ── PROYECTOS ────────────────────────────────────────────────────────────
  {
    id: 'proj_creation',
    category: 'proyectos',
    name: 'Creación y Kickoff de Proyecto',
    description: 'Desde la solicitud inicial hasta el arranque oficial del proyecto con el equipo asignado.',
    owner: 'Project Manager',
    sla: '3 días hábiles',
    steps: ['Solicitar proyecto','Definir alcance y objetivos','Estimar presupuesto','Aprobar solicitud','Asignar PM y equipo','Crear proyecto en sistema','Reunión de kickoff','Proyecto activo'],
    bpmn: buildBpmn('proj_creation', 'Creación y Kickoff de Proyecto',
      [
        { id: 'st',  type: 'startEvent',       name: 'Solicitud',             col: 0 },
        { id: 't1',  type: 'userTask',          name: 'Definir Alcance',       col: 1 },
        { id: 't2',  type: 'userTask',          name: 'Estimar Presupuesto',   col: 2 },
        { id: 'gw1', type: 'exclusiveGateway',  name: '¿Aprobado?',            col: 3 },
        { id: 't3',  type: 'userTask',          name: 'Asignar PM y Equipo',   col: 4 },
        { id: 't4',  type: 'serviceTask',       name: 'Crear en Sistema',      col: 5 },
        { id: 't5',  type: 'userTask',          name: 'Reunión de Kickoff',    col: 6 },
        { id: 'en1', type: 'endEvent',          name: 'Proyecto Activo',       col: 7 },
        { id: 'en2', type: 'endEvent',          name: 'Rechazado',             col: 4, row: 1 },
      ],
      [
        ['st', 't1'], ['t1', 't2'], ['t2', 'gw1'],
        ['gw1', 't3', 'Sí'], ['gw1', 'en2', 'No'],
        ['t3', 't4'], ['t4', 't5'], ['t5', 'en1'],
      ]),
  },
  {
    id: 'sprint_planning',
    category: 'proyectos',
    name: 'Planificación de Sprint',
    description: 'Proceso para planificar y arrancar un nuevo sprint en proyectos ágiles.',
    owner: 'Scrum Master / PM',
    sla: '1 día hábil',
    steps: ['Revisar backlog','Seleccionar items','Estimar tareas','Asignar responsables','Definir objetivo','Iniciar sprint'],
    bpmn: buildBpmn('sprint_planning', 'Planificación de Sprint',
      [
        { id: 'st',  type: 'startEvent',      name: 'Inicio Sprint',         col: 0 },
        { id: 't1',  type: 'userTask',         name: 'Revisar Backlog',       col: 1 },
        { id: 't2',  type: 'userTask',         name: 'Seleccionar Items',     col: 2 },
        { id: 't3',  type: 'userTask',         name: 'Estimar Tareas',        col: 3 },
        { id: 'gw1', type: 'parallelGateway',  name: '',                      col: 4 },
        { id: 't4',  type: 'userTask',         name: 'Asignar Responsables',  col: 5 },
        { id: 't5',  type: 'userTask',         name: 'Definir Objetivo',      col: 5, row: 1 },
        { id: 'gw2', type: 'parallelGateway',  name: '',                      col: 6 },
        { id: 't6',  type: 'serviceTask',      name: 'Crear Sprint',          col: 7 },
        { id: 'en',  type: 'endEvent',         name: 'Sprint Activo',         col: 8 },
      ],
      [
        ['st','t1'], ['t1','t2'], ['t2','t3'], ['t3','gw1'],
        ['gw1','t4'], ['gw1','t5'],
        ['t4','gw2'], ['t5','gw2'],
        ['gw2','t6'], ['t6','en'],
      ]),
  },
  {
    id: 'task_lifecycle',
    category: 'proyectos',
    name: 'Ciclo de Vida de Tarea',
    description: 'Flujo completo desde la creación de una tarea hasta su cierre y verificación.',
    owner: 'Miembro del equipo',
    sla: 'Según estimación',
    steps: ['Crear tarea','Asignar','En progreso','Revisión / QA','Aprobado','Cerrado'],
    bpmn: buildBpmn('task_lifecycle', 'Ciclo de Vida de Tarea',
      [
        { id: 'st',  type: 'startEvent',       name: 'Nueva Tarea',           col: 0 },
        { id: 't1',  type: 'userTask',          name: 'Asignar Responsable',   col: 1 },
        { id: 't2',  type: 'userTask',          name: 'Desarrollar / Ejecutar',col: 2 },
        { id: 'gw1', type: 'exclusiveGateway',  name: '¿Revisión?',            col: 3 },
        { id: 't3',  type: 'userTask',          name: 'Code Review / QA',      col: 4 },
        { id: 'gw2', type: 'exclusiveGateway',  name: '¿OK?',                  col: 5 },
        { id: 't4',  type: 'userTask',          name: 'Corregir',              col: 4, row: 1 },
        { id: 'en',  type: 'endEvent',          name: 'Tarea Cerrada',         col: 6 },
      ],
      [
        ['st','t1'], ['t1','t2'], ['t2','gw1'],
        ['gw1','t3','Sí'], ['gw1','en','No'],
        ['t3','gw2'],
        ['gw2','en','Aprobado'], ['gw2','t4','Rechazado'],
        ['t4','t3'],
      ]),
  },
  {
    id: 'project_closure',
    category: 'proyectos',
    name: 'Cierre de Proyecto',
    description: 'Proceso de entrega final, aceptación del cliente, facturación y archivado del proyecto.',
    owner: 'Project Manager',
    sla: '5 días hábiles',
    steps: ['Completar entregables','Revisión interna QA','Presentar al cliente','Obtener aceptación','Emitir factura final','Cerrar proyecto','Archivar'],
    bpmn: buildBpmn('project_closure', 'Cierre de Proyecto',
      [
        { id: 'st',  type: 'startEvent',       name: 'Inicio Cierre',         col: 0 },
        { id: 't1',  type: 'userTask',          name: 'Completar Entregables', col: 1 },
        { id: 't2',  type: 'userTask',          name: 'Revisión QA Interna',   col: 2 },
        { id: 'gw1', type: 'exclusiveGateway',  name: '¿Calidad OK?',          col: 3 },
        { id: 't3',  type: 'userTask',          name: 'Presentar a Cliente',   col: 4 },
        { id: 'gw2', type: 'exclusiveGateway',  name: '¿Aceptado?',            col: 5 },
        { id: 't4',  type: 'serviceTask',       name: 'Factura Final',         col: 6 },
        { id: 't5',  type: 'serviceTask',       name: 'Cerrar y Archivar',     col: 7 },
        { id: 'en',  type: 'endEvent',          name: 'Proyecto Cerrado',      col: 8 },
        { id: 'tc1', type: 'userTask',          name: 'Corregir Defectos',     col: 3, row: 1 },
        { id: 'tc2', type: 'userTask',          name: 'Revisar Observaciones', col: 5, row: 1 },
      ],
      [
        ['st','t1'], ['t1','t2'], ['t2','gw1'],
        ['gw1','t3','Sí'], ['gw1','tc1','No'],
        ['tc1','t2'],
        ['t3','gw2'],
        ['gw2','t4','Aceptado'], ['gw2','tc2','Observaciones'],
        ['tc2','t3'],
        ['t4','t5'], ['t5','en'],
      ]),
  },
  {
    id: 'epic_management',
    category: 'proyectos',
    name: 'Gestión de Épicas',
    description: 'Proceso de definición, descomposición y seguimiento de épicas en el backlog.',
    owner: 'Product Owner / PM',
    sla: 'Continuo',
    steps: ['Identificar épica','Definir criterios de aceptación','Descomponer en historias','Priorizar en backlog','Asignar a sprints','Seguimiento y cierre'],
    bpmn: buildBpmn('epic_management', 'Gestión de Épicas',
      [
        { id: 'st', type: 'startEvent',      name: 'Nueva Épica',             col: 0 },
        { id: 't1', type: 'userTask',         name: 'Definir Criterios',       col: 1 },
        { id: 't2', type: 'userTask',         name: 'Descomponer en Historias',col: 2 },
        { id: 't3', type: 'userTask',         name: 'Estimar y Priorizar',     col: 3 },
        { id: 't4', type: 'serviceTask',      name: 'Asignar a Sprint',        col: 4 },
        { id: 't5', type: 'userTask',         name: 'Seguimiento',             col: 5 },
        { id: 'gw1',type: 'exclusiveGateway', name: '¿Completada?',            col: 6 },
        { id: 'en', type: 'endEvent',         name: 'Épica Cerrada',           col: 7 },
      ],
      [
        ['st','t1'],['t1','t2'],['t2','t3'],['t3','t4'],['t4','t5'],['t5','gw1'],
        ['gw1','en','Sí'], ['gw1','t4','No'],
      ]),
  },

  // ── FINANZAS ─────────────────────────────────────────────────────────────
  {
    id: 'invoicing',
    category: 'finanzas',
    name: 'Generación y Cobro de Factura',
    description: 'Proceso de creación, aprobación, envío y cobro de facturas a clientes.',
    owner: 'Finance / PM',
    sla: '2 días para emitir',
    steps: ['Revisar horas y gastos','Generar borrador','Revisión interna','Aprobar','Enviar a cliente','Registrar pago','Cerrar'],
    bpmn: buildBpmn('invoicing', 'Generación y Cobro de Factura',
      [
        { id: 'st',  type: 'startEvent',       name: 'Inicio Facturación',     col: 0 },
        { id: 't1',  type: 'serviceTask',       name: 'Revisar Horas/Gastos',   col: 1 },
        { id: 't2',  type: 'serviceTask',       name: 'Generar Borrador',       col: 2 },
        { id: 't3',  type: 'userTask',          name: 'Revisión Interna',       col: 3 },
        { id: 'gw1', type: 'exclusiveGateway',  name: '¿Aprobada?',             col: 4 },
        { id: 't4',  type: 'serviceTask',       name: 'Enviar a Cliente',       col: 5 },
        { id: 'gw2', type: 'exclusiveGateway',  name: '¿Pagada?',               col: 6 },
        { id: 't5',  type: 'serviceTask',       name: 'Registrar Pago',         col: 7 },
        { id: 'en',  type: 'endEvent',          name: 'Factura Cobrada',        col: 8 },
        { id: 'tc1', type: 'userTask',          name: 'Corregir Factura',       col: 4, row: 1 },
        { id: 'tc2', type: 'userTask',          name: 'Enviar Recordatorio',    col: 6, row: 1 },
      ],
      [
        ['st','t1'],['t1','t2'],['t2','t3'],['t3','gw1'],
        ['gw1','t4','Sí'], ['gw1','tc1','No'],
        ['tc1','t3'],
        ['t4','gw2'],
        ['gw2','t5','Pagada'], ['gw2','tc2','Pendiente'],
        ['tc2','t4'],
        ['t5','en'],
      ]),
  },
  {
    id: 'expense_approval',
    category: 'finanzas',
    name: 'Aprobación de Gastos',
    description: 'Registro, validación y reembolso de gastos por parte de empleados.',
    owner: 'Finance / Manager',
    sla: '3 días hábiles',
    steps: ['Registrar gasto','Adjuntar justificante','Enviar a manager','Aprobar/Rechazar','Finance procesa','Reembolsar'],
    bpmn: buildBpmn('expense_approval', 'Aprobación de Gastos',
      [
        { id: 'st',  type: 'startEvent',       name: 'Empleado\nRegistra Gasto', col: 0 },
        { id: 't1',  type: 'userTask',          name: 'Adjuntar Justificante',   col: 1 },
        { id: 't2',  type: 'userTask',          name: 'Enviar a Manager',        col: 2 },
        { id: 'gw1', type: 'exclusiveGateway',  name: '¿Aprobado?',              col: 3 },
        { id: 't3',  type: 'userTask',          name: 'Finance Procesa',         col: 4 },
        { id: 't4',  type: 'serviceTask',       name: 'Tramitar Reembolso',      col: 5 },
        { id: 'en1', type: 'endEvent',          name: 'Reembolsado',             col: 6 },
        { id: 'en2', type: 'endEvent',          name: 'Rechazado',               col: 4, row: 1 },
      ],
      [
        ['st','t1'],['t1','t2'],['t2','gw1'],
        ['gw1','t3','Sí'], ['gw1','en2','No'],
        ['t3','t4'],['t4','en1'],
      ]),
  },
  {
    id: 'budget_management',
    category: 'finanzas',
    name: 'Gestión de Presupuesto de Proyecto',
    description: 'Definición, aprobación y seguimiento del presupuesto de un proyecto.',
    owner: 'Finance / PM',
    sla: '5 días hábiles',
    steps: ['Definir presupuesto','Revisión PM','Aprobación Dirección','Activar','Monitorear ejecución','Alerta desviación','Revisar y ajustar'],
    bpmn: buildBpmn('budget_management', 'Gestión de Presupuesto',
      [
        { id: 'st',  type: 'startEvent',       name: 'Solicitar Presupuesto', col: 0 },
        { id: 't1',  type: 'userTask',          name: 'Definir Partidas',      col: 1 },
        { id: 't2',  type: 'userTask',          name: 'Revisión PM',           col: 2 },
        { id: 'gw1', type: 'exclusiveGateway',  name: '¿Aprobado?',            col: 3 },
        { id: 't3',  type: 'serviceTask',       name: 'Activar Presupuesto',   col: 4 },
        { id: 't4',  type: 'serviceTask',       name: 'Monitorear Ejecución',  col: 5 },
        { id: 'gw2', type: 'exclusiveGateway',  name: '¿Desviación?',          col: 6 },
        { id: 'en',  type: 'endEvent',          name: 'Presupuesto Cerrado',   col: 7 },
        { id: 'ta',  type: 'userTask',          name: 'Revisar y Ajustar',     col: 6, row: 1 },
      ],
      [
        ['st','t1'],['t1','t2'],['t2','gw1'],
        ['gw1','t3','Aprobado'], ['gw1','t2','Revisar'],
        ['t3','t4'],['t4','gw2'],
        ['gw2','en','No'], ['gw2','ta','Sí'],
        ['ta','t4'],
      ]),
  },
  {
    id: 'contract_management',
    category: 'finanzas',
    name: 'Gestión de Contratos',
    description: 'Proceso de creación, negociación, firma y seguimiento de contratos con clientes.',
    owner: 'Legal / PM',
    sla: '10 días hábiles',
    steps: ['Crear borrador','Revisión legal','Enviar al cliente','Negociación','Firma electrónica','Activar contrato','Seguimiento hitos'],
    bpmn: buildBpmn('contract_management', 'Gestión de Contratos',
      [
        { id: 'st',  type: 'startEvent',       name: 'Nuevo Contrato',          col: 0 },
        { id: 't1',  type: 'userTask',          name: 'Redactar Borrador',       col: 1 },
        { id: 't2',  type: 'userTask',          name: 'Revisión Legal/PM',       col: 2 },
        { id: 't3',  type: 'userTask',          name: 'Enviar a Cliente',        col: 3 },
        { id: 'gw1', type: 'exclusiveGateway',  name: '¿Firma OK?',              col: 4 },
        { id: 't4',  type: 'userTask',          name: 'Negociación',             col: 4, row: 1 },
        { id: 't5',  type: 'serviceTask',       name: 'Firma Electrónica',       col: 5 },
        { id: 't6',  type: 'serviceTask',       name: 'Activar Contrato',        col: 6 },
        { id: 'en',  type: 'endEvent',          name: 'Contrato Activo',         col: 7 },
      ],
      [
        ['st','t1'],['t1','t2'],['t2','t3'],['t3','gw1'],
        ['gw1','t5','Aceptado'], ['gw1','t4','Modificaciones'],
        ['t4','t3'],
        ['t5','t6'],['t6','en'],
      ]),
  },

  // ── RRHH & RECURSOS ──────────────────────────────────────────────────────
  {
    id: 'timesheet_approval',
    category: 'rrhh',
    name: 'Aprobación de Hoja de Tiempo',
    description: 'Proceso de registro, revisión y aprobación de horas trabajadas por empleados.',
    owner: 'Manager / Finance',
    sla: '2 días hábiles',
    steps: ['Registrar horas','Enviar hoja de tiempo','Manager revisa','Aprobar/Rechazar','Procesar para nómina/billing'],
    bpmn: buildBpmn('timesheet_approval', 'Aprobación de Hoja de Tiempo',
      [
        { id: 'st',  type: 'startEvent',       name: 'Empleado Registra Horas', col: 0 },
        { id: 't1',  type: 'serviceTask',       name: 'Completar Timesheet',     col: 1 },
        { id: 't2',  type: 'userTask',          name: 'Enviar para Aprobación',  col: 2 },
        { id: 't3',  type: 'userTask',          name: 'Manager Revisa',          col: 3 },
        { id: 'gw1', type: 'exclusiveGateway',  name: '¿Aprobado?',              col: 4 },
        { id: 't4',  type: 'serviceTask',       name: 'Enviar a Nómina/Billing', col: 5 },
        { id: 'en1', type: 'endEvent',          name: 'Horas Procesadas',        col: 6 },
        { id: 'tc',  type: 'userTask',          name: 'Corregir Horas',          col: 4, row: 1 },
      ],
      [
        ['st','t1'],['t1','t2'],['t2','t3'],['t3','gw1'],
        ['gw1','t4','Sí'], ['gw1','tc','No'],
        ['tc','t2'],
        ['t4','en1'],
      ]),
  },
  {
    id: 'absence_request',
    category: 'rrhh',
    name: 'Solicitud de Ausencia / Vacaciones',
    description: 'Proceso de solicitud, aprobación y registro de ausencias del empleado.',
    owner: 'RRHH / Manager',
    sla: '2 días hábiles',
    steps: ['Solicitar ausencia','Manager revisa','Verificar disponibilidad','Aprobar/Rechazar','Actualizar calendario','Notificar'],
    bpmn: buildBpmn('absence_request', 'Solicitud de Ausencia',
      [
        { id: 'st',  type: 'startEvent',       name: 'Empleado Solicita',      col: 0 },
        { id: 't1',  type: 'userTask',          name: 'Verificar Disponibilidad',col: 1 },
        { id: 't2',  type: 'userTask',          name: 'Manager Revisa',         col: 2 },
        { id: 'gw1', type: 'exclusiveGateway',  name: '¿Aprobada?',             col: 3 },
        { id: 't3',  type: 'serviceTask',       name: 'Registrar en RRHH',      col: 4 },
        { id: 't4',  type: 'serviceTask',       name: 'Actualizar Calendario',  col: 5 },
        { id: 't5',  type: 'serviceTask',       name: 'Notificar Equipo',       col: 6 },
        { id: 'en1', type: 'endEvent',          name: 'Ausencia Aprobada',      col: 7 },
        { id: 'en2', type: 'endEvent',          name: 'Solicitud Rechazada',    col: 4, row: 1 },
      ],
      [
        ['st','t1'],['t1','t2'],['t2','gw1'],
        ['gw1','t3','Sí'], ['gw1','en2','No'],
        ['t3','t4'],['t4','t5'],['t5','en1'],
      ]),
  },
  {
    id: 'resource_allocation',
    category: 'rrhh',
    name: 'Asignación de Recursos a Proyecto',
    description: 'Proceso para solicitar, verificar disponibilidad y asignar recursos a un proyecto.',
    owner: 'PM / Resource Manager',
    sla: '3 días hábiles',
    steps: ['PM solicita recurso','Verificar disponibilidad','Revisar capacidad','Asignar al proyecto','Notificar al recurso','Confirmar'],
    bpmn: buildBpmn('resource_allocation', 'Asignación de Recursos',
      [
        { id: 'st',  type: 'startEvent',       name: 'PM Solicita Recurso',    col: 0 },
        { id: 't1',  type: 'serviceTask',       name: 'Verificar Disponibilidad',col: 1 },
        { id: 'gw1', type: 'exclusiveGateway',  name: '¿Disponible?',           col: 2 },
        { id: 't2',  type: 'userTask',          name: 'Confirmar Asignación',   col: 3 },
        { id: 't3',  type: 'serviceTask',       name: 'Registrar en Sistema',   col: 4 },
        { id: 't4',  type: 'serviceTask',       name: 'Notificar al Recurso',   col: 5 },
        { id: 'en1', type: 'endEvent',          name: 'Recurso Asignado',       col: 6 },
        { id: 'ta',  type: 'userTask',          name: 'Buscar Alternativa',     col: 2, row: 1 },
        { id: 'en2', type: 'endEvent',          name: 'Sin Disponibilidad',     col: 3, row: 1 },
      ],
      [
        ['st','t1'],['t1','gw1'],
        ['gw1','t2','Sí'], ['gw1','ta','No'],
        ['ta','en2'],
        ['t2','t3'],['t3','t4'],['t4','en1'],
      ]),
  },
  {
    id: 'performance_review',
    category: 'rrhh',
    name: 'Evaluación de Desempeño',
    description: 'Ciclo de evaluación, autoevaluación y planificación de desarrollo del empleado.',
    owner: 'RRHH / Manager',
    sla: 'Anual / Semestral',
    steps: ['Iniciar ciclo evaluación','Autoevaluación empleado','Evaluación manager','Calibración RRHH','Sesión feedback 1:1','Definir plan desarrollo','Aprobar y archivar'],
    bpmn: buildBpmn('performance_review', 'Evaluación de Desempeño',
      [
        { id: 'st', type: 'startEvent',     name: 'Inicio Ciclo',           col: 0 },
        { id: 't1', type: 'userTask',        name: 'Autoevaluación',         col: 1 },
        { id: 't2', type: 'userTask',        name: 'Evaluación Manager',     col: 2 },
        { id: 't3', type: 'userTask',        name: 'Calibración RRHH',       col: 3 },
        { id: 't4', type: 'userTask',        name: 'Sesión Feedback 1:1',    col: 4 },
        { id: 't5', type: 'userTask',        name: 'Plan de Desarrollo',     col: 5 },
        { id: 't6', type: 'serviceTask',     name: 'Archivar Evaluación',    col: 6 },
        { id: 'en', type: 'endEvent',        name: 'Evaluación Completada',  col: 7 },
      ],
      [['st','t1'],['t1','t2'],['t2','t3'],['t3','t4'],['t4','t5'],['t5','t6'],['t6','en']]),
  },

  // ── SERVICE DESK ──────────────────────────────────────────────────────────
  {
    id: 'incident_management',
    category: 'servicedesk',
    name: 'Gestión de Incidentes',
    description: 'Proceso ITIL para la detección, clasificación, diagnóstico y resolución de incidentes.',
    owner: 'Service Desk / L1-L3',
    sla: 'P1: 4h | P2: 8h | P3: 24h',
    steps: ['Detectar/Reportar','Registrar incidente','Clasificar y priorizar','Asignar técnico','Diagnosticar','Resolver','Notificar usuario','Encuesta satisfacción','Cerrar'],
    bpmn: buildBpmn('incident_management', 'Gestión de Incidentes',
      [
        { id: 'st',  type: 'startEvent',       name: 'Incidente Detectado',    col: 0 },
        { id: 't1',  type: 'serviceTask',       name: 'Registrar Incidente',    col: 1 },
        { id: 't2',  type: 'userTask',          name: 'Clasificar y Priorizar', col: 2 },
        { id: 't3',  type: 'userTask',          name: 'Asignar Técnico L1',     col: 3 },
        { id: 'gw1', type: 'exclusiveGateway',  name: '¿L1 Resuelve?',          col: 4 },
        { id: 't4',  type: 'userTask',          name: 'Escalar a L2/L3',        col: 4, row: 1 },
        { id: 't5',  type: 'userTask',          name: 'Resolver Incidente',     col: 5 },
        { id: 't6',  type: 'serviceTask',       name: 'Documentar Solución',    col: 6 },
        { id: 't7',  type: 'serviceTask',       name: 'Notificar Usuario',      col: 7 },
        { id: 't8',  type: 'userTask',          name: 'Encuesta Satisfacción',  col: 8 },
        { id: 'en',  type: 'endEvent',          name: 'Incidente Cerrado',      col: 9 },
      ],
      [
        ['st','t1'],['t1','t2'],['t2','t3'],['t3','gw1'],
        ['gw1','t5','Sí'], ['gw1','t4','No'],
        ['t4','t5'],
        ['t5','t6'],['t6','t7'],['t7','t8'],['t8','en'],
      ]),
  },
  {
    id: 'service_request',
    category: 'servicedesk',
    name: 'Solicitud de Servicio',
    description: 'Proceso de atención a solicitudes estándar del catálogo de servicios.',
    owner: 'Service Desk',
    sla: '8-48h según tipo',
    steps: ['Recibir solicitud','Categorizar','Verificar aprobación','Asignar','Ejecutar','Verificar calidad','Confirmar con usuario','Cerrar'],
    bpmn: buildBpmn('service_request', 'Solicitud de Servicio',
      [
        { id: 'st',  type: 'startEvent',       name: 'Solicitud Recibida',     col: 0 },
        { id: 't1',  type: 'serviceTask',       name: 'Categorizar Solicitud',  col: 1 },
        { id: 'gw1', type: 'exclusiveGateway',  name: '¿Requiere Aprobación?',  col: 2 },
        { id: 't2',  type: 'userTask',          name: 'Aprobar Solicitud',      col: 2, row: 1 },
        { id: 't3',  type: 'userTask',          name: 'Asignar Técnico',        col: 3 },
        { id: 't4',  type: 'userTask',          name: 'Ejecutar Servicio',      col: 4 },
        { id: 't5',  type: 'userTask',          name: 'Verificar Calidad',      col: 5 },
        { id: 't6',  type: 'serviceTask',       name: 'Confirmar con Usuario',  col: 6 },
        { id: 'en',  type: 'endEvent',          name: 'Solicitud Cerrada',      col: 7 },
      ],
      [
        ['st','t1'],['t1','gw1'],
        ['gw1','t3','No'], ['gw1','t2','Sí'],
        ['t2','t3'],
        ['t3','t4'],['t4','t5'],['t5','t6'],['t6','en'],
      ]),
  },
  {
    id: 'change_management',
    category: 'servicedesk',
    name: 'Gestión de Cambios (CAB)',
    description: 'Proceso ITIL para la solicitud, evaluación, aprobación e implementación de cambios en TI.',
    owner: 'Change Manager / CAB',
    sla: 'Normal: 5 días | Urgente: 24h',
    steps: ['Crear RFC','Clasificar cambio','Análisis de impacto y riesgo','Presentar al CAB','Aprobación CAB','Planificar implementación','Implementar','Verificar','Post-implementación','Cerrar RFC'],
    bpmn: buildBpmn('change_management', 'Gestión de Cambios',
      [
        { id: 'st',  type: 'startEvent',       name: 'Crear RFC',              col: 0 },
        { id: 't1',  type: 'userTask',          name: 'Clasificar Cambio',      col: 1 },
        { id: 't2',  type: 'userTask',          name: 'Análisis Impacto/Riesgo',col: 2 },
        { id: 't3',  type: 'userTask',          name: 'Presentar a CAB',        col: 3 },
        { id: 'gw1', type: 'exclusiveGateway',  name: '¿CAB Aprueba?',          col: 4 },
        { id: 't4',  type: 'userTask',          name: 'Planificar Implementación',col: 5 },
        { id: 't5',  type: 'userTask',          name: 'Implementar Cambio',     col: 6 },
        { id: 'gw2', type: 'exclusiveGateway',  name: '¿Éxito?',                col: 7 },
        { id: 't6',  type: 'serviceTask',       name: 'Revisar PIR',            col: 8 },
        { id: 'en1', type: 'endEvent',          name: 'RFC Cerrada',            col: 9 },
        { id: 'en2', type: 'endEvent',          name: 'RFC Rechazada',          col: 5, row: 1 },
        { id: 'rb',  type: 'userTask',          name: 'Rollback',               col: 7, row: 1 },
      ],
      [
        ['st','t1'],['t1','t2'],['t2','t3'],['t3','gw1'],
        ['gw1','t4','Aprobado'], ['gw1','en2','Rechazado'],
        ['t4','t5'],['t5','gw2'],
        ['gw2','t6','Éxito'], ['gw2','rb','Fallo'],
        ['rb','t5'],
        ['t6','en1'],
      ]),
  },
  {
    id: 'problem_management',
    category: 'servicedesk',
    name: 'Gestión de Problemas',
    description: 'Proceso para identificar la causa raíz de incidentes recurrentes e implementar soluciones permanentes.',
    owner: 'Problem Manager / L3',
    sla: 'Variable según severidad',
    steps: ['Identificar problema','Registrar y clasificar','Asignar investigador','Análisis causa raíz','Implementar workaround','Desarrollar fix permanente','Verificar solución','Cerrar problema'],
    bpmn: buildBpmn('problem_management', 'Gestión de Problemas',
      [
        { id: 'st', type: 'startEvent',     name: 'Problema Identificado',   col: 0 },
        { id: 't1', type: 'serviceTask',     name: 'Registrar y Clasificar',  col: 1 },
        { id: 't2', type: 'userTask',        name: 'Asignar Investigador',    col: 2 },
        { id: 't3', type: 'userTask',        name: 'Análisis Causa Raíz',     col: 3 },
        { id: 't4', type: 'serviceTask',     name: 'Implementar Workaround',  col: 4 },
        { id: 't5', type: 'userTask',        name: 'Desarrollar Fix',         col: 5 },
        { id: 'gw1',type: 'exclusiveGateway',name: '¿Resuelto?',              col: 6 },
        { id: 't6', type: 'serviceTask',     name: 'Documentar y Cerrar',     col: 7 },
        { id: 'en', type: 'endEvent',        name: 'Problema Cerrado',        col: 8 },
      ],
      [
        ['st','t1'],['t1','t2'],['t2','t3'],['t3','t4'],['t4','t5'],['t5','gw1'],
        ['gw1','t6','Sí'], ['gw1','t5','No'],
        ['t6','en'],
      ]),
  },

  // ── CRM & VENTAS ──────────────────────────────────────────────────────────
  {
    id: 'sales_process',
    category: 'crm',
    name: 'Proceso de Ventas (Pipeline)',
    description: 'Desde la identificación de una oportunidad hasta el cierre del contrato y arranque del proyecto.',
    owner: 'Comercial / Account Manager',
    sla: 'Variable',
    steps: ['Lead identificado','Calificar lead','Reunión descubrimiento','Elaborar propuesta','Presentar propuesta','Negociación','Cerrar contrato','Pasar a entrega'],
    bpmn: buildBpmn('sales_process', 'Proceso de Ventas',
      [
        { id: 'st',  type: 'startEvent',       name: 'Lead Identificado',      col: 0 },
        { id: 'gw1', type: 'exclusiveGateway',  name: '¿Calificado?',           col: 1 },
        { id: 't1',  type: 'userTask',          name: 'Reunión Descubrimiento', col: 2 },
        { id: 't2',  type: 'userTask',          name: 'Elaborar Propuesta',     col: 3 },
        { id: 't3',  type: 'userTask',          name: 'Presentar Propuesta',    col: 4 },
        { id: 'gw2', type: 'exclusiveGateway',  name: '¿Interesado?',           col: 5 },
        { id: 't4',  type: 'userTask',          name: 'Negociación',            col: 6 },
        { id: 'gw3', type: 'exclusiveGateway',  name: '¿Cerrado?',              col: 7 },
        { id: 't5',  type: 'serviceTask',       name: 'Firmar Contrato',        col: 8 },
        { id: 'en1', type: 'endEvent',          name: 'Venta Ganada',           col: 9 },
        { id: 'en2', type: 'endEvent',          name: 'Lead Descartado',        col: 2, row: 1 },
        { id: 'en3', type: 'endEvent',          name: 'Venta Perdida',          col: 6, row: 1 },
      ],
      [
        ['st','gw1'],
        ['gw1','t1','Sí'], ['gw1','en2','No'],
        ['t1','t2'],['t2','t3'],['t3','gw2'],
        ['gw2','t4','Sí'], ['gw2','en3','No'],
        ['t4','gw3'],
        ['gw3','t5','Sí'], ['gw3','t4','Renegociar'],
        ['t5','en1'],
      ]),
  },
  {
    id: 'client_onboarding',
    category: 'crm',
    name: 'Onboarding de Cliente',
    description: 'Proceso de incorporación de un nuevo cliente tras la firma del contrato.',
    owner: 'Customer Success / PM',
    sla: '5 días hábiles',
    steps: ['Contrato firmado','Kickoff call','Configurar entorno','Sesión de formación','Asignar CSM','Go Live','Check-in 30 días'],
    bpmn: buildBpmn('client_onboarding', 'Onboarding de Cliente',
      [
        { id: 'st', type: 'startEvent',  name: 'Contrato Firmado',          col: 0 },
        { id: 't1', type: 'userTask',     name: 'Kickoff Call',              col: 1 },
        { id: 't2', type: 'serviceTask',  name: 'Configurar Acceso',         col: 2 },
        { id: 't3', type: 'userTask',     name: 'Sesión de Formación',       col: 3 },
        { id: 't4', type: 'userTask',     name: 'Asignar CSM',               col: 4 },
        { id: 't5', type: 'serviceTask',  name: 'Go Live',                   col: 5 },
        { id: 't6', type: 'userTask',     name: 'Check-in 30 días',          col: 6 },
        { id: 'en', type: 'endEvent',     name: 'Cliente Activo',            col: 7 },
      ],
      [['st','t1'],['t1','t2'],['t2','t3'],['t3','t4'],['t4','t5'],['t5','t6'],['t6','en']]),
  },

  // ── ADMINISTRACIÓN ────────────────────────────────────────────────────────
  {
    id: 'user_onboarding',
    category: 'admin',
    name: 'Onboarding de Usuario (Alta)',
    description: 'Proceso de creación de cuenta, asignación de permisos y formación de nuevos usuarios.',
    owner: 'IT / RRHH',
    sla: '1 día hábil',
    steps: ['Solicitar alta','Aprobar acceso','Crear cuenta','Asignar roles y permisos','Enviar credenciales','Sesión formación','Usuario activo'],
    bpmn: buildBpmn('user_onboarding', 'Onboarding de Usuario',
      [
        { id: 'st',  type: 'startEvent',       name: 'Solicitar Alta',         col: 0 },
        { id: 'gw1', type: 'exclusiveGateway',  name: '¿Aprobado?',             col: 1 },
        { id: 't1',  type: 'serviceTask',       name: 'Crear Cuenta',           col: 2 },
        { id: 't2',  type: 'serviceTask',       name: 'Asignar Roles/Permisos', col: 3 },
        { id: 't3',  type: 'serviceTask',       name: 'Enviar Credenciales',    col: 4 },
        { id: 't4',  type: 'userTask',          name: 'Sesión de Formación',    col: 5 },
        { id: 'en1', type: 'endEvent',          name: 'Usuario Activo',         col: 6 },
        { id: 'en2', type: 'endEvent',          name: 'Solicitud Rechazada',    col: 2, row: 1 },
      ],
      [
        ['st','gw1'],
        ['gw1','t1','Aprobado'], ['gw1','en2','Rechazado'],
        ['t1','t2'],['t2','t3'],['t3','t4'],['t4','en1'],
      ]),
  },
  {
    id: 'document_approval',
    category: 'admin',
    name: 'Aprobación y Publicación de Documentos',
    description: 'Proceso de creación, revisión, aprobación y publicación de documentos corporativos.',
    owner: 'Owner del documento',
    sla: '3 días hábiles',
    steps: ['Crear documento','Revisión colaborativa','Enviar para aprobación','Aprobar/Rechazar','Publicar','Notificar destinatarios'],
    bpmn: buildBpmn('document_approval', 'Aprobación de Documentos',
      [
        { id: 'st',  type: 'startEvent',       name: 'Crear Documento',        col: 0 },
        { id: 't1',  type: 'userTask',          name: 'Revisión Colaborativa',  col: 1 },
        { id: 't2',  type: 'userTask',          name: 'Enviar para Aprobación', col: 2 },
        { id: 'gw1', type: 'exclusiveGateway',  name: '¿Aprobado?',             col: 3 },
        { id: 't3',  type: 'serviceTask',       name: 'Publicar Documento',     col: 4 },
        { id: 't4',  type: 'serviceTask',       name: 'Notificar Destinatarios',col: 5 },
        { id: 'en1', type: 'endEvent',          name: 'Documento Publicado',    col: 6 },
        { id: 'tc',  type: 'userTask',          name: 'Incorporar Cambios',     col: 3, row: 1 },
      ],
      [
        ['st','t1'],['t1','t2'],['t2','gw1'],
        ['gw1','t3','Aprobado'], ['gw1','tc','Revisiones'],
        ['tc','t1'],
        ['t3','t4'],['t4','en1'],
      ]),
  },
  {
    id: 'risk_management',
    category: 'admin',
    name: 'Gestión de Riesgos de Proyecto',
    description: 'Identificación, evaluación, mitigación y seguimiento continuo de riesgos en proyectos.',
    owner: 'PM / Risk Manager',
    sla: 'Continuo / mensual',
    steps: ['Identificar riesgo','Evaluar probabilidad e impacto','Clasificar (alto/medio/bajo)','Definir mitigación','Asignar responsable','Monitorear','Cerrar o escalar'],
    bpmn: buildBpmn('risk_management', 'Gestión de Riesgos',
      [
        { id: 'st',  type: 'startEvent',       name: 'Riesgo Identificado',    col: 0 },
        { id: 't1',  type: 'userTask',          name: 'Evaluar P x I',          col: 1 },
        { id: 'gw1', type: 'exclusiveGateway',  name: 'Nivel de Riesgo',        col: 2 },
        { id: 't2',  type: 'userTask',          name: 'Plan Mitigación Alto',   col: 3 },
        { id: 't3',  type: 'userTask',          name: 'Plan Mitigación Medio',  col: 3, row: 1 },
        { id: 't4',  type: 'userTask',          name: 'Monitorear',             col: 4 },
        { id: 'gw2', type: 'exclusiveGateway',  name: '¿Materializado?',        col: 5 },
        { id: 't5',  type: 'userTask',          name: 'Activar Plan Respuesta', col: 5, row: 1 },
        { id: 'en',  type: 'endEvent',          name: 'Riesgo Cerrado',         col: 6 },
      ],
      [
        ['st','t1'],['t1','gw1'],
        ['gw1','t2','Alto'], ['gw1','t3','Medio'],
        ['t2','t4'], ['t3','t4'],
        ['t4','gw2'],
        ['gw2','en','No'], ['gw2','t5','Sí'],
        ['t5','t4'],
      ]),
  },

  // ── PROYECTOS (adicionales) ───────────────────────────────────────────────
  {
    id: 'sprint_review',
    category: 'proyectos',
    name: 'Sprint Review y Retrospectiva',
    description: 'Revisión del sprint con el cliente, validación de entregables y retrospectiva del equipo.',
    owner: 'Scrum Master / PM',
    sla: 'Último día del sprint',
    steps: ['Preparar demo','Demo al cliente','Validar items','Registrar feedback','Retrospectiva interna','Definir mejoras','Actualizar backlog','Cerrar sprint'],
    bpmn: buildBpmn('sprint_review', 'Sprint Review y Retrospectiva',
      [
        { id: 'st',  type: 'startEvent',       name: 'Fin de Sprint',            col: 0 },
        { id: 't1',  type: 'userTask',          name: 'Preparar Demo',            col: 1 },
        { id: 't2',  type: 'userTask',          name: 'Demo al Cliente',          col: 2 },
        { id: 'gw1', type: 'exclusiveGateway',  name: '¿Items Aceptados?',        col: 3 },
        { id: 't3',  type: 'userTask',          name: 'Registrar Feedback',       col: 4 },
        { id: 't4',  type: 'userTask',          name: 'Retrospectiva Equipo',     col: 5 },
        { id: 't5',  type: 'userTask',          name: 'Definir Mejoras',          col: 6 },
        { id: 't6',  type: 'serviceTask',       name: 'Actualizar Backlog',       col: 7 },
        { id: 'en',  type: 'endEvent',          name: 'Sprint Cerrado',           col: 8 },
        { id: 'tc',  type: 'userTask',          name: 'Replanificar Items',       col: 3, row: 1 },
      ],
      [
        ['st','t1'],['t1','t2'],['t2','gw1'],
        ['gw1','t3','Aceptados'], ['gw1','tc','Pendientes'],
        ['tc','t6'],
        ['t3','t4'],['t4','t5'],['t5','t6'],['t6','en'],
      ]),
  },
  {
    id: 'deliverable_management',
    category: 'proyectos',
    name: 'Gestión de Entregables y Hitos',
    description: 'Proceso de definición, desarrollo, validación y entrega formal de hitos del proyecto.',
    owner: 'Project Manager',
    sla: 'Según plan de proyecto',
    steps: ['Definir entregable','Desarrollar','QA interno','Revisar QA','Presentar cliente','Aceptar hito','Registrar en sistema','Facturar hito','Actualizar proyecto','Cierre'],
    bpmn: buildBpmn('deliverable_management', 'Gestión de Entregables y Hitos',
      [
        { id: 'st',  type: 'startEvent',       name: 'Inicio Hito',              col: 0 },
        { id: 't1',  type: 'userTask',          name: 'Definir Entregable',       col: 1 },
        { id: 't2',  type: 'userTask',          name: 'Desarrollar',              col: 2 },
        { id: 't3',  type: 'userTask',          name: 'QA Interno',               col: 3 },
        { id: 'gw1', type: 'exclusiveGateway',  name: '¿Calidad OK?',             col: 4 },
        { id: 't4',  type: 'userTask',          name: 'Presentar a Cliente',      col: 5 },
        { id: 'gw2', type: 'exclusiveGateway',  name: '¿Hito Aceptado?',          col: 6 },
        { id: 't5',  type: 'serviceTask',       name: 'Registrar Hito',           col: 7 },
        { id: 't6',  type: 'serviceTask',       name: 'Trigger Facturación',      col: 8 },
        { id: 'en',  type: 'endEvent',          name: 'Hito Entregado',           col: 9 },
        { id: 'tc1', type: 'userTask',          name: 'Corregir Defectos',        col: 4, row: 1 },
        { id: 'tc2', type: 'userTask',          name: 'Revisar Observaciones',    col: 6, row: 1 },
      ],
      [
        ['st','t1'],['t1','t2'],['t2','t3'],['t3','gw1'],
        ['gw1','t4','OK'], ['gw1','tc1','Defectos'],
        ['tc1','t3'],
        ['t4','gw2'],
        ['gw2','t5','Aceptado'], ['gw2','tc2','Observaciones'],
        ['tc2','t4'],
        ['t5','t6'],['t6','en'],
      ]),
  },
  {
    id: 'uat_process',
    category: 'proyectos',
    name: 'UAT — Pruebas de Aceptación',
    description: 'Proceso de pruebas de aceptación del usuario con ciclos de detección y corrección de defectos.',
    owner: 'PM / Cliente / QA',
    sla: 'Según plan de pruebas',
    steps: ['Preparar entorno','Ejecutar casos de prueba','Detectar defectos','Priorizar defectos','Corregir','Regresar','Validar corrección','Sign-off cliente','Cierre UAT'],
    bpmn: buildBpmn('uat_process', 'UAT — Pruebas de Aceptación',
      [
        { id: 'st',  type: 'startEvent',       name: 'Inicio UAT',               col: 0 },
        { id: 't1',  type: 'userTask',          name: 'Preparar Entorno Test',    col: 1 },
        { id: 't2',  type: 'userTask',          name: 'Ejecutar Casos de Prueba', col: 2 },
        { id: 'gw1', type: 'exclusiveGateway',  name: '¿Defectos?',               col: 3 },
        { id: 't3',  type: 'userTask',          name: 'Registrar Defectos',       col: 4 },
        { id: 't4',  type: 'userTask',          name: 'Corregir Defectos',        col: 4, row: 1 },
        { id: 'gw2', type: 'exclusiveGateway',  name: '¿Todo OK?',                col: 5 },
        { id: 't5',  type: 'userTask',          name: 'Sign-off Cliente',         col: 6 },
        { id: 'en',  type: 'endEvent',          name: 'UAT Completado',           col: 7 },
      ],
      [
        ['st','t1'],['t1','t2'],['t2','gw1'],
        ['gw1','t3','Con defectos'], ['gw1','gw2','Sin defectos'],
        ['t3','t4'],['t4','gw2'],
        ['gw2','t5','Aprobado'], ['gw2','t2','Más pruebas'],
        ['t5','en'],
      ]),
  },
  {
    id: 'portfolio_review',
    category: 'proyectos',
    name: 'Portfolio Review',
    description: 'Revisión periódica del portfolio de proyectos: estado, KPIs, priorización y estrategia.',
    owner: 'PMO / Dirección',
    sla: 'Mensual / Trimestral',
    steps: ['Recopilar datos','Analizar KPIs','Reunión de revisión','Evaluar cambios','Actualizar prioridades','Comunicar decisiones','Actualizar roadmap','Cierre'],
    bpmn: buildBpmn('portfolio_review', 'Portfolio Review',
      [
        { id: 'st',  type: 'startEvent',       name: 'Inicio Review',            col: 0 },
        { id: 't1',  type: 'serviceTask',       name: 'Recopilar Datos',          col: 1 },
        { id: 't2',  type: 'serviceTask',       name: 'Analizar KPIs',            col: 2 },
        { id: 't3',  type: 'userTask',          name: 'Reunión Revisión',         col: 3 },
        { id: 'gw1', type: 'exclusiveGateway',  name: '¿Cambios Necesarios?',     col: 4 },
        { id: 't4',  type: 'userTask',          name: 'Actualizar Prioridades',   col: 5 },
        { id: 't5',  type: 'serviceTask',       name: 'Comunicar Decisiones',     col: 6 },
        { id: 't6',  type: 'serviceTask',       name: 'Actualizar Roadmap',       col: 7 },
        { id: 'en',  type: 'endEvent',          name: 'Review Completado',        col: 8 },
        { id: 'td',  type: 'userTask',          name: 'Definir Plan Cambios',     col: 4, row: 1 },
      ],
      [
        ['st','t1'],['t1','t2'],['t2','t3'],['t3','gw1'],
        ['gw1','t5','Sin cambios'], ['gw1','td','Con cambios'],
        ['td','t4'],['t4','t5'],
        ['t5','t6'],['t6','en'],
      ]),
  },

  // ── FINANZAS (adicionales) ────────────────────────────────────────────────
  {
    id: 'milestone_billing',
    category: 'finanzas',
    name: 'Facturación por Hitos',
    description: 'Proceso de facturación vinculada a la consecución y aceptación de hitos contractuales.',
    owner: 'Finance / PM',
    sla: '48h desde aceptación del hito',
    steps: ['Hito alcanzado','Validar entregable','Solicitar aceptación cliente','Generar factura','Enviar factura','Confirmar pago','Registrar ingreso','Cerrar hito'],
    bpmn: buildBpmn('milestone_billing', 'Facturación por Hitos',
      [
        { id: 'st',  type: 'startEvent',       name: 'Hito Alcanzado',           col: 0 },
        { id: 't1',  type: 'userTask',          name: 'Validar Entregable',       col: 1 },
        { id: 't2',  type: 'userTask',          name: 'Solicitar Aceptación',     col: 2 },
        { id: 'gw1', type: 'exclusiveGateway',  name: '¿Cliente Acepta?',         col: 3 },
        { id: 't3',  type: 'serviceTask',       name: 'Generar Factura',          col: 4 },
        { id: 't4',  type: 'serviceTask',       name: 'Enviar Factura',           col: 5 },
        { id: 'gw2', type: 'exclusiveGateway',  name: '¿Pagada?',                 col: 6 },
        { id: 't5',  type: 'serviceTask',       name: 'Registrar Ingreso',        col: 7 },
        { id: 'en',  type: 'endEvent',          name: 'Hito Facturado',           col: 8 },
        { id: 'tc1', type: 'userTask',          name: 'Revisar Observaciones',    col: 3, row: 1 },
        { id: 'tc2', type: 'userTask',          name: 'Gestionar Cobro',          col: 6, row: 1 },
      ],
      [
        ['st','t1'],['t1','t2'],['t2','gw1'],
        ['gw1','t3','Aceptado'], ['gw1','tc1','Observaciones'],
        ['tc1','t2'],
        ['t3','t4'],['t4','gw2'],
        ['gw2','t5','Pagada'], ['gw2','tc2','Pendiente'],
        ['tc2','t4'],
        ['t5','en'],
      ]),
  },
  {
    id: 'subcontractor_onboarding',
    category: 'finanzas',
    name: 'Onboarding y Gestión de Subcontratistas',
    description: 'Proceso de selección, due diligence, contratación y onboarding de subcontratistas.',
    owner: 'Finance / Legal / PM',
    sla: '10 días hábiles',
    steps: ['Identificar necesidad','Seleccionar candidatos','Due diligence','Aprobar proveedor','Negociar contrato','Firmar','Onboarding','Asignar trabajo'],
    bpmn: buildBpmn('subcontractor_onboarding', 'Onboarding de Subcontratistas',
      [
        { id: 'st',  type: 'startEvent',       name: 'Necesidad Identificada',   col: 0 },
        { id: 't1',  type: 'userTask',          name: 'Seleccionar Candidatos',   col: 1 },
        { id: 't2',  type: 'userTask',          name: 'Due Diligence',            col: 2 },
        { id: 'gw1', type: 'exclusiveGateway',  name: '¿Aprobado?',               col: 3 },
        { id: 't3',  type: 'userTask',          name: 'Negociar Contrato',        col: 4 },
        { id: 't4',  type: 'serviceTask',       name: 'Firma Electrónica',        col: 5 },
        { id: 't5',  type: 'userTask',          name: 'Onboarding',               col: 6 },
        { id: 'en1', type: 'endEvent',          name: 'Subcontratista Activo',    col: 7 },
        { id: 'en2', type: 'endEvent',          name: 'Proveedor Rechazado',      col: 4, row: 1 },
      ],
      [
        ['st','t1'],['t1','t2'],['t2','gw1'],
        ['gw1','t3','Aprobado'], ['gw1','en2','Rechazado'],
        ['t3','t4'],['t4','t5'],['t5','en1'],
      ]),
  },
  {
    id: 'revenue_recognition',
    category: 'finanzas',
    name: 'Reconocimiento de Ingresos',
    description: 'Proceso contable para identificar, calcular y registrar ingresos según criterios IFRS/GAAP.',
    owner: 'Finance / Controller',
    sla: 'Cierre mensual',
    steps: ['Identificar evento de ingreso','Calcular importe','Verificar criterios IFRS','Conformidad contable','Asiento contable','Revisar CFO','Cierre de periodo','Reportar'],
    bpmn: buildBpmn('revenue_recognition', 'Reconocimiento de Ingresos',
      [
        { id: 'st',  type: 'startEvent',       name: 'Evento de Ingreso',        col: 0 },
        { id: 't1',  type: 'userTask',          name: 'Identificar Ingreso',      col: 1 },
        { id: 't2',  type: 'serviceTask',       name: 'Calcular Importe',         col: 2 },
        { id: 'gw1', type: 'exclusiveGateway',  name: '¿Cumple IFRS?',            col: 3 },
        { id: 't3',  type: 'userTask',          name: 'Asiento Contable',         col: 4 },
        { id: 't4',  type: 'userTask',          name: 'Revisión CFO',             col: 5 },
        { id: 't5',  type: 'serviceTask',       name: 'Cierre de Periodo',        col: 6 },
        { id: 'en',  type: 'endEvent',          name: 'Ingreso Registrado',       col: 7 },
        { id: 'td',  type: 'userTask',          name: 'Ajustar Criterios',        col: 3, row: 1 },
      ],
      [
        ['st','t1'],['t1','t2'],['t2','gw1'],
        ['gw1','t3','Cumple'], ['gw1','td','No cumple'],
        ['td','t2'],
        ['t3','t4'],['t4','t5'],['t5','en'],
      ]),
  },

  // ── RRHH (adicionales) ────────────────────────────────────────────────────
  {
    id: 'training_request',
    category: 'rrhh',
    name: 'Solicitud y Aprobación de Formación',
    description: 'Proceso para solicitar, aprobar y registrar formaciones y certificaciones de empleados.',
    owner: 'RRHH / Manager',
    sla: '5 días hábiles',
    steps: ['Solicitar formación','Seleccionar curso','Aprobación manager','Verificar presupuesto','Inscribir','Realizar formación','Registrar certificado','Actualizar perfil'],
    bpmn: buildBpmn('training_request', 'Solicitud de Formación',
      [
        { id: 'st',  type: 'startEvent',       name: 'Empleado Solicita',        col: 0 },
        { id: 't1',  type: 'userTask',          name: 'Seleccionar Curso',        col: 1 },
        { id: 't2',  type: 'userTask',          name: 'Aprobación Manager',       col: 2 },
        { id: 'gw1', type: 'exclusiveGateway',  name: '¿Aprobado?',               col: 3 },
        { id: 't3',  type: 'userTask',          name: 'Verificar Presupuesto',    col: 4 },
        { id: 't4',  type: 'userTask',          name: 'Inscribir en Curso',       col: 5 },
        { id: 't5',  type: 'userTask',          name: 'Realizar Formación',       col: 6 },
        { id: 't6',  type: 'serviceTask',       name: 'Registrar Certificado',    col: 7 },
        { id: 'en1', type: 'endEvent',          name: 'Formación Completada',     col: 8 },
        { id: 'en2', type: 'endEvent',          name: 'Solicitud Rechazada',      col: 4, row: 1 },
      ],
      [
        ['st','t1'],['t1','t2'],['t2','gw1'],
        ['gw1','t3','Aprobado'], ['gw1','en2','Rechazado'],
        ['t3','t4'],['t4','t5'],['t5','t6'],['t6','en1'],
      ]),
  },
  {
    id: 'capacity_forecast',
    category: 'rrhh',
    name: 'Planificación y Forecast de Capacidad',
    description: 'Análisis de demanda vs capacidad del equipo y planificación de contratación o externalización.',
    owner: 'Resource Manager / PM',
    sla: 'Mensual',
    steps: ['Recopilar demanda proyectos','Calcular capacidad disponible','Análisis gap','Detectar déficit/superávit','Plan contratación/externalización','Actualizar forecast','Comunicar a dirección','Ajustar'],
    bpmn: buildBpmn('capacity_forecast', 'Forecast de Capacidad',
      [
        { id: 'st',  type: 'startEvent',       name: 'Inicio Planificación',     col: 0 },
        { id: 't1',  type: 'serviceTask',       name: 'Recopilar Demanda',        col: 1 },
        { id: 't2',  type: 'serviceTask',       name: 'Calcular Capacidad',       col: 2 },
        { id: 't3',  type: 'userTask',          name: 'Análisis de Gap',          col: 3 },
        { id: 'gw1', type: 'exclusiveGateway',  name: '¿Déficit?',                col: 4 },
        { id: 't4',  type: 'userTask',          name: 'Plan Contratación',        col: 5 },
        { id: 't5',  type: 'serviceTask',       name: 'Actualizar Forecast',      col: 6 },
        { id: 'en',  type: 'endEvent',          name: 'Forecast Actualizado',     col: 7 },
        { id: 'ts',  type: 'userTask',          name: 'Reasignar Recursos',       col: 4, row: 1 },
      ],
      [
        ['st','t1'],['t1','t2'],['t2','t3'],['t3','gw1'],
        ['gw1','t4','Déficit'], ['gw1','ts','Superávit'],
        ['t4','t5'], ['ts','t5'],
        ['t5','en'],
      ]),
  },

  // ── SERVICE DESK (adicionales) ────────────────────────────────────────────
  {
    id: 'major_incident',
    category: 'servicedesk',
    name: 'Major Incident (P0/P1) — Gestión de Crisis',
    description: 'Proceso de gestión de incidentes críticos con activación de war room, escalado y comunicación de crisis.',
    owner: 'Incident Commander / CTO',
    sla: 'P0: 2h resolución | P1: 4h',
    steps: ['Detectar P0/P1','Activar war room','Notificar stakeholders','Investigar causa','Implementar fix','Verificar resolución','Comunicar resolución','Post-mortem 48h','Acciones correctivas','Cerrar'],
    bpmn: buildBpmn('major_incident', 'Major Incident P0/P1',
      [
        { id: 'st',  type: 'startEvent',       name: 'P0/P1 Detectado',          col: 0 },
        { id: 't1',  type: 'userTask',          name: 'Activar War Room',         col: 1 },
        { id: 't2',  type: 'serviceTask',       name: 'Notificar Stakeholders',   col: 2 },
        { id: 't3',  type: 'userTask',          name: 'Investigar Causa',         col: 3 },
        { id: 'gw1', type: 'exclusiveGateway',  name: '¿Fix Identificado?',       col: 4 },
        { id: 't4',  type: 'userTask',          name: 'Escalar Expertos',         col: 4, row: 1 },
        { id: 't5',  type: 'userTask',          name: 'Implementar Fix',          col: 5 },
        { id: 'gw2', type: 'exclusiveGateway',  name: '¿Resuelto?',               col: 6 },
        { id: 't6',  type: 'serviceTask',       name: 'Comunicar Resolución',     col: 7 },
        { id: 't7',  type: 'userTask',          name: 'Post-Mortem',              col: 8 },
        { id: 'en',  type: 'endEvent',          name: 'Incidente Cerrado',        col: 9 },
      ],
      [
        ['st','t1'],['t1','t2'],['t2','t3'],['t3','gw1'],
        ['gw1','t5','Sí'], ['gw1','t4','No'],
        ['t4','t3'],
        ['t5','gw2'],
        ['gw2','t6','Resuelto'], ['gw2','t3','Regresión'],
        ['t6','t7'],['t7','en'],
      ]),
  },
  {
    id: 'cmdb_management',
    category: 'servicedesk',
    name: 'Gestión de CMDB / Alta de CIs',
    description: 'Proceso de identificación, validación y registro de Configuration Items en la CMDB.',
    owner: 'Configuration Manager / ITSM',
    sla: '3 días hábiles',
    steps: ['Identificar CI','Recopilar atributos','Validar datos','Aprobar registro','Registrar en CMDB','Relacionar CIs','Verificar relaciones','Publicar'],
    bpmn: buildBpmn('cmdb_management', 'Gestión de CMDB',
      [
        { id: 'st',  type: 'startEvent',       name: 'CI Identificado',          col: 0 },
        { id: 't1',  type: 'userTask',          name: 'Recopilar Atributos',      col: 1 },
        { id: 'gw1', type: 'exclusiveGateway',  name: '¿Datos Completos?',        col: 2 },
        { id: 't2',  type: 'userTask',          name: 'Aprobar Registro',         col: 3 },
        { id: 't3',  type: 'serviceTask',       name: 'Registrar en CMDB',        col: 4 },
        { id: 't4',  type: 'userTask',          name: 'Relacionar con CIs',       col: 5 },
        { id: 't5',  type: 'userTask',          name: 'Verificar Relaciones',     col: 6 },
        { id: 'en',  type: 'endEvent',          name: 'CI Registrado',            col: 7 },
        { id: 'td',  type: 'userTask',          name: 'Completar Datos',          col: 2, row: 1 },
      ],
      [
        ['st','t1'],['t1','gw1'],
        ['gw1','t2','Completos'], ['gw1','td','Incompletos'],
        ['td','t1'],
        ['t2','t3'],['t3','t4'],['t4','t5'],['t5','en'],
      ]),
  },
  {
    id: 'sla_breach',
    category: 'servicedesk',
    name: 'Breach de SLA y Escalado',
    description: 'Proceso de detección, notificación, investigación y resolución de incumplimientos de SLA.',
    owner: 'Service Desk Manager / Account Manager',
    sla: 'Inmediato al detectar breach',
    steps: ['Detectar breach SLA','Notificar cliente','Escalar internamente','Investigar causa','Resolver incidente','Verificar resolución','Tramitar compensación','Análisis causa raíz','Actualizar SLA/proceso','Cerrar'],
    bpmn: buildBpmn('sla_breach', 'Breach de SLA y Escalado',
      [
        { id: 'st',  type: 'startEvent',       name: 'Breach Detectado',         col: 0 },
        { id: 't1',  type: 'serviceTask',       name: 'Notificar Cliente',        col: 1 },
        { id: 't2',  type: 'userTask',          name: 'Escalar Internamente',     col: 2 },
        { id: 't3',  type: 'userTask',          name: 'Investigar y Resolver',    col: 3 },
        { id: 'gw1', type: 'exclusiveGateway',  name: '¿Resuelto?',               col: 4 },
        { id: 't4',  type: 'serviceTask',       name: 'Confirmar Resolución',     col: 5 },
        { id: 'gw2', type: 'exclusiveGateway',  name: '¿Compensación?',           col: 6 },
        { id: 't5',  type: 'userTask',          name: 'Tramitar Penalización',    col: 6, row: 1 },
        { id: 't6',  type: 'userTask',          name: 'Análisis Causa Raíz',      col: 7 },
        { id: 't7',  type: 'serviceTask',       name: 'Actualizar Proceso',       col: 8 },
        { id: 'en',  type: 'endEvent',          name: 'Breach Cerrado',           col: 9 },
      ],
      [
        ['st','t1'],['t1','t2'],['t2','t3'],['t3','gw1'],
        ['gw1','t4','Resuelto'], ['gw1','t2','Escalar más'],
        ['t4','gw2'],
        ['gw2','t6','No aplica'], ['gw2','t5','Aplica'],
        ['t5','t6'],
        ['t6','t7'],['t7','en'],
      ]),
  },

  // ── CRM & VENTAS (adicionales) ────────────────────────────────────────────
  {
    id: 'nps_survey',
    category: 'crm',
    name: 'Encuesta NPS y Seguimiento',
    description: 'Proceso de envío, recopilación y seguimiento de encuestas NPS para medir satisfacción del cliente.',
    owner: 'Customer Success / Account Manager',
    sla: 'Respuesta en 7 días',
    steps: ['Planificar envío','Enviar encuesta NPS','Recopilar respuestas','Calcular NPS','Segmentar promotores/detractores','Contactar detractores','Agradecer promotores','Analizar tendencias','Plan mejora'],
    bpmn: buildBpmn('nps_survey', 'Encuesta NPS',
      [
        { id: 'st',  type: 'startEvent',       name: 'Disparar NPS',             col: 0 },
        { id: 't1',  type: 'serviceTask',       name: 'Enviar Encuesta',          col: 1 },
        { id: 't2',  type: 'serviceTask',       name: 'Recopilar Respuestas',     col: 2 },
        { id: 't3',  type: 'serviceTask',       name: 'Calcular NPS',             col: 3 },
        { id: 'gw1', type: 'exclusiveGateway',  name: 'Tipo Respondente',         col: 4 },
        { id: 't4',  type: 'userTask',          name: 'Contactar Detractor',      col: 4, row: 1 },
        { id: 't5',  type: 'userTask',          name: 'Agradecer Promotor',       col: 5 },
        { id: 't6',  type: 'userTask',          name: 'Analizar Tendencias',      col: 6 },
        { id: 'en',  type: 'endEvent',          name: 'NPS Procesado',            col: 7 },
      ],
      [
        ['st','t1'],['t1','t2'],['t2','t3'],['t3','gw1'],
        ['gw1','t5','Promotor'], ['gw1','t4','Detractor'],
        ['t4','t6'], ['t5','t6'],
        ['t6','en'],
      ]),
  },
  {
    id: 'claim_management',
    category: 'crm',
    name: 'Gestión de Reclamaciones de Cliente',
    description: 'Proceso de registro, investigación, resolución y seguimiento de reclamaciones de clientes.',
    owner: 'Customer Success / AM',
    sla: 'Acuse 24h | Resolución 5 días',
    steps: ['Recibir reclamación','Acusar recibo','Verificar validez','Investigar','Proponer solución','Aceptación cliente','Implementar solución','Compensar si aplica','Cerrar y documentar'],
    bpmn: buildBpmn('claim_management', 'Gestión de Reclamaciones',
      [
        { id: 'st',  type: 'startEvent',       name: 'Reclamación Recibida',     col: 0 },
        { id: 't1',  type: 'serviceTask',       name: 'Acusar Recibo',            col: 1 },
        { id: 'gw1', type: 'exclusiveGateway',  name: '¿Válida?',                 col: 2 },
        { id: 't2',  type: 'userTask',          name: 'Investigar',               col: 3 },
        { id: 't3',  type: 'userTask',          name: 'Proponer Solución',        col: 4 },
        { id: 'gw2', type: 'exclusiveGateway',  name: '¿Aceptada?',               col: 5 },
        { id: 't4',  type: 'userTask',          name: 'Implementar Solución',     col: 6 },
        { id: 't5',  type: 'serviceTask',       name: 'Cerrar y Documentar',      col: 7 },
        { id: 'en1', type: 'endEvent',          name: 'Reclamación Cerrada',      col: 8 },
        { id: 'en2', type: 'endEvent',          name: 'Rechazada',                col: 3, row: 1 },
        { id: 'tc',  type: 'userTask',          name: 'Revisar Propuesta',        col: 5, row: 1 },
      ],
      [
        ['st','t1'],['t1','gw1'],
        ['gw1','t2','Válida'], ['gw1','en2','No válida'],
        ['t2','t3'],['t3','gw2'],
        ['gw2','t4','Aceptada'], ['gw2','tc','No aceptada'],
        ['tc','t3'],
        ['t4','t5'],['t5','en1'],
      ]),
  },

  // ── ADMINISTRACIÓN (adicionales) ─────────────────────────────────────────
  {
    id: 'user_offboarding',
    category: 'admin',
    name: 'Offboarding de Usuario (Baja)',
    description: 'Proceso de baja de usuario: revocación de accesos, traspaso de información y cierre de cuenta.',
    owner: 'IT / RRHH',
    sla: 'Mismo día de la baja',
    steps: ['Notificar baja','Revocar accesos','Backup de datos','Traspasar responsabilidades','Desactivar cuenta','Actualizar RRHH','Informe final','Archivar'],
    bpmn: buildBpmn('user_offboarding', 'Offboarding de Usuario',
      [
        { id: 'st', type: 'startEvent',  name: 'Notificar Baja',           col: 0 },
        { id: 't1', type: 'serviceTask', name: 'Revocar Accesos',           col: 1 },
        { id: 't2', type: 'serviceTask', name: 'Backup de Datos',           col: 2 },
        { id: 't3', type: 'userTask',    name: 'Traspasar Responsabilidades',col: 3 },
        { id: 't4', type: 'serviceTask', name: 'Desactivar Cuenta',         col: 4 },
        { id: 't5', type: 'serviceTask', name: 'Actualizar RRHH/Nómina',    col: 5 },
        { id: 't6', type: 'serviceTask', name: 'Informe Final',             col: 6 },
        { id: 'en', type: 'endEvent',    name: 'Baja Completada',           col: 7 },
      ],
      [['st','t1'],['t1','t2'],['t2','t3'],['t3','t4'],['t4','t5'],['t5','t6'],['t6','en']]),
  },
  {
    id: 'esignature_process',
    category: 'admin',
    name: 'Firma Electrónica de Documentos',
    description: 'Proceso de preparación, envío, firma y almacenamiento de documentos con firma electrónica.',
    owner: 'Legal / Owner del documento',
    sla: '5 días hábiles',
    steps: ['Preparar documento','Identificar firmantes','Enviar para firma','Firmar electrónicamente','Verificar todas las firmas','Enviar recordatorio si pendiente','Almacenar firmado','Notificar interesados','Registrar en expediente'],
    bpmn: buildBpmn('esignature_process', 'Firma Electrónica',
      [
        { id: 'st',  type: 'startEvent',       name: 'Documento Listo',          col: 0 },
        { id: 't1',  type: 'userTask',          name: 'Identificar Firmantes',    col: 1 },
        { id: 't2',  type: 'serviceTask',       name: 'Enviar para Firma',        col: 2 },
        { id: 't3',  type: 'userTask',          name: 'Firmar Electrónicamente',  col: 3 },
        { id: 'gw1', type: 'exclusiveGateway',  name: '¿Todos Firmaron?',         col: 4 },
        { id: 't4',  type: 'serviceTask',       name: 'Enviar Recordatorio',      col: 4, row: 1 },
        { id: 't5',  type: 'serviceTask',       name: 'Almacenar Firmado',        col: 5 },
        { id: 't6',  type: 'serviceTask',       name: 'Notificar Interesados',    col: 6 },
        { id: 't7',  type: 'serviceTask',       name: 'Registrar Expediente',     col: 7 },
        { id: 'en',  type: 'endEvent',          name: 'Documento Firmado',        col: 8 },
      ],
      [
        ['st','t1'],['t1','t2'],['t2','t3'],['t3','gw1'],
        ['gw1','t5','Todos firmaron'], ['gw1','t4','Pendientes'],
        ['t4','t3'],
        ['t5','t6'],['t6','t7'],['t7','en'],
      ]),
  },
  {
    id: 'grc_audit',
    category: 'admin',
    name: 'Auditoría GRC / Compliance',
    description: 'Proceso de planificación, ejecución, informe y seguimiento de auditorías de cumplimiento normativo.',
    owner: 'Compliance Officer / Auditor',
    sla: 'Anual / Según normativa',
    steps: ['Planificar auditoría','Definir alcance','Recopilar evidencias','Evaluar controles','Detectar hallazgos','Plan de remediación','Implementar correcciones','Verificar correcciones','Emitir informe final','Archivar'],
    bpmn: buildBpmn('grc_audit', 'Auditoría GRC',
      [
        { id: 'st',  type: 'startEvent',       name: 'Inicio Auditoría',         col: 0 },
        { id: 't1',  type: 'userTask',          name: 'Definir Alcance',          col: 1 },
        { id: 't2',  type: 'userTask',          name: 'Recopilar Evidencias',     col: 2 },
        { id: 't3',  type: 'userTask',          name: 'Evaluar Controles',        col: 3 },
        { id: 'gw1', type: 'exclusiveGateway',  name: '¿Hallazgos Críticos?',     col: 4 },
        { id: 't4',  type: 'userTask',          name: 'Plan de Remediación',      col: 5 },
        { id: 't5',  type: 'userTask',          name: 'Implementar Correcciones', col: 6 },
        { id: 't6',  type: 'userTask',          name: 'Verificar Correcciones',   col: 7 },
        { id: 't7',  type: 'serviceTask',       name: 'Emitir Informe Final',     col: 8 },
        { id: 'en',  type: 'endEvent',          name: 'Auditoría Cerrada',        col: 9 },
        { id: 'tn',  type: 'userTask',          name: 'Documentar Observaciones', col: 4, row: 1 },
      ],
      [
        ['st','t1'],['t1','t2'],['t2','t3'],['t3','gw1'],
        ['gw1','t4','Críticos'], ['gw1','tn','Menores'],
        ['tn','t7'],
        ['t4','t5'],['t5','t6'],['t6','t7'],['t7','en'],
      ]),
  },
  {
    id: 'access_request',
    category: 'admin',
    name: 'Solicitud de Acceso a Sistemas',
    description: 'Proceso de solicitud, aprobación y provisión de accesos a sistemas y aplicaciones.',
    owner: 'IT / Security',
    sla: '1 día hábil para accesos estándar',
    steps: ['Solicitar acceso','Aprobación manager','Evaluar datos sensibles','Revisión IT/Security','Provisionar acceso','Notificar usuario','Registrar en CMDB','Revisar periódicamente'],
    bpmn: buildBpmn('access_request', 'Solicitud de Acceso',
      [
        { id: 'st',  type: 'startEvent',       name: 'Solicitar Acceso',         col: 0 },
        { id: 'gw1', type: 'exclusiveGateway',  name: '¿Manager Aprueba?',        col: 1 },
        { id: 'gw2', type: 'exclusiveGateway',  name: '¿Datos Sensibles?',        col: 2 },
        { id: 't1',  type: 'userTask',          name: 'Revisión IT/Security',     col: 3 },
        { id: 't2',  type: 'serviceTask',       name: 'Provisionar Acceso',       col: 4 },
        { id: 't3',  type: 'serviceTask',       name: 'Notificar Usuario',        col: 5 },
        { id: 't4',  type: 'serviceTask',       name: 'Registrar en CMDB',        col: 6 },
        { id: 'en1', type: 'endEvent',          name: 'Acceso Concedido',         col: 7 },
        { id: 'en2', type: 'endEvent',          name: 'Solicitud Rechazada',      col: 2, row: 1 },
      ],
      [
        ['st','gw1'],
        ['gw1','gw2','Aprobado'], ['gw1','en2','Rechazado'],
        ['gw2','t1','Sensibles'], ['gw2','t2','Estándar'],
        ['t1','t2'],
        ['t2','t3'],['t3','t4'],['t4','en1'],
      ]),
  },
]

// ─── BPMN VIEWER HOOK ────────────────────────────────────────────────────────
function useBpmnViewer(containerRef: RefObject<HTMLDivElement | null>, xml: string | null, editMode: boolean) {
  const instanceRef = useRef<any>(null)

  useEffect(() => {
    if (!containerRef.current || !xml) return

    const init = async () => {
      if (instanceRef.current) {
        try { instanceRef.current.destroy() } catch {}
        instanceRef.current = null
      }

      // Dynamic import: keeps bpmn-js (~400 KB) and its CSS out of the
      // initial bundle. CSS is loaded once, lazily, in parallel with the
      // JS module.
      await loadBpmnCssOnce()

      let BpmnClass: any
      if (editMode) {
        const mod = await import('bpmn-js/lib/Modeler')
        BpmnClass = mod.default
      } else {
        const mod = await import('bpmn-js')
        BpmnClass = mod.default
      }

      const instance = new BpmnClass({ container: containerRef.current })
      instanceRef.current = instance

      try {
        await instance.importXML(xml)
        const canvas = instance.get('canvas')
        canvas.zoom('fit-viewport', 'auto')
      } catch (err) {
        console.error('BPMN import error:', err)
      }
    }

    init()

    return () => {
      if (instanceRef.current) {
        try { instanceRef.current.destroy() } catch {}
        instanceRef.current = null
      }
    }
  }, [xml, editMode])

  const getXml = async () => {
    if (!instanceRef.current) return null
    try {
      const { xml: exported } = await instanceRef.current.saveXML({ format: true })
      return exported
    } catch { return null }
  }

  return { getXml }
}

// ─── BLANK BPMN TEMPLATE ─────────────────────────────────────────────────────
const BLANK_BPMN = `<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
  xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
  xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"
  id="Definitions_new" targetNamespace="http://contecflow.io/bpmn">
  <bpmn:process id="Process_new" name="Nuevo Proceso" isExecutable="false">
    <bpmn:startEvent id="StartEvent_1" name="Inicio">
      <bpmn:outgoing>Flow_1</bpmn:outgoing>
    </bpmn:startEvent>
    <bpmn:task id="Task_1" name="Actividad">
      <bpmn:incoming>Flow_1</bpmn:incoming>
      <bpmn:outgoing>Flow_2</bpmn:outgoing>
    </bpmn:task>
    <bpmn:endEvent id="EndEvent_1" name="Fin">
      <bpmn:incoming>Flow_2</bpmn:incoming>
    </bpmn:endEvent>
    <bpmn:sequenceFlow id="Flow_1" sourceRef="StartEvent_1" targetRef="Task_1" />
    <bpmn:sequenceFlow id="Flow_2" sourceRef="Task_1" targetRef="EndEvent_1" />
  </bpmn:process>
  <bpmndi:BPMNDiagram id="BPMNDiagram_1">
    <bpmndi:BPMNPlane id="BPMNPlane_1" bpmnElement="Process_new">
      <bpmndi:BPMNShape id="StartEvent_1_di" bpmnElement="StartEvent_1">
        <dc:Bounds x="152" y="82" width="36" height="36" />
      </bpmndi:BPMNShape>
      <bpmndi:BPMNShape id="Task_1_di" bpmnElement="Task_1">
        <dc:Bounds x="250" y="60" width="100" height="80" />
      </bpmndi:BPMNShape>
      <bpmndi:BPMNShape id="EndEvent_1_di" bpmnElement="EndEvent_1">
        <dc:Bounds x="412" y="82" width="36" height="36" />
      </bpmndi:BPMNShape>
      <bpmndi:BPMNEdge id="Flow_1_di" bpmnElement="Flow_1">
        <di:waypoint xmlns:di="http://www.omg.org/spec/DD/20100524/DI" x="188" y="100" />
        <di:waypoint xmlns:di="http://www.omg.org/spec/DD/20100524/DI" x="250" y="100" />
      </bpmndi:BPMNEdge>
      <bpmndi:BPMNEdge id="Flow_2_di" bpmnElement="Flow_2">
        <di:waypoint xmlns:di="http://www.omg.org/spec/DD/20100524/DI" x="350" y="100" />
        <di:waypoint xmlns:di="http://www.omg.org/spec/DD/20100524/DI" x="412" y="100" />
      </bpmndi:BPMNEdge>
    </bpmndi:BPMNPlane>
  </bpmndi:BPMNDiagram>
</bpmn:definitions>`

// ─── STYLES ───────────────────────────────────────────────────────────────────
const card: CSSProperties = {
  background: 'var(--surface-2)',
  border: '1px solid var(--surface-4)',
  borderRadius: 12,
  padding: '16px 18px',
  cursor: 'pointer',
  transition: 'border-color .15s, box-shadow .15s',
}
const tag = (color: string): CSSProperties => ({
  display: 'inline-block',
  fontSize: 'var(--text-xs)',
  fontWeight: 700,
  padding: '2px 10px',
  borderRadius: 20,
  background: color + '22',
  color: color,
  border: `1px solid ${color}44`,
})
const inp: CSSProperties = {
  width: '100%',
  background: 'var(--surface-3)',
  border: '1px solid var(--surface-4)',
  borderRadius: 8,
  padding: '8px 12px',
  color: 'var(--text-1)',
  fontSize: 'var(--text-base)',
  fontFamily: 'inherit',
  outline: 'none',
  boxSizing: 'border-box',
}
const lbl: CSSProperties = {
  fontSize: 'var(--text-xs)',
  fontWeight: 600,
  color: 'var(--text-2)',
  textTransform: 'uppercase',
  letterSpacing: '.07em',
  display: 'block',
  marginBottom: 4,
}
// Shared ghost button (transparent bg, 1px surface border, muted text).
const ghostBtn: CSSProperties = {
  borderRadius: 8,
  border: '1px solid var(--surface-4)',
  background: 'none',
  color: 'var(--text-2)',
  cursor: 'pointer',
  fontFamily: 'inherit',
  display: 'flex',
  alignItems: 'center',
  gap: 4,
}
// Outlined accent button used for the "Editar" CTA.
const outlineAccentBtn: CSSProperties = {
  padding: '6px 14px',
  borderRadius: 8,
  border: '1px solid var(--accent)',
  background: 'none',
  color: 'var(--accent)',
  cursor: 'pointer',
  fontFamily: 'inherit',
  fontWeight: 600,
  display: 'flex',
  alignItems: 'center',
  gap: 4,
  fontSize: 'var(--text-base)',
}
// Container that hosts the bpmn-js canvas. White background is required:
// the diagram is rendered with dark strokes/labels.
const diagramContainer: CSSProperties = {
  width: '100%',
  height: '100%',
  border: '1px solid var(--surface-4)',
  borderRadius: 10,
  background: '#ffffff',
  overflow: 'hidden',
}
// Pill used for the "Modo edición" indicator overlaid on the diagram.
const editModeBadge: CSSProperties = {
  position: 'absolute',
  top: 8,
  left: 8,
  zIndex: 10,
  background: 'var(--surface-2)',
  border: '1px solid var(--accent)',
  borderRadius: 8,
  padding: '4px 12px',
  fontSize: 'var(--text-xs)',
  color: 'var(--accent)',
  fontWeight: 600,
  display: 'flex',
  alignItems: 'center',
  gap: 4,
}
// Meta-info row (Responsable / SLA / Description) below the detail header.
const metaText: CSSProperties = { fontSize: 'var(--text-xs)', color: 'var(--text-2)' }

// ─── MAIN COMPONENT ───────────────────────────────────────────────────────────
type BackendProcess = {
  id: string
  key: string
  category: string
  name: string
  description?: string
  latest_version?: number
}
type Process = {
  id: string
  category: string
  name: string
  description: string
  owner?: string
  sla?: string
  steps?: string[]
  bpmn: string
  isCustom?: boolean
  _backendId?: string
  _version?: number
}
type NewProcess = { name: string; category: string; description: string; owner: string; sla: string }

export default function BPMPage(): JSX.Element {
  const [selectedCat, setSelectedCat]         = useState('all')
  const [selectedProcess, setSelectedProcess] = useState<Process | null>(null)
  const [editMode, setEditMode]               = useState(false)
  const [showAddForm, setShowAddForm]         = useState(false)
  // Grouped backend data: list of records (custom + catalogue overrides) and
  // a key->latestXML map. They're updated together after reloadBackend(); the
  // XML map is also patched in-place when a process is saved or created.
  const [backend, setBackend]                 = useState<{ processes: BackendProcess[]; xmlByKey: Record<string, string> }>({ processes: [], xmlByKey: {} })
  const { processes: backendProcesses, xmlByKey: versionXmlByKey } = backend
  const [newProcess, setNewProcess]           = useState<NewProcess>({ name: '', category: 'proyectos', description: '', owner: '', sla: '' })
  const [search, setSearch]                   = useState('')
  const [saving, setSaving]                   = useState(false)
  const containerRef                          = useRef<HTMLDivElement>(null)
  // NOTE (latent bug): the toast API exposes success/error/warning/info, not
  // `push`. Preserved as-is to avoid changing runtime behavior; cast so it
  // type-checks.
  const toast                                 = useToast()

  // ── Load backend processes (custom + catalogue overrides) ────────────────
  const reloadBackend = async () => {
    try {
      const r = await bpmnProcessesApi.list({ include_inactive: false })
      const list: BackendProcess[] = r.data || []
      // Lazily fetch latest XML per process key (only ones we don't have yet)
      const updates: Record<string, string> = {}
      await Promise.all(list.map(async (p: BackendProcess) => {
        try {
          const detail = await bpmnProcessesApi.get(p.id)
          const xml = detail.data?.latest?.bpmn_xml
          if (xml) updates[p.key] = xml
        } catch { /* skip */ }
      }))
      setBackend(prev => ({
        processes: list,
        xmlByKey: { ...prev.xmlByKey, ...updates },
      }))
    } catch (e) {
      // Non-fatal: page still works with PROCESS_CATALOG only
      console.warn('[BPM] backend load failed:', e)
    }
  }
  useEffect(() => { reloadBackend() }, [])

  // Merge: catalogue (with backend XML override if present) + custom backend processes
  const allProcesses = useMemo<Process[]>(() => {
    const catalogIds = new Set(PROCESS_CATALOG.map(p => p.id))
    const overriddenCatalog = PROCESS_CATALOG.map(p => {
      const ov = backendProcesses.find(b => b.key === p.id)
      const xml = versionXmlByKey[p.id]
      return { ...p, bpmn: xml || p.bpmn, _backendId: ov?.id, _version: ov?.latest_version || 1 }
    })
    const customs = backendProcesses
      .filter(b => !catalogIds.has(b.key))
      .map(b => ({
        id: b.key,
        category: b.category,
        name: b.name,
        description: b.description || '',
        owner: '', sla: '', steps: [],
        bpmn: versionXmlByKey[b.key] || BLANK_BPMN,
        isCustom: true,
        _backendId: b.id,
        _version: b.latest_version || 1,
      }))
    return [...overriddenCatalog, ...customs]
  }, [backendProcesses, versionXmlByKey])

  // Keep selectedProcess fresh when data reloads.
  // Solo queremos reaccionar cuando se recarga la lista del backend
  // (allProcesses cambia de referencia). Añadir selectedProcess a las deps
  // crearía un bucle: el efecto llama a setSelectedProcess, lo que volvería
  // a disparar el efecto inmediatamente.
   
  useEffect(() => {
    if (!selectedProcess) return
    const fresh = allProcesses.find(p => p.id === selectedProcess.id)
    if (fresh && fresh !== selectedProcess) setSelectedProcess(fresh)
  }, [allProcesses])

  const filtered = allProcesses.filter(p => {
    const catOk = selectedCat === 'all' || p.category === selectedCat
    const q = search.toLowerCase()
    const searchOk = !q || p.name.toLowerCase().includes(q) || p.description.toLowerCase().includes(q)
    return catOk && searchOk
  })

  const currentBpmn = selectedProcess
    ? (editMode && selectedProcess.isCustom ? selectedProcess.bpmn : selectedProcess.bpmn)
    : null

  const { getXml } = useBpmnViewer(containerRef, currentBpmn, editMode)

  async function handleSaveCustom() {
    const xml = await getXml()
    if (!xml || !selectedProcess) return
    setSaving(true)
    try {
      let backendId = selectedProcess._backendId
      // If this is a catalog process being edited for the first time, create the backend record
      if (!backendId) {
        const created = await bpmnProcessesApi.create({
          name: selectedProcess.name,
          key: selectedProcess.id,
          category: selectedProcess.category || 'admin',
          description: selectedProcess.description || '',
          bpmn_xml: xml,
        })
        backendId = created.data.id
      } else {
        await bpmnProcessesApi.saveVersion(backendId, xml, null)
      }
      setBackend(prev => ({ ...prev, xmlByKey: { ...prev.xmlByKey, [selectedProcess.id]: xml } }))
      await reloadBackend()
      setEditMode(false)
      toast.success('Diseño guardado')
    } catch (e) {
      toast.error(apiErrorMsg(e, 'Error al guardar'))
    } finally {
      setSaving(false)
    }
  }

  async function handleExport() {
    const xml = await getXml()
    if (!xml) return
    const blob = new Blob([xml], { type: 'application/xml' })
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    a.href     = url
    a.download = `${selectedProcess?.id ?? 'process'}.bpmn`
    a.click()
    URL.revokeObjectURL(url)
  }

  async function handleAddProcess() {
    if (!newProcess.name.trim()) return
    const key = `custom_${Date.now()}`
    const xml = BLANK_BPMN
      .replace('Nuevo Proceso', xmlEsc(newProcess.name))
      .replace('Process_new', key)
      .replace('Definitions_new', `Def_${key}`)
    setSaving(true)
    try {
      const r = await bpmnProcessesApi.create({
        name: newProcess.name.trim(),
        key,
        category: newProcess.category,
        description: newProcess.description,
        bpmn_xml: xml,
      })
      const created = r.data
      setBackend(prev => ({ ...prev, xmlByKey: { ...prev.xmlByKey, [key]: xml } }))
      await reloadBackend()
      const proc = {
        id: key,
        category: newProcess.category,
        name: newProcess.name.trim(),
        description: newProcess.description,
        owner: newProcess.owner, sla: newProcess.sla, steps: [],
        bpmn: xml, isCustom: true,
        _backendId: created.id, _version: 1,
      }
      setNewProcess({ name: '', category: 'proyectos', description: '', owner: '', sla: '' })
      setShowAddForm(false)
      setSelectedProcess(proc)
      setEditMode(true)
      toast.success('Proceso creado')
    } catch (e) {
      toast.error(apiErrorMsg(e, 'Error al crear proceso'))
    } finally {
      setSaving(false)
    }
  }

  const catColor = selectedProcess ? CAT_COLOR[selectedProcess.category] : 'var(--accent)'

  return (
    <Page
      icon={<Network size={18} />}
      title="BPM — Procesos de Negocio"
      subtitle={`${allProcesses.length} procesos · ${PROCESS_CATALOG.length} del sistema · ${allProcesses.filter(p => (p as any).isCustom).length} personalizados`}
      rightActions={
        <Button onClick={() => { setShowAddForm(true); setSelectedProcess(null) }}>
          <Plus size={13} /> Nuevo proceso
        </Button>
      }
    >
      <div style={{ display: 'flex', gap: 'var(--space-4)', height: 'calc(100vh - 180px)', minHeight: 600 }}>

        {/* ── SIDEBAR ─────────────────────────────────────────────── */}
        <div className="ds-card" style={{
          width: 220, flexShrink: 0, padding: 0,
          display: 'flex', flexDirection: 'column',
          overflow: 'hidden',
        }}>
          <div style={{ padding: 'var(--space-3)', borderBottom: '1px solid var(--surface-4)', position: 'relative' }}>
            <Search size={13} aria-hidden style={{
              position: 'absolute', left: 22, top: '50%', transform: 'translateY(-50%)',
              color: 'var(--text-3)', pointerEvents: 'none',
            }} />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Buscar proceso..."
              className="ds-input"
              style={{ paddingLeft: 30, fontSize: 'var(--text-sm)' }}
            />
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
            {CATEGORIES.map(cat => {
              const count = cat.id === 'all' ? allProcesses.length : allProcesses.filter(p => p.category === cat.id).length
              const active = selectedCat === cat.id
              return (
                <button
                  key={cat.id}
                  onClick={() => { setSelectedCat(cat.id); setSelectedProcess(null); setEditMode(false) }}
                  style={{
                    width: '100%', textAlign: 'left', display: 'flex', alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '9px 14px', border: 'none',
                    background: active ? cat.color + '18' : 'transparent',
                    color: active ? cat.color : 'var(--text-1)',
                    cursor: 'pointer', fontFamily: 'inherit',
                    fontSize: 'var(--text-sm)', fontWeight: active ? 700 : 400,
                    borderLeft: active ? `3px solid ${cat.color}` : '3px solid transparent',
                  }}
                >
                  <span>{cat.label}</span>
                  <span style={{
                    fontSize: 'var(--text-xs)', background: 'var(--surface-4)',
                    color: 'var(--text-2)', borderRadius: 10, padding: '1px 7px',
                  }}>{count}</span>
                </button>
              )
            })}
          </div>
        </div>

        {/* ── MAIN AREA ────────────────────────────────────────────── */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

          {/* ── ADD FORM ── */}
          {showAddForm && (
            <div style={{
              ...card, marginBottom: 16, cursor: 'default',
              border: '1px solid var(--accent)',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                <div style={{ fontSize: 'var(--text-md)', fontWeight: 700 }}>Nuevo proceso personalizado</div>
                <button onClick={() => setShowAddForm(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-2)' }}>
                  <X size={16} />
                </button>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr', gap: 12, marginBottom: 12 }}>
                <div>
                  <label style={lbl}>Nombre del proceso *</label>
                  <input value={newProcess.name} onChange={e => setNewProcess(p => ({ ...p, name: e.target.value }))} placeholder="Ej: Gestión de proveedores" style={inp} />
                </div>
                <div>
                  <label style={lbl}>Categoría</label>
                  <select value={newProcess.category} onChange={e => setNewProcess(p => ({ ...p, category: e.target.value }))} style={inp}>
                    {CATEGORIES.filter(c => c.id !== 'all').map(c => <option key={c.id} value={c.id}>{c.label}</option>)}
                  </select>
                </div>
                <div>
                  <label style={lbl}>Responsable</label>
                  <input value={newProcess.owner} onChange={e => setNewProcess(p => ({ ...p, owner: e.target.value }))} placeholder="Ej: PM" style={inp} />
                </div>
                <div>
                  <label style={lbl}>SLA</label>
                  <input value={newProcess.sla} onChange={e => setNewProcess(p => ({ ...p, sla: e.target.value }))} placeholder="Ej: 3 días" style={inp} />
                </div>
              </div>
              <div style={{ marginBottom: 12 }}>
                <label style={lbl}>Descripción</label>
                <input value={newProcess.description} onChange={e => setNewProcess(p => ({ ...p, description: e.target.value }))} placeholder="Describe brevemente el proceso..." style={inp} />
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <Button disabled={!newProcess.name.trim()} onClick={handleAddProcess}>Crear y diseñar</Button>
                <button onClick={() => setShowAddForm(false)} style={{ ...ghostBtn, padding: '8px 14px', fontSize: 'var(--text-base)' }}>Cancelar</button>
              </div>
            </div>
          )}

          {selectedProcess ? (
            /* ── PROCESS DETAIL VIEW ── */
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
              {/* Header */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12, flexWrap: 'wrap' }}>
                <button
                  onClick={() => { setSelectedProcess(null); setEditMode(false) }}
                  style={{ ...ghostBtn, padding: '5px 10px' }}
                >
                  <ChevronLeft size={14} /> Volver
                </button>
                <div style={{ ...tag(catColor) }}>{CATEGORIES.find(c => c.id === selectedProcess.category)?.label}</div>
                <div style={{ fontSize: 'var(--text-md-em)', fontWeight: 700 }}>{selectedProcess.name}</div>
                {selectedProcess.isCustom && <div style={{ ...tag('#f59e0b') }}>Personalizado</div>}
                <div style={{ flex: 1 }} />
                <button
                  onClick={handleExport}
                  style={{ ...ghostBtn, padding: '6px 12px', fontSize: 'var(--text-sm)' }}
                >
                  <Download size={13} /> Exportar BPMN
                </button>
                {editMode ? (
                  <Button onClick={handleSaveCustom} disabled={saving}>
                    {saving ? 'Guardando…' : '💾 Guardar diseño'}
                  </Button>
                ) : (
                  <button
                    onClick={() => setEditMode(true)}
                    style={outlineAccentBtn}
                  >
                    <Edit3 size={13} /> Editar
                  </button>
                )}
              </div>

              {/* Meta info */}
              <div style={{ display: 'flex', gap: 12, marginBottom: 12, flexWrap: 'wrap' }}>
                {selectedProcess.owner && (
                  <div style={metaText}>
                    👤 <strong>Responsable:</strong> {selectedProcess.owner}
                  </div>
                )}
                {selectedProcess.sla && (
                  <div style={metaText}>
                    ⏱ <strong>SLA:</strong> {selectedProcess.sla}
                  </div>
                )}
                {selectedProcess.description && (
                  <div style={metaText}>
                    {selectedProcess.description}
                  </div>
                )}
              </div>

              {/* Steps summary */}
              {(selectedProcess?.steps?.length ?? 0) > 0 && (
                <div style={{ display: 'flex', gap: 0, marginBottom: 12, overflowX: 'auto', paddingBottom: 4, flexShrink: 0 }}>
                  {(selectedProcess?.steps || []).map((step, i) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'center' }}>
                      <div style={{
                        background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
                        borderRadius: 8, padding: '4px 10px',
                        fontSize: 'var(--text-xs)', color: 'var(--text-1)', whiteSpace: 'nowrap',
                        fontWeight: 500,
                      }}>
                        <span style={{ color: catColor, fontWeight: 700, marginRight: 4 }}>{i + 1}.</span>
                        {step}
                      </div>
                      {i < (selectedProcess?.steps?.length ?? 0) - 1 && (
                        <div style={{ color: 'var(--text-3)', padding: '0 3px', fontSize: 10 }}>›</div>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* BPMN Diagram */}
              <div style={{ flex: 1, position: 'relative', minHeight: 0 }}>
                {editMode && (
                  <div style={editModeBadge}>
                    <Edit3 size={11} /> Modo edición — arrastra nodos, añade elementos desde la paleta
                  </div>
                )}
                <div ref={containerRef} style={diagramContainer} />
              </div>
            </div>
          ) : (
            /* ── CATALOG GRID ── */
            <div style={{ flex: 1, overflowY: 'auto' }}>
              {filtered.length === 0 ? (
                <div style={{ ...card, textAlign: 'center', padding: '48px 24px', cursor: 'default' }}>
                  <div style={{ fontSize: 48, marginBottom: 12 }}>🔀</div>
                  <div style={{ fontSize: 'var(--text-md-em)', fontWeight: 600, marginBottom: 6 }}>
                    {search ? `Sin resultados para "${search}"` : 'Sin procesos en esta categoría'}
                  </div>
                  <div style={{ color: 'var(--text-2)', fontSize: 'var(--text-sm)', marginBottom: 16 }}>
                    {search ? 'Prueba con otro término de búsqueda.' : 'Crea el primer proceso personalizado.'}
                  </div>
                  {!search && <Button onClick={() => setShowAddForm(true)}><Plus size={13} style={{ marginRight: 4 }} />Nuevo proceso</Button>}
                </div>
              ) : (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(290px, 1fr))', gap: 14 }}>
                  {filtered.map(proc => {
                    const color = CAT_COLOR[proc.category] || 'var(--accent)'
                    const catLabel = CATEGORIES.find(c => c.id === proc.category)?.label || proc.category
                    return (
                      <button
                        key={proc.id}
                        style={{ ...card, width: '100%', textAlign: 'left' }}
                        onClick={() => { setSelectedProcess(proc); setEditMode(false); setShowAddForm(false) }}
                        onMouseEnter={e => { e.currentTarget.style.borderColor = color; e.currentTarget.style.boxShadow = `0 0 0 3px ${color}18` }}
                        onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--surface-4)'; e.currentTarget.style.boxShadow = 'none' }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                          <div style={{ fontSize: 'var(--text-md)', fontWeight: 700, lineHeight: 1.3 }}>{proc.name}</div>
                          {(proc as any).isCustom && <div style={{ ...tag('#f59e0b'), flexShrink: 0, marginLeft: 6 }}>Custom</div>}
                        </div>
                        <div style={{ marginBottom: 8 }}>
                          <span style={tag(color)}>{catLabel}</span>
                        </div>
                        {proc.description && (
                          <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-2)', marginBottom: 8, lineHeight: 1.4 }}>
                            {proc.description.length > 90 ? proc.description.slice(0, 88) + '…' : proc.description}
                          </div>
                        )}
                        <div style={{ display: 'flex', gap: 12, fontSize: 'var(--text-xs)', color: 'var(--text-2)' }}>
                          {proc.owner && <span>👤 {proc.owner}</span>}
                          {proc.sla   && <span>⏱ {proc.sla}</span>}
                          {(proc.steps?.length ?? 0) > 0 && <span>📋 {proc.steps!.length} pasos</span>}
                        </div>
                        <div style={{ marginTop: 10, fontSize: 'var(--text-xs)', color: color, fontWeight: 600 }}>
                          Ver diagrama BPMN →
                        </div>
                      </button>
                    )
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </Page>
  )
}
