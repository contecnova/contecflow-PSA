# 培训与意识记录 — {{empresa}}

| 字段 | 值 |
|---|---|
| 类型 | 记录 |
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

记录每个人接受的培训。

## 2. 范围

适用于 {{empresa}} 的 {{alcance}}，包括以下场所：{{sedes}}。

## 3. 涵盖的控制措施

| 通用控制措施 | 标题 | 对应关系 |
|---|---|---|
| `formacion-concienciacion` | 培训与意识 | iso27001 7.3, iso27001 A.6.3, tisax 2.1.3, nis2 art.21.2.g, iec62443 SPE 1 |
| `formacion-ciberseguridad-direccion` | 管理机构网络安全培训 | nis2 art.20.2 |
| `formacion-proteccion-prototipos` | 原型件相关员工培训与承诺 | tisax 8.2.3 |

## 4. 角色与职责

- **人力资源部门**：将相关要求纳入人员管理流程。

## 5. 记录字段

| 字段 | 说明 | 必填 |
|---|---|---|
| 人员 | 标识符 | 是 |
| 培训项目 | 标题 | 是 |
| 日期 | 实施日期 | 是 |
| 结果 | 评估 | 是 |
| 到期 | 续期日期 | 是 |

## 6. 保存与访问

- 保存期限：{{plazo_retencion}}；适用时受法律保全约束。
- 内部审计和经门户授权的外部审计人员享有只读访问权限。
- 所有修改均记入平台审计日志。

## 7. 变更控制

| 版本 | 日期 | 编写人 | 批准人 | 变更内容 |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | 初始版本 |
