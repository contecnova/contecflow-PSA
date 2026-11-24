# 备份与恢复程序 — {{empresa}}

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

说明如何进行备份、保护备份并测试备份。

## 2. 范围

适用于 {{empresa}} 的 {{alcance}}，包括以下场所：{{sedes}}。

## 3. 涵盖的控制措施

| 通用控制措施 | 标题 | 对应关系 |
|---|---|---|
| `copias-seguridad` | 备份与恢复 | iso27001 A.8.13, tisax 5.2.9, nis2 art.21.2.c, iec62443 SR 7.3, iec62443 CR 7.3, sox ITGC-CO-03, jsox ITGC-OPE-03 |
| `preparacion-tic-continuidad` | IT 与 OT 的业务连续性与恢复 | iso27001 A.5.30, tisax 5.2.8, nis2 art.21.2.c, iec62443 SR 7.4, iec62443 CR 7.4, iec62443 SPE 8, sox ITGC-CO-04, jsox ITGC-OPE-04 |

## 4. 角色与职责

- **信息技术（IT）部门**：落实技术措施并提供系统证据。
- **运营技术（OT）部门**：在工厂和自动化系统中落实相关措施。

## 5. 程序步骤

### 5.1 备份政策

保存什么、何时保存以及保存多久。

{{detalle_politica_de_copias}}

### 5.2 保护

加密与隔离副本。

{{detalle_proteccion}}

### 5.3 恢复测试

频率与标准。

{{detalle_pruebas_de_restauracion}}

## 6. 记录与证据

- 备份报告
- 恢复测试

## 7. 违规处理

违反本文件的行为，按 {{empresa}} 的纪律处分流程和不符合项流程处理。

## 8. 变更控制

| 版本 | 日期 | 编写人 | 批准人 | 变更内容 |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | 初始版本 |
