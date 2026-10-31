"""The GitHub Wiki of Remiqora Video, built from the in-app help (frontend/src/lib/help*.ts, tutorials/) in both languages.

    py -3.13 tools\\wiki\\build_wiki.py <out-dir> [--version 0.1.0] [--preview]

Pages: Home (English contents) and «Справка» (Russian contents), «From idea to video» / «От идеи до ролика» (the
worked example), one page per help section and scenario in each language, _Sidebar and _Footer. Every section page
links to its twin in the other language. --preview also writes <out-dir>/preview/*.html rendered by GitHub's own
Markdown API, to look at the pages before they are pushed. The help in the app stays the source: never edit the wiki.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
REPO = "inikolax/remiqora-video"
RAW = f"https://raw.githubusercontent.com/{REPO}/master"
VOID = {"br", "img", "hr", "input", "meta", "link", "source", "wbr"}
BLOCK = {"p", "div", "ul", "ol", "li", "dl", "dt", "dd", "pre", "table", "figure", "figcaption", "h1", "h2", "h3", "h4",
         "thead", "tbody", "tr", "td", "th", "section", "blockquote"}
T = {
    "ru": {"home": "Справка", "hero": "От идеи до ролика", "contents": "Содержание", "other": "English",
           "keys": "Клавиши", "action": "Что делает", "worse": "Так хуже", "better": "Так лучше",
           "intro": "Справка Remiqora Video — та же, что встроена в приложение (кнопка «Справка» в шапке и «?» у каждого поля): "
                    "каждый экран, каждый узел графа, формат промтов, модели, настройки и сценарии по шагам.",
           "start": "Начните с разбора одного ролика целиком", "footer": "Собрано из справки приложения"},
    "en": {"home": "Home", "hero": "From idea to video", "contents": "Contents", "other": "Русский",
           "keys": "Keys", "action": "What it does", "worse": "Worse", "better": "Better",
           "intro": "The Remiqora Video help — the same one that is built into the app (the «Help» button in the header and the "
                    "«?» by every field): every screen, every graph node, the prompt format, the models, the settings and step-by-step scenarios.",
           "start": "Start with one video taken apart from idea to film", "footer": "Built from the app's help"},
}


# the README's screenshots (docs/screenshots, English ones in en/), shown under a page's lead: file -> (ru, en) caption
SHOTS = {
    "01-idea.png": ("Экран идеи: сценарист, длина, кадр и уже снятые ролики", "The idea screen: the writer, the length, the frame and the videos made so far"),
    "02-storyboard.png": ("Раскадровка: карточка героя, лента цепочек и карточки сцен", "The storyboard: the hero's card, the timeline of chains and the scene cards"),
    "03-film.png": ("Ролик: снятые сцены, выход и плеер", "The film: the shot scenes, the output and the player"),
    "04-music-video.png": ("Раскадровка клипа: части песни и сцены по её тактам", "A music video's storyboard: the song's parts, the scenes cut to its bars"),
    "05-montage.png": ("Монтаж: плеер, таймлайн с переходами и звуком, цвет ролика", "Montage: the player, the timeline with transitions and sound, the film's color"),
    "06-graph.png": ("Граф: герои, картинки, сцены и выход на одном холсте", "The graph: heroes, pictures, scenes and the output on one canvas"),
    "07-lab.png": ("Лаборатория: одна сцена вручную на любой модели", "The lab: one scene by hand on any model"),
    "08-models.png": ("Страница «Модели»: веса по ролям, скачивание и папки", "The Models page: the weights by role, downloads and folders"),
    "09-installer.png": ("Установщик: проверка компьютера и выбор наборов моделей", "The installer: the computer check and the choice of model sets"),
    "10-installer-download.png": ("Установщик: загрузка движка и наборов, с паузой и докачкой", "The installer: downloading the engine and the sets, with pause and resume"),
    "graph-music-video.png": ("Клип под свой трек: сцены, склейка, трек и музыка перед выходом", "A clip to your own track: scenes, a join, the track and music before the output"),
    "graph-picture-start.png": ("Картинка → сцена: Krea 2 рисует кадр, сцена его оживляет", "Picture → scene: Krea 2 draws the frame, the scene brings it to life"),
    "graph-templates.png": ("Окно шаблонов: 16 встроенных и ваши", "The templates dialog: 16 built-in and your own"),
}
# which help section shows which screenshots
SHOTS_OF = {
    "tut-first-run": ["09-installer.png", "10-installer-download.png"],
    "tut-idea": ["01-idea.png", "02-storyboard.png", "03-film.png"],
    "tut-clip": ["04-music-video.png"], "clip": ["04-music-video.png"],
    "tut-lab": ["07-lab.png"], "lab": ["07-lab.png"],
    "tut-graph": ["graph-templates.png"], "graph": ["06-graph.png"],
    "graph-edit": ["06-graph.png", "graph-templates.png"], "graph-nodes": ["graph-picture-start.png", "graph-music-video.png"],
    "tut-edit": ["05-montage.png"], "edit": ["05-montage.png"],
    "tut-final": ["03-film.png"], "video": ["03-film.png"],
    "tut-loras": ["08-models.png"], "models": ["08-models.png"],
    "idea": ["01-idea.png"], "timeline": ["02-storyboard.png"], "cards": ["02-storyboard.png"],
}


def shots(section_id: str, lang: str) -> str:
    """The section's screenshots as Markdown: the picture (from master) and its caption."""
    out = []
    for f in SHOTS_OF.get(section_id, []):
        cap = SHOTS[f][0 if lang == "ru" else 1]
        out.append(f"![{cap}]({RAW}/docs/screenshots/{'en/' if lang == 'en' else ''}{f})\n*{cap}*")
    return "\n\n".join(out)


# ---------------------------------------------------------------------------------------------------------------
# HTML -> a small tree
# ---------------------------------------------------------------------------------------------------------------
class Node:
    def __init__(self, tag: str, attrs: dict | None = None, parent: "Node | None" = None):
        self.tag, self.attrs, self.parent, self.children = tag, attrs or {}, parent, []

    @property
    def cls(self) -> set:
        return set(self.attrs.get("class", "").split())

    def text(self) -> str:
        return "".join(c if isinstance(c, str) else c.text() for c in self.children)


class Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = self.cur = Node("root")

    def handle_starttag(self, tag, attrs):
        n = Node(tag, {k: (v or "") for k, v in attrs}, self.cur)
        self.cur.children.append(n)
        if tag not in VOID:
            self.cur = n

    def handle_startendtag(self, tag, attrs):
        self.cur.children.append(Node(tag, {k: (v or "") for k, v in attrs}, self.cur))

    def handle_endtag(self, tag):
        n = self.cur
        while n is not self.root and n.tag != tag:
            n = n.parent
        if n is not self.root:
            self.cur = n.parent

    def handle_data(self, data):
        self.cur.children.append(data)


def parse(src: str) -> Node:
    t = Tree()
    t.feed(src)
    t.close()
    return t.root


# ---------------------------------------------------------------------------------------------------------------
# the tree -> Markdown
# ---------------------------------------------------------------------------------------------------------------
class Md:
    def __init__(self, lang: str, slug_of: dict[str, str]):
        self.lang, self.slug_of = lang, slug_of

    # -- inline ----------------------------------------------------------------------------------------------------
    @staticmethod
    def esc(s: str) -> str:
        s = re.sub(r"\s+", " ", s)
        return s.replace("\\", "\\\\").replace("*", "\\*").replace("_", "\\_").replace("<", "&lt;").replace(">", "&gt;")

    def inline(self, n) -> str:
        if isinstance(n, str):
            return self.esc(n)
        tag, cls = n.tag, n.cls
        if tag in ("svg", "script", "style") or "tut-go" in cls:
            return ""
        if tag == "br":
            return "<br>"
        if tag == "code":
            t = re.sub(r"\s+", " ", n.text()).strip()
            tick = "``" if "`" in t else "`"
            return f"{tick}{t}{tick}" if t else ""
        if tag == "kbd":
            return f"<kbd>{html.escape(n.text().strip())}</kbd>"
        inner = "".join(self.inline(c) for c in n.children)
        if tag in ("b", "strong"):
            return f"**{inner.strip()}**" if inner.strip() else ""
        if tag in ("i", "em"):
            return f"*{inner.strip()}*" if inner.strip() else ""
        if tag == "a":
            href = n.attrs.get("href", "")
            if m := re.match(r"#/help/([\w-]+)", href):
                slug = self.slug_of.get(m.group(1))
                return f"[{inner.strip()}]({quote(slug)})" if slug else inner
            if href.startswith("http"):
                return f"[{inner.strip()}]({href})"
            return inner   # a link to a screen of the app: just its name here
        if tag == "img":
            return ""
        return inner

    def inlines(self, nodes) -> str:
        s = "".join(self.inline(c) for c in nodes)
        s = re.sub(r"[ \t]+", " ", s)
        return re.sub(r" *<br> *", "<br>", s).strip()

    # -- blocks ----------------------------------------------------------------------------------------------------
    def is_block(self, n) -> bool:
        return not isinstance(n, str) and (n.tag in BLOCK or n.tag == "svg" and n.parent and n.parent.tag == "figure")

    def blocks(self, n: Node) -> list[str]:
        """The children of n as Markdown blocks; runs of inline content become paragraphs."""
        out, run = [], []

        def flush():
            if run:
                p = self.inlines(run)
                if p:
                    out.append(p)
                run.clear()
        for c in n.children:
            if self.is_block(c):
                flush()
                out.extend(self.block(c))
            else:
                run.append(c)
        flush()
        return out

    def block(self, n: Node) -> list[str]:
        tag, cls = n.tag, n.cls
        if tag in ("svg", "script", "style") or "tut-go" in cls:
            return []
        if tag in ("h1",):
            return []   # the page title is the page's name
        if tag in ("h2", "h3", "h4"):
            return [f"{'#' * int(tag[1])} {self.inlines(n.children)}"]
        if tag == "p":
            t = self.inlines(n.children)
            if not t:
                return []
            return [f"> {t}"] if "ru" in cls else [t]
        if tag == "pre":
            return [f"```\n{n.text().strip(chr(10))}\n```"]
        if tag in ("ul", "ol"):
            return self.listing(n)
        if tag == "dl":
            return self.dl(n)
        if tag == "table":
            return self.table(n)
        if tag == "figure":
            return self.figure(n)
        if tag == "figcaption":
            t = self.inlines(n.children)
            return [f"*{t}*"] if t else []
        if tag == "div":
            if "ex" in cls:
                return self.example(n)
            if "tip" in cls:
                inner = self.blocks(n)
                return ["\n".join("> " + ("💡 " if i == 0 else "") + l for i, l in enumerate("\n\n".join(inner).split("\n")))] if inner else []
            if "node-card" in cls:
                return self.node_card(n)
            if "keys-grid" in cls:
                return self.keys(n)
            if "legend-row" in cls:
                items = [re.sub(r"\s+", " ", c.text()).strip() for c in n.children if not isinstance(c, str)]
                return [" · ".join(i for i in items if i)]
            return self.blocks(n)
        if tag in ("dt", "dd", "li", "section", "blockquote", "thead", "tbody", "tr", "td", "th"):
            return self.blocks(n)
        return self.blocks(n)

    def listing(self, n: Node) -> list[str]:
        items = [c for c in n.children if not isinstance(c, str) and c.tag == "li"]
        if "flow" in n.cls:   # numbered steps (a scenario, the worked example): a heading per step
            out = []
            for i, li in enumerate(items, 1):
                kids = list(li.children)
                title = ""
                while kids and isinstance(kids[0], str) and not kids[0].strip():
                    kids.pop(0)
                if kids and not isinstance(kids[0], str) and kids[0].tag == "b":
                    title = self.inlines(kids.pop(0).children)
                rest = Node("div", {}, li)
                rest.children = kids
                body = []
                lead = []
                for k in kids:   # what follows the title on its line (a kind, a short note) stays beside it
                    if self.is_block(k):
                        break
                    lead.append(k)
                rest.children = kids[len(lead):]
                side = self.inlines([k for k in lead if not (not isinstance(k, str) and k.tag == "small")])
                small = [k for k in lead if not isinstance(k, str) and k.tag == "small"]
                out.append(f"### {i}. {title}" + (f" · {side}" if side else ""))
                if small:
                    out.append(f"*{self.inlines(small[0].children)}*")
                for b in self.blocks(rest):
                    body.append(b)
                out.extend(self.smalls_italic(body, rest))
            return out
        out, ordered = [], n.tag == "ol"
        for i, li in enumerate(items, 1):
            parts = self.blocks(li)
            mark = f"{i}. " if ordered else "- "
            pad = " " * len(mark)
            if not parts:
                continue
            first, more = parts[0], parts[1:]
            text = mark + first.replace("\n", "\n" + pad)
            for m in more:
                text += "\n\n" + pad + m.replace("\n", "\n" + pad)
            out.append(text)
        return ["\n".join(out)] if out and all("\n\n" not in o for o in out) else out

    def smalls_italic(self, body: list[str], node: Node) -> list[str]:
        """A step's <small> line under its text reads as a muted note."""
        smalls = {self.inlines(s.children) for s in node.children if not isinstance(s, str) and s.tag == "small"}
        return [f"*{b}*" if b in smalls else b for b in body]

    def dl(self, n: Node) -> list[str]:
        out = []
        for c in n.children:
            if isinstance(c, str):
                continue
            if c.tag == "dt":
                t = self.inlines(c.children)
                if t:
                    out.append(f"#### {t}")
            elif c.tag == "dd":
                out.extend(self.blocks(c))
            elif "node-card" in c.cls:
                out.extend(self.node_card(c))
            else:
                out.extend(self.block(c))
        return out

    def node_card(self, n: Node) -> list[str]:
        out = []
        for c in n.children:
            if isinstance(c, str):
                continue
            if c.tag == "dt":
                out.append(f"#### {self.inlines(c.children)}")
            elif c.tag == "dd":
                for d in c.children:
                    if isinstance(d, str):
                        continue
                    if "nc-list" in d.cls:
                        lines = []
                        for r in d.children:
                            if isinstance(r, str):
                                continue
                            if "nc-h" in r.cls:
                                lines.append(f"\n*{r.text().strip()}*\n")
                            elif "nc-row" in r.cls:
                                port = next((x for x in r.children if not isinstance(x, str) and "pt" in x.cls), None)
                                hint = next((x for x in r.children if not isinstance(x, str) and "nc-hint" in x.cls), None)
                                name = re.sub(r"\s+", " ", port.text()).strip() if port else ""
                                lines.append(f"- `{name}` — {self.inlines(hint.children) if hint else ''}")
                        out.append("\n".join(lines).strip())
                    else:
                        out.extend(self.block(d))
        return out

    def example(self, n: Node) -> list[str]:
        out = []
        for c in n.children:
            if isinstance(c, str):
                continue
            if "ex-w" in c.cls or "ex-b" in c.cls:
                label = next((x for x in c.children if not isinstance(x, str) and x.tag == "span"), None)
                rest = [x for x in c.children if x is not label]
                name = label.text().strip() if label else T[self.lang]["worse" if "ex-w" in c.cls else "better"]
                body = self.inlines(rest)
                out.append(f"> **{'✗' if 'ex-w' in c.cls else '✓'} {name}:** {body}")
            elif "ex-why" in c.cls:
                out.append(self.inlines(c.children))
        return ["\n>\n".join(out[:2])] + out[2:] if len(out) >= 2 else out

    def keys(self, n: Node) -> list[str]:
        cells = [c for c in n.children if not isinstance(c, str)]
        rows = [f"| {T[self.lang]['keys']} | {T[self.lang]['action']} |", "|---|---|"]
        for k, v in zip(cells[0::2], cells[1::2]):
            rows.append(f"| {self.inlines(k.children).replace('|', '¦')} | {self.inlines(v.children).replace('|', '¦')} |")
        return ["\n".join(rows)]

    def table(self, n: Node) -> list[str]:
        rows = []
        def walk(x):
            for c in x.children:
                if isinstance(c, str):
                    continue
                if c.tag == "tr":
                    rows.append([self.inlines(td.children).replace("|", "\\|") for td in c.children
                                 if not isinstance(td, str) and td.tag in ("td", "th")])
                else:
                    walk(c)
        walk(n)
        if not rows:
            return []
        w = max(len(r) for r in rows)
        rows = [r + [""] * (w - len(r)) for r in rows]
        lines = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * w] + ["| " + " | ".join(r) + " |" for r in rows[1:]]
        return ["\n".join(lines)]

    def figure(self, n: Node) -> list[str]:
        cls = n.cls
        out = []
        if "graph-pic" in cls:   # the canvas drawn in SVG: the real screenshot of the same template instead
            shot = f"{RAW}/docs/screenshots/{'en/' if self.lang == 'en' else ''}graph-two-endings.png"
            alt = n.attrs.get("aria-label", "")
            out.append(f"![{alt}]({shot})")
            cap = next((c for c in n.children if not isinstance(c, str) and c.tag == "figcaption"), None)
            if cap:
                out.append(f"*{self.inlines(cap.children)}*")
            return out
        if "anatomy" in cls:     # a prompt taken apart: each part's name, where it comes from, its text
            for an in n.children:
                if isinstance(an, str) or "an" not in an.cls:
                    continue
                lab = next((x for x in an.children if not isinstance(x, str) and "an-l" in x.cls), None)
                code = next((x for x in an.children if not isinstance(x, str) and x.tag == "code"), None)
                name = "".join(x for x in lab.children if isinstance(x, str)).strip() if lab else ""
                where = next((x.text().strip() for x in lab.children if not isinstance(x, str) and x.tag == "small"), "") if lab else ""
                out.append(f"**{name}**" + (f" — *{where}*" if where else ""))
                if code:
                    out.append(f"```\n{code.text().strip()}\n```")
            return out
        return self.blocks(n)

    def render(self, src: str) -> str:
        md = "\n\n".join(b for b in self.blocks(parse(src)) if b.strip())
        return re.sub(r"\n{3,}", "\n\n", md).strip() + "\n"


# ---------------------------------------------------------------------------------------------------------------
# pages
# ---------------------------------------------------------------------------------------------------------------
def page_name(title: str) -> str:
    """A wiki page's file name (GitHub shows it with spaces): no characters Windows or URLs choke on."""
    t = title.replace(": ", " — ").replace("/", " · ")
    t = re.sub(r'[\\:*?"<>|#%«»]', "", t)
    return re.sub(r"\s+", "-", t.strip())


def dump_help() -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "help.json"
        r = subprocess.run(["node", str(ROOT / "tools" / "wiki" / "dump_help.mjs"), str(out)], cwd=ROOT,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            sys.exit(f"the help could not be read:\n{r.stdout}\n{r.stderr}")
        return json.loads(out.read_text(encoding="utf-8"))


def grouped(sections: list[dict]) -> list[tuple[str, list[dict]]]:
    """The sections by group, groups in the order they first appear - as the app's help contents show them."""
    order: dict[str, list[dict]] = {}
    for s in sections:
        order.setdefault(s["group"], []).append(s)
    return list(order.items())


def build(out: Path, version: str) -> list[Path]:
    data = dump_help()
    names: dict[str, dict[str, str]] = {}
    for lang in ("ru", "en"):
        secs = data[lang]["sections"]
        taken = {T[lang]["home"], T[lang]["hero"], "Home", "Справка", "_Sidebar", "_Footer"}
        names[lang] = {}
        for s in secs:
            n = page_name(s["title"])
            if n in taken or n in names["ru"].values():
                n = page_name(f"{s['title']} ({s['group']})")
            taken.add(n)
            names[lang][s["id"]] = n
    if out.exists():
        for f in out.glob("*.md"):
            f.unlink()
    out.mkdir(parents=True, exist_ok=True)
    written = []

    def write(name: str, text: str):
        p = out / f"{name}.md"
        p.write_text(text, encoding="utf-8", newline="\n")
        written.append(p)

    other = {"ru": "en", "en": "ru"}
    home = {"ru": page_name(T["ru"]["home"]), "en": "Home"}
    hero = {l: page_name(T[l]["hero"]) for l in ("ru", "en")}
    for lang in ("ru", "en"):
        md = Md(lang, names[lang])
        o = other[lang]
        # the contents
        lines = [f"**[{T[lang]['other']}]({quote(home[o])})**", "", T[lang]["intro"], "",
                 f"{T[lang]['start']}: **[{T[lang]['hero']}]({quote(hero[lang])})**.", "", f"## {T[lang]['contents']}"]
        for group, secs in grouped(data[lang]["sections"]):
            lines += ["", f"### {group}", ""]
            lines += [f"- [{s['title']}]({quote(names[lang][s['id']])})" for s in secs]
        write(home[lang], "\n".join(lines) + "\n")
        # the worked example
        write(hero[lang], f"*[{T[lang]['other']}]({quote(hero[o])}) · [{T[lang]['contents']}]({quote(home[lang])})*\n\n"
              + md.render(data[lang]["hero"]))
        # a page per section, with its twin in the other language
        by_id = {s["id"]: s for s in data[o]["sections"]}
        for s in data[lang]["sections"]:
            twin = names[o].get(s["id"])
            top = f"*{s['group']} · [{T[lang]['other']}]({quote(twin)}) · [{T[lang]['contents']}]({quote(home[lang])})*" if twin and s["id"] in by_id \
                else f"*{s['group']} · [{T[lang]['contents']}]({quote(home[lang])})*"
            body = md.render(s["html"])
            if pics := shots(s["id"], lang):   # under the lead paragraph, before the details
                lead, _, rest = body.partition("\n\n")
                body = f"{lead}\n\n{pics}\n\n{rest}" if rest else f"{lead}\n\n{pics}\n"
            write(names[lang][s["id"]], top + "\n\n" + body)
    # the sidebar: both contents, the reader's language first by habit (English is the wiki's home)
    side = []
    for lang in ("en", "ru"):
        side.append(f"<details{' open' if lang == 'en' else ''}><summary><b>{'English' if lang == 'en' else 'Русский'}</b></summary>\n")
        side.append(f"- **[{T[lang]['contents']}]({quote(home[lang])})**")
        side.append(f"- [{T[lang]['hero']}]({quote(hero[lang])})")
        for group, secs in grouped(data[lang]["sections"]):
            side.append(f"\n**{group}**\n")
            side += [f"- [{s['title']}]({quote(names[lang][s['id']])})" for s in secs]
        side.append("\n</details>\n")
    write("_Sidebar", "\n".join(side) + "\n")
    commit = subprocess.run(["git", "rev-parse", "--short", "master"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    write("_Footer", f"{T['en']['footer']} · {T['ru']['footer']} — [Remiqora Video](https://github.com/{REPO}) "
          f"{version} ({commit}). The help lives in the app; this wiki is rebuilt with every release.\n")
    return written


def preview(out: Path, pages: list[Path]) -> Path:
    """Each page through GitHub's own Markdown renderer, wiki links pointed at the local files."""
    pv = out / "preview"
    shutil.rmtree(pv, ignore_errors=True)
    pv.mkdir()
    side = ""
    for p in pages:
        body = subprocess.run(["gh", "api", "markdown", "-f", f"text={p.read_text(encoding='utf-8')}", "-f", "mode=gfm",
                               "-f", f"context={REPO}"], capture_output=True, text=True, encoding="utf-8", check=True).stdout
        # relative links (wiki pages) -> the preview's html files
        body = re.sub(r'href="(?!https?:|#)([^"]+)"', lambda m: f'href="{m.group(1)}.html"', body)
        if p.stem == "_Sidebar":
            side = body
        (pv / f"{p.stem}.html").write_text(body, encoding="utf-8")
    css = ("body{margin:0;font:15px/1.6 -apple-system,Segoe UI,Helvetica,Arial,sans-serif;color:#1f2328;background:#fff}"
           ".wrap{display:flex;gap:32px;max-width:1280px;margin:0 auto;padding:24px}main{flex:1;min-width:0}aside{width:300px;"
           "font-size:13px;border:1px solid #d1d9e0;border-radius:6px;padding:12px 16px;align-self:flex-start}h1.t{font-weight:400;"
           "font-size:32px;border-bottom:1px solid #d1d9e0;padding-bottom:8px}code{background:#eff1f3;padding:.2em .4em;border-radius:6px;"
           "font-size:85%}pre{background:#f6f8fa;padding:16px;border-radius:6px;overflow:auto}pre code{background:none;padding:0}"
           "blockquote{margin:0;padding:0 1em;color:#59636e;border-left:.25em solid #d1d9e0}table{border-collapse:collapse}"
           "td,th{border:1px solid #d1d9e0;padding:6px 13px}img{max-width:100%}a{color:#0969da}kbd{border:1px solid #d1d9e0;"
           "border-bottom-width:2px;border-radius:6px;padding:0 4px;font-size:12px}footer{border-top:1px solid #d1d9e0;margin-top:32px;"
           "padding-top:12px;font-size:12px;color:#59636e}")
    footer = (pv / "_Footer.html").read_text(encoding="utf-8") if (pv / "_Footer.html").exists() else ""
    for f in pv.glob("*.html"):
        if f.stem.startswith("_"):
            continue
        title = f.stem.replace("-", " ")
        f.write_text(f'<!doctype html><meta charset="utf-8"><title>{html.escape(title)}</title><style>{css}</style>'
                     f'<div class="wrap"><main><h1 class="t">{html.escape(title)}</h1>{f.read_text(encoding="utf-8")}'
                     f'<footer>{footer}</footer></main><aside>{side}</aside></div>', encoding="utf-8")
    return pv / "Home.html"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", help="the folder for the .md pages (a clone of the .wiki repository, or any folder)")
    ap.add_argument("--version", default=json.loads((ROOT / "desktop" / "package.json").read_text(encoding="utf-8"))["version"])
    ap.add_argument("--preview", action="store_true", help="also render the pages to HTML with GitHub's Markdown API")
    a = ap.parse_args()
    out = Path(a.out)
    pages = build(out, a.version)
    print(f"{len(pages)} pages in {out}")
    if a.preview:
        print("preview:", preview(out, pages))


if __name__ == "__main__":
    main()
