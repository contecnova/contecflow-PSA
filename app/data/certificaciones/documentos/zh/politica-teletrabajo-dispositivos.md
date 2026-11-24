# 远程办公与移动设备政策 — {{empresa}}

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

在场所外工作或使用移动设备时保护信息。

## 2. 范围

适用于 {{empresa}} 的 {{alcance}}，包括以下场所：{{sedes}}。

## 3. 涵盖的控制措施

| 通用控制措施 | 标题 | 对应关系 |
|---|---|---|
| `teletrabajo` | 远程办公与移动办公 | iso27001 A.6.7, tisax 2.1.4 |
| `dispositivos-usuario` | 用户终端与移动设备 | iso27001 A.8.1, tisax 3.1.4, iec62443 SR 2.3 |
| `activos-fuera-instalaciones` | 场所外资产 | iso27001 A.7.9, tisax 3.1.4 |
| `soportes-almacenamiento` | 存储介质 | iso27001 A.7.10, tisax 3.1.3, tisax 3.1.4 |

## 4. 角色与职责

- **安全负责人**：维护本文件，监督其执行并报告偏差。
- **信息技术（IT）部门**：落实技术措施并提供系统证据。
- **人力资源部门**：将相关要求纳入人员管理流程。

## 5. 指导原则

### 5.1 远程办公条件

地点、网络连接和环境。

{{detalle_condiciones_del_teletrabajo}}

### 5.2 设备

集中管理、加密和远程擦除。

{{detalle_dispositivos}}

### 5.3 可移动介质

允许的使用与加密。

{{detalle_soportes_extraibles}}

## 6. 记录与证据

- 已分配设备清单

## 7. 违规处理

违反本文件的行为，按 {{empresa}} 的纪律处分流程和不符合项流程处理。

## 8. 变更控制

| 版本 | 日期 | 编写人 | 批准人 | 变更内容 |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | 初始版本 |
