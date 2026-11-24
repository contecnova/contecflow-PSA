# 脆弱性管理程序 — {{empresa}}

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

说明如何检测 IT 和 OT 中的技术脆弱性、确定其优先级并加以修复。

## 2. 范围

适用于 {{empresa}} 的 {{alcance}}，包括以下场所：{{sedes}}。

## 3. 涵盖的控制措施

| 通用控制措施 | 标题 | 对应关系 |
|---|---|---|
| `gestion-vulnerabilidades-tecnicas` | 技术脆弱性管理 | iso27001 A.8.8, tisax 5.2.5, nis2 art.21.2.e, iec62443 SPE 4, iec62443 SPE 8 |
| `inteligencia-amenazas` | 威胁情报 | iso27001 A.5.7, nis2 art.21.2.e |
| `pruebas-intrusion` | 渗透测试 | iso27001 A.8.8, iso27001 A.8.29, iec62443 SVV-4 |

## 4. 角色与职责

- **信息技术（IT）部门**：落实技术措施并提供系统证据。
- **运营技术（OT）部门**：在工厂和自动化系统中落实相关措施。
- **安全负责人**：维护本文件，监督其执行并报告偏差。

## 5. 程序步骤

### 5.1 检测

扫描、厂商公告和威胁情报。

{{detalle_deteccion}}

### 5.2 优先级排序

按严重程度确定的时限（{{plazos_parcheo}}）。

{{detalle_priorizacion}}

### 5.3 OT 环境整改

维护窗口与补偿措施。

{{detalle_correccion_en_ot}}

### 5.4 例外

设有有效期的风险接受。

{{detalle_excepciones}}

## 6. 记录与证据

- 扫描报告
- 实测时限

## 7. 违规处理

违反本文件的行为，按 {{empresa}} 的纪律处分流程和不符合项流程处理。

## 8. 变更控制

| 版本 | 日期 | 编写人 | 批准人 | 变更内容 |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | 初始版本 |
