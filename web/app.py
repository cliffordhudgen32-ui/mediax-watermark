"""
Watermark Engine Web - Flask 后端
短视频去水印解析 Web 操作平台
"""

import os
import sys
import json
import logging
import requests
from flask import Flask, render_template, request, jsonify, Response, stream_with_context

# 将项目根目录加入 path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from watermark_engine.engine import WatermarkEngine
from watermark_engine.router import route

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False

engine = WatermarkEngine()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("watermark_web")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/parse", methods=["POST"])
def api_parse():
    data = request.get_json(silent=True) or {}
    text = data.get("url", "").strip()

    if not text:
        return jsonify({"status": "error", "msg": "请输入链接或分享文案"})

    try:
        result = engine.parse(text)
        return jsonify(result)
    except Exception as e:
        logger.exception(f"解析异常: {e}")
        return jsonify({
            "status": "error",
            "msg": f"服务器内部错误: {str(e)}",
            "platform": "unknown",
            "original_url": text,
        })


@app.route("/api/parse_batch", methods=["POST"])
def api_parse_batch():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()

    if not text:
        return jsonify({"status": "error", "msg": "请输入包含链接的文本"})

    try:
        routes = route(text)
        if not routes:
            return jsonify({
                "status": "error",
                "msg": "未在输入中找到任何有效链接",
                "results": [],
            })

        results = []
        for platform, url in routes:
            result = engine.parse(url)
            results.append(result)

        return jsonify({
            "status": "success",
            "count": len(results),
            "results": results,
        })
    except Exception as e:
        logger.exception(f"批量解析异常: {e}")
        return jsonify({"status": "error", "msg": str(e), "results": []})


@app.route("/api/proxy")
def api_proxy():
    url = request.args.get("url", "").strip()
    filename = request.args.get("filename", "video.mp4").strip()

    if not url:
        return jsonify({"status": "error", "msg": "缺少 url 参数"}), 400

    referer = "https://www.douyin.com/"
    if "bilibili" in url or "b23.tv" in url:
        referer = "https://www.bilibili.com/"
    elif "xiaohongshu" in url or "xhslink" in url:
        referer = "https://www.xiaohongshu.com/"
    elif "kuaishou" in url:
        referer = "https://www.kuaishou.com/"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/130.0.0.0 Mobile Safari/537.36"
        ),
        "Referer": referer,
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Accept-Encoding": "identity",
    }

    try:
        remote = requests.get(url, headers=headers, allow_redirects=True, stream=True, timeout=30)
        remote.raise_for_status()

        content_type = remote.headers.get("Content-Type", "video/mp4")
        content_length = remote.headers.get("Content-Length")

        resp_headers = {
            "Content-Type": content_type,
            "Content-Disposition": 'attachment; filename="' + filename + '"',
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*",
            "Pragma": "no-cache",
        }
        if content_length:
            resp_headers["Content-Length"] = content_length

        def generate():
            for chunk in remote.iter_content(chunk_size=65536):
                if chunk:
                    yield chunk

        return Response(
            stream_with_context(generate()),
            status=200,
            headers=resp_headers,
        )

    except requests.exceptions.RequestException as e:
        logger.error(f"代理下载失败: {e}")
        return jsonify({"status": "error", "msg": f"下载失败: {str(e)}"}), 502


@app.route("/api/platforms", methods=["GET"])
def api_platforms():
    platforms = {
        "douyin": {"name": "抖音", "icon": "🎵", "domains": ["douyin.com"]},
        "kuaishou": {"name": "快手", "icon": "⚡", "domains": ["kuaishou.com"]},
        "bilibili": {"name": "B站", "icon": "📺", "domains": ["bilibili.com", "b23.tv"]},
        "xiaohongshu": {"name": "小红书", "icon": "📕", "domains": ["xiaohongshu.com", "xhslink.com"]},
    }
    return jsonify(platforms)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("=" * 50)
    print("  Video Watermark Removal Engine - Web UI")
    print(f"  http://localhost:{port}")
    print("=" * 50)
    app.run(host="0.0.0.0", port=port, debug=True)
