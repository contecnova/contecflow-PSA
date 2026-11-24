# 自动化系统安全政策 — {{empresa}}

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

建立 {{empresa}} 工厂和自动化系统的安全方案。

## 2. 范围

适用于 {{empresa}} 的 {{alcance}}，包括以下场所：{{sedes}}。涵盖 {{plantas_ot}} 中列出的工厂和自动化系统。

## 3. 涵盖的控制措施

| 通用控制措施 | 标题 | 对应关系 |
|---|---|---|
| `programa-seguridad-ot` | 自动化系统安全方案 | iec62443 SPE 1 |
| `zonas-y-conductos` | 区域与管道 | iec62443 ZCR 3, iec62443 SPE 3 |
| `nivel-seguridad-objetivo-por-zona` | 各区域的目标安全等级 | iec62443 ZCR 5, iec62443 ZCR 6 |
| `acceso-redes-no-confiables` | 来自不可信网络的访问 | iec62443 SR 1.13, iec62443 NDR 1.13 |
| `gestion-eventos-ot` | 工厂事件与事故管理 | iec62443 SPE 7 |

## 4. 角色与职责

- **管理层**：批准本文件并分配所需资源。
- **运营技术（OT）部门**：在工厂和自动化系统中落实相关措施。
- **安全负责人**：维护本文件，监督其执行并报告偏差。
- **信息技术（IT）部门**：落实技术措施并提供系统证据。

## 5. 指导原则

### 5.1 OT 组织

各工厂的责任人及其与公司安全部门的关系。

{{detalle_organizacion_ot}}

### 5.2 区域与管道

区域划分标准及各区域的目标 SL。

{{detalle_zonas_y_conductos}}

### 5.3 远程访问

供应商访问的条件与批准。

{{detalle_acceso_remoto}}

### 5.4 变更与补丁

维护窗口与事前测试。

{{detalle_cambios_y_parches}}

### 5.5 工厂事件

与公司级响应协调。

{{detalle_incidentes_en_planta}}

## 6. 记录与证据

- 区域与 SL 记录

## 7. 违规处理

违反本文件的行为，按 {{empresa}} 的纪律处分流程和不符合项流程处理。

## 8. 变更控制

| 版本 | 日期 | 编写人 | 批准人 | 变更内容 |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | 初始版本 |
