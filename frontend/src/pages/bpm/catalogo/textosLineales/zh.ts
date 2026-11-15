// Textos de los procesos lineales del catálogo BPM — zh. Misma forma en los tres
// idiomas (ver tipos.ts): nombre, descripción y un texto por paso. 
import type { TextosLineales } from '../tipos'

const textos: TextosLineales = {
  "ticket_assignment_ml": {
    "name": "智能分配（ML）",
    "description": "将工单自动路由给最合适的处理人。",
    "steps": [
      "工单已创建",
      "提取特征",
      "预测处理人",
      "校验负载",
      "分配"
    ]
  },
  "auto_resolution": {
    "name": "自动解决",
    "description": "由 AI 建议并自动应用解决方案。",
    "steps": [
      "工单进入",
      "查找相似工单",
      "置信度评分",
      "建议回复",
      "自动关闭"
    ]
  },
  "alert_correlation": {
    "name": "告警关联",
    "description": "将相关告警归并为单个事件。",
    "steps": [
      "告警进入",
      "查找关联",
      "归并",
      "创建父事件",
      "通知"
    ]
  },
  "voice_agent_ivr": {
    "name": "语音助手 / IVR",
    "description": "支持场景下语音助手的对话流程。",
    "steps": [
      "来电进入",
      "识别用户",
      "意图识别",
      "解决 / 升级",
      "结束通话"
    ]
  },
  "multichannel_intake": {
    "name": "多渠道受理",
    "description": "接收来自邮件、聊天、门户和移动端的工单。",
    "steps": [
      "消息进入",
      "统一渠道格式",
      "提取数据",
      "创建工单",
      "确认"
    ]
  },
  "escalation_routing": {
    "name": "升级",
    "description": "按 SLA、优先级和值班制定的升级规则。",
    "steps": [
      "阈值检查",
      "确定目标",
      "通知",
      "重新分配",
      "审计"
    ]
  },
  "sla_monitoring": {
    "name": "SLA 监控",
    "description": "持续监控工单的 SLA 期限。",
    "steps": [
      "工单开启",
      "正常",
      "有风险",
      "违约",
      "上报"
    ]
  },
  "oncall_scheduling": {
    "name": "值班排班",
    "description": "值班的轮换与分配。",
    "steps": [
      "定义轮换",
      "分配班次",
      "通知",
      "启动值班",
      "结束班次"
    ]
  },
  "cab_review": {
    "name": "CAB 委员会",
    "description": "CAB 评审与批准会议。",
    "steps": [
      "待处理变更",
      "召集 CAB",
      "讨论",
      "投票",
      "记录决定"
    ]
  },
  "change_impact_analysis": {
    "name": "影响分析",
    "description": "评估对 CMDB 和服务的影响。",
    "steps": [
      "拟议变更",
      "识别受影响的 CI",
      "计算风险",
      "记录",
      "附加到 RFC"
    ]
  },
  "change_rollout": {
    "name": "分阶段部署",
    "description": "带检查点的分阶段发布。",
    "steps": [
      "已批准",
      "试点",
      "第 1 批",
      "第 2 批",
      "生产",
      "收尾"
    ]
  },
  "rca_wizard": {
    "name": "RCA 助手",
    "description": "引导式根本原因调查（5 个为什么）。",
    "steps": [
      "定义问题",
      "收集数据",
      "5 个为什么",
      "根本原因",
      "行动计划"
    ]
  },
  "kedb_lookup": {
    "name": "已知错误库",
    "description": "查询并推荐现有解决方案。",
    "steps": [
      "发现症状",
      "搜索 KEDB",
      "匹配得分",
      "应用临时方案",
      "反馈"
    ]
  },
  "kb_authoring": {
    "name": "知识库文章创作",
    "description": "知识库文章的编辑流程。",
    "steps": [
      "草稿",
      "评审",
      "已发布",
      "维护",
      "已归档"
    ]
  },
  "smart_catalog": {
    "name": "智能目录",
    "description": "带情境推荐的服务目录。",
    "steps": [
      "客户搜索",
      "AI 推荐",
      "选择",
      "申请",
      "跟踪"
    ]
  },
  "project_lifecycle": {
    "name": "项目生命周期",
    "description": "项目从规划到关闭的状态。",
    "steps": [
      "规划",
      "进行中",
      "搁置",
      "暂停",
      "已完成",
      "已关闭"
    ]
  },
  "task_workflow": {
    "name": "任务工作流",
    "description": "敏捷任务的标准状态。",
    "steps": [
      "待办池",
      "待处理",
      "进行中",
      "受阻",
      "评审",
      "完成"
    ]
  },
  "project_phase": {
    "name": "项目阶段",
    "description": "各阶段里程碑及阶段关口审批。",
    "steps": [
      "启动",
      "设计",
      "构建",
      "测试",
      "验收",
      "收尾"
    ]
  },
  "task_auto_assignment": {
    "name": "任务自动分配",
    "description": "由 ML 将任务分配给最合适的团队成员。",
    "steps": [
      "任务已创建",
      "提取所需技能",
      "按用户评分",
      "产能",
      "分配"
    ]
  },
  "multi_level_approval": {
    "name": "多级审批",
    "description": "带升级和委派的审批链。",
    "steps": [
      "申请",
      "一级",
      "二级",
      "最终决定",
      "通知"
    ]
  },
  "invoice_workflow": {
    "name": "发票工作流",
    "description": "发票的开具、发送与对账。",
    "steps": [
      "草稿",
      "已开具",
      "已发送",
      "已付款",
      "已关闭"
    ]
  },
  "churn_prediction": {
    "name": "流失预测",
    "description": "及早发现有流失风险的客户。",
    "steps": [
      "收集特征",
      "ML 推理",
      "评分",
      "通知 CSM",
      "挽留计划"
    ]
  },
  "anomaly_detection": {
    "name": "登录异常检测",
    "description": "识别异常的访问模式。",
    "steps": [
      "登录事件",
      "基线检查",
      "异常评分",
      "通知安全运营",
      "拦截"
    ]
  },
  "revenue_forecast": {
    "name": "收入预测",
    "description": "基于销售管道的收入预测。",
    "steps": [
      "管道快照",
      "商机加权",
      "预测模型",
      "生成预测",
      "发布"
    ]
  },
  "incident_predictions": {
    "name": "事件预测",
    "description": "预测 MTTR 和工单量。",
    "steps": [
      "历史数据",
      "训练",
      "推理",
      "仪表盘",
      "重新训练"
    ]
  },
  "semantic_feedback": {
    "name": "语义反馈闭环",
    "description": "基于用户反馈的持续学习。",
    "steps": [
      "AI 预测",
      "接收反馈",
      "标注",
      "重新训练",
      "部署 v+1"
    ]
  },
  "project_overrun_ml": {
    "name": "超支预测",
    "description": "用 ML 预判项目偏差。",
    "steps": [
      "项目快照",
      "推理",
      "风险",
      "通知项目经理",
      "缓解"
    ]
  },
  "resource_forecast": {
    "name": "资源预测",
    "description": "产能与需求的预测。",
    "steps": [
      "当前产能",
      "预期需求",
      "缺口分析",
      "人员配置计划",
      "发布"
    ]
  },
  "training_plan": {
    "name": "培训计划",
    "description": "课程的分配与跟踪。",
    "steps": [
      "发现缺口",
      "分配课程",
      "进行中",
      "已完成",
      "已认证"
    ]
  },
  "onboarding": {
    "name": "员工入职",
    "description": "入职与初始培训。",
    "steps": [
      "入职前",
      "第 1 天",
      "第 1 周",
      "第 1 个月",
      "转正确认"
    ]
  },
  "governance_compliance": {
    "name": "治理合规",
    "description": "定期核查治理控制措施。",
    "steps": [
      "定义控制",
      "审计",
      "发现项",
      "整改",
      "关闭"
    ]
  },
  "esign_workflow": {
    "name": "电子签名",
    "description": "文档的签署请求、签署与归档。",
    "steps": [
      "准备",
      "发送签署",
      "已签署",
      "归档",
      "通知"
    ]
  },
  "uat_acceptance": {
    "name": "UAT — 用户验收测试",
    "description": "客户对交付物的验收。",
    "steps": [
      "UAT 计划",
      "执行",
      "缺陷",
      "复测",
      "已验收"
    ]
  },
  "workflow_blueprint": {
    "name": "工作流蓝图",
    "description": "服务台声明式工作流的可视化设计。",
    "steps": [
      "草稿",
      "编译规则",
      "发布",
      "使用中",
      "已归档"
    ]
  },
  "automation_workflow": {
    "name": "自动化工作流",
    "description": "触发器 + 条件 + 程序化动作。",
    "steps": [
      "草稿",
      "已启用",
      "已触发",
      "已暂停",
      "已归档"
    ]
  },
  "data_import": {
    "name": "数据导入",
    "description": "批量上传 CSV / Excel。",
    "steps": [
      "上传文件",
      "校验",
      "处理中",
      "已完成",
      "报告"
    ]
  },
  "jira_sync": {
    "name": "Jira 同步",
    "description": "与 Jira 的持续双向同步。",
    "steps": [
      "拉取 Jira",
      "比对差异",
      "推送本地",
      "对账",
      "下一周期"
    ]
  },
  "etl_pipeline": {
    "name": "ETL 管道",
    "description": "向数据仓库抽取、转换并加载数据。",
    "steps": [
      "抽取",
      "转换",
      "校验",
      "加载",
      "质量检查"
    ]
  },
  "data_governance_review": {
    "name": "数据治理评审",
    "description": "数据集和访问策略的审批。",
    "steps": [
      "编目",
      "分类",
      "审批",
      "已发布",
      "审计"
    ]
  }
}

export default textos
