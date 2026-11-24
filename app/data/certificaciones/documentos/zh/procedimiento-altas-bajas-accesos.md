# 访问权限开通、变更与注销程序 — {{empresa}}

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

说明如何申请、批准、开通和撤销访问权限。

## 2. 范围

适用于 {{empresa}} 的 {{alcance}}，包括以下场所：{{sedes}}。

## 3. 涵盖的控制措施

| 通用控制措施 | 标题 | 对应关系 |
|---|---|---|
| `alta-modificacion-accesos` | 经批准的访问权限开通与变更 | iso27001 A.5.18, tisax 4.2.1, sox ITGC-APD-01, jsox ITGC-SEG-01 |
| `baja-accesos` | 及时撤销访问权限 | iso27001 A.5.18, sox ITGC-APD-02, jsox ITGC-SEG-02 |
| `gestion-identidades` | 身份生命周期 | iso27001 A.5.16, tisax 4.1.1, tisax 4.1.3, iec62443 SR 1.1, iec62443 SR 1.3, iec62443 SR 1.4, iec62443 CR 1.1, iec62443 CR 1.3, iec62443 CR 1.4, iec62443 SG-6 |
| `cuentas-servicio-y-dispositivos` | 服务账户、通用账户和设备账户 | iec62443 SR 1.2, iec62443 CR 1.2, sox ITGC-APD-08, jsox ITGC-SEG-08 |

## 4. 角色与职责

- **信息技术（IT）部门**：落实技术措施并提供系统证据。
- **流程负责人**：在其流程中执行本文件，并对相应控制措施负责。
- **人力资源部门**：将相关要求纳入人员管理流程。

## 5. 程序步骤

### 5.1 申请与批准

由谁申请、由谁批准。

{{detalle_solicitud_y_aprobacion}}

### 5.2 应用

时限与检查。

{{detalle_aplicacion}}

### 5.3 岗位变动与离职

由人力资源部门触发及最长期限（{{plazo_baja}}）。

{{detalle_cambio_de_puesto_y_baja}}

### 5.4 服务账户

机密信息的责任人与轮换。

{{detalle_cuentas_de_servicio}}

## 6. 记录与证据

- 已批准的申请
- 离职注销报告

## 7. 违规处理

违反本文件的行为，按 {{empresa}} 的纪律处分流程和不符合项流程处理。

## 8. 变更控制

| 版本 | 日期 | 编写人 | 批准人 | 变更内容 |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | 初始版本 |
