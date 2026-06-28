"""
Xiaohongshu Parser - 小红书无水印解析模块

核心逻辑：
1. 从分享链接中提取笔记 ID
2. 请求小红书页面获取 SSR 渲染数据
3. 提取无水印图片/视频地址

反爬要点：
- 小红书的 X-s, X-t, X-s-common 签名是核心防护
- 需要处理多种链接格式（分享卡片、直接链接等）
"""

import json
import re
import time
import logging
from typing import Optional

from .base import BaseParser, ParseResult

logger = logging.getLogger("watermark_engine")


class XiaohongshuParser(BaseParser):
    PLATFORM_NAME = "xiaohongshu"

    # 小红书 Web 端笔记详情 API
    NOTE_API = "https://edith.xiaohongshu.com/api/sns/web/v1/feed"

    def parse(self, url: str) -> ParseResult:
        try:
            # Step 1: 解析短链接
            real_url = self._resolve_short_url(url)
            logger.info(f"[xiaohongshu] 解析: {url} -> {real_url}")

            # Step 2: 提取笔记 ID
            note_id = self._extract_note_id(real_url)
            if not note_id:
                return ParseResult.error(
                    msg="无法从 URL 中提取小红书笔记 ID",
                    platform=self.PLATFORM_NAME,
                    url=url,
                )
            logger.info(f"[xiaohongshu] 笔记ID: {note_id}")

            # Step 3: 尝试从网页中提取数据
            result = self._parse_from_webpage(real_url, note_id)
            if result and result.status == "success":
                return result

            # Step 4: 尝试通过 API 获取
            result = self._parse_from_api(url, note_id)
            if result and result.status == "success":
                return result

            return ParseResult.error(
                msg="解析失败，可能是链接已失效或需要登录查看",
                platform=self.PLATFORM_NAME,
                url=url,
            )

        except Exception as e:
            logger.exception(f"[xiaohongshu] 解析异常: {e}")
            return ParseResult.error(
                msg=f"小红书解析失败: {str(e)}",
                platform=self.PLATFORM_NAME,
                url=url,
            )

    def _resolve_short_url(self, url: str) -> str:
        """解析 xhslink.com 等短链接"""
        if "xhslink.com" in url:
            resp = self._make_request(url)
            return resp.url
        return url

    def _extract_note_id(self, url: str) -> Optional[str]:
        """从 URL 中提取笔记 ID"""
        patterns = [
            r'/(?:explore|discovery/item)/(\w+)',
            r'/note/(\w+)',
            r'noteId[=:](\w+)',
            r'note_id[=:](\w+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def _parse_from_webpage(self, url: str, note_id: str) -> Optional[ParseResult]:
        """
        从小红书网页中提取 SSR 数据。
        
        小红书页面会在 <script>window.__INITIAL_STATE__=...</script> 中嵌入笔记数据。
        """
        try:
            resp = self._make_request(url)
            html = resp.text

            # 提取 __INITIAL_STATE__ 数据
            match = re.search(
                r'window\.__INITIAL_STATE__\s*=\s*({.+?})\s*</script>',
                html, re.DOTALL
            )
            if not match:
                # 尝试另一种格式
                match = re.search(
                    r'window\.__INITIAL_STATE__\s*=\s*({.+?});',
                    html, re.DOTALL
                )

            if match:
                import urllib.parse
                raw = match.group(1)
                # 小红书可能对 undefined 进行了处理
                raw = raw.replace('undefined', 'null')
                try:
                    state = json.loads(raw)
                except json.JSONDecodeError:
                    # JSON 解析失败，尝试正则提取
                    return self._extract_from_html_regex(html, url)

                return self._extract_from_state(state, url, note_id)

            return None
        except Exception as e:
            logger.warning(f"[xiaohongshu] 网页解析失败: {e}")
            return None

    def _extract_from_state(self, state: dict, url: str, note_id: str) -> Optional[ParseResult]:
        """从 __INITIAL_STATE__ JSON 中提取笔记信息"""
        try:
            # 搜索 note 数据（键名可能有变化）
            note_data = None
            for key in ["note", "noteDetail", "noteData"]:
                if key in state and isinstance(state[key], dict):
                    # 有时 note 下面还会嵌套一层 noteId
                    if note_id in state[key]:
                        note_data = state[key][note_id]
                    elif "note" in state[key]:
                        note_data = state[key]["note"]
                    else:
                        note_data = state[key]
                    break

            if not note_data:
                # 递归搜索
                note_data = self._deep_find(state, "noteDetailMap")
                if note_data and isinstance(note_data, dict):
                    note_data = note_data.get(note_id, note_data)

            if not note_data:
                return None

            # 提取标题
            title = note_data.get("title", "") or note_data.get("desc", "")

            # 提取图片列表
            image_list = note_data.get("imageList", [])
            cover_url = ""
            download_url = ""

            if image_list:
                # 图文笔记 —— 提取第一张图的原始地址
                first_img = image_list[0]
                url_list = first_img.get("urlDefault", "") or first_img.get("url", "")
                if isinstance(url_list, str):
                    download_url = url_list
                elif isinstance(url_list, list) and url_list:
                    download_url = url_list[0]
                cover_url = download_url

            # 检查是否是视频笔记
            video = note_data.get("video", {})
            if video:
                consumer = video.get("consumer", {})
                origin_video = video.get("originVideoKey", "")
                if origin_video:
                    # 小红书视频通常在 CDN 上
                    download_url = f"https://sns-video-bd.xhscdn.com/{origin_video}"
                    cover_url = video.get("cover", {}).get("urlDefault", "")

            if not download_url:
                return None

            return ParseResult.success(
                platform=self.PLATFORM_NAME,
                original_url=url,
                title=title,
                cover_url=cover_url,
                download_url=download_url,
            )
        except Exception as e:
            logger.warning(f"[xiaohongshu] 状态数据提取失败: {e}")
            return None

    def _extract_from_html_regex(self, html: str, url: str) -> Optional[ParseResult]:
        """从 HTML 中直接用正则提取数据（兜底方案）"""
        # 尝试提取图片 URL
        img_match = re.search(r'"urlDefault"\s*:\s*"(https?://[^"]+)', html)
        cover_url = img_match.group(1) if img_match else ""

        title_match = re.search(r'"title"\s*:\s*"([^"]*)"', html)
        title = title_match.group(1) if title_match else ""

        if cover_url:
            return ParseResult.success(
                platform=self.PLATFORM_NAME,
                original_url=url,
                title=title,
                cover_url=cover_url,
                download_url=cover_url,
            )
        return None

    def _parse_from_api(self, url: str, note_id: str) -> Optional[ParseResult]:
        """
        通过小红书 API 获取笔记详情。
        
        TODO: 小红书 API 需要以下签名参数：
              - X-s: 请求签名（由 X-s 签名算法生成）
              - X-t: 时间戳
              - X-s-common: 公共参数签名
              这些参数的生成算法需要逆向小红书前端 JS。
              推荐使用 Playwright 渲染页面后提取 cookie 和签名。
        """
        import requests

        payload = {
            "source_note_id": note_id,
            "image_formats": ["jpg", "webp", "avif"],
            "extra": {"need_body_topic": 1},
        }
        headers = {
            **self.MOBILE_HEADERS,
            "Referer": "https://www.xiaohongshu.com/",
            "Origin": "https://www.xiaohongshu.com",
            # TODO: 添加 X-s, X-t, X-s-common 签名参数
            # "X-s": generate_x_s(url, payload),
            # "X-t": str(int(time.time() * 1000)),
            # "X-s-common": generate_x_s_common(),
        }

        try:
            resp = requests.post(
                self.NOTE_API,
                json=payload,
                headers=headers,
                timeout=15,
            )
            data = resp.json()
            items = data.get("data", {}).get("items", [])
            if not items:
                return None

            note = items[0].get("note_card", {})
            title = note.get("title", "") or note.get("desc", "")
            cover_url = ""
            download_url = ""

            # 图文
            image_list = note.get("image_list", [])
            if image_list:
                first = image_list[0]
                urls = first.get("url_default") or first.get("url", "")
                download_url = urls[0] if isinstance(urls, list) else urls
                cover_url = download_url

            # 视频
            video = note.get("video", {})
            if video:
                key = video.get("consumer", {}).get("origin_video_key", "")
                if key:
                    download_url = f"https://sns-video-bd.xhscdn.com/{key}"

            if download_url:
                return ParseResult.success(
                    platform=self.PLATFORM_NAME,
                    original_url=url,
                    title=title,
                    cover_url=cover_url,
                    download_url=download_url,
                )
            return None
        except Exception as e:
            logger.warning(f"[xiaohongshu] API 解析失败: {e}")
            return None

    @staticmethod
    def _deep_find(obj, target_key: str):
        """递归搜索嵌套字典"""
        if isinstance(obj, dict):
            if target_key in obj:
                return obj[target_key]
            for v in obj.values():
                result = XiaohongshuParser._deep_find(v, target_key)
                if result is not None:
                    return result
        elif isinstance(obj, list):
            for item in obj:
                result = XiaohongshuParser._deep_find(item, target_key)
                if result is not None:
                    return result
        return None
