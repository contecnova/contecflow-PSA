# 内部审核程序 — {{empresa}}

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

说明如何策划和实施本方案的内部审核。

## 2. 范围

适用于 {{empresa}} 的 {{alcance}}，包括以下场所：{{sedes}}。

## 3. 涵盖的控制措施

| 通用控制措施 | 标题 | 对应关系 |
|---|---|---|
| `auditoria-interna` | 内部审核方案 | iso27001 9.2, tisax 1.5.1, iec62443 SM-12 |
| `revision-independiente` | 安全独立评审 | iso27001 A.5.35, tisax 1.5.2 |
| `cumplimiento-politicas` | 政策与标准合规性检查 | iso27001 A.5.36, tisax 1.5.1, nis2 art.21.2.f |

## 4. 角色与职责

- **内部审计**：独立核查本文件的执行情况。
- **安全负责人**：维护本文件，监督其执行并报告偏差。

## 5. 程序步骤

### 5.1 方案

覆盖所有标准、场所和控制措施的周期。

{{detalle_programa}}

### 5.2 独立性

审核员不得审核自己的工作。

{{detalle_independencia}}

### 5.3 执行

抽样、访谈和证据。

{{detalle_ejecucion}}

### 5.4 报告

审核发现与分级。

{{detalle_informe}}

## 6. 记录与证据

- 年度计划
- 报告

## 7. 违规处理

违反本文件的行为，按 {{empresa}} 的纪律处分流程和不符合项流程处理。

## 8. 变更控制

| 版本 | 日期 | 编写人 | 批准人 | 变更内容 |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | 初始版本 |
