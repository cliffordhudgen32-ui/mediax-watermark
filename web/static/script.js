const PLATFORM_META = {
    douyin:       { name: "抖音",     icon: "🎵", badge: "badge-douyin" },
    kuaishou:     { name: "快手",     icon: "⚡", badge: "badge-kuaishou" },
    bilibili:     { name: "B站",      icon: "📺", badge: "badge-bilibili" },
    xiaohongshu:  { name: "小红书",   icon: "📕", badge: "badge-xiaohongshu" },
    unknown:      { name: "未知",     icon: "🔗", badge: "badge-unknown" },
};

let history = JSON.parse(localStorage.getItem("parseHistory") || "[]");

// ===== Core Parse =====

async function parseUrl() {
    const input = document.getElementById("urlInput");
    const text = input.value.trim();
    if (!text) { showToast("请输入链接或分享文案"); input.focus(); return; }

    const btn = document.getElementById("parseBtn");
    const btnText = btn.querySelector(".btn-text");
    const btnLoading = btn.querySelector(".btn-loading");

    btn.disabled = true;
    btnText.style.display = "none";
    btnLoading.style.display = "inline-flex";

    const area = document.getElementById("resultArea");
    area.style.display = "block";
    area.innerHTML = renderLoading();

    try {
        const resp = await fetch("/api/parse", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url: text }),
        });
        const data = await resp.json();
        area.innerHTML = renderResult(data);
        addToHistory(data);
    } catch (err) {
        area.innerHTML = renderResult({
            status: "error", msg: "网络请求失败，请检查服务是否运行",
            platform: "unknown", original_url: text,
        });
    } finally {
        btn.disabled = false;
        btnText.style.display = "inline-flex";
        btnLoading.style.display = "none";
    }
}

// ===== Render =====

function renderLoading() {
    return '<div class="result-card" style="padding:48px 16px;text-align:center;">'
        + '<div class="spinner" style="width:28px;height:28px;border-width:3px;margin:0 auto;"></div>'
        + '<p style="margin-top:14px;color:var(--text3);font-size:13px;">正在解析中，请稍候...</p></div>';
}

function renderResult(data) {
    const meta = PLATFORM_META[data.platform] || PLATFORM_META.unknown;
    const ok = data.status === "success";

    if (!ok) {
        return '<div class="result-card">'
            + '<div class="result-top">'
            + '<span class="result-badge ' + meta.badge + '">' + meta.icon + ' ' + esc(meta.name) + '</span>'
            + '<span class="result-title" style="color:var(--error);">解析失败</span>'
            + '</div>'
            + '<div class="error-box">❌ ' + esc(data.msg || "解析失败") + '</div>'
            + (data.original_url
                ? '<div class="result-fields"><div class="result-field">'
                + '<span class="field-label">链接</span>'
                + '<span class="field-value">' + esc(data.original_url) + '</span></div></div>'
                : '')
            + '</div>';
    }

    let cover = "";
    if (data.cover_url) {
        cover = '<div style="padding:0 16px;"><img class="result-cover" src="' + escAttr(data.cover_url)
            + '" onerror="this.style.display=\'none\'" alt="cover"></div>';
    }

    var proxyUrl = '/api/proxy?url=' + encodeURIComponent(data.download_url)
        + '&filename=' + encodeURIComponent((data.title || "video") + ".mp4");

    return '<div class="result-card">'
        + '<div class="result-top">'
        + '<span class="result-badge ' + meta.badge + '">' + meta.icon + ' ' + esc(meta.name) + '</span>'
        + '<span class="result-title">' + esc(data.title || "未知标题") + '</span>'
        + '</div>'
        + cover
        + '<div class="result-fields">'
        + fieldRow("标题", esc(data.title || "-"))
        + fieldRow("来源", '<a href="' + escAttr(data.original_url) + '" target="_blank" rel="noopener">' + esc(data.original_url) + '</a>')
        + (data.download_url ? fieldRow("下载链接",
            '<a href="' + escAttr(data.download_url) + '" target="_blank" rel="noopener">' + truncUrl(data.download_url) + '</a>',
            data.download_url) : '')
        + (data.cover_url ? fieldRow("封面链接",
            '<a href="' + escAttr(data.cover_url) + '" target="_blank" rel="noopener">' + truncUrl(data.cover_url) + '</a>',
            data.cover_url) : '')
        + '</div>'
        + (data.download_url
            ? '<div class="result-actions">'
            + '<button class="btn-download" onclick="downloadVideo(this)" data-url="' + escAttr(data.download_url) + '" data-filename="' + escAttr((data.title || "video") + ".mp4") + '">'
            + '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>'
            + '<span>下载视频</span></button>'
            + '<button class="btn-copy-link" onclick="copyText(\'' + escAttr(data.download_url) + '\', this)">'
            + '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>'
            + '复制链接</button></div>'
            : '')
        + '</div>';
}

function fieldRow(label, content, copyVal) {
    var btn = copyVal
        ? '<button class="btn-copy-sm" onclick="copyText(\'' + escAttr(copyVal) + '\', this)">复制</button>'
        : '';
    return '<div class="result-field">'
        + '<span class="field-label">' + label + '</span>'
        + '<span class="field-value">' + content + btn + '</span></div>';
}

// ===== Download Handler =====
// Use fetch -> blob -> objectURL to trigger download on mobile

async function downloadVideo(btnEl) {
    var url = btnEl.getAttribute("data-url");
    var filename = btnEl.getAttribute("data-filename") || "video.mp4";
    if (!url) return;

    var originalHTML = btnEl.innerHTML;
    btnEl.disabled = true;
    btnEl.innerHTML = '<span class="spinner" style="width:14px;height:14px;border-width:2px;"></span><span>下载中...</span>';

    try {
        var proxyUrl = '/api/proxy?url=' + encodeURIComponent(url) + '&filename=' + encodeURIComponent(filename);

        var resp = await fetch(proxyUrl);
        if (!resp.ok) throw new Error("下载失败: " + resp.status);

        var blob = await resp.blob();
        var blobUrl = URL.createObjectURL(blob);

        var a = document.createElement("a");
        a.href = blobUrl;
        a.download = filename;
        a.style.display = "none";
        document.body.appendChild(a);
        a.click();

        setTimeout(function() {
            document.body.removeChild(a);
            URL.revokeObjectURL(blobUrl);
        }, 1000);

        showToast("下载已开始");
    } catch (e) {
        console.error("下载失败:", e);
        showToast("下载失败，请复制链接手动下载");

        // Fallback: open in new tab
        try {
            window.open(proxyUrl, "_blank");
        } catch (e2) {
            // ignore
        }
    } finally {
        btnEl.disabled = false;
        btnEl.innerHTML = originalHTML;
    }
}

// ===== History =====

function addToHistory(item) {
    var row = {
        platform: item.platform,
        title: item.title || "未知标题",
        url: item.original_url,
        downloadUrl: item.download_url,
        status: item.status,
    };
    history = history.filter(function(h) { return h.url !== row.url; });
    history.unshift(row);
    if (history.length > 30) history = history.slice(0, 30);
    localStorage.setItem("parseHistory", JSON.stringify(history));
    renderHistory();
}

function renderHistory() {
    var section = document.getElementById("historySection");
    var list = document.getElementById("historyList");
    if (!history.length) {
        section.style.display = "none";
        return;
    }

    section.style.display = "block";
    list.innerHTML = history.map(function(h) {
        var m = PLATFORM_META[h.platform] || PLATFORM_META.unknown;
        var statusClass = h.status === "success" ? "ok" : "err";
        var statusText = h.status === "success" ? "成功" : "失败";
        return '<div class="history-item" onclick="reuse(\'' + escAttr(h.url || '') + '\')">'
            + '<span class="h-icon">' + m.icon + '</span>'
            + '<div class="h-info">'
            + '<div class="h-title">' + esc(h.title) + '</div>'
            + '<div class="h-meta">' + esc(m.name) + '</div>'
            + '</div>'
            + '<span class="h-status ' + statusClass + '">' + statusText + '</span>'
            + '</div>';
    }).join("");
}

function reuse(url) {
    if (url) {
        document.getElementById("urlInput").value = url;
        parseUrl();
        window.scrollTo({ top: 0, behavior: "smooth" });
    }
}

function clearHistory() {
    history = [];
    localStorage.removeItem("parseHistory");
    renderHistory();
    showToast("已清空记录");
}

// ===== Utilities =====

async function pasteFromClipboard() {
    try {
        var t = await navigator.clipboard.readText();
        document.getElementById("urlInput").value = t;
        showToast("已粘贴");
    } catch (e) {
        showToast("无法访问剪贴板，请手动粘贴");
    }
}

function clearAll() {
    document.getElementById("urlInput").value = "";
    document.getElementById("resultArea").style.display = "none";
    document.getElementById("urlInput").focus();
}

function copyText(text, btnEl) {
    navigator.clipboard.writeText(text).then(function() {
        if (btnEl) {
            var orig = btnEl.textContent;
            btnEl.textContent = "已复制";
            btnEl.classList.add("copied");
            setTimeout(function() {
                btnEl.textContent = orig;
                btnEl.classList.remove("copied");
            }, 1500);
        }
        showToast("已复制到剪贴板");
    }).catch(function() {
        showToast("复制失败，请长按手动复制");
    });
}

function showToast(msg) {
    var t = document.getElementById("toast");
    t.textContent = msg;
    t.classList.add("show");
    clearTimeout(t._timer);
    t._timer = setTimeout(function() { t.classList.remove("show"); }, 2000);
}

function esc(s) {
    if (!s) return "";
    var d = document.createElement("div"); d.textContent = s; return d.innerHTML;
}

function escAttr(s) {
    if (!s) return "";
    return s.replace(/&/g,"&amp;").replace(/'/g,"&#39;").replace(/"/g,"&quot;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

function truncUrl(u) {
    if (!u) return "";
    return u.length <= 50 ? u : u.substring(0, 22) + "..." + u.substring(u.length - 22);
}

// ===== Platform Filter =====

document.querySelectorAll(".ptag").forEach(function(tag) {
    tag.addEventListener("click", function() {
        document.querySelectorAll(".ptag").forEach(function(t) { t.classList.remove("active"); });
        tag.classList.add("active");
    });
});

// ===== Keyboard =====

var urlInput = document.getElementById("urlInput");
if (urlInput) {
    urlInput.addEventListener("keydown", function(e) {
        if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
            e.preventDefault();
            parseUrl();
        }
    });
}

// ===== Init =====
renderHistory();
