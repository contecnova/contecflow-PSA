# 会计期间关账程序 — {{empresa}}

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

说明 {{empresa}} 的会计期间关账以及关账后对修改的锁定。

## 2. 范围

适用于 {{empresa}} 的 {{alcance}}，包括以下场所：{{sedes}}。

## 3. 涵盖的控制措施

| 通用控制措施 | 标题 | 对应关系 |
|---|---|---|
| `cierre-periodos-contables` | 会计期间关账 | sox FC-01, jsox FCRP-01 |
| `asientos-manuales` | 手工记账凭证 | sox FC-02, jsox FCRP-02 |
| `conciliaciones-cuentas` | 账户对账 | sox FC-03, jsox FCRP-03 |
| `hojas-calculo-criticas` | 关键电子表格与终端用户工具 | sox FC-04, jsox FCRP-04 |
| `informacion-generada-por-entidad` | 系统报告的准确性与完整性 | sox FC-05, jsox FCRP-05 |

## 4. 角色与职责

- **财务部门**：负责财务信息相关控制措施。
- **信息技术（IT）部门**：落实技术措施并提供系统证据。
- **内部审计**：独立核查本文件的执行情况。

## 5. 程序步骤

### 5.1 关账日程

各实体的里程碑。

{{detalle_calendario_de_cierre}}

### 5.2 手工记账凭证

编制、审核和批准由不同人员完成。

{{detalle_asientos_manuales}}

### 5.3 对账

账户与频率。

{{detalle_conciliaciones}}

### 5.4 锁定与重新开启

对任何重新开启的授权与登记。

{{detalle_bloqueo_y_reapertura}}

## 6. 记录与证据

- 日程
- 重新开启记录

## 7. 违规处理

违反本文件的行为，按 {{empresa}} 的纪律处分流程和不符合项流程处理。

## 8. 变更控制

| 版本 | 日期 | 编写人 | 批准人 | 变更内容 |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | 初始版本 |
