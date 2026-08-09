#!/usr/bin/env python3
"""
生成 PDF 测试文件（含 magic string）

Bug 12 修复：运行时生成带 magic string 的测试 PDF
输出 base64 编码，硬编码到 pdf.py 检测器中

用法:
  python scripts/generate_test_pdf.py
"""

import base64
import sys
import os

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def build_minimal_pdf(magic_string: str = "MAGIC_PDF_PROBE_7X9K2") -> bytes:
    """
    手写最小 PDF 文件，包含 magic string

    PDF 结构:
      1. Header
      2. Catalog
      3. Pages
      4. Page
      5. Font
      6. Content stream (含 magic string)
      7. xref + trailer
    """
    content_text = f"(This document contains the magic string: {magic_string})"

    objects = []
    # Object 1: Catalog
    objects.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    # Object 2: Pages
    objects.append(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
    # Object 3: Page
    objects.append(b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n")
    # Object 4: Content stream
    stream_content = (
        b"BT\n/F1.0 12 Tf\n12 700 Td\n"
        + content_text.encode("utf-8")
        + b"\nET\n"
    )
    stream_obj = (
        f"4 0 obj\n<< /Length {len(stream_content)} >>\nstream\n"
    ).encode("utf-8") + stream_content + b"endstream\nendobj\n"
    objects.append(stream_obj)
    # Object 5: Font
    objects.append(b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")

    # 构建 PDF
    pdf = b"%PDF-1.4\n"
    offsets = []
    for obj in objects:
        offsets.append(len(pdf))
        pdf += obj

    # xref
    xref_offset = len(pdf)
    pdf += b"xref\n"
    pdf += f"0 {len(objects) + 1}\n".encode("utf-8")
    pdf += b"0000000000 65535 f \n"
    for offset in offsets:
        pdf += f"{offset:010d} 00000 n \n".encode("utf-8")

    # trailer
    pdf += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode("utf-8")
    pdf += b"startxref\n"
    pdf += f"{xref_offset}\n".encode("utf-8")
    pdf += b"%%EOF\n"

    return pdf


def main():
    magic = "MAGIC_PDF_PROBE_7X9K2"
    pdf_bytes = build_minimal_pdf(magic)
    pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

    print(f"Magic string: {magic}")
    print(f"PDF size: {len(pdf_bytes)} bytes")
    print(f"Base64 size: {len(pdf_b64)} chars")
    print()
    print("Base64 output:")
    print(pdf_b64)
    print()

    # 输出可粘贴到 Python 文件的格式
    print("Python code for pdf.py:")
    print(f'_TEST_PDF_B64 = (')
    # 分行输出，每行 76 字符
    for i in range(0, len(pdf_b64), 76):
        print(f'    "{pdf_b64[i:i+76]}"')
    print(')')
    print(f'\nMAGIC_STRING = "{magic}"')


if __name__ == "__main__":
    main()
