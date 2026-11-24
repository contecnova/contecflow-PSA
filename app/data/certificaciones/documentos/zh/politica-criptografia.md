# 密码与密钥管理政策 — {{empresa}}

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

规定 {{empresa}} 密钥和证书的算法、长度及生命周期。

## 2. 范围

适用于 {{empresa}} 的 {{alcance}}，包括以下场所：{{sedes}}。

## 3. 涵盖的控制措施

| 通用控制措施 | 标题 | 对应关系 |
|---|---|---|
| `uso-criptografia` | 密码技术使用与密钥管理 | iso27001 A.8.24, tisax 5.1.1, nis2 art.21.2.h, iec62443 SR 4.3, iec62443 CR 4.3 |
| `certificados-y-claves-publicas` | 证书与公钥认证 | iec62443 SR 1.8, iec62443 SR 1.9, iec62443 CR 1.8, iec62443 CR 1.9, iec62443 CR 1.14 |
| `confidencialidad-informacion` | 静态与传输中信息的保密性 | iec62443 SR 4.1, iec62443 CR 4.1 |
| `proteccion-claves-firma` | 产品签名私钥保护 | iso27001 A.8.24, iec62443 SM-8 |

## 4. 角色与职责

- **安全负责人**：维护本文件，监督其执行并报告偏差。
- **信息技术（IT）部门**：落实技术措施并提供系统证据。

## 5. 指导原则

### 5.1 批准的算法

算法清单及最小长度。

{{detalle_algoritmos_aprobados}}

### 5.2 静态与传输加密

在何种情形下强制使用。

{{detalle_cifrado_en_reposo_y_en_transito}}

### 5.3 密钥生命周期

生成、保管、轮换、撤销和销毁。

{{detalle_ciclo_de_vida_de_claves}}

### 5.4 产品签名密钥

HSM 保管与双人访问。

{{detalle_claves_de_firma_del_producto}}

## 6. 记录与证据

- 密钥与证书清单

## 7. 违规处理

违反本文件的行为，按 {{empresa}} 的纪律处分流程和不符合项流程处理。

## 8. 变更控制

| 版本 | 日期 | 编写人 | 批准人 | 变更内容 |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | 初始版本 |
