# -*- coding: utf-8 -*-
"""
大米星球 dmxq39.com - TVBox/FongMi Spider 学习版

说明：
1. 本脚本根据用户提供的 dmxq39.com 首页 HTML 编写。
2. 已确认网站采用 MacCMS 风格 URL，并确认了主要栏目：
   Netflix、电影、电视剧、短剧、动漫、综艺。
3. 列表页解析已经按照实际 HTML 中的 /voddetail/xxx.html、
   module-poster-item-title、module-item-note、data-original 等结构编写。
4. 详情页的“真实播放地址”结构没有包含在当前提供的首页源码中，
   因此播放地址解析采用通用 m3u8/mp4 检测；如果网站详情页另有
   加密播放器接口，需要再针对详情页源码调整。

依赖：
    requests

TVBox 环境通常自带 base.spider。
"""

import json
import re
from urllib.parse import quote, urlencode

import requests

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider:
        """本地学习/测试时的占位基类。"""
        pass


SITE = "https://www.dmxq39.com"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
}

TIMEOUT = 15

# 根据你提供的 dmxq39.com 首页源码确认
CATEGORY_LIST = [
    {"type_id": "netflix", "type_name": "Netflix"},
    {"type_id": "20", "type_name": "电影"},
    {"type_id": "21", "type_name": "电视剧"},
    {"type_id": "36", "type_name": "短剧"},
    {"type_id": "22", "type_name": "动漫"},
    {"type_id": "23", "type_name": "综艺"},
]


def fetch_html(url):
    """请求网页并返回 HTML。"""
    try:
        r = requests.get(
            url,
            headers={**HEADERS, "Referer": SITE + "/"},
            timeout=TIMEOUT,
            allow_redirects=True,
        )
        if r.status_code == 200:
            r.encoding = r.apparent_encoding or "utf-8"
            return r.text
    except Exception:
        pass
    return ""


def clean_html_text(text):
    """简单去除 HTML 标签并清理空白。"""
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&nbsp;", " ")
    text = text.replace("&amp;", "&")
    return re.sub(r"\s+", " ", text).strip()


def parse_video_list(html):
    """
    根据 dmxq39.com 实际首页 HTML 解析视频卡片。

    实际源码示例结构：
    <a href="/voddetail/403531.html" ...>
        <div class="module-item-note">第8集完结</div>
        <div class="module-item-pic">
            <img ... data-original="图片地址" alt="片名">
        </div>
        <div class="module-poster-item-title">片名</div>
    </a>
    """
    if not html:
        return []

    result = []
    seen = set()

    pattern = re.compile(
        r'<a\s+[^>]*href=["\'](/voddetail/\d+\.html)["\'][^>]*>'
        r'(.*?)'
        r'</a>',
        re.I | re.S,
    )

    for m in pattern.finditer(html):
        href = m.group(1)
        block = m.group(2)

        id_m = re.search(r"/voddetail/(\d+)\.html", href, re.I)
        if not id_m:
            continue

        vod_id = id_m.group(1)
        if vod_id in seen:
            continue
        seen.add(vod_id)

        # 片名：优先实际的 module-poster-item-title
        title_m = re.search(
            r'class=["\'][^"\']*module-poster-item-title[^"\']*["\'][^>]*>'
            r'\s*(.*?)\s*</div>',
            block,
            re.I | re.S,
        )

        # 回退到 a 的 title
        if title_m:
            title = clean_html_text(title_m.group(1))
        else:
            title_attr = re.search(
                r'\btitle=["\']([^"\']+)["\']',
                m.group(0),
                re.I,
            )
            title = clean_html_text(title_attr.group(1)) if title_attr else vod_id

        # 备注：例如“正片”“第8集完结”“更新至第05集”
        note_m = re.search(
            r'class=["\'][^"\']*module-item-note[^"\']*["\'][^>]*>'
            r'\s*(.*?)\s*</div>',
            block,
            re.I | re.S,
        )
        remark = clean_html_text(note_m.group(1)) if note_m else ""

        # 封面：网站实际源码把图片放在 data-original
        pic_m = re.search(
            r'data-original=["\']([^"\']+)["\']',
            block,
            re.I,
        )
        if not pic_m:
            pic_m = re.search(
                r'<img[^>]+src=["\']([^"\']+)["\']',
                block,
                re.I,
            )
        pic = pic_m.group(1) if pic_m else ""

        result.append({
            "vod_id": vod_id,
            "vod_name": title,
            "vod_pic": pic,
            "vod_remarks": remark,
        })

    return result


def parse_page_count(html):
    """从分页链接中尽量找出最大页码。"""
    if not html:
        return 1

    max_page = 1

    # MacCMS 常见：
    # /vodshow/20-----------2---.html
    # /vodsearch/-------------.html?page=2
    patterns = [
        r'/vodshow/[^"\']*?(\d+)---\.html',
        r'[?&]page=(\d+)',
        r'>\s*(\d+)\s*</a>',
    ]

    for pattern in patterns:
        for m in re.finditer(pattern, html, re.I):
            try:
                p = int(m.group(1))
                if 1 <= p <= 9999:
                    max_page = max(max_page, p)
            except Exception:
                pass

    return max_page


def parse_detail(html, vod_id):
    """解析详情页基础信息。"""
    if not html:
        return {}

    # 标题
    title = ""
    for pattern in (
        r'<h1[^>]*>(.*?)</h1>',
        r'<title[^>]*>(.*?)</title>',
    ):
        m = re.search(pattern, html, re.I | re.S)
        if m:
            title = clean_html_text(m.group(1))
            if title:
                break

    # OG 图片
    pic = ""
    m = re.search(
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        html,
        re.I,
    )
    if m:
        pic = m.group(1)

    # 简介
    content = ""
    m = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)["\']',
        html,
        re.I,
    )
    if m:
        content = clean_html_text(m.group(1))

    # 兼容常见直链/HLS格式。
    # 注意：如果网站详情页使用 JS/接口动态生成播放地址，
    # 这里需要根据详情页实际源码继续定制。
    play_urls = []
    seen = set()

    for m in re.finditer(
        r'https?://[^"\'<>\s]+?\.(?:m3u8|mp4)(?:\?[^"\'<>\s]*)?',
        html,
        re.I,
    ):
        url = m.group(0)
        if url not in seen:
            seen.add(url)
            play_urls.append(url)

    play_from = []
    play_url = []

    for i, url in enumerate(play_urls, 1):
        play_from.append("线路%d" % i)
        play_url.append("正片$" + url)

    return {
        "vod_id": vod_id,
        "vod_name": title or vod_id,
        "vod_pic": pic,
        "vod_content": content,
        "vod_play_from": "$$$".join(play_from),
        "vod_play_url": "$$$".join(play_url),
    }


class Spider(BaseSpider):
    """TVBox/FongMi Spider。"""

    def getName(self):
        return "大米星球"

    def init(self, extend=""):
        pass

    def destroy(self):
        pass

    def isVideoFormat(self, url):
        if not url:
            return False
        return bool(re.search(r"\.(m3u8|mp4|flv|ts)(?:\?|$)", url, re.I))

    def manualVideoCheck(self):
        return False

    def homeContent(self, filter):
        result = {
            "class": CATEGORY_LIST,
        }

        html = fetch_html(SITE + "/index/home.html")
        if not html:
            html = fetch_html(SITE + "/")

        result["list"] = parse_video_list(html)
        return result

    def homeVideoContent(self):
        html = fetch_html(SITE + "/index/home.html")
        if not html:
            html = fetch_html(SITE + "/")
        return {"list": parse_video_list(html)}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = max(1, int(pg or 1))
        except Exception:
            page = 1

        # Netflix 是网站自己的 label 路由
        if tid == "netflix":
            if page == 1:
                url = SITE + "/label/netflix.html"
            else:
                url = SITE + "/label/netflix.html?page=" + str(page)
        else:
            # dmxq39 首页实际导航：
            # 电影 /vodtype/20.html
            # 电视剧 /vodtype/21.html
            # 短剧 /vodtype/36.html
            # 动漫 /vodtype/22.html
            # 综艺 /vodtype/23.html
            #
            # 列表页采用 MacCMS 常见 vodshow 路由。
            if page == 1:
                url = SITE + "/vodshow/%s-----------.html" % tid
            else:
                url = SITE + "/vodshow/%s-----------%d---.html" % (tid, page)

        html = fetch_html(url)
        videos = parse_video_list(html)

        return {
            "list": videos,
            "page": page,
            "pagecount": parse_page_count(html),
            "limit": len(videos) if videos else 20,
            "total": 0,
        }

    def detailContent(self, ids):
        if not ids:
            return {"list": []}

        vod_id = ids[0] if isinstance(ids, list) else str(ids)

        html = fetch_html(SITE + "/voddetail/%s.html" % vod_id)
        if not html:
            return {"list": []}

        return {"list": [parse_detail(html, vod_id)]}

    def searchContent(self, key, quick, pg="1"):
        if not key:
            return {"list": []}

        try:
            page = max(1, int(pg or 1))
        except Exception:
            page = 1

        # 首页源代码已经确认搜索表单：
        # action="/vodsearch/-------------.html" method="get"
        # input name="wd"
        params = {"wd": key.strip()}
        if page > 1:
            params["page"] = page

        url = SITE + "/vodsearch/-------------.html?" + urlencode(params)

        html = fetch_html(url)

        return {
            "list": parse_video_list(html),
            "page": page,
            "pagecount": parse_page_count(html),
            "total": 0,
        }

    def playerContent(self, flag, id, vipFlags):
        if not id:
            return {
                "parse": 0,
                "playUrl": "",
                "url": "",
            }

        return {
            "parse": 0,
            "playUrl": "",
            "url": id.strip(),
            "header": json.dumps({
                "User-Agent": HEADERS["User-Agent"],
                "Referer": SITE + "/",
            }),
        }

    def localProxy(self, param):
        return [200, "text/plain", b"", ""]


# 本地测试：
# python dmxq39.py
if __name__ == "__main__":
    html = fetch_html(SITE + "/")
    videos = parse_video_list(html)

    print("站点:", SITE)
    print("解析到视频:", len(videos))

    for item in videos[:10]:
        print(
            item["vod_id"],
            item["vod_name"],
            item["vod_remarks"],
            item["vod_pic"],
        )
