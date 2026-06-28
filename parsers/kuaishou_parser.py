"""
Kuaishou Parser - 快手无水印解析模块

核心逻辑：
1. 解析 v.kuaishou.com 短链接
2. 从网页中提取视频信息
3. 提取无水印播放地址

反爬要点：
- 快手的接口使用签名验证
- 需要处理多种短链格式
"""

import json
import re
import logging
from typing import Optional

from .base import BaseParser, ParseResult

logger = logging.getLogger("watermark_engine")


class KuaishouParser(BaseParser):
    PLATFORM_NAME = "kuaishou"

    # 快手 Web API
    VIDEO_DETAIL_API = "https://v.m.chenzhongtech.com/rest/wd/photo/info"

    def parse(self, url: str) -> ParseResult:
        try:
            # Step 1: 解析短链接
            real_url = self._resolve_short_url(url)
            logger.info(f"[kuaishou] 解析: {url} -> {real_url}")

            # Step 2: 提取视频 ID
            photo_id = self._extract_photo_id(real_url)
            logger.info(f"[kuaishou] 视频ID: {photo_id}")

            # Step 3: 从网页中提取数据
            result = self._parse_from_webpage(real_url, photo_id)
            if result and result.status == "success":
                return result

            # Step 4: 通过 API 获取
            if photo_id:
                result = self._parse_from_api(url, photo_id)
                if result and result.status == "success":
                    return result

            return ParseResult.error(
                msg="解析失败，可能是视频已删除或链接已过期",
                platform=self.PLATFORM_NAME,
                url=url,
            )

        except Exception as e:
            logger.exception(f"[kuaishou] 解析异常: {e}")
            return ParseResult.error(
                msg=f"快手解析失败: {str(e)}",
                platform=self.PLATFORM_NAME,
                url=url,
            )

    def _resolve_short_url(self, url: str) -> str:
        """解析 v.kuaishou.com 短链接"""
        resp = self._make_request(url)
        return resp.url

    def _extract_photo_id(self, url: str) -> Optional[str]:
        """从 URL 中提取视频/照片 ID"""
        patterns = [
            r'/short-video/(\w+)',
            r'photoId[=:](\w+)',
            r'photo_id[=:](\w+)',
            r'/(?:photo|video)/(\w+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def _parse_from_webpage(self, url: str, photo_id: str) -> Optional[ParseResult]:
        """
        从快手网页中提取视频数据。
        
        快手页面通常在 <script> 中嵌入 __APOLLO_STATE__ 或 window.__INITIAL_STATE__
        """
        try:
            resp = self._make_request(url)
            html = resp.text

            # 方式1: 提取 window.__APOLLO_STATE__ (Apollo GraphQL 缓存)
            match = re.search(
                r'window\.__APOLLO_STATE__\s*=\s*({.+?});?\s*</script>',
                html, re.DOTALL
            )
            if match:
                try:
                    state = json.loads(match.group(1))
                    return self._extract_from_apollo_state(state, url)
                except json.JSONDecodeError:
                    pass

            # 方式2: 提取 window.__INITIAL_STATE__
            match = re.search(
                r'window\.__INITIAL_STATE__\s*=\s*({.+?});?\s*</script>',
                html, re.DOTALL
            )
            if match:
                try:
                    state = json.loads(match.group(1))
                    return self._extract_from_initial_state(state, url)
                except json.JSONDecodeError:
                    pass

            # 方式3: 正则兜底 —— 直接从 HTML 中提取视频地址
            return self._extract_from_html_regex(html, url)

        except Exception as e:
            logger.warning(f"[kuaishou] 网页解析失败: {e}")
            return None

    def _extract_from_apollo_state(self, state: dict, url: str) -> Optional[ParseResult]:
        """从 Apollo State 中提取视频信息"""
        try:
            # 搜索 Photo 对象
            photo_obj = None
            for key, value in state.items():
                if isinstance(value, dict) and value.get("__typename") == "Photo":
                    photo_obj = value
                    break

            if not photo_obj:
                return None

            title = photo_obj.get("caption", "")
            cover_url = photo_obj.get("coverUrl", "")
            play_url = photo_obj.get("playUrl", "")

            # 无水印 URL 通常可以通过修改 URL 参数获得
            if play_url:
                play_url = self._to_no_watermark_url(play_url)

            if play_url:
                return ParseResult.success(
                    platform=self.PLATFORM_NAME,
                    original_url=url,
                    title=title,
                    cover_url=cover_url,
                    download_url=play_url,
                )
            return None
        except Exception as e:
            logger.warning(f"[kuaishou] Apollo State 提取失败: {e}")
            return None

    def _extract_from_initial_state(self, state: dict, url: str) -> Optional[ParseResult]:
        """从 Initial State 中提取视频信息"""
        try:
            # 递归搜索 photo 相关数据
            photo_data = self._deep_find(state, "photo")
            if not photo_data or not isinstance(photo_data, dict):
                photo_data = self._deep_find(state, "videoDetail")

            if not photo_data:
                return None

            title = photo_data.get("caption", "") or photo_data.get("title", "")
            cover_url = photo_data.get("coverUrl", "") or photo_data.get("cover", "")
            play_url = photo_data.get("playUrl", "") or photo_data.get("play_url", "")

            if play_url:
                play_url = self._to_no_watermark_url(play_url)

            if play_url:
                return ParseResult.success(
                    platform=self.PLATFORM_NAME,
                    original_url=url,
                    title=title,
                    cover_url=cover_url,
                    download_url=play_url,
                )
            return None
        except Exception as e:
            logger.warning(f"[kuaishou] Initial State 提取失败: {e}")
            return None

    def _extract_from_html_regex(self, html: str, url: str) -> Optional[ParseResult]:
        """正则兜底方案"""
        # 尝试提取视频播放地址
        patterns = [
            r'"playUrl"\s*:\s*"(https?://[^"]+)"',
            r'"play_url"\s*:\s*"(https?://[^"]+)"',
            r'src="(https?://[^"]*?\.mp4[^"]*)"',
        ]
        play_url = ""
        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                play_url = match.group(1)
                break

        # 标题
        title_match = re.search(r'"caption"\s*:\s*"([^"]*)"', html)
        title = title_match.group(1) if title_match else ""

        # 封面
        cover_match = re.search(r'"coverUrl"\s*:\s*"(https?://[^"]+)"', html)
        cover_url = cover_match.group(1) if cover_match else ""

        if play_url:
            return ParseResult.success(
                platform=self.PLATFORM_NAME,
                original_url=url,
                title=title,
                cover_url=cover_url,
                download_url=self._to_no_watermark_url(play_url),
            )
        return None

    def _parse_from_api(self, url: str, photo_id: str) -> Optional[ParseResult]:
        """
        通过快手 API 获取视频详情。
        
        TODO: 快手 API 签名验证：
              - 请求需要携带 did (设备ID), lt (登录token), 以及签名
              - 签名算法基于请求参数的 HMAC 或自定义哈希
              - 需要逆向快手 App 或 Web 端的签名逻辑
        """
        import requests

        payload = {"photoId": photo_id, "isLongVideo": False}
        headers = {
            **self.MOBILE_HEADERS,
            "Referer": "https://v.kuaishou.com/",
            "Origin": "https://v.kuaishou.com",
            # TODO: 添加签名参数
            # "Cookie": "did=xxx; lt=xxx;",
        }

        try:
            resp = requests.post(
                self.VIDEO_DETAIL_API,
                json=payload,
                headers=headers,
                timeout=15,
            )
            data = resp.json()
            result = data.get("result", {})
            photo = result.get("photo", {})

            if not photo:
                return None

            title = photo.get("caption", "")
            cover_url = photo.get("coverUrl", "")
            play_url = photo.get("mainMvUrl", "") or photo.get("playUrl", "")

            if play_url:
                play_url = self._to_no_watermark_url(play_url)

            if play_url:
                return ParseResult.success(
                    platform=self.PLATFORM_NAME,
                    original_url=url,
                    title=title,
                    cover_url=cover_url,
                    download_url=play_url,
                )
            return None
        except Exception as e:
            logger.warning(f"[kuaishou] API 解析失败: {e}")
            return None

    @staticmethod
    def _to_no_watermark_url(url: str) -> str:
        """将快手视频 URL 转换为无水印版本"""
        if not url:
            return ""
        # 快手的水印通常通过 URL 参数添加
        # 移除可能的水印参数
        url = re.sub(r'[?&](?:watermark|wm)[^&]*', '', url)
        return url

    @staticmethod
    def _deep_find(obj, target_key: str):
        """递归搜索嵌套字典"""
        if isinstance(obj, dict):
            if target_key in obj:
                return obj[target_key]
            for v in obj.values():
                result = KuaishouParser._deep_find(v, target_key)
                if result is not None:
                    return result
        elif isinstance(obj, list):
            for item in obj:
                result = KuaishouParser._deep_find(item, target_key)
                if result is not None:
                    return result
        return None
