# 业务连续性与恢复政策 — {{empresa}}

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

确保 {{empresa}} 以必要的安全水平维持并恢复其关键服务。

## 2. 范围

适用于 {{empresa}} 的 {{alcance}}，包括以下场所：{{sedes}}。

## 3. 涵盖的控制措施

| 通用控制措施 | 标题 | 对应关系 |
|---|---|---|
| `preparacion-tic-continuidad` | IT 与 OT 的业务连续性与恢复 | iso27001 A.5.30, tisax 5.2.8, nis2 art.21.2.c, iec62443 SR 7.4, iec62443 CR 7.4, iec62443 SPE 8, sox ITGC-CO-04, jsox ITGC-OPE-04 |
| `seguridad-durante-interrupcion` | 中断期间的安全 | iso27001 A.5.29, nis2 art.21.2.c |
| `gestion-crisis` | 危机管理 | tisax 1.6.3, nis2 art.21.2.c |
| `copias-seguridad` | 备份与恢复 | iso27001 A.8.13, tisax 5.2.9, nis2 art.21.2.c, iec62443 SR 7.3, iec62443 CR 7.3, sox ITGC-CO-03, jsox ITGC-OPE-03 |
| `redundancia` | 处理设施冗余 | iso27001 A.8.14, tisax 5.2.8 |

## 4. 角色与职责

- **管理层**：批准本文件并分配所需资源。
- **信息技术（IT）部门**：落实技术措施并提供系统证据。
- **运营技术（OT）部门**：在工厂和自动化系统中落实相关措施。
- **流程负责人**：在其流程中执行本文件，并对相应控制措施负责。

## 5. 指导原则

### 5.1 影响分析

关键服务、RTO 和 RPO。

{{detalle_analisis_de_impacto}}

### 5.2 策略

冗余、备份和备用站点。

{{detalle_estrategias}}

### 5.3 危机管理

委员会、启动与沟通。

{{detalle_gestion_de_crisis}}

### 5.4 测试

日程与成功标准。

{{detalle_pruebas}}

## 6. 记录与证据

- BIA
- 测试报告

## 7. 违规处理

违反本文件的行为，按 {{empresa}} 的纪律处分流程和不符合项流程处理。

## 8. 变更控制

| 版本 | 日期 | 编写人 | 批准人 | 变更内容 |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | 初始版本 |
