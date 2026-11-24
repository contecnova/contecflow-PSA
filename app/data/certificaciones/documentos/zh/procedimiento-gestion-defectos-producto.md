# 产品安全缺陷管理程序 — {{empresa}}

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

说明如何接收、评价、修复和披露产品安全问题。

## 2. 范围

适用于 {{empresa}} 的 {{alcance}}，包括以下场所：{{sedes}}。

## 3. 涵盖的控制措施

| 通用控制措施 | 标题 | 对应关系 |
|---|---|---|
| `recepcion-notificaciones-vulnerabilidades` | 产品脆弱性报告的接收 | iec62443 DM-1 |
| `gestion-defectos-seguridad-producto` | 产品安全缺陷管理 | iec62443 DM-2, iec62443 DM-3, iec62443 DM-4, iec62443 DM-6 |
| `divulgacion-vulnerabilidades` | 脆弱性协调披露 | iec62443 DM-5, nis2 art.21.2.e |

## 4. 角色与职责

- **流程负责人**：在其流程中执行本文件，并对相应控制措施负责。
- **安全负责人**：维护本文件，监督其执行并报告偏差。
- **信息技术（IT）部门**：落实技术措施并提供系统证据。

## 5. 程序步骤

### 5.1 接收

公开渠道与回执确认。

{{detalle_recepcion}}

### 5.2 评价

严重程度及受影响的产品。

{{detalle_valoracion}}

### 5.3 纠正

按严重程度确定的时限。

{{detalle_correccion}}

### 5.4 披露

协调向客户和主管机构发出通知。

{{detalle_divulgacion}}

## 6. 记录与证据

- 缺陷登记册
- 已发布的公告

## 7. 违规处理

违反本文件的行为，按 {{empresa}} 的纪律处分流程和不符合项流程处理。

## 8. 变更控制

| 版本 | 日期 | 编写人 | 批准人 | 变更内容 |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | 初始版本 |
