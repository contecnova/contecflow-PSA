# 版本、SBOM 与签名记录 — {{empresa}}

| 字段 | 值 |
|---|---|
| 类型 | 记录 |
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

记录每个已发布版本及其 SBOM、独立评审和签名。

## 2. 范围

适用于 {{empresa}} 的 {{alcance}}，包括以下场所：{{sedes}}。

## 3. 涵盖的控制措施

| 通用控制措施 | 标题 | 对应关系 |
|---|---|---|
| `sbom-y-versiones-firmadas` | SBOM 及已标记并签名的版本 | iec62443 SM-9, iec62443 SUM-3 |
| `aprobacion-independiente-paso-produccion` | 生产发布的独立批准 | iso27001 A.8.32, sox ITGC-PC-03, sox ITGC-PD-04, jsox ITGC-DES-05 |

## 4. 角色与职责

- **流程负责人**：在其流程中执行本文件，并对相应控制措施负责。

## 5. 记录字段

| 字段 | 说明 | 必填 |
|---|---|---|
| 产品 | 名称 | 是 |
| 版本 | 标签 | 是 |
| SBOM | 文件引用 | 是 |
| 独立评审人 | 非作者本人 | 是 |
| 签名 | 指纹与证书 | 是 |
| 发布日期 | 日期 | 是 |

## 6. 保存与访问

- 保存期限：{{plazo_retencion}}；适用时受法律保全约束。
- 内部审计和经门户授权的外部审计人员享有只读访问权限。
- 所有修改均记入平台审计日志。

## 7. 变更控制

| 版本 | 日期 | 编写人 | 批准人 | 变更内容 |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | 初始版本 |
