"""邮件原始头部解析包。"""

from .parser import analyze_headers, parse_header_blocks

__all__ = ["analyze_headers", "parse_header_blocks"]
