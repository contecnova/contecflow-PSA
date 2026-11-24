# 重大事件通报程序（NIS2） — {{empresa}}

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

确保 {{empresa}} 按期向 CSIRT 或主管机构（{{autoridad_nis2}}）通报重大事件。

## 2. 范围

适用于 {{empresa}} 的 {{alcance}}，包括以下场所：{{sedes}}。

## 3. 涵盖的控制措施

| 通用控制措施 | 标题 | 对应关系 |
|---|---|---|
| `notificacion-incidentes-significativos` | 重大事件通报 | nis2 art.23.1, nis2 art.23.3 |
| `alerta-temprana-24h` | 24 小时内预警 | nis2 art.23.4.a |
| `notificacion-incidente-72h` | 72 小时内事件通报 | nis2 art.23.4.b |
| `informe-intermedio-incidente` | 应要求提交中期报告 | nis2 art.23.4.c |
| `informe-final-incidente` | 一个月内提交最终报告 | nis2 art.23.4.d, nis2 art.23.4.e |
| `comunicacion-destinatarios-servicio` | 向服务接收方通报 | nis2 art.23.1, nis2 art.23.2 |
| `contacto-autoridades` | 与主管机构的联系 | iso27001 A.5.5, nis2 art.23.1 |

## 4. 角色与职责

- **安全负责人**：维护本文件，监督其执行并报告偏差。
- **合规负责人**：统筹证据并协调其与各项标准的对应关系。
- **管理层**：批准本文件并分配所需资源。
- **信息技术（IT）部门**：落实技术措施并提供系统证据。

## 5. 程序步骤

### 5.1 重大事件的判定

判定标准及决定人；知悉时间。

{{detalle_determinacion_del_incidente_significativ}}

### 5.2 预警（24 小时）

最低内容与渠道。

{{detalle_alerta_temprana_24_h}}

### 5.3 通报（72 小时）

初步评估、严重程度、影响及失陷指标。

{{detalle_notificacion_72_h}}

### 5.4 中期报告

应主管机构要求提供。

{{detalle_informe_intermedio}}

### 5.5 最终报告（1 个月）

描述、原因、措施和跨境影响；若事件仍在持续，提交情况报告。

{{detalle_informe_final_1_mes}}

### 5.6 向服务接收方通报

何时以及如何通知客户。

{{detalle_comunicacion_a_destinatarios}}

## 6. 记录与证据

- 带时间戳的通报记录

## 7. 违规处理

违反本文件的行为，按 {{empresa}} 的纪律处分流程和不符合项流程处理。

## 8. 变更控制

| 版本 | 日期 | 编写人 | 批准人 | 变更内容 |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | 初始版本 |
