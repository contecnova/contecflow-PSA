# 区域、管道与安全等级程序 — {{empresa}}

| 字段 | 值 |
|---|---|
| 类型 | 程序 |
| 编码 | {{codigo_documento}} |
| 版本 | {{version}} |
| 责任人 | {{propietario}} |
| 批准人 | {{aprobador}}（文档批准流程） |
| 批准日期 | {{fecha_aprobacion}} |
| 下次评审 | {{fecha_revision}} |
| 分级 | {{clasificacion}} |
| 范围 | {{alcance}} |

> 本模板由 contecflow 编写。请替换 `{{...}}` 标记，并根据贵组织的实际情况调整内容。模板不包含受版权保护的标准文本；如贵公司持有授权，可将官方文本导入目录。

## 1. 目的

说明 {{empresa}} 如何将工厂系统划分为区域和管道，并为各区域确定目标 SL。

## 2. 范围

适用于 {{empresa}} 的 {{alcance}}，包括以下场所：{{sedes}}。涵盖 {{plantas_ot}} 中列出的工厂和自动化系统。

## 3. 涵盖的控制措施

| 通用控制措施 | 标题 | 对应关系 |
|---|---|---|
| `sistema-bajo-consideracion` | 待评估系统的定义 | iec62443 ZCR 1 |
| `evaluacion-riesgos-ot` | OT 网络安全风险评估 | iec62443 ZCR 2, iec62443 ZCR 4, iec62443 ZCR 5, iec62443 SPE 1 |
| `zonas-y-conductos` | 区域与管道 | iec62443 ZCR 3, iec62443 SPE 3 |
| `nivel-seguridad-objetivo-por-zona` | 各区域的目标安全等级 | iec62443 ZCR 5, iec62443 ZCR 6 |
| `especificacion-requisitos-ciberseguridad` | 系统网络安全要求规格说明 | iec62443 ZCR 6 |
| `aprobacion-propietario-activo` | 资产责任人批准 | iec62443 ZCR 7 |

## 4. 角色与职责

- **运营技术（OT）部门**：在工厂和自动化系统中落实相关措施。
- **安全负责人**：维护本文件，监督其执行并报告偏差。
- **流程负责人**：在其流程中执行本文件，并对相应控制措施负责。

## 5. 程序步骤

### 5.1 待评估系统

边界与清单。

{{detalle_sistema_bajo_consideracion}}

### 5.2 初步评估

未采取对策时的风险。

{{detalle_evaluacion_inicial}}

### 5.3 划分

分组标准及其在 CMDB 中的体现。

{{detalle_particion}}

### 5.4 详细评估与 SL-T

按区域和管道。

{{detalle_evaluacion_detallada_y_sl_t}}

### 5.5 要求与批准

规格说明及责任人签字确认。

{{detalle_requisitos_y_aprobacion}}

## 6. 记录与证据

- 区域与 SL 记录

## 7. 违规处理

违反本文件的行为，按 {{empresa}} 的纪律处分流程和不符合项流程处理。

## 8. 变更控制

| 版本 | 日期 | 编写人 | 批准人 | 变更内容 |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | 初始版本 |
