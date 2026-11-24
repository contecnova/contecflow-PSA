# 产品安全更新程序 — {{empresa}}

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

说明安全更新的验证、文档编制和交付。

## 2. 范围

适用于 {{empresa}} 的 {{alcance}}，包括以下场所：{{sedes}}。

## 3. 涵盖的控制措施

| 通用控制措施 | 标题 | 对应关系 |
|---|---|---|
| `actualizaciones-seguridad-producto` | 产品安全更新 | iec62443 SUM-1, iec62443 SUM-2, iec62443 SUM-3, iec62443 SUM-4, iec62443 SUM-5, iec62443 EDR 3.10, iec62443 HDR 3.10, iec62443 NDR 3.10 |
| `sbom-y-versiones-firmadas` | SBOM 及已标记并签名的版本 | iec62443 SM-9, iec62443 SUM-3 |
| `integridad-artefactos-desarrollo` | 开发制品的完整性 | iso27001 A.8.4, iec62443 SM-6 |

## 4. 角色与职责

- **流程负责人**：在其流程中执行本文件，并对相应控制措施负责。
- **信息技术（IT）部门**：落实技术措施并提供系统证据。

## 5. 程序步骤

### 5.1 验证

发布前测试。

{{detalle_cualificacion}}

### 5.2 文档

说明及依赖组件。

{{detalle_documentacion}}

### 5.3 交付

客户签字与验证。

{{detalle_entrega}}

### 5.4 时限

交付承诺。

{{detalle_plazos}}

## 6. 记录与证据

- 版本说明
- SBOM

## 7. 违规处理

违反本文件的行为，按 {{empresa}} 的纪律处分流程和不符合项流程处理。

## 8. 变更控制

| 版本 | 日期 | 编写人 | 批准人 | 变更内容 |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | 初始版本 |
