#!/usr/bin/env python3
"""GitHub 中文热门日报生成器。

用法：
  python3 generate.py fetch   # 抓取 trending 日榜/周榜，存 data-YYYY-MM-DD.json
  python3 generate.py build   # 读 data + comments-YYYY-MM-DD.json（可选），
                              # 生成 daily/YYYY-MM-DD.md 并更新 README.md 索引

数据来源：https://github.com/trending （普通网页请求，不用任何令牌）。
中文项目判定：仓库简介中含有中文字符。
点评来源：comments 文件里人工基于真实简介写的一句话；缺失时回退为简介首句浓缩，
两者都只源自仓库真实简介，不编造功能。
"""
import html
import json
import os
import re
import sys
import urllib.request
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def fetch_page(since):
    req = urllib.request.Request(
        f"https://github.com/trending?since={since}",
        headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", "replace")


def _strip_tags(fragment):
    text = re.sub(r"<[^>]+>", " ", fragment)
    return " ".join(html.unescape(text).split())


def parse_trending(html):
    """Split the page into <article class="Box-row"> chunks and extract fields."""
    chunks = re.split(r'<article class="Box-row">', html)[1:]
    repos = []
    for chunk in chunks:
        chunk = chunk.split("</article>")[0]
        m = re.search(r"<h2[^>]*>.*?<a[^>]+href=\"(/[^\"]+)\"", chunk, re.S)
        if not m or not re.fullmatch(r"/[^/]+/[^/]+", m.group(1)):
            continue
        path = m.group(1)
        repo = {"name": path.strip("/"),
                "url": "https://github.com" + path,
                "description": "", "language": "",
                "total_stars": "", "period_stars": ""}
        m = re.search(r'<p class="col-9[^"]*">(.*?)</p>', chunk, re.S)
        if m:
            repo["description"] = _strip_tags(m.group(1))
        m = re.search(r'itemprop="programmingLanguage">([^<]+)<', chunk)
        if m:
            repo["language"] = m.group(1).strip()
        m = re.search(r'href="' + re.escape(path) + r'/stargazers"[^>]*>(.*?)</a>',
                      chunk, re.S)
        if m:
            repo["total_stars"] = _strip_tags(m.group(1))
        m = re.search(r"([\d,]+)\s+stars?\s+(?:today|this week)", chunk)
        if m:
            repo["period_stars"] = m.group(1)
        repos.append(repo)
    return repos


def is_chinese(repo):
    return bool(CJK.search(repo.get("description") or ""))


def today_str():
    return date.today().isoformat()


def do_fetch():
    day = today_str()
    data = {}
    for since in ("daily", "weekly"):
        repos = parse_trending(fetch_page(since))
        for r in repos:
            r["is_chinese"] = is_chinese(r)
        data[since] = repos
        cn = sum(1 for r in repos if r["is_chinese"])
        print(f"{since}: {len(repos)} repos, {cn} chinese")
    out = os.path.join(HERE, f"data-{day}.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    print("saved", out)


def fallback_comment(desc):
    """Condense the real description's first sentence; never invents features."""
    d = (desc or "").strip()
    for sep in ("。", ". ", "！", "!", "；", ";"):
        if sep in d:
            d = d.split(sep)[0]
            break
    return d[:60].rstrip("，。,. ")


def do_build():
    day = today_str()
    with open(os.path.join(HERE, f"data-{day}.json"), encoding="utf-8") as fh:
        data = json.load(fh)
    comments = {}
    cpath = os.path.join(HERE, f"comments-{day}.json")
    if os.path.exists(cpath):
        with open(cpath, encoding="utf-8") as fh:
            comments = json.load(fh)

    daily = data["daily"]
    weekly = data["weekly"]
    cn_daily = [r for r in daily if r["is_chinese"]][:15]
    cn_weekly = [r for r in weekly if r["is_chinese"]]

    lines = []
    lines.append(f"# GitHub 中文热门日报 · {day}")
    lines.append("")
    lines.append(f"今日 GitHub 热门榜共 {len(daily)} 个仓库，其中中文项目 "
                 f"{sum(1 for r in daily if r['is_chinese'])} 个"
                 + ("，本期全部列出如下。" if len(cn_daily) < 15
                    else "，取前 15 个列出如下。"))
    lines.append("")
    lines.append("## 今日中文热门项目")
    lines.append("")
    if not cn_daily:
        lines.append("今日热门榜暂无简介含中文的项目。")
        lines.append("")
    for i, r in enumerate(cn_daily, 1):
        comment = comments.get(r["name"]) or fallback_comment(r["description"])
        meta = []
        if r["language"]:
            meta.append(r["language"])
        if r["total_stars"]:
            meta.append(f"总星 {r['total_stars']}")
        if r["period_stars"]:
            meta.append(f"今日 +{r['period_stars']}")
        lines.append(f"### {i}. [{r['name']}]({r['url']})")
        lines.append("")
        if meta:
            lines.append(" · ".join(meta))
            lines.append("")
        if r["description"]:
            lines.append(f"> {r['description']}")
            lines.append("")
        lines.append(f"**一句话点评：** {comment}")
        lines.append("")

    if cn_weekly:
        lines.append("## 本周上榜的中文项目（周榜）")
        lines.append("")
        for r in cn_weekly:
            meta = []
            if r["language"]:
                meta.append(r["language"])
            if r["total_stars"]:
                meta.append(f"总星 {r['total_stars']}")
            if r["period_stars"]:
                meta.append(f"本周 +{r['period_stars']}")
            lines.append(f"- [{r['name']}]({r['url']})"
                         + (f"（{' · '.join(meta)}）" if meta else "")
                         + f"：{r['description']}")
        lines.append("")

    lines.append("## 附录：今日完整热门榜前 10")
    lines.append("")
    for i, r in enumerate(daily[:10], 1):
        meta = []
        if r["language"]:
            meta.append(r["language"])
        if r["total_stars"]:
            meta.append(f"总星 {r['total_stars']}")
        if r["period_stars"]:
            meta.append(f"今日 +{r['period_stars']}")
        lines.append(f"{i}. [{r['name']}]({r['url']})"
                     + (f"（{' · '.join(meta)}）" if meta else ""))
        if r["description"]:
            lines.append(f"   {r['description']}")
    lines.append("")
    lines.append("---")
    lines.append("数据来源：GitHub Trending（日榜/周榜）。中文项目按简介含中文字符判定；"
                 "点评均基于仓库真实简介概括。")
    lines.append("")

    os.makedirs(os.path.join(HERE, "daily"), exist_ok=True)
    out = os.path.join(HERE, "daily", f"{day}.md")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print("wrote", out)
    update_readme(day, cn_daily)


README_TEMPLATE = """# GitHub 中文热门日报

每天追踪 GitHub 热门榜（Trending），专挑**中文项目**，每个项目配一句基于其真实简介的中文点评，帮你快速发现值得关注的国产/中文开源项目。

- 数据来源：GitHub Trending 日榜与周榜
- 中文项目判定：仓库简介中含有中文字符
- 更新方式：由 `generate.py` 抓取生成（`fetch` 抓榜单 → `build` 出日报）

## 最新一期

<!-- LATEST:START -->
<!-- LATEST:END -->

## 历史索引

<!-- INDEX:START -->
<!-- INDEX:END -->
"""


def update_readme(day, cn_daily):
    path = os.path.join(HERE, "README.md")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            readme = fh.read()
    else:
        readme = README_TEMPLATE
    latest = f"**最新一期：[{day} 日报](daily/{day}.md)**"
    if cn_daily:
        names = "、".join(r["name"] for r in cn_daily[:5])
        latest += f"\n\n本期中文项目速览：{names} 等 {len(cn_daily)} 个。"
    readme = re.sub(r"<!-- LATEST:START -->.*?<!-- LATEST:END -->",
                    f"<!-- LATEST:START -->\n{latest}\n<!-- LATEST:END -->",
                    readme, flags=re.S)
    entry = f"- [{day}](daily/{day}.md)"
    m = re.search(r"<!-- INDEX:START -->\n(.*?)<!-- INDEX:END -->", readme, flags=re.S)
    old = m.group(1) if m else ""
    entries = [ln for ln in old.splitlines() if ln.strip().startswith("- [")]
    if entry not in entries:
        entries.insert(0, entry)
    readme = re.sub(r"<!-- INDEX:START -->.*?<!-- INDEX:END -->",
                    "<!-- INDEX:START -->\n" + "\n".join(entries) + "\n<!-- INDEX:END -->",
                    readme, flags=re.S)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(readme)
    print("updated README.md")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("fetch", "build"):
        print(__doc__)
        sys.exit(1)
    {"fetch": do_fetch, "build": do_build}[sys.argv[1]]()
