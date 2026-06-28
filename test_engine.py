"""
Test Engine - 全模块 Mock 测试用例
使用 unittest.mock 模拟各平台的网络请求，验证整个引擎的解析流程。
"""

import json
import sys
import os
import unittest
from unittest.mock import patch, MagicMock

# 将项目根目录加入 sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from watermark_engine.router import extract_urls, identify_platform, route
from watermark_engine.parsers import (
    ParseResult,
    DouyinParser,
    BilibiliParser,
    XiaohongshuParser,
    KuaishouParser,
)
from watermark_engine.engine import WatermarkEngine


# ============================================================
# 模拟数据
# ============================================================

MOCK_DOUYIN_RENDER_DATA = """
<script id="RENDER_DATA" type="application/json">
%7B%22aweme_detail%22%3A%7B%22desc%22%3A%22%E4%BB%8A%E5%A4%A9%E7%9A%84%E5%A4%A9%E6%B0%94%E7%9C%9F%E5%A5%BD%22%2C%22author%22%3A%7B%22nickname%22%3A%22%E5%B0%8F%E6%98%8E%22%7D%2C%22video%22%3A%7B%22cover%22%3A%7B%22url_list%22%3A%5B%22https%3A%2F%2Fp9-pc-sign.douyinpic.com%2Fimg%2Fcover%2Ftest.jpg%22%5D%7D%2C%22play_addr%22%3A%7B%22url_list%22%3A%5B%22https%3A%2F%2Fv26-web.douyinvod.com%2Fplaywm%2Ftest.mp4%22%5D%7D%7D%7D%7D
</script>
"""

MOCK_DOUYIN_SIMPLE_HTML = """
<html>
<head><title>抖音视频 - 测试标题</title></head>
<body>
<div id="RENDER_DATA" style="display:none"></div>
<script>window.__RENDER_DATA__ = '{"test": 1}'</script>
<p>"play_addr": {"url_list": ["https://v26-web.douyinvod.com/playwm/video/test123.mp4"]}</p>
"cover": {"url_list": ["https://p9-pc-sign.douyinpic.com/img/cover.jpg"]}
<title>测试标题</title>
</body>
</html>
"""

MOCK_BILIBILI_VIDEO_INFO = {
    "code": 0,
    "data": {
        "title": "【4K】超震撼自然风光",
        "pic": "//i0.hdslb.com/bfs/archive/test_cover.jpg",
        "aid": 123456,
        "cid": 789012,
    },
}

MOCK_BILIBILI_PLAY_URL = {
    "code": 0,
    "data": {
        "durl": [
            {
                "url": "https://upos-sz-mirrorcos.bilivideo.com/test_video.mp4?sign=test123",
                "length": 5000000,
            }
        ],
        "dash": {
            "video": [
                {"baseUrl": "https://upos-sz-mirrorcos.bilivideo.com/dash_video.m4s"}
            ],
            "audio": [
                {"baseUrl": "https://upos-sz-mirrorcos.bilivideo.com/dash_audio.m4s"}
            ],
        },
    },
}

MOCK_XHS_INITIAL_STATE = """
<script>window.__INITIAL_STATE__ = {
  "note": {
    "note12345": {
      "title": "超好看的春日穿搭分享",
      "desc": "分享一套超好看的春日穿搭",
      "imageList": [
        {"urlDefault": "https://sns-webpic-qc.xhscdn.com/test_image.jpg"}
      ]
    }
  }
}</script>
"""

MOCK_KUAISHOU_HTML = """
<html>
<body>
<script>window.__INITIAL_STATE__ = {
  "videoDetail": {
    "caption": "搞笑视频合集",
    "coverUrl": "https://v1.kwaixiaodian.com/test_cover.jpg",
    "playUrl": "https://v2-web.douyinvod.com/kuaishou_test.mp4"
  }
}</script>
</body>
</html>
"""


class TestRouter(unittest.TestCase):
    """测试 URL 提取与路由模块"""

    def test_extract_urls_clean_text(self):
        """纯链接文本提取"""
        urls = extract_urls("https://v.douyin.com/abc123/")
        self.assertEqual(len(urls), 1)
        self.assertIn("douyin.com", urls[0])

    def test_extract_urls_with_noise(self):
        """从带干扰文本中提取链接"""
        text = "你看这个太搞笑了！http://v.douyin.com/xxx/ 复制打开抖音"
        urls = extract_urls(text)
        self.assertEqual(len(urls), 1)
        self.assertIn("douyin.com", urls[0])

    def test_extract_multiple_urls(self):
        """提取多个链接"""
        text = "抖音 https://v.douyin.com/abc/ B站 https://www.bilibili.com/video/BV1xx411c7mD"
        urls = extract_urls(text)
        self.assertEqual(len(urls), 2)

    def test_extract_no_urls(self):
        """无链接文本"""
        urls = extract_urls("这里没有任何链接")
        self.assertEqual(len(urls), 0)

    def test_identify_platform_douyin(self):
        """识别抖音链接"""
        self.assertEqual(identify_platform("https://v.douyin.com/abc123/"), "douyin")
        self.assertEqual(identify_platform("https://www.douyin.com/video/12345"), "douyin")

    def test_identify_platform_bilibili(self):
        """识别B站链接"""
        self.assertEqual(
            identify_platform("https://www.bilibili.com/video/BV1xx411c7mD"),
            "bilibili",
        )
        self.assertEqual(identify_platform("https://b23.tv/abc123"), "bilibili")

    def test_identify_platform_xiaohongshu(self):
        """识别小红书链接"""
        self.assertEqual(
            identify_platform("https://www.xiaohongshu.com/explore/abc123"),
            "xiaohongshu",
        )
        self.assertEqual(
            identify_platform("https://xhslink.com/abc123"),
            "xiaohongshu",
        )

    def test_identify_platform_kuaishou(self):
        """识别快手链接"""
        self.assertEqual(identify_platform("https://v.kuaishou.com/abc123"), "kuaishou")

    def test_identify_unknown_platform(self):
        """未知平台返回 None"""
        self.assertIsNone(identify_platform("https://www.google.com"))

    def test_route_integration(self):
        """路由集成测试"""
        text = "抖音 https://v.douyin.com/abc/ B站 https://b23.tv/xyz"
        result = route(text)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0][0], "douyin")
        self.assertEqual(result[1][0], "bilibili")


class TestParseResult(unittest.TestCase):
    """测试统一数据结构"""

    def test_success_result(self):
        """成功结果"""
        r = ParseResult.success(
            platform="douyin",
            original_url="https://v.douyin.com/abc/",
            title="测试视频",
            cover_url="https://cover.jpg",
            download_url="https://video.mp4",
        )
        d = r.to_dict()
        self.assertEqual(d["status"], "success")
        self.assertEqual(d["platform"], "douyin")
        self.assertEqual(d["title"], "测试视频")
        self.assertEqual(d["download_url"], "https://video.mp4")

    def test_error_result(self):
        """错误结果"""
        r = ParseResult.error(msg="解析失败", platform="bilibili", url="https://b23.tv/abc")
        d = r.to_dict()
        self.assertEqual(d["status"], "error")
        self.assertEqual(d["msg"], "解析失败")
        self.assertIn("bilibili", d["platform"])

class TestDouyinParser(unittest.TestCase):
    """抖音解析器 Mock 测试"""

    @patch("watermark_engine.parsers.douyin_parser.requests.get")
    def test_parse_webpage_success(self, mock_get):
        """网页 SSR 解析成功"""
        redirect_resp = MagicMock()
        redirect_resp.url = "https://www.douyin.com/video/12345"
        redirect_resp.text = MOCK_DOUYIN_SIMPLE_HTML
        mock_get.return_value = redirect_resp

        parser = DouyinParser()
        result = parser.parse("https://v.douyin.com/abc123/")

        self.assertEqual(result.status, "success")
        self.assertEqual(result.platform, "douyin")
        self.assertIn("/play/", result.download_url)

    def test_abogus_signature_generation(self):
        """验证 a_bogus 签名算法可正常工作"""
        try:
            from watermark_engine.abogus import ABogus
        except ImportError:
            self.skipTest("gmssl not installed, skip abogus test")
        bogus = ABogus()
        params = {
            "device_platform": "webapp",
            "aid": "6383",
            "aweme_id": "7345492945006595379",
        }
        result = bogus.get_value(params)
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    @patch("watermark_engine.parsers.douyin_parser.requests.get")
    def test_parse_mobile_share(self, mock_get):
        """移动端分享页解析 (iesdouyin.com)"""
        # Mock _resolve_url -> returns video ID
        redirect_resp = MagicMock()
        redirect_resp.url = "https://www.douyin.com/video/7345492945006595379"
        redirect_resp.text = "<html></html>"

        # Mock iesdouyin mobile share page with _ROUTER_DATA
        router_data = {
            "loaderData": {
                "video_(id)/page": {
                    "videoInfoRes": {
                        "item_list": [{
                            "desc": "test video desc",
                            "author": {"nickname": "test_user"},
                            "video": {
                                "cover": {
                                    "url_list": ["https://p3-pc-sign.douyinpic.com/test_cover.jpg"]
                                },
                                "play_addr": {
                                    "uri": "v0d00fg_test123",
                                    "url_list": [
                                        "https://aweme.snssdk.com/aweme/v1/playwm/?video_id=v0d00fg_test123"
                                    ],
                                },
                            },
                        }]
                    }
                }
            }
        }
        mobile_resp = MagicMock()
        mobile_resp.status_code = 200
        mobile_resp.text = (
            '<script>window._ROUTER_DATA = '
            + json.dumps(router_data).replace("/", "\\u002F")
            + '</script>'
        )

        mock_get.side_effect = [redirect_resp, mobile_resp]

        parser = DouyinParser()
        result = parser.parse("https://v.douyin.com/abc123/")

        self.assertEqual(result.status, "success")
        self.assertEqual(result.platform, "douyin")
        self.assertIn("test_user", result.title)
        # Should use URI-based no-watermark URL
        self.assertIn("v0d00fg_test123", result.download_url)
        self.assertIn("aweme.snssdk.com", result.download_url)
class TestBilibiliParser(unittest.TestCase):
    """B站解析器 Mock 测试"""

    @patch("requests.get")
    @patch.object(BilibiliParser, "_resolve_short_url")
    def test_parse_full_flow(self, mock_resolve, mock_get):
        """完整解析流程"""
        mock_resolve.return_value = "https://www.bilibili.com/video/BV1xx411c7mD"

        def side_effect(url, **kwargs):
            mock_resp = MagicMock()
            if "view" in url:
                mock_resp.json.return_value = MOCK_BILIBILI_VIDEO_INFO
            elif "playurl" in url:
                mock_resp.json.return_value = MOCK_BILIBILI_PLAY_URL
            else:
                mock_resp.json.return_value = {"code": -1}
            mock_resp.raise_for_status = MagicMock()
            return mock_resp

        mock_get.side_effect = side_effect

        parser = BilibiliParser()
        result = parser.parse("https://www.bilibili.com/video/BV1xx411c7mD")

        self.assertEqual(result.status, "success")
        self.assertEqual(result.platform, "bilibili")
        self.assertEqual(result.title, "【4K】超震撼自然风光")
        self.assertIn("test_video.mp4", result.download_url)

    @patch("requests.get")
    @patch.object(BilibiliParser, "_resolve_short_url")
    def test_parse_short_link(self, mock_resolve, mock_get):
        """B站短链接解析"""
        mock_resolve.return_value = "https://www.bilibili.com/video/BV1xx411c7mD"

        def side_effect(url, **kwargs):
            mock_resp = MagicMock()
            if "view" in url:
                mock_resp.json.return_value = MOCK_BILIBILI_VIDEO_INFO
            elif "playurl" in url:
                mock_resp.json.return_value = MOCK_BILIBILI_PLAY_URL
            else:
                mock_resp.json.return_value = {"code": -1}
            mock_resp.raise_for_status = MagicMock()
            return mock_resp

        mock_get.side_effect = side_effect

        parser = BilibiliParser()
        result = parser.parse("https://b23.tv/abc123")

        self.assertEqual(result.status, "success")


class TestXiaohongshuParser(unittest.TestCase):
    """小红书解析器 Mock 测试"""

    @patch.object(XiaohongshuParser, "_make_request")
    def test_parse_from_webpage(self, mock_request):
        """网页数据提取"""
        mock_resp = MagicMock()
        mock_resp.text = MOCK_XHS_INITIAL_STATE
        mock_resp.url = "https://www.xiaohongshu.com/explore/note12345"
        mock_request.return_value = mock_resp

        parser = XiaohongshuParser()
        result = parser.parse("https://www.xiaohongshu.com/explore/note12345")

        self.assertEqual(result.status, "success")
        self.assertEqual(result.platform, "xiaohongshu")
        self.assertIn("xhscdn.com", result.download_url)


class TestKuaishouParser(unittest.TestCase):
    """快手解析器 Mock 测试"""

    @patch.object(KuaishouParser, "_make_request")
    def test_parse_from_webpage(self, mock_request):
        """网页数据提取"""
        mock_resp = MagicMock()
        mock_resp.text = MOCK_KUAISHOU_HTML
        mock_resp.url = "https://v.kuaishou.com/short-video/abc123"
        mock_request.return_value = mock_resp

        parser = KuaishouParser()
        result = parser.parse("https://v.kuaishou.com/abc123")

        self.assertEqual(result.status, "success")
        self.assertEqual(result.platform, "kuaishou")
        self.assertEqual(result.title, "搞笑视频合集")


class TestWatermarkEngine(unittest.TestCase):
    """引擎主类集成测试"""

    def test_engine_parse_douyin(self):
        """引擎解析抖音链接"""
        engine = WatermarkEngine()
        # Mock 掉实际的网络请求
        with patch.object(DouyinParser, "parse") as mock_parse:
            mock_parse.return_value = ParseResult.success(
                platform="douyin",
                original_url="https://v.douyin.com/abc/",
                title="测试视频",
                cover_url="https://cover.jpg",
                download_url="https://video.mp4",
            )
            result = engine.parse("来看这个 https://v.douyin.com/abc/ 复制打开")
            self.assertEqual(result["status"], "success")
            self.assertEqual(result["platform"], "douyin")

    def test_engine_parse_bilibili(self):
        """引擎解析B站链接"""
        engine = WatermarkEngine()
        with patch.object(BilibiliParser, "parse") as mock_parse:
            mock_parse.return_value = ParseResult.success(
                platform="bilibili",
                original_url="https://b23.tv/abc",
                title="测试视频",
                cover_url="https://cover.jpg",
                download_url="https://video.mp4",
            )
            result = engine.parse("推荐你看 https://b23.tv/abc 超好看")
            self.assertEqual(result["status"], "success")
            self.assertEqual(result["platform"], "bilibili")

    def test_engine_no_url(self):
        """无链接输入"""
        engine = WatermarkEngine()
        result = engine.parse("这里没有任何链接")
        self.assertEqual(result["status"], "error")
        self.assertIn("有效链接", result["msg"])

    def test_engine_unsupported_platform(self):
        """不支持的平台"""
        engine = WatermarkEngine()
        result = engine.parse("https://www.google.com/search?q=xxx")
        self.assertEqual(result["status"], "error")
        self.assertIn("平台", result["msg"])

    def test_engine_batch_parse(self):
        """批量解析"""
        engine = WatermarkEngine()
        with patch.object(DouyinParser, "parse") as mock_douyin, \
             patch.object(BilibiliParser, "parse") as mock_bili:
            mock_douyin.return_value = ParseResult.success(
                platform="douyin",
                original_url="https://v.douyin.com/a/",
                title="抖音视频",
                download_url="https://douyin.mp4",
            )
            mock_bili.return_value = ParseResult.success(
                platform="bilibili",
                original_url="https://b23.tv/b",
                title="B站视频",
                download_url="https://bilibili.mp4",
            )
            text = "抖音 https://v.douyin.com/a/ 和 B站 https://b23.tv/b"
            results = engine.parse_batch(text)
            self.assertEqual(len(results), 2)
            self.assertEqual(results[0]["platform"], "douyin")
            self.assertEqual(results[1]["platform"], "bilibili")

    def test_engine_get_supported_platforms(self):
        """获取支持的平台列表"""
        platforms = WatermarkEngine.get_supported_platforms()
        self.assertIn("douyin", platforms)
        self.assertIn("bilibili", platforms)
        self.assertIn("xiaohongshu", platforms)
        self.assertIn("kuaishou", platforms)


# ============================================================
# 运行测试
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("  水印去除引擎 - Mock 测试套件")
    print("=" * 60)
    print()

    # 先运行 router 单元测试
    print("▶ 运行 Router 模块测试...")
    suite = unittest.TestLoader().loadTestsFromTestCase(TestRouter)
    unittest.TextTestRunner(verbosity=2).run(suite)

    print()
    print("▶ 运行 ParseResult 测试...")
    suite = unittest.TestLoader().loadTestsFromTestCase(TestParseResult)
    unittest.TextTestRunner(verbosity=2).run(suite)

    print()
    print("▶ 运行各平台解析器 Mock 测试...")
    loader = unittest.TestLoader()
    test_classes = [
        TestDouyinParser,
        TestBilibiliParser,
        TestXiaohongshuParser,
        TestKuaishouParser,
    ]
    for cls in test_classes:
        suite = loader.loadTestsFromTestCase(cls)
        unittest.TextTestRunner(verbosity=2).run(suite)

    print()
    print("▶ 运行 WatermarkEngine 集成测试...")
    suite = unittest.TestLoader().loadTestsFromTestCase(TestWatermarkEngine)
    unittest.TextTestRunner(verbosity=2).run(suite)

    print()
    print("=" * 60)
    print("  所有测试完成！")
    print("=" * 60)
