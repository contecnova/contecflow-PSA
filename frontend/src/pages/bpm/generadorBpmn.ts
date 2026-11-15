import { BPMN_TARGET_NAMESPACE } from '../../constants/bpmn'

// Generador de XML BPMN (layout por columnas/filas). Sin textos: los nombres llegan ya traducidos.
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

export type BpmnNode = { id: string; type: string; name: string; col?: number; row?: number }
export type BpmnConn = [string, string, string?, string?]
type NodePos = { cx: number; cy: number; x: number; y: number; w: number; h: number }

export function xmlEsc(s: unknown): string {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')
}

export function buildBpmn(pid: string, pname: string, nodes: BpmnNode[], conns: BpmnConn[]): string {
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
  id="Definitions_${pid}" targetNamespace="${BPMN_TARGET_NAMESPACE}">
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

