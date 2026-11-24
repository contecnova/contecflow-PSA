# 事件管理程序 — {{empresa}}

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

说明 {{empresa}} 的安全事件如何报告、分级、响应和关闭。

## 2. 范围

适用于 {{empresa}} 的 {{alcance}}，包括以下场所：{{sedes}}。

## 3. 涵盖的控制措施

| 通用控制措施 | 标题 | 对应关系 |
|---|---|---|
| `preparacion-gestion-incidentes` | 事件管理准备 | iso27001 A.5.24, tisax 1.6.1, nis2 art.21.2.b, iec62443 SPE 7 |
| `evaluacion-eventos` | 事件评估与分级 | iso27001 A.5.25, tisax 1.6.2, nis2 art.23.3 |
| `respuesta-incidentes` | 事件响应 | iso27001 A.5.26, tisax 1.6.2, nis2 art.21.2.b |
| `lecciones-incidentes` | 从事件中学习 | iso27001 A.5.27, tisax 1.6.2 |
| `recogida-evidencias` | 证据的收集与保管 | iso27001 A.5.28 |
| `notificacion-eventos` | 员工事件报告 | iso27001 A.6.8, tisax 1.6.1 |

## 4. 角色与职责

- **安全负责人**：维护本文件，监督其执行并报告偏差。
- **信息技术（IT）部门**：落实技术措施并提供系统证据。
- **运营技术（OT）部门**：在工厂和自动化系统中落实相关措施。
- **合规负责人**：统筹证据并协调其与各项标准的对应关系。

## 5. 程序步骤

### 5.1 沟通

渠道与最低数据要求。

{{detalle_comunicacion}}

### 5.2 分级

严重程度标准及重大事件判定标准。

{{detalle_clasificacion}}

### 5.3 响应

遏制、根除和恢复。

{{detalle_respuesta}}

### 5.4 证据

收集与保管。

{{detalle_evidencias}}

### 5.5 关闭与经验教训

事后复盘报告与改进。

{{detalle_cierre_y_lecciones}}

## 6. 记录与证据

- 事件工单
- 事后复盘报告

## 7. 违规处理

违反本文件的行为，按 {{empresa}} 的纪律处分流程和不符合项流程处理。

## 8. 变更控制

| 版本 | 日期 | 编写人 | 批准人 | 变更内容 |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | 初始版本 |
