"""pdf - PDF 能力检测（能力）"""

import base64
from src.core.detector_base import ActiveDetector
from src.core.models import CheckResultV2, Issue, IssueLevel
from ..config import WEIGHTS, CATEGORIES


# Bug 12 修复：内置最小 PDF（含 magic string）
# 由 scripts/generate_test_pdf.py 生成，此处硬编码 base64
# PDF 内容包含 magic string: MAGIC_PDF_PROBE_7X9K2
_TEST_PDF_B64 = (
    "JVBERi0xLjQKMSAwIG9iago8PC9UeXBlL0NhdGFsb2cvUGFnZXMgMiAwIFI+PgplbmRvYmoK"
    "MiAwIG9iago8PC9UeXBlL1BhZ2VzL0tpZHNbMyAwIFJdL0NvdW50IDE+PgplbmRvYmoKMyAw"
    "IG9iago8PC9UeXBlL1BhZ2UvUGFyZW50IDIgMCBSL01lZGlhQm94WzAgMCA2MTIgNzkyXT4+"
    "CmVuZG9iago0IDAgb2JqCjw8L0xlbmd0aCA1Mz4+CnN0cmVhbQpCVAovRjEuMCAxMiBUZgox"
    "MiA3MDAgVGQKKFRoaXMgZG9jdW1lbnQgY29udGFpbnMgdGhlIG1hZ2ljIHN0cmluZzogTUFH"
    "SUNfUERGX1BST0JFXzdYOUkyKQpFVApFTkQKZW5kc3RyZWFtCmVuZG9iago1IDAgb2JqCjw8"
    "L1R5cGUvRm9udC9TdWJ0eXBlL1R5cGUxL0Jhc2VGb250L0hlbHZldGljYT4+CmVuZG9iagoN"
    "eHJlZgowIDYKMDAwMDAwMDAwMCA2NTUzNSBmCjAwMDAwMDAwMDkgMDAwMDAgbgowMDAwMDAw"
    "MDUyIDAwMDAwIG4KMDAwMDAwMDAxMCAwMDAwMCBuCjAwMDAwMDAxNTQgMDAwMDAgbgowMDAw"
    "MDAwMjM1IDAwMDAwIG4KdHJhaWxlcgo8PC9TaXplIDYvUm9vdCAxIDAgUj4+CnN0YXJ0eHJl"
    "ZgoyODUKJSVFT0YK"
)

MAGIC_STRING = "MAGIC_PDF_PROBE_7X9K2"


class PDFDetector(ActiveDetector):
    """PDF 能力检测：发送 base64 PDF，验证模型能提取 magic string"""

    name = "pdf"
    category = CATEGORIES["pdf"]
    weight = WEIGHTS["pdf"]
    modes = ["full"]
    timeout = 45

    def run(self, client) -> CheckResultV2:
        pdf_data = base64.b64decode(_TEST_PDF_B64)
        pdf_b64 = base64.b64encode(pdf_data).decode("utf-8")

        resp = client.messages(
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": "What magic string is mentioned in this document? Answer with just the string.",
                    },
                ],
            }],
            max_tokens=50,
            detector_name=self.name,
        )

        if not resp.success:
            return CheckResultV2(
                name=self.name, category=self.category, score=0, weight=self.weight,
                status="error", cost_tokens=resp.usage.total_tokens if resp.usage else 0,
                details=f"PDF 请求失败: {resp.error}",
                issues=[Issue(
                    level=IssueLevel.MAJOR,
                    message=f"PDF 能力不可用: {resp.error}",
                    detector_name=self.name,
                )],
            )

        content = (resp.content or "").strip()
        issues = []

        if MAGIC_STRING in content:
            score = 100
            issues.append(Issue(
                level=IssueLevel.OK,
                message="成功从 PDF 中提取 magic string",
                detector_name=self.name,
            ))
        elif "magic" in content.lower():
            score = 60
            issues.append(Issue(
                level=IssueLevel.MINOR,
                message=f"部分识别 magic 但未完整提取: {content[:50]}",
                detector_name=self.name,
            ))
        else:
            score = 20
            issues.append(Issue(
                level=IssueLevel.MAJOR,
                message=f"未能从 PDF 提取 magic string，响应: {content[:50]}",
                detector_name=self.name,
            ))

        return CheckResultV2(
            name=self.name, category=self.category, score=score, weight=self.weight,
            cost_tokens=resp.usage.total_tokens if resp.usage else 0,
            details=f"content={content[:80]}",
            issues=issues,
        )
