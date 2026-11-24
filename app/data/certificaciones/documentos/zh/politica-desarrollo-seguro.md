# 安全开发政策 — {{empresa}}

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

将安全融入 {{empresa}} 所开发软件和设备的生命周期。

## 2. 范围

适用于 {{empresa}} 的 {{alcance}}，包括以下场所：{{sedes}}。

## 3. 涵盖的控制措施

| 通用控制措施 | 标题 | 对应关系 |
|---|---|---|
| `ciclo-desarrollo-seguro` | 安全开发生命周期 | iso27001 A.8.25, tisax 5.3.1, nis2 art.21.2.e, iec62443 SM-1, sox ITGC-PD-01, jsox ITGC-DES-01 |
| `requisitos-seguridad-aplicaciones` | 应用程序与产品的安全要求 | iso27001 A.8.26, tisax 5.3.1, iec62443 SR-3, iec62443 SR-4, iec62443 SR-5 |
| `codificacion-segura` | 安全编码 | iso27001 A.8.28, iec62443 SI-2 |
| `pruebas-seguridad` | 开发与验收中的安全测试 | iso27001 A.8.29, iec62443 SVV-1, iec62443 SVV-2, iec62443 SVV-3 |
| `separacion-entornos` | 环境分离与开发环境安全 | iso27001 A.8.31, tisax 5.2.2, iec62443 SM-7, sox ITGC-PC-04, jsox ITGC-DES-04 |
| `aprobacion-independiente-paso-produccion` | 生产发布的独立批准 | iso27001 A.8.32, sox ITGC-PC-03, sox ITGC-PD-04, jsox ITGC-DES-05 |
| `sbom-y-versiones-firmadas` | SBOM 及已标记并签名的版本 | iec62443 SM-9, iec62443 SUM-3 |

## 4. 角色与职责

- **流程负责人**：在其流程中执行本文件，并对相应控制措施负责。
- **安全负责人**：维护本文件，监督其执行并报告偏差。
- **信息技术（IT）部门**：落实技术措施并提供系统证据。
- **内部审计**：独立核查本文件的执行情况。

## 5. 指导原则

### 5.1 流程

生命周期各阶段及各阶段的安全实践。

{{detalle_proceso}}

### 5.2 要求与威胁

安全要求与威胁建模。

{{detalle_requisitos_y_amenazas}}

### 5.3 按版本独立评审

编写变更者不得批准其投入生产。

{{detalle_revision_independiente_por_version}}

### 5.4 测试

静态分析、依赖项检查、安全测试和渗透测试。

{{detalle_pruebas}}

### 5.5 发布

每个版本的 SBOM、标记和签名。

{{detalle_publicacion}}

## 6. 记录与证据

- 各版本的评审证据
- SBOM

## 7. 违规处理

违反本文件的行为，按 {{empresa}} 的纪律处分流程和不符合项流程处理。

## 8. 变更控制

| 版本 | 日期 | 编写人 | 批准人 | 变更内容 |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | 初始版本 |
