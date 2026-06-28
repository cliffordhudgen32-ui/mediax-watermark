# MediaX - 短视频去水印解析引擎

全网短视频/图文去水印解析聚合引擎，支持多平台一键提取无水印视频/图文直链。

## 支持平台

| 平台 | 域名 |
|------|------|
| 抖音 | douyin.com |
| 快手 | kuaishou.com |
| B站 | bilibili.com, b23.tv |
| 小红书 | xiaohongshu.com, xhslink.com |

## 功能特性

- 🔗 一键粘贴分享文案，自动提取有效链接
- 🎵 多平台智能识别与路由解析
- 📱 移动端优先的响应式 Web UI
- ⬇️ 代理下载，解决 CDN 403 问题
- 📋 解析历史记录本地存储
- 🔍 统一数据输出格式

## 快速开始

### 安装依赖

`ash
pip install requests gmssl flask
`

### 启动服务

`ash
cd watermark_engine
python -m watermark_engine.web.app
`

打开浏览器访问 http://localhost:5000

### API 接口

**解析接口**

`
POST /api/parse
Content-Type: application/json

{
  "url": "https://v.douyin.com/xxx/ 或包含链接的分享文案"
}
`

**批量解析**

`
POST /api/parse_batch
Content-Type: application/json

{
  "text": "包含多个链接的文本"
}
`

**代理下载**

`
GET /api/proxy?url=<视频直链>&filename=<文件名>.mp4
`

## 项目结构

`
watermark_engine/
├── engine.py              # 核心解析引擎
├── router.py              # URL 提取与路由分发
├── abogus.py              # 抖音 a_bogus 签名算法
├── xbogus.py              # 抖音 X-Bogus 签名算法
├── parsers/
│   ├── base.py            # 解析器基类
│   ├── douyin_parser.py   # 抖音解析器
│   ├── kuaishou_parser.py # 快手解析器
│   ├── bilibili_parser.py # B站解析器
│   └── xiaohongshu_parser.py # 小红书解析器
├── web/
│   ├── app.py             # Flask Web 服务
│   ├── templates/
│   │   └── index.html     # 移动端前端页面
│   └── static/
│       ├── style.css      # 样式文件
│       └── script.js      # 前端逻辑
└── test_engine.py         # 单元测试
`

## 技术栈

- Python 3.11+
- Flask
- requests
- gmssl (SM3 哈希)

## License

MIT
