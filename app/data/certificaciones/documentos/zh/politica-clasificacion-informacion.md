# 信息分级与处理政策 — {{empresa}}

| 字段 | 值 |
|---|---|
| 类型 | 政策 |
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

规定 {{empresa}} 的信息分级级别以及各级别信息的处理方式。

## 2. 范围

适用于 {{empresa}} 的 {{alcance}}，包括以下场所：{{sedes}}。

## 3. 涵盖的控制措施

| 通用控制措施 | 标题 | 对应关系 |
|---|---|---|
| `clasificacion-informacion` | 信息分级 | iso27001 A.5.12, tisax 1.3.2, iec62443 SPE 5 |
| `etiquetado-informacion` | 信息标识 | iso27001 A.5.13, tisax 1.3.2 |
| `transferencia-informacion` | 信息交换 | iso27001 A.5.14, tisax 5.1.2 |
| `borrado-informacion` | 信息删除与残留 | iso27001 A.8.10, tisax 5.3.3, iec62443 SR 4.2, iec62443 CR 4.2 |

## 4. 角色与职责

- **安全负责人**：维护本文件，监督其执行并报告偏差。
- **流程负责人**：在其流程中执行本文件，并对相应控制措施负责。
- **信息技术（IT）部门**：落实技术措施并提供系统证据。

## 5. 指导原则

### 5.1 级别

定义各级别（{{niveles_clasificacion}}）及分配标准。

{{detalle_niveles}}

### 5.2 标识

各级别在文档、邮件和系统中如何标识。

{{detalle_etiquetado}}

### 5.3 处理

按级别规定存储、传输、打印和销毁要求。

{{detalle_tratamiento}}

### 5.4 客户信息

如何遵守客户规定的分级要求。

{{detalle_informacion_de_clientes}}

## 6. 记录与证据

- 含分级信息的清单

## 7. 违规处理

违反本文件的行为，按 {{empresa}} 的纪律处分流程和不符合项流程处理。

## 8. 变更控制

| 版本 | 日期 | 编写人 | 批准人 | 变更内容 |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | 初始版本 |
