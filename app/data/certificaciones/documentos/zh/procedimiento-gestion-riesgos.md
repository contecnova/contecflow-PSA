# 风险管理程序 — {{empresa}}

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

说明 {{empresa}} 如何识别、分析、评价和处置安全风险。

## 2. 范围

适用于 {{empresa}} 的 {{alcance}}，包括以下场所：{{sedes}}。

## 3. 涵盖的控制措施

| 通用控制措施 | 标题 | 对应关系 |
|---|---|---|
| `evaluacion-riesgos` | 安全风险评估 | iso27001 6.1.1, iso27001 6.1.2, iso27001 8.2, tisax 1.4.1, nis2 art.21.1, nis2 art.21.2.a, iec62443 SPE 1 |
| `tratamiento-riesgos-declaracion-aplicabilidad` | 风险处置与适用性声明 | iso27001 6.1.3, iso27001 8.3, nis2 art.21.1 |
| `evaluacion-riesgos-ot` | OT 网络安全风险评估 | iec62443 ZCR 2, iec62443 ZCR 4, iec62443 ZCR 5, iec62443 SPE 1 |

## 4. 角色与职责

- **安全负责人**：维护本文件，监督其执行并报告偏差。
- **流程负责人**：在其流程中执行本文件，并对相应控制措施负责。
- **管理层**：批准本文件并分配所需资源。

## 5. 程序步骤

### 5.1 评分等级

可能性与影响（{{escala_riesgo}}）。

{{detalle_escalas}}

### 5.2 识别

按流程和区域识别资产、威胁和脆弱性。

{{detalle_identificacion}}

### 5.3 评价与接受

接受标准及接受人。

{{detalle_valoracion_y_aceptacion}}

### 5.4 处理

处置选项及其与适用性声明的关系。

{{detalle_tratamiento}}

### 5.5 评审

每年一次，并在发生重大变更时进行。

{{detalle_revision}}

## 6. 记录与证据

- 风险登记册
- 处置计划

## 7. 违规处理

违反本文件的行为，按 {{empresa}} 的纪律处分流程和不符合项流程处理。

## 8. 变更控制

| 版本 | 日期 | 编写人 | 批准人 | 变更内容 |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | 初始版本 |
