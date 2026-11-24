# 供应商安全政策 — {{empresa}}

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

确保 {{empresa}} 的供应商按其关键程度保护信息和服务。

## 2. 范围

适用于 {{empresa}} 的 {{alcance}}，包括以下场所：{{sedes}}。

## 3. 涵盖的控制措施

| 通用控制措施 | 标题 | 对应关系 |
|---|---|---|
| `seguridad-proveedores` | 供应商关系中的安全 | iso27001 A.5.19, tisax 6.1.1, nis2 art.21.2.d, iec62443 SPE 1 |
| `acuerdos-proveedores` | 合同中的安全要求 | iso27001 A.5.20, tisax 1.2.4, tisax 6.1.1, nis2 art.21.2.d |
| `cadena-suministro-tic` | ICT 供应链安全 | iso27001 A.5.21, nis2 art.21.2.d, nis2 art.21.3, iec62443 SM-9 |
| `seguimiento-proveedores` | 供应商服务监控与鉴证报告 | iso27001 A.5.22, tisax 6.1.1, sox ITGC-CO-05, jsox ITGC-EXT-01 |
| `servicios-nube` | 云服务与外部服务的安全使用 | iso27001 A.5.23, tisax 1.3.3, tisax 5.3.3, tisax 5.3.4 |

## 4. 角色与职责

- **合规负责人**：统筹证据并协调其与各项标准的对应关系。
- **安全负责人**：维护本文件，监督其执行并报告偏差。
- **财务部门**：负责财务信息相关控制措施。
- **供应商**：满足合同要求并提供其鉴证报告。

## 5. 指导原则

### 5.1 供应商分类

关键程度标准，包括直接 ICT 供应商。

{{detalle_clasificacion_de_proveedores}}

### 5.2 事前评估

调查问卷、TISAX 标签、证书和 SOC 报告。

{{detalle_evaluacion_previa}}

### 5.3 合同条款

安全、保密、事件通报、审计和退出。

{{detalle_clausulas_contractuales}}

### 5.4 跟踪

服务的定期评审与变更管理。

{{detalle_seguimiento}}

### 5.5 退出

信息的归还与删除。

{{detalle_salida}}

## 6. 记录与证据

- 关键供应商记录
- 评估

## 7. 违规处理

违反本文件的行为，按 {{empresa}} 的纪律处分流程和不符合项流程处理。

## 8. 变更控制

| 版本 | 日期 | 编写人 | 批准人 | 变更内容 |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | 初始版本 |
