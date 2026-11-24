# 关键供应商记录 — {{empresa}}

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

记录关键供应商及其评估状态。

## 2. 范围

适用于 {{empresa}} 的 {{alcance}}，包括以下场所：{{sedes}}。

## 3. 涵盖的控制措施

| 通用控制措施 | 标题 | 对应关系 |
|---|---|---|
| `seguridad-proveedores` | 供应商关系中的安全 | iso27001 A.5.19, tisax 6.1.1, nis2 art.21.2.d, iec62443 SPE 1 |
| `seguimiento-proveedores` | 供应商服务监控与鉴证报告 | iso27001 A.5.22, tisax 6.1.1, sox ITGC-CO-05, jsox ITGC-EXT-01 |
| `cadena-suministro-tic` | ICT 供应链安全 | iso27001 A.5.21, nis2 art.21.2.d, nis2 art.21.3, iec62443 SM-9 |

## 4. 角色与职责

- **合规负责人**：统筹证据并协调其与各项标准的对应关系。

## 5. 记录字段

| 字段 | 说明 | 必填 |
|---|---|---|
| 供应商 | 名称 | 是 |
| 服务 | 说明 | 是 |
| 关键程度 | 等级 | 是 |
| 评估 | 日期与结果 | 是 |
| 鉴证 | 证书、标签或 SOC 报告 | 是 |
| 下次评审 | 日期 | 是 |

## 6. 保存与访问

- 保存期限：{{plazo_retencion}}；适用时受法律保全约束。
- 内部审计和经门户授权的外部审计人员享有只读访问权限。
- 所有修改均记入平台审计日志。

## 7. 变更控制

| 版本 | 日期 | 编写人 | 批准人 | 变更内容 |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | 初始版本 |
