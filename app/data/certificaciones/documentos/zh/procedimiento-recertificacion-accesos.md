# 访问权限复核程序 — {{empresa}}

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

说明定期开展的访问权限复核活动。

## 2. 范围

适用于 {{empresa}} 的 {{alcance}}，包括以下场所：{{sedes}}。

## 3. 涵盖的控制措施

| 通用控制措施 | 标题 | 对应关系 |
|---|---|---|
| `revision-periodica-accesos` | 访问权限定期复核 | iso27001 A.5.18, tisax 4.2.1, sox ITGC-APD-03, jsox ITGC-SEG-03 |
| `accesos-privilegiados` | 特权访问 | iso27001 A.8.2, tisax 4.2.1, sox ITGC-APD-04, jsox ITGC-SEG-04 |
| `segregacion-funciones` | 职责分离 | iso27001 A.5.3, sox ITGC-APD-06, jsox ITGC-SEG-06 |

## 4. 角色与职责

- **信息技术（IT）部门**：落实技术措施并提供系统证据。
- **流程负责人**：在其流程中执行本文件，并对相应控制措施负责。
- **内部审计**：独立核查本文件的执行情况。

## 5. 程序步骤

### 5.1 范围与频率

按关键程度确定的系统与周期。

{{detalle_alcance_y_frecuencia}}

### 5.2 评审

责任人评审的内容。

{{detalle_revision}}

### 5.3 纠正

撤回未确认事项的期限。

{{detalle_correccion}}

### 5.4 证据

复核活动已关闭并导出。

{{detalle_evidencia}}

## 6. 记录与证据

- 已关闭的复核活动

## 7. 违规处理

违反本文件的行为，按 {{empresa}} 的纪律处分流程和不符合项流程处理。

## 8. 变更控制

| 版本 | 日期 | 编写人 | 批准人 | 变更内容 |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | 初始版本 |
