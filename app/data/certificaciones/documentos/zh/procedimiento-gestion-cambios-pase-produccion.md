# 变更与生产发布程序 — {{empresa}}

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

说明变更从申请到事后评审的流程。

## 2. 范围

适用于 {{empresa}} 的 {{alcance}}，包括以下场所：{{sedes}}。

## 3. 涵盖的控制措施

| 通用控制措施 | 标题 | 对应关系 |
|---|---|---|
| `gestion-cambios` | 变更管理 | iso27001 A.8.32, tisax 5.2.1, nis2 art.21.2.e, sox ITGC-PC-01, jsox ITGC-DES-05 |
| `pruebas-cambios` | 变更测试 | iso27001 A.8.32, sox ITGC-PC-02, jsox ITGC-DES-02 |
| `aprobacion-independiente-paso-produccion` | 生产发布的独立批准 | iso27001 A.8.32, sox ITGC-PC-03, sox ITGC-PD-04, jsox ITGC-DES-05 |
| `cambios-emergencia` | 紧急变更 | iso27001 A.8.32, sox ITGC-PC-05, jsox ITGC-DES-05 |
| `gestion-configuracion` | 配置管理 | iso27001 A.8.9, iec62443 SR 7.6, iec62443 CR 7.6, iec62443 SPE 2, sox ITGC-PC-06, jsox ITGC-DES-06 |

## 4. 角色与职责

- **信息技术（IT）部门**：落实技术措施并提供系统证据。
- **流程负责人**：在其流程中执行本文件，并对相应控制措施负责。
- **内部审计**：独立核查本文件的执行情况。

## 5. 程序步骤

### 5.1 申请

最低数据要求与分级。

{{detalle_solicitud}}

### 5.2 评估与批准

CAB 及按版本进行的独立批准。

{{detalle_evaluacion_y_aprobacion}}

### 5.3 测试

环境与证据。

{{detalle_pruebas}}

### 5.4 生产发布

由谁执行以及如何记录。

{{detalle_paso_a_produccion}}

### 5.5 事后评审

适用时开展事后评审（PIR）。

{{detalle_revision_posterior}}

## 6. 记录与证据

- 变更记录

## 7. 违规处理

违反本文件的行为，按 {{empresa}} 的纪律处分流程和不符合项流程处理。

## 8. 变更控制

| 版本 | 日期 | 编写人 | 批准人 | 变更内容 |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | 初始版本 |
