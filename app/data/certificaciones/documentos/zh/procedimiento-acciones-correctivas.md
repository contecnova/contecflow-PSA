# 不符合项与纠正措施程序 — {{empresa}}

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

说明审核发现的处理，直至有效关闭。

## 2. 范围

适用于 {{empresa}} 的 {{alcance}}，包括以下场所：{{sedes}}。

## 3. 涵盖的控制措施

| 通用控制措施 | 标题 | 对应关系 |
|---|---|---|
| `no-conformidades-acciones-correctivas` | 不符合项与纠正措施 | iso27001 10.2, nis2 art.21.4, iec62443 SM-11, sox ELC-04, jsox ELC-04 |
| `mejora-continua` | 持续改进 | iso27001 10.1, iec62443 SM-13 |
| `evaluacion-deficiencias-control` | 控制缺陷的评价与沟通 | sox ELC-04, jsox ELC-04 |

## 4. 角色与职责

- **安全负责人**：维护本文件，监督其执行并报告偏差。
- **内部审计**：独立核查本文件的执行情况。
- **流程负责人**：在其流程中执行本文件，并对相应控制措施负责。

## 5. 程序步骤

### 5.1 登记

审核发现的来源与分级。

{{detalle_registro}}

### 5.2 原因

根本原因分析。

{{detalle_causa}}

### 5.3 计划

措施、责任人和期限。

{{detalle_plan}}

### 5.4 验证与关闭

关闭者与纠正者不得为同一人。

{{detalle_verificacion_y_cierre}}

## 6. 记录与证据

- 审核发现与 CAPA 记录

## 7. 违规处理

违反本文件的行为，按 {{empresa}} 的纪律处分流程和不符合项流程处理。

## 8. 变更控制

| 版本 | 日期 | 编写人 | 批准人 | 变更内容 |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | 初始版本 |
