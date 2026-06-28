"""
Douyin Parser - 抖音无水印解析模块 (v3 - 移动端分享页方案)

核心策略：
1. 解析短链接获取 video_id
2. 访问 iesdouyin.com 移动端分享页获取 SSR 数据（无需 Cookie）
3. 从 window._ROUTER_DATA 中提取无水印视频地址
4. 降级方案：使用 a_bogus 签名调用 Web API
"""

import json
import re
import logging
import requests
from typing import Optional
from urllib.parse import urlencode, quote

from .base import BaseParser, ParseResult

try:
    from ..abogus import ABogus
except ImportError:
    try:
        from abogus import ABogus
    except ImportError:
        ABogus = None

logger = logging.getLogger("watermark_engine")


class DouyinParser(BaseParser):
    PLATFORM_NAME = "douyin"

    # PC Web API (需要 a_bogus 签名 + Cookie)
    WEB_API = "https://www.douyin.com/aweme/v1/web/aweme/detail/"

    # 移动端分享页（核心方案，无需 Cookie）
    MOBILE_SHARE_TEMPLATE = "https://www.iesdouyin.com/share/video/{video_id}/"

    # 也试试 m.douyin.com
    M_SHARE_TEMPLATE = "https://m.douyin.com/share/video/{video_id}"

    PC_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    )

    MOBILE_USER_AGENT = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.0 Mobile/15E148 Safari/604.1"
    )

    BASE_PARAMS = {
        "device_platform": "webapp",
        "aid": "6383",
        "channel": "channel_pc_web",
        "pc_client_type": "1",
        "version_code": "290100",
        "version_name": "29.1.0",
        "cookie_enabled": "true",
        "browser_language": "zh-CN",
        "browser_platform": "Win32",
        "browser_name": "Chrome",
        "browser_version": "130.0.0.0",
        "browser_online": "true",
        "engine_name": "Blink",
        "engine_version": "130.0.0.0",
        "os_name": "Windows",
        "os_version": "10",
        "cpu_core_num": "12",
        "device_memory": "8",
        "platform": "PC",
        "downlink": "10",
        "effective_type": "4g",
        "round_trip_time": "50",
    }

    def __init__(self, cookie: str = ""):
        self.cookie = cookie
        self.abogus = ABogus() if ABogus else None

    def set_cookie(self, cookie: str):
        self.cookie = (cookie or "").strip()

    def parse(self, url: str) -> ParseResult:
        try:
            # Step 1: 解析短链接获取真实 URL + video_id
            real_url, html, video_id = self._resolve_url(url)
            logger.info(f"[douyin] video_id={video_id}, url={real_url}")

            if not video_id:
                return ParseResult.error(
                    msg="无法从链接中提取视频 ID",
                    platform=self.PLATFORM_NAME,
                    url=url,
                )

            # Step 2: 从移动端分享页提取数据（首选方案，无需 Cookie）
            result = self._parse_from_mobile_share(video_id, url)
            if result and result.status == "success":
                return result

            # Step 3: 从 PC 端网页提取
            result = self._parse_from_pc_webpage(html, url)
            if result and result.status == "success":
                return result

            # Step 4: 使用 a_bogus 签名调用 API（需要 Cookie）
            result = self._parse_from_api(video_id, url)
            if result and result.status == "success":
                return result

            return ParseResult.error(
                msg="所有解析方式均失败，可能是视频已删除或受限",
                platform=self.PLATFORM_NAME,
                url=url,
            )

        except Exception as e:
            logger.exception(f"[douyin] 解析异常: {e}")
            return ParseResult.error(
                msg=f"抖音解析失败: {str(e)}",
                platform=self.PLATFORM_NAME,
                url=url,
            )

    def _resolve_url(self, url: str) -> tuple:
        """解析短链接，返回 (real_url, html, video_id)"""
        headers = {
            "User-Agent": self.PC_USER_AGENT,
            "Referer": "https://www.douyin.com/",
        }
        resp = requests.get(url, headers=headers, allow_redirects=True, timeout=15)
        real_url = resp.url
        html = resp.text

        video_id = self._extract_video_id(real_url, html)
        return real_url, html, video_id

    def _extract_video_id(self, url: str, html: str = "") -> Optional[str]:
        """从 URL 或 HTML 中提取 video_id"""
        patterns = [
            r'/video/(\d+)',
            r'/aweme/detail/(\d+)',
            r'/note/(\d+)',
            r'video_id=(\d+)',
            r'aweme_id=(\d+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        if html:
            html_patterns = [
                r'"aweme_id"\s*:\s*"(\d{15,})"',
                r'"itemId"\s*:\s*"(\d{15,})"',
            ]
            for pattern in html_patterns:
                match = re.search(pattern, html)
                if match:
                    return match.group(1)
        return None

    def _parse_from_mobile_share(self, video_id: str, original_url: str) -> Optional[ParseResult]:
        """
        核心方案：从移动端分享页提取视频数据。
        
        iesdouyin.com 的分享页会在 window._ROUTER_DATA 中
        嵌入完整的 SSR 数据，包含无水印播放地址。
        """
        mobile_headers = {
            "User-Agent": self.MOBILE_USER_AGENT,
            "Referer": "https://www.douyin.com/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }

        # 尝试 iesdouyin.com
        for template in [self.MOBILE_SHARE_TEMPLATE, self.M_SHARE_TEMPLATE]:
            try:
                share_url = template.format(video_id=video_id)
                resp = requests.get(share_url, headers=mobile_headers, allow_redirects=True, timeout=15)
                html = resp.text

                result = self._extract_from_router_data(html, original_url)
                if result:
                    return result
            except Exception as e:
                logger.warning(f"[douyin] 移动端分享页请求失败 ({template}): {e}")

        return None

    def _extract_from_router_data(self, html: str, original_url: str) -> Optional[ParseResult]:
        """从 window._ROUTER_DATA 中提取视频信息"""
        try:
            match = re.search(
                r'window\._ROUTER_DATA\s*=\s*(\{.*?\})\s*</script>',
                html, re.DOTALL
            )
            if not match:
                return None

            raw = match.group(1).replace("\\u002F", "/")
            data = json.loads(raw)

            loader = data.get("loaderData", {})
            # 找到 video 页面的数据 key
            page_key = None
            for k in loader.keys():
                if "page" in k:
                    page_key = k
                    break
            if not page_key:
                return None

            page_data = loader.get(page_key, {})

            # videoInfoRes -> item_list
            video_info = page_data.get("videoInfoRes")
            if not video_info:
                return None

            item_list = video_info.get("item_list", [])
            if not item_list:
                return None

            item = item_list[0]
            return self._build_result(item, original_url)

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"[douyin] _ROUTER_DATA 解析失败: {e}")
            return None

    def _build_result(self, item: dict, original_url: str) -> Optional[ParseResult]:
        """从 aweme item 字典中构建解析结果"""
        title = item.get("desc", "")
        author = item.get("author", {})
        author_name = author.get("nickname", "")

        video = item.get("video", {})

        # 封面图
        cover_url = ""
        cover_data = video.get("cover", {})
        cover_list = cover_data.get("url_list", [])
        if cover_list:
            cover_url = cover_list[0]

        # 无水印播放地址
        download_url = self._extract_no_watermark_url(video)

        # 图集处理
        if not download_url:
            images = item.get("images") or item.get("image_list", [])
            if images:
                first_img = images[0]
                img_urls = first_img.get("url_list", [])
                if img_urls:
                    download_url = img_urls[0]
                if not cover_url and img_urls:
                    cover_url = img_urls[0]

        if not download_url:
            return None

        display_title = f"{title} - @{author_name}" if author_name and title else (title or author_name or "未知标题")

        return ParseResult.success(
            platform=self.PLATFORM_NAME,
            original_url=original_url,
            title=display_title,
            cover_url=cover_url,
            download_url=download_url,
        )

    def _extract_no_watermark_url(self, video: dict) -> str:
        """从 video 字典中提取无水印播放地址"""
        if not video:
            return ""

        play_addr = video.get("play_addr", {})
        uri = play_addr.get("uri", "")
        url_list = play_addr.get("url_list", [])

        # 方案1: 通过 uri 构造无水印地址（最可靠）
        if uri:
            return f"https://aweme.snssdk.com/aweme/v1/play/?video_id={uri}&ratio=1080p&line=0"

        # 方案2: 替换 /playwm/ -> /play/
        if url_list:
            url = url_list[0]
            no_wm = url.replace("/playwm/", "/play/")
            if no_wm != url:
                return no_wm

        # 方案3: bit_rate 列表
        bit_rates = video.get("bit_rate", [])
        for br in sorted(bit_rates, key=lambda x: x.get("bit_rate", 0), reverse=True):
            br_play = br.get("play_addr", {})
            br_uri = br_play.get("uri", "")
            if br_uri:
                return f"https://aweme.snssdk.com/aweme/v1/play/?video_id={br_uri}&ratio=1080p&line=0"
            br_urls = br_play.get("url_list", [])
            if br_urls:
                return br_urls[0].replace("/playwm/", "/play/")

        return ""

    def _parse_from_pc_webpage(self, html: str, url: str) -> Optional[ParseResult]:
        """从 PC 端网页提取 SSR 数据（兜底方案）"""
        if not html:
            return None
        try:
            import urllib.parse
            render_match = re.search(
                r'<script\s+id="RENDER_DATA"[^>]*>(.*?)</script>',
                html, re.DOTALL
            )
            if render_match:
                raw = urllib.parse.unquote(render_match.group(1))
                data = json.loads(raw)
                detail = self._deep_find(data, "aweme_detail")
                if detail:
                    return self._build_result(detail, url)

            play_match = re.search(
                r'"play_addr":\s*\{[^}]*"url_list":\s*\[([^\]]+)\]',
                html
            )
            if play_match:
                play_urls = json.loads(f"[{play_match.group(1)}]")
                if play_urls:
                    return ParseResult.success(
                        platform=self.PLATFORM_NAME,
                        original_url=url,
                        title="",
                        cover_url="",
                        download_url=play_urls[0].replace("/playwm/", "/play/"),
                    )
        except Exception as e:
            logger.warning(f"[douyin] PC 网页解析失败: {e}")
        return None

    def _parse_from_api(self, video_id: str, url: str) -> Optional[ParseResult]:
        """使用 a_bogus 签名调用 Web API（需要 Cookie）"""
        if not self.abogus:
            return None

        params = {**self.BASE_PARAMS, "aweme_id": video_id}
        try:
            a_bogus = self.abogus.get_value(params)
            params["a_bogus"] = quote(a_bogus, safe="")
        except Exception as e:
            logger.warning(f"[douyin] a_bogus 生成失败: {e}")
            return None

        headers = {
            "User-Agent": self.PC_USER_AGENT,
            "Referer": "https://www.douyin.com/",
            "Accept": "application/json, text/plain, */*",
        }
        if self.cookie:
            headers["Cookie"] = self.cookie

        try:
            resp = requests.get(self.WEB_API, params=params, headers=headers, timeout=15)
            data = resp.json()
            if data.get("status_code") != 0:
                return None
            detail = data.get("aweme_detail")
            if detail:
                return self._build_result(detail, url)
        except Exception as e:
            logger.warning(f"[douyin] API 调用失败: {e}")
        return None

    @staticmethod
    def _deep_find(obj, target_key: str):
        if isinstance(obj, dict):
            if target_key in obj:
                return obj[target_key]
            for v in obj.values():
                result = DouyinParser._deep_find(v, target_key)
                if result is not None:
                    return result
        elif isinstance(obj, list):
            for item in obj:
                result = DouyinParser._deep_find(item, target_key)
                if result is not None:
                    return result
        return None
