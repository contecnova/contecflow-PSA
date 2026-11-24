# 管理评审程序 — {{empresa}}

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

说明管理层对本方案的定期评审。

## 2. 范围

适用于 {{empresa}} 的 {{alcance}}，包括以下场所：{{sedes}}。

## 3. 涵盖的控制措施

| 通用控制措施 | 标题 | 对应关系 |
|---|---|---|
| `revision-direccion` | 管理评审 | iso27001 9.3, nis2 art.20.1 |
| `seguimiento-medicion` | 措施的监测、测量与有效性 | iso27001 9.1, nis2 art.21.2.f |
| `responsabilidad-direccion` | 管理层承诺与责任 | iso27001 5.1, iso27001 A.5.4, nis2 art.20.1, tisax 1.2.1 |

## 4. 角色与职责

- **管理层**：批准本文件并分配所需资源。
- **安全负责人**：维护本文件，监督其执行并报告偏差。
- **合规负责人**：统筹证据并协调其与各项标准的对应关系。

## 5. 程序步骤

### 5.1 频率

至少每年一次。

{{detalle_frecuencia}}

### 5.2 输入

指标、审核、事件、风险、供应商和变更。

{{detalle_entradas}}

### 5.3 输出

决定、资源与改进。

{{detalle_salidas}}

## 6. 记录与证据

- 评审纪要

## 7. 违规处理

违反本文件的行为，按 {{empresa}} 的纪律处分流程和不符合项流程处理。

## 8. 变更控制

| 版本 | 日期 | 编写人 | 批准人 | 变更内容 |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | 初始版本 |
