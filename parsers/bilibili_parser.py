"""
Bilibili Parser - B站无水印解析模块

核心逻辑：
1. 解析短链接 b23.tv 或直接处理 bilibili.com URL
2. 从 URL 中提取 BV 号
3. 通过 B 站 API 获取视频信息
4. 提取最高画质无水印播放地址

B站相对友好，API 签名机制较为简单。
"""

import json
import re
import logging
from typing import Optional

import requests
from .base import BaseParser, ParseResult

logger = logging.getLogger("watermark_engine")


class BilibiliParser(BaseParser):
    PLATFORM_NAME = "bilibili"

    # B站视频信息 API
    VIDEO_INFO_API = "https://api.bilibili.com/x/web-interface/view"
    # B站视频播放地址 API
    PLAY_URL_API = "https://api.bilibili.com/x/player/playurl"

    # 中国大陆地区可用的清晰度等级（数字越小越高）
    # 112 = 1080P, 116 = 1080P60, 120 = 4K, 125 = HDR, 126 = Dolby
    DASH_QUALITY = 112

    def parse(self, url: str) -> ParseResult:
        try:
            # Step 1: 解析短链接
            real_url = self._resolve_short_url(url)
            logger.info(f"[bilibili] 解析: {url} -> {real_url}")

            # Step 2: 提取 BV 号
            bvid = self._extract_bvid(real_url)
            if not bvid:
                return ParseResult.error(
                    msg="无法从 URL 中提取 B站视频 BV号",
                    platform=self.PLATFORM_NAME,
                    url=url,
                )
            logger.info(f"[bilibili] BV号: {bvid}")

            # Step 3: 获取视频信息
            video_info = self._get_video_info(bvid)
            if not video_info:
                return ParseResult.error(
                    msg="获取视频信息失败，可能是视频已下架或需要登录",
                    platform=self.PLATFORM_NAME,
                    url=url,
                )

            title = video_info.get("title", "")
            cover_url = video_info.get("pic", "")
            cid = video_info.get("cid", 0)
            aid = video_info.get("aid", 0)

            # Step 4: 获取无水印播放地址
            download_url = self._get_play_url(bvid, cid, aid)
            if not download_url:
                return ParseResult.error(
                    msg="获取播放地址失败，可能需要大会员或视频受限",
                    platform=self.PLATFORM_NAME,
                    url=url,
                )

            return ParseResult.success(
                platform=self.PLATFORM_NAME,
                original_url=url,
                title=title,
                cover_url=cover_url if cover_url.startswith("http") else f"https:{cover_url}",
                download_url=download_url,
            )

        except Exception as e:
            logger.exception(f"[bilibili] 解析异常: {e}")
            return ParseResult.error(
                msg=f"B站解析失败: {str(e)}",
                platform=self.PLATFORM_NAME,
                url=url,
            )

    def _resolve_short_url(self, url: str) -> str:
        """解析 b23.tv 短链接"""
        if "b23.tv" in url:
            resp = self._make_request(url)
            return resp.url
        return url

    def _extract_bvid(self, url: str) -> Optional[str]:
        """从 URL 中提取 BV 号"""
        match = re.search(r'(BV\w{10})', url)
        if match:
            return match.group(1)
        match = re.search(r'/video/av(\d+)', url)
        if match:
            # AV 号转 BV 号需要算法，这里先直接用 AV 号查询
            return f"av{match.group(1)}"
        return None

    def _get_video_info(self, bvid: str) -> Optional[dict]:
        """通过 B站 API 获取视频基本信息"""
        params = {"bvid": bvid}
        headers = {
            **self.MOBILE_HEADERS,
            "Referer": "https://www.bilibili.com/",
        }
        try:
            import requests
            resp = requests.get(
                self.VIDEO_INFO_API,
                params=params,
                headers=headers,
                timeout=15,
            )
            data = resp.json()
            if data.get("code") == 0:
                return data.get("data", {})
            else:
                logger.warning(f"[bilibili] API 返回错误: {data.get('message')}")
                return None
        except Exception as e:
            logger.warning(f"[bilibili] 获取视频信息失败: {e}")
            return None

    def _get_play_url(self, bvid: str, cid: int, aid: int) -> Optional[str]:
        """
        获取无水印播放地址。
        
        TODO: B站的无水印策略：
              - 登录用户可以获取更高画质
              - DASH 格式需要分别下载音视频后合并
              - FLV 格式直接包含音视频，但画质可能受限
              - 如果需要 1080P+，需要 Wbi 签名（见 https://github.com/SocialSisterYi/bilibili-API-collect）
        """
        params = {
            "bvid": bvid,
            "cid": cid,
            "qn": self.DASH_QUALITY,  # 1080P
            "type": "mp4",             # 优先获取 mp4 格式（音视频合一）
            "otype": "json",
            "platform": "html5",
            "high_quality": 1,
        }
        headers = {
            **self.MOBILE_HEADERS,
            "Referer": f"https://www.bilibili.com/video/{bvid}",
        }

        try:
            import requests
            resp = requests.get(
                self.PLAY_URL_API,
                params=params,
                headers=headers,
                timeout=15,
            )
            data = resp.json()
            
            if data.get("code") != 0:
                logger.warning(f"[bilibili] 播放地址 API 错误: {data.get('message')}")
                return None

            result = data.get("data", {})

            # 优先取 durl 列表中的地址（mp4 格式，音视频合一）
            durl_list = result.get("durl", [])
            if durl_list:
                # 选最长的那个（通常是最高画质）
                best = max(durl_list, key=lambda x: x.get("length", 0))
                play_url = best.get("url", "")
                # 去掉 B站 的水印参数
                play_url = play_url.split("&sign=")[0] if "&sign=" in play_url else play_url
                return play_url

            # 备选: DASH 格式（音视频分离，需要合并）
            dash = result.get("dash", {})
            if dash:
                video_list = dash.get("video", [])
                audio_list = dash.get("audio", [])
                if video_list:
                    # TODO: DASH 格式需要使用 ffmpeg 分别下载音视频并合并
                    # 这里返回视频流地址作为参考
                    return video_list[0].get("baseUrl") or video_list[0].get("base_url", "")

            return None
        except Exception as e:
            logger.warning(f"[bilibili] 获取播放地址失败: {e}")
            return None
