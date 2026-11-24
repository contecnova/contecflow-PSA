# 控制测试程序（SOX 与 J-SOX） — {{empresa}}

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

说明如何测试控制措施的设计和运行有效性。

## 2. 范围

适用于 {{empresa}} 的 {{alcance}}，包括以下场所：{{sedes}}。

## 3. 涵盖的控制措施

| 通用控制措施 | 标题 | 对应关系 |
|---|---|---|
| `evaluacion-direccion-control-interno` | 管理层对财务报告内部控制的评估 | sox Sec.404(a), jsox FIEA-24-4-4 |
| `evaluacion-deficiencias-control` | 控制缺陷的评价与沟通 | sox ELC-04, jsox ELC-04 |
| `controles-aplicacion` | 应用程序自动化控制 | sox ITAC-01, jsox ITAC-01 |
| `independencia-probadores` | 测试人员的独立性 | iec62443 SVV-5 |

## 4. 角色与职责

- **内部审计**：独立核查本文件的执行情况。
- **财务部门**：负责财务信息相关控制措施。
- **流程负责人**：在其流程中执行本文件，并对相应控制措施负责。

## 5. 程序步骤

### 5.1 设计测试

穿行测试及设计的充分性。

{{detalle_prueba_de_diseno}}

### 5.2 有效性测试

总体、依据控制频率确定的样本量及结果。

{{detalle_prueba_de_eficacia}}

### 5.3 独立性

测试人员不得是该控制措施的实施者或执行者。

{{detalle_independencia}}

### 5.4 缺陷

评价与汇总。

{{detalle_deficiencias}}

## 6. 记录与证据

- 测试工作底稿

## 7. 违规处理

违反本文件的行为，按 {{empresa}} 的纪律处分流程和不符合项流程处理。

## 8. 变更控制

| 版本 | 日期 | 编写人 | 批准人 | 变更内容 |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | 初始版本 |
