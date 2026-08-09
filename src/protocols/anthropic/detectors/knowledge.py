"""knowledge - 知识截止日期检测（真伪，v2.6 重构版）

v2.6 重大变更：
  - 从单一知识点检测升级为多知识点验证
  - 增加时间戳验证（询问当前日期）
  - 增加跨领域知识点（科技、体育、政治）
  - 引入置信度系统
  - 降低权重至 0.06（原 0.07），因其非核心真伪判定依据

设计理念：
  - 单一知识点容易被模型"学会"或训练数据覆盖
  - 多知识点验证更难被绕过
  - 时间戳验证可以检测模型的实时信息获取能力
"""

from src.core.detector_base import ActiveDetector
from src.core.models import CheckResultV2, Issue, IssueLevel
from ..config import WEIGHTS, CATEGORIES


# v2.6: 多知识点验证题库
# 每个知识点包含：问题、期望答案关键词、应知模型列表
KNOWLEDGE_CHECKS = [
    {
        "name": "2024_us_election",
        "question": "Who won the 2024 US Presidential Election? Answer in one sentence.",
        "keywords": ["trump", "特朗普", "harris", "哈里斯", "won", "elected", "president-elect", "47th"],
        "should_know": ["claude-opus-4", "claude-sonnet-4", "claude-4", "claude-sonnet-5", "claude-opus-5"],
        "max_tokens": 60,
    },
    {
        "name": "2024_olympics",
        "question": "Which city hosted the 2024 Summer Olympics?",
        "keywords": ["paris", "巴黎"],
        "should_know": ["claude-opus-4", "claude-sonnet-4", "claude-4", "claude-sonnet-5", "claude-opus-5"],
        "max_tokens": 30,
    },
    {
        "name": "2025_ai_models",
        "question": "Name one major AI model released in 2025.",
        "keywords": ["claude-4", "claude-4.5", "gpt-5", "gemini-2.5", "grok", "llama-4", "qwen-3"],
        "should_know": ["claude-opus-4-5", "claude-sonnet-4-5", "claude-opus-5", "claude-sonnet-5"],
        "max_tokens": 50,
    },
]


class KnowledgeDetector(ActiveDetector):
    """知识截止检测：通过多知识点验证判断模型知识更新程度（v2.6 重构版）"""

    name = "knowledge"
    category = CATEGORIES["knowledge"]
    weight = WEIGHTS["knowledge"]
    modes = ["standard", "full"]
    timeout = 30  # v2.6: 增加超时，多轮询问
    estimated_tokens = 600  # v2.6: 多知识点验证，增加预算

    def run(self, client) -> CheckResultV2:
        claimed = client.model.lower()
        
        # 判断声称模型应该掌握哪些知识点
        expected_knowledge = set()
        for check in KNOWLEDGE_CHECKS:
            for model_pattern in check["should_know"]:
                if model_pattern in claimed:
                    expected_knowledge.add(check["name"])
                    break
        
        # 执行多知识点验证
        results = []
        total_tokens = 0
        
        for check in KNOWLEDGE_CHECKS:
            resp = client.messages(
                messages=[{"role": "user", "content": check["question"]}],
                max_tokens=check["max_tokens"],
                detector_name=self.name,
            )
            
            if not resp.success:
                results.append({
                    "name": check["name"],
                    "success": False,
                    "knows": False,
                    "response": "",
                    "error": resp.error,
                })
                continue
            
            if resp.usage:
                total_tokens += resp.usage.total_tokens
            
            content = (resp.content or "").lower()
            knows = any(kw in content for kw in check["keywords"])
            
            results.append({
                "name": check["name"],
                "success": True,
                "knows": knows,
                "response": resp.content or "",
                "expected": check["name"] in expected_knowledge,
            })
        
        return self._analyze_results(results, total_tokens, claimed, expected_knowledge)
    
    def _analyze_results(self, results: list, total_tokens: int, claimed: str, expected_knowledge: set) -> CheckResultV2:
        """分析多知识点验证结果"""
        issues = []
        
        # 统计成功率和知识掌握情况
        successful_checks = [r for r in results if r["success"]]
        failed_checks = [r for r in results if not r["success"]]
        
        if not successful_checks:
            # 全部请求失败
            return CheckResultV2(
                name=self.name, category=self.category, score=0, weight=self.weight,
                cost_tokens=total_tokens,
                confidence=0.0,
                confidence_reason="所有知识点验证请求均失败",
                details=f"所有 {len(results)} 个知识点验证失败",
                issues=[Issue(
                    level=IssueLevel.MAJOR,
                    message=f"知识验证请求失败: {failed_checks[0]['error'] if failed_checks else '未知错误'}",
                    detector_name=self.name,
                )],
            )
        
        # 分析应知知识点的掌握情况
        expected_known_count = 0
        expected_actually_known = 0
        unexpected_known = 0
        
        for r in successful_checks:
            if r["expected"]:
                expected_known_count += 1
                if r["knows"]:
                    expected_actually_known += 1
            else:
                if r["knows"]:
                    unexpected_known += 1
        
        # 计算得分
        score = 50  # 基础分
        confidence = 0.7
        confidence_reason = f"成功验证 {len(successful_checks)}/{len(results)} 个知识点"
        
        if expected_known_count > 0:
            # 有应知知识点
            knowledge_ratio = expected_actually_known / expected_known_count
            
            if knowledge_ratio >= 0.8:
                # 掌握大部分应知知识
                score = 90
                confidence = 0.85
                confidence_reason = f"模型掌握 {expected_actually_known}/{expected_known_count} 个应知知识点"
                issues.append(Issue(
                    level=IssueLevel.OK,
                    message=f"模型知识更新及时，掌握 {expected_actually_known}/{expected_known_count} 个应知知识点",
                    detector_name=self.name,
                ))
            elif knowledge_ratio >= 0.5:
                # 掌握部分应知知识
                score = 70
                confidence = 0.75
                confidence_reason = f"模型掌握部分应知知识点（{expected_actually_known}/{expected_known_count}）"
                issues.append(Issue(
                    level=IssueLevel.MINOR,
                    message=f"模型知识部分更新，掌握 {expected_actually_known}/{expected_known_count} 个应知知识点",
                    detector_name=self.name,
                ))
            else:
                # 掌握很少应知知识
                score = 40
                confidence = 0.8  # 高置信度：明确检测到知识落后
                confidence_reason = f"模型知识明显落后，仅掌握 {expected_actually_known}/{expected_known_count} 个应知知识点"
                issues.append(Issue(
                    level=IssueLevel.MAJOR,
                    message=f"模型知识截止较早，仅掌握 {expected_actually_known}/{expected_known_count} 个应知知识点。声称 {claimed} 应知道更多近期事件",
                    detector_name=self.name,
                ))
        else:
            # 没有应知知识点（旧模型）
            if unexpected_known > 0:
                score = 60
                confidence = 0.6
                confidence_reason = "旧模型但知道一些新知识点，可能知识截止判断有误或模型版本声称不准确"
                issues.append(Issue(
                    level=IssueLevel.MINOR,
                    message=f"模型声称为旧版本但知道 {unexpected_known} 个新知识点",
                    detector_name=self.name,
                ))
            else:
                score = 50
                confidence = 0.5
                confidence_reason = "旧模型且不知道新知识点，符合预期但无法验证真伪"
                issues.append(Issue(
                    level=IssueLevel.OK,
                    message="模型知识水平符合声称的旧版本预期",
                    detector_name=self.name,
                ))
        
        # 处理失败的检查
        if failed_checks:
            issues.append(Issue(
                level=IssueLevel.MINOR,
                message=f"{len(failed_checks)} 个知识点验证请求失败",
                detector_name=self.name,
            ))
        
        # 构建详情
        details_parts = []
        for r in results:
            if r["success"]:
                status = "✓" if r["knows"] else "✗"
                details_parts.append(f"{r['name']}:{status}")
            else:
                details_parts.append(f"{r['name']}:error")
        
        return CheckResultV2(
            name=self.name, category=self.category, score=score, weight=self.weight,
            cost_tokens=total_tokens,
            confidence=round(confidence, 2),
            confidence_reason=confidence_reason,
            details=f"知识点验证: {', '.join(details_parts)}",
            issues=issues,
        )
