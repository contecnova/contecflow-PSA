# 可接受使用规则 — {{empresa}}

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

规定 {{empresa}} 信息和资源的正确使用方式。

## 2. 范围

适用于 {{empresa}} 的 {{alcance}}，包括以下场所：{{sedes}}。

## 3. 涵盖的控制措施

| 通用控制措施 | 标题 | 对应关系 |
|---|---|---|
| `uso-aceptable` | 信息和资产的可接受使用 | iso27001 A.5.10 |
| `devolucion-activos` | 资产归还 | iso27001 A.5.11 |
| `mesa-pantalla-limpias` | 桌面整洁与屏幕锁定 | iso27001 A.7.7 |
| `dispositivos-usuario` | 用户终端与移动设备 | iso27001 A.8.1, tisax 3.1.4, iec62443 SR 2.3 |
| `proceso-disciplinario` | 纪律处分流程 | iso27001 A.6.4 |

## 4. 角色与职责

- **安全负责人**：维护本文件，监督其执行并报告偏差。
- **人力资源部门**：将相关要求纳入人员管理流程。
- **信息技术（IT）部门**：落实技术措施并提供系统证据。

## 5. 指导原则

### 5.1 允许和禁止的使用

电子邮件、互联网、即时通讯、个人云存储及未经授权的软件。

{{detalle_uso_permitido_y_prohibido}}

### 5.2 工作场所

桌面整洁与屏幕锁定。

{{detalle_puesto_de_trabajo}}

### 5.3 资产归还

归还什么以及何时归还。

{{detalle_devolucion_de_activos}}

### 5.4 后果

移交纪律处分流程。

{{detalle_consecuencias}}

## 6. 记录与证据

- 每位用户签署的接受确认

## 7. 违规处理

违反本文件的行为，按 {{empresa}} 的纪律处分流程和不符合项流程处理。

## 8. 变更控制

| 版本 | 日期 | 编写人 | 批准人 | 变更内容 |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | 初始版本 |
