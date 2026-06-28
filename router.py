"""
Router Module - 文本提取与正则路由
从用户输入的杂乱文本中提取有效 URL，并根据域名分发到对应的平台解析器。
"""

import re
from typing import Optional, List, Tuple
from urllib.parse import urlparse


# ============================================================
# 平台域名匹配规则（按优先级排列）
# ============================================================
PLATFORM_RULES: List[Tuple[str, re.Pattern, str]] = [
    # (平台名称, URL正则, 匹配优先级说明)
    ("douyin", re.compile(
        r'https?://(?:v|www)\.douyin\.com/[^\s<>"\']+', re.IGNORECASE
    ), "抖音 - v.douyin.com / www.douyin.com"),

    ("xiaohongshu", re.compile(
        r'https?://(?:www\.xiaohongshu\.com|link\.xiaohongshu\.com|xhslink\.com)/[^\s<>"\']+', re.IGNORECASE
    ), "小红书 - xiaohongshu.com / xhslink.com"),

    ("bilibili", re.compile(
        r'https?://(?:www\.bilibili\.com/video/[^\s<>"\']+|b23\.tv/[^\s<>"\']+|m\.bilibili\.com/video/[^\s<>"\']+)',
        re.IGNORECASE
    ), "B站 - bilibili.com / b23.tv"),

    ("kuaishou", re.compile(
        r'https?://(?:v\.kuaishou\.com|www\.kuaishou\.com|v\.yxj\.net\.cn)/[^\s<>"\']+', re.IGNORECASE
    ), "快手 - kuaishou.com"),
]

# 通用 URL 正则 —— 兜底提取所有看起来像链接的内容
URL_FALLBACK_RE = re.compile(
    r'https?://[^\s<>"\']+',
    re.IGNORECASE
)


def extract_urls(text: str) -> List[str]:
    """
    从用户输入的文本中提取所有有效的 HTTP/HTTPS URL。
    
    示例:
        "你看这个太搞笑了！http://v.douyin.com/xxx/ 复制打开"
        -> ["http://v.douyin.com/xxx/"]
    """
    urls = URL_FALLBACK_RE.findall(text)
    # 清理 URL 尾部常见的干扰字符
    cleaned = []
    for url in urls:
        # 移除末尾可能粘连的中文标点或括号
        url = re.sub(r'[）\)」』》\]\}，,。.！!？?]+$', '', url)
        cleaned.append(url)
    return cleaned


def identify_platform(url: str) -> Optional[str]:
    """
    根据 URL 的域名特征识别所属平台。
    
    Returns:
        平台名称字符串，如 "douyin", "bilibili" 等；无法识别时返回 None。
    """
    for platform_name, pattern, _ in PLATFORM_RULES:
        if pattern.search(url):
            return platform_name
    return None


def route(text: str) -> List[Tuple[str, str]]:
    """
    主路由函数：从文本中提取 URL 并识别平台。
    
    Returns:
        [(平台名称, URL), ...] 的列表，未识别平台的 URL 会被标记为 "unknown"。
    """
    urls = extract_urls(text)
    results = []
    for url in urls:
        platform = identify_platform(url) or "unknown"
        results.append((platform, url))
    return results


def resolve_short_url(url: str) -> str:
    """
    解析短链接（如 v.douyin.com, b23.tv）获取最终的重定向 URL。
    
    使用 requests 库跟踪重定向链，返回最终跳转后的真实地址。
    """
    import requests
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/17.0 Mobile/15E148 Safari/604.1"
        ),
    }
    try:
        resp = requests.head(url, headers=headers, allow_redirects=True, timeout=10)
        return resp.url
    except requests.RequestException:
        return url


def extract_video_id(url: str, platform: str) -> Optional[str]:
    """
    根据平台和 URL 提取视频/内容 ID。
    
    Returns:
        内容 ID 字符串，提取失败返回 None。
    """
    if platform == "douyin":
        # https://v.douyin.com/xxxxxxx/ -> 先解析短链得到真实URL，再提取ID
        match = re.search(r'/video/(\d+)', url)
        if match:
            return match.group(1)
        # 短链情况下需要解析重定向
        return None

    elif platform == "bilibili":
        # https://www.bilibili.com/video/BVxxxxxxxxxx
        match = re.search(r'/video/(BV\w+|av\d+)', url)
        if match:
            return match.group(1)
        # https://b23.tv/xxxxxxx
        match = re.search(r'b23\.tv/(\w+)', url)
        if match:
            return match.group(1)
        return None

    elif platform == "xiaohongshu":
        # https://www.xiaohongshu.com/explore/xxxxxxxxxx
        match = re.search(r'/(?:explore|discovery/item)/(\w+)', url)
        if match:
            return match.group(1)
        # /note/xxxxx
        match = re.search(r'/note/(\w+)', url)
        if match:
            return match.group(1)
        return None

    elif platform == "kuaishou":
        # https://v.kuaishou.com/xxxxxxx
        match = re.search(r'/short-video/(\w+)', url)
        if match:
            return match.group(1)
        return None

    return None
