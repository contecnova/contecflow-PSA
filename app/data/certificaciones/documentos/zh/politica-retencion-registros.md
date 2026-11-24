# 记录保存政策 — {{empresa}}

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

规定 {{empresa}} 记录的保存期限和保存方式，包括法律保全。

## 2. 范围

适用于 {{empresa}} 的 {{alcance}}，包括以下场所：{{sedes}}。

## 3. 涵盖的控制措施

| 通用控制措施 | 标题 | 对应关系 |
|---|---|---|
| `proteccion-registros` | 记录的保护与保存 | iso27001 A.5.33, sox Sec.802, jsox FIEA-24-4-4 |
| `privacidad-datos-personales` | 隐私与个人数据保护 | iso27001 A.5.34, tisax 7.1.2 |
| `integridad-registros-auditoria` | 审计日志的完整性 | iso27001 A.8.15, iec62443 SR 3.9, iec62443 CR 3.9 |
| `borrado-informacion` | 信息删除与残留 | iso27001 A.8.10, tisax 5.3.3, iec62443 SR 4.2, iec62443 CR 4.2 |

## 4. 角色与职责

- **合规负责人**：统筹证据并协调其与各项标准的对应关系。
- **信息技术（IT）部门**：落实技术措施并提供系统证据。
- **财务部门**：负责财务信息相关控制措施。

## 5. 指导原则

### 5.1 保存期限表

按记录类型和国家确定的期限。

{{detalle_calendario_de_conservacion}}

### 5.2 财务记录

审计文档的保存期限。

{{detalle_registros_financieros}}

### 5.3 法律保全

何时启动及由谁解除。

{{detalle_bloqueo_legal}}

### 5.4 销毁

期限届满时安全删除。

{{detalle_destruccion}}

## 6. 记录与证据

- 保存期限表
- 法律保全

## 7. 违规处理

违反本文件的行为，按 {{empresa}} 的纪律处分流程和不符合项流程处理。

## 8. 变更控制

| 版本 | 日期 | 编写人 | 批准人 | 变更内容 |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | 初始版本 |
