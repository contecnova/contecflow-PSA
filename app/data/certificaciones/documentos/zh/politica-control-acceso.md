# 访问控制政策 — {{empresa}}

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

规定 {{empresa}} 如何依据须知原则和最小权限原则授予、复核和撤销访问权限。

## 2. 范围

适用于 {{empresa}} 的 {{alcance}}，包括以下场所：{{sedes}}。

## 3. 涵盖的控制措施

| 通用控制措施 | 标题 | 对应关系 |
|---|---|---|
| `politica-control-acceso` | 访问控制政策 | iso27001 A.5.15, tisax 4.2.1, nis2 art.21.2.i, iec62443 SPE 6, sox ITGC-APD-00, jsox ITGC-SEG-00 |
| `gestion-identidades` | 身份生命周期 | iso27001 A.5.16, tisax 4.1.1, tisax 4.1.3, iec62443 SR 1.1, iec62443 SR 1.3, iec62443 SR 1.4, iec62443 CR 1.1, iec62443 CR 1.3, iec62443 CR 1.4, iec62443 SG-6 |
| `informacion-autenticacion` | 凭据与口令管理 | iso27001 A.5.17, tisax 4.1.2, iec62443 SR 1.5, iec62443 SR 1.7, iec62443 CR 1.5, iec62443 CR 1.7, sox ITGC-APD-05, jsox ITGC-SEG-05 |
| `autenticacion-segura` | 强身份认证与多因素认证 | iso27001 A.8.5, tisax 4.1.2, nis2 art.21.2.j, iec62443 SR 1.10, iec62443 SR 1.11, iec62443 CR 1.10, iec62443 CR 1.11 |
| `accesos-privilegiados` | 特权访问 | iso27001 A.8.2, tisax 4.2.1, sox ITGC-APD-04, jsox ITGC-SEG-04 |
| `segregacion-funciones` | 职责分离 | iso27001 A.5.3, sox ITGC-APD-06, jsox ITGC-SEG-06 |
| `revision-periodica-accesos` | 访问权限定期复核 | iso27001 A.5.18, tisax 4.2.1, sox ITGC-APD-03, jsox ITGC-SEG-03 |

## 4. 角色与职责

- **安全负责人**：维护本文件，监督其执行并报告偏差。
- **信息技术（IT）部门**：落实技术措施并提供系统证据。
- **流程负责人**：在其流程中执行本文件，并对相应控制措施负责。
- **人力资源部门**：将相关要求纳入人员管理流程。
- **内部审计**：独立核查本文件的执行情况。

## 5. 指导原则

### 5.1 原则

须知原则、最小权限、唯一身份和职责分离。

{{detalle_principios}}

### 5.2 身份认证

按访问类型确定的口令与多因素认证要求（{{politica_mfa}}）。

{{detalle_autenticacion}}

### 5.3 特权访问

临时提权、理由说明和活动记录。

{{detalle_accesos_privilegiados}}

### 5.4 定期评审

按关键程度确定的复核频率（{{frecuencia_recertificacion}}）。

{{detalle_revision_periodica}}

### 5.5 例外

如何申请、批准及到期失效。

{{detalle_excepciones}}

## 6. 记录与证据

- 复核活动
- MFA 覆盖率报告

## 7. 违规处理

违反本文件的行为，按 {{empresa}} 的纪律处分流程和不符合项流程处理。

## 8. 变更控制

| 版本 | 日期 | 编写人 | 批准人 | 变更内容 |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | 初始版本 |
