"""
Base Parser - 解析器基类
所有平台解析器必须继承此基类，实现统一接口。
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("watermark_engine")


@dataclass
class ParseResult:
    """统一解析结果数据结构"""
    status: str = "error"
    msg: str = ""
    platform: str = ""
    original_url: str = ""
    title: str = ""
    cover_url: str = ""
    download_url: str = ""

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "msg": self.msg,
            "platform": self.platform,
            "original_url": self.original_url,
            "title": self.title,
            "cover_url": self.cover_url,
            "download_url": self.download_url,
        }

    @staticmethod
    def success(**kwargs) -> "ParseResult":
        return ParseResult(status="success", **kwargs)

    @staticmethod
    def error(msg: str, platform: str = "", url: str = "") -> "ParseResult":
        return ParseResult(status="error", msg=msg, platform=platform, original_url=url)


class BaseParser(ABC):
    """
    平台解析器抽象基类。
    所有子类必须实现 parse() 方法。
    """

    PLATFORM_NAME: str = "unknown"

    # 统一请求头 —— 模拟移动端浏览器
    MOBILE_HEADERS: dict = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/17.0 Mobile/15E148 Safari/604.1"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Referer": "https://www.google.com/",
    }

    @abstractmethod
    def parse(self, url: str) -> ParseResult:
        """
        解析给定 URL，返回无水印内容信息。
        
        Args:
            url: 用户分享的原始链接
            
        Returns:
            ParseResult: 统一的解析结果
        """
        ...

    def _make_request(self, url: str, **kwargs) -> "requests.Response":
        """
        封装 requests 请求，自动注入移动端 Headers 并处理常见异常。
        """
        import requests
        
        merged_headers = {**self.MOBILE_HEADERS, **kwargs.pop("headers", {})}
        try:
            resp = requests.get(
                url,
                headers=merged_headers,
                timeout=15,
                allow_redirects=True,
                **kwargs,
            )
            resp.raise_for_status()
            return resp
        except requests.exceptions.Timeout:
            logger.error(f"[{self.PLATFORM_NAME}] 请求超时: {url}")
            raise
        except requests.exceptions.HTTPError as e:
            logger.error(f"[{self.PLATFORM_NAME}] HTTP错误 {e.response.status_code}: {url}")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"[{self.PLATFORM_NAME}] 请求异常: {e}")
            raise
