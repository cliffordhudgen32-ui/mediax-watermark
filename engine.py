"""
Watermark Removal Engine - 主入口模块
全网短视频/图文去水印解析聚合引擎

Usage:
    from watermark_engine.engine import WatermarkEngine
    
    engine = WatermarkEngine()
    result = engine.parse("你看这个 https://v.douyin.com/xxx/ 复制打开")
    print(result)  # {"status": "success", "platform": "douyin", ...}
"""

import json
import logging
from typing import Dict, List, Optional

from .router import route, identify_platform, extract_urls
from .parsers import (
    BaseParser,
    ParseResult,
    DouyinParser,
    BilibiliParser,
    XiaohongshuParser,
    KuaishouParser,
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("watermark_engine")


# ============================================================
# 平台解析器注册表
# ============================================================
PARSER_REGISTRY: Dict[str, BaseParser] = {
    "douyin": DouyinParser(),
    "bilibili": BilibiliParser(),
    "xiaohongshu": XiaohongshuParser(),
    "kuaishou": KuaishouParser(),
}


class WatermarkEngine:
    """
    水印去除引擎主类。
    
    支持：
    - 自动识别文本中的链接并提取
    - 自动分发到对应的平台解析器
    - 返回统一格式的 JSON 结果
    """

    def __init__(self, parser_overrides: Optional[Dict[str, BaseParser]] = None):
        """
        初始化引擎。
        
        Args:
            parser_overrides: 可选的解析器覆盖字典，用于注册自定义解析器。
        """
        self.parsers = {**PARSER_REGISTRY}
        if parser_overrides:
            self.parsers.update(parser_overrides)

    def parse(self, text_or_url: str) -> dict:
        """
        核心入口：解析用户输入的文本或 URL，返回无水印内容信息。
        
        Args:
            text_or_url: 用户输入的分享文案或直接 URL
            
        Returns:
            统一格式的结果字典：
            {
                "status": "success" | "error",
                "msg": "...",
                "platform": "douyin" | "bilibili" | ...,
                "original_url": "https://...",
                "title": "...",
                "cover_url": "https://...",
                "download_url": "https://...",
            }
        """
        # Step 1: 从文本中提取 URL 并识别平台
        routes = route(text_or_url)

        if not routes:
            return ParseResult.error(
                msg="未在输入文本中找到任何有效链接",
                platform="unknown",
                url=text_or_url,
            ).to_dict()

        # 取第一个可识别的平台链接进行解析
        results = []
        for platform, url in routes:
            if platform == "unknown":
                continue
            result = self._dispatch_parse(platform, url)
            results.append(result)

        if not results:
            # 所有链接都是 unknown 平台
            return ParseResult.error(
                msg=f"未识别到支持的平台，找到的链接域名不在支持范围内。"
                    f"当前支持: {', '.join(self.parsers.keys())}",
                platform="unknown",
                url=routes[0][1] if routes else "",
            ).to_dict()

        # 返回第一个成功的结果
        for result in results:
            if result["status"] == "success":
                return result

        # 全部失败，返回最后一个错误
        return results[-1]

    def parse_url(self, url: str) -> dict:
        """
        直接解析 URL（跳过文本提取步骤）。
        """
        platform = identify_platform(url)
        if not platform:
            return ParseResult.error(
                msg=f"不支持的平台链接: {url}",
                platform="unknown",
                url=url,
            ).to_dict()

        return self._dispatch_parse(platform, url)

    def parse_batch(self, text_or_urls: str) -> List[dict]:
        """
        批量解析：从文本中提取所有链接并逐一解析。
        
        Args:
            text_or_urls: 包含多个链接的文本
            
        Returns:
            解析结果列表
        """
        routes = route(text_or_urls)
        results = []
        for platform, url in routes:
            if platform == "unknown":
                results.append(
                    ParseResult.error(
                        msg=f"不支持的平台: {url}",
                        platform="unknown",
                        url=url,
                    ).to_dict()
                )
            else:
                results.append(self._dispatch_parse(platform, url))
        return results

    def _dispatch_parse(self, platform: str, url: str) -> dict:
        """根据平台名称分发到对应的解析器"""
        parser = self.parsers.get(platform)
        if not parser:
            return ParseResult.error(
                msg=f"未注册的平台解析器: {platform}",
                platform=platform,
                url=url,
            ).to_dict()

        logger.info(f"分发到 [{platform}] 解析器: {url}")
        try:
            result = parser.parse(url)
            return result.to_dict()
        except Exception as e:
            logger.exception(f"[{platform}] 解析器未捕获异常: {e}")
            return ParseResult.error(
                msg=f"解析器内部错误: {str(e)}",
                platform=platform,
                url=url,
            ).to_dict()

    @staticmethod
    def get_supported_platforms() -> List[str]:
        """返回所有支持的平台列表"""
        return list(PARSER_REGISTRY.keys())


# ============================================================
# 便捷函数
# ============================================================

def parse_url(text_or_url: str) -> dict:
    """
    一行代码调用解析引擎的便捷函数。
    
    Example:
        result = parse_url("https://v.douyin.com/xxx/")
        print(result["download_url"])
    """
    engine = WatermarkEngine()
    return engine.parse(text_or_url)


# ============================================================
# CLI 入口
# ============================================================
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m watermark_engine.engine <URL or text>")
        print(f"Supported platforms: {', '.join(WatermarkEngine.get_supported_platforms())}")
        sys.exit(1)

    input_text = " ".join(sys.argv[1:])
    engine = WatermarkEngine()
    result = engine.parse(input_text)
    print(json.dumps(result, ensure_ascii=False, indent=2))
