"""long_context - 长上下文 needle-in-haystack 探针（能力，full + --long-context only）"""

from src.core.detector_base import ActiveDetector
from src.core.models import CheckResultV2, Issue, IssueLevel
from ..config import WEIGHTS, CATEGORIES
from src.core.modes import LONG_CONTEXT_PROBES


class LongContextDetector(ActiveDetector):
    """长上下文检测：三层渐进式 needle-in-haystack（32k→100k→200k）"""

    name = "long_context"
    category = CATEGORIES["long_context"]
    weight = WEIGHTS.get("long_context", 0.10)
    modes = ["full"]
    timeout = 120
    estimated_tokens = 350_000  # BUG-1/6: 保守预估，用于预算预分配

    def run(self, client) -> CheckResultV2:
        issues = []
        total_tokens = 0
        results_per_probe = []

        for probe in LONG_CONTEXT_PROBES:
            probe_name = probe["name"]
            target_tokens = probe["input_tokens"]
            needle = probe["needle"]

            # BUG-6 修复：逐探针预算检查
            if self.budget_limit > 0 and total_tokens + target_tokens > self.budget_limit:
                issues.append(Issue(
                    level=IssueLevel.MINOR,
                    message=f"预算耗尽，跳过 {probe_name} 探针（已用 {total_tokens}/{self.budget_limit}）",
                    detector_name=self.name,
                ))
                break

            # 构建 haystack
            filler_text = ("The quick brown fox jumps over the lazy dog. " * 100)
            repeat_count = max(1, target_tokens // 50)
            haystack = (filler_text * repeat_count)[:target_tokens * 4]

            mid = len(haystack) // 2
            haystack = haystack[:mid] + f"\n\n{needle}\n\n" + haystack[mid:]

            resp = client.messages(
                messages=[{
                    "role": "user",
                    "content": f"{haystack}\n\nWhat is the secret code mentioned in the text above? Answer with just the code.",
                }],
                max_tokens=30,
                detector_name=self.name,
            )

            if not resp.success:
                issues.append(Issue(
                    level=IssueLevel.MAJOR,
                    message=f"{probe_name} 探针失败: {resp.error}",
                    detector_name=self.name,
                ))
                results_per_probe.append({"probe": probe_name, "found": False, "error": resp.error})
                break

            if resp.usage:
                total_tokens += resp.usage.total_tokens

            content = (resp.content or "").strip()
            found = needle.split(": ")[-1] in content if ": " in needle else needle in content

            results_per_probe.append({
                "probe": probe_name,
                "found": found,
                "response": content[:100],
            })

            if not found:
                issues.append(Issue(
                    level=IssueLevel.MAJOR,
                    message=f"{probe_name} 探针未找到 needle",
                    detector_name=self.name,
                ))
                break

        found_count = sum(1 for r in results_per_probe if r["found"])
        total_probes = len(LONG_CONTEXT_PROBES)
        score = (found_count / total_probes) * 100

        if found_count == total_probes:
            issues.append(Issue(
                level=IssueLevel.OK,
                message=f"全部 {total_probes} 层探针均通过",
                detector_name=self.name,
            ))

        details_parts = [f"{r['probe']}: {'[OK]' if r['found'] else '[FAIL]'}" for r in results_per_probe]

        return CheckResultV2(
            name=self.name, category=self.category, score=score, weight=self.weight,
            cost_tokens=total_tokens,
            details=f"探针结果: {', '.join(details_parts)}",
            issues=issues,
        )
