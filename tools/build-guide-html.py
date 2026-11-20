# -*- coding: utf-8 -*-
"""Turn docs/build-guide.de.md into docs/build-guide.html.

The guide lives twice: as Markdown in the repository, where GitHub renders
it, and as one standalone page for event.pics. Writing it twice would mean
keeping two texts in step, so only the Markdown is written by hand and this
script makes the page from it: same words, same pictures, a design around
them. The pictures are not copied, the page points at docs/images.

Run it after every change to the guide:  python3 tools/build-guide-html.py
"""
import html
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
SRC = HERE / "docs" / "build-guide.de.md"
OUT = HERE / "docs" / "build-guide.html"
STL_URL = "https://github.com/eventpics/photobooth/raw/main/docs/pi-mount.stl"

CSS = """
/* Layout: one reading column, drawings and photo strips break out of it. */
:root{
  --paper:#FBFAF7; --ink:#15213A; --muted:#5A6678; --line:#DCD9D0;
  --accent:#C98A00; --accent-soft:#FBF0D5; --card:#FFFFFF; --warn:#B4341F;
  --font-display:"Archivo","Helvetica Neue",Arial,sans-serif;
  --font-body:"IBM Plex Sans","Helvetica Neue",Arial,sans-serif;
  --font-mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --paper:#11161F; --ink:#E8EAEE; --muted:#9BA6B6; --line:#2A3342;
    --accent:#F0B429; --accent-soft:#2A2314; --card:#171E29; --warn:#F08A77;
    color-scheme:dark;
  }
}
:root[data-theme="dark"]{
  --paper:#11161F; --ink:#E8EAEE; --muted:#9BA6B6; --line:#2A3342;
  --accent:#F0B429; --accent-soft:#2A2314; --card:#171E29; --warn:#F08A77;
  color-scheme:dark;
}
*{box-sizing:border-box}
body{background:var(--paper);color:var(--ink);font-family:var(--font-body);
     font-size:17px;line-height:1.62;margin:0}
.wrap{max-width:780px;margin:0 auto;
      padding-left:max(16px,env(safe-area-inset-left,0px));
      padding-right:max(16px,env(safe-area-inset-right,0px));padding-block:0}
header.top{border-bottom:1px solid var(--line);padding-block:56px 40px}
header.top .wrap{display:flex;flex-direction:column;gap:18px}
.eyebrow{font-family:var(--font-mono);font-size:12px;letter-spacing:.14em;
         text-transform:uppercase;color:var(--accent)}
h1{font-family:var(--font-display);font-size:clamp(34px,6vw,52px);line-height:1.05;
   margin:0;font-weight:700;letter-spacing:-.02em;text-wrap:balance}
.lede{font-size:19px;color:var(--muted);margin:0;max-width:62ch}
.facts{display:flex;flex-wrap:wrap;gap:10px;margin-top:6px}
.fact{font-family:var(--font-mono);font-size:12.5px;border:1px solid var(--line);
      border-radius:999px;padding:5px 12px;color:var(--muted);background:var(--card)}
main{padding-block:8px 64px}
h2{font-family:var(--font-display);font-size:clamp(24px,3.6vw,32px);line-height:1.15;
   margin:56px 0 4px;letter-spacing:-.01em;text-wrap:balance;
   padding-top:18px;border-top:2px solid var(--ink)}
h3{font-family:var(--font-display);font-size:21px;margin:36px 0 2px;letter-spacing:-.01em}
h4{font-family:var(--font-mono);font-size:13px;letter-spacing:.1em;text-transform:uppercase;
   color:var(--muted);margin:28px 0 0}
p{margin:14px 0}
a{color:var(--ink);text-decoration-color:var(--accent);text-decoration-thickness:2px;
  text-underline-offset:3px}
a:hover{color:var(--accent)}
code{font-family:var(--font-mono);font-size:.88em;background:var(--accent-soft);
     padding:1px 5px;border-radius:4px}
pre{background:var(--card);border:1px solid var(--line);border-radius:10px;
    padding:16px;overflow-x:auto;margin:20px 0}
pre code{background:none;padding:0;font-size:13.5px;line-height:1.6}
ul,ol{margin:14px 0;padding-left:22px}
li{margin:7px 0}
blockquote{margin:28px 0;padding:18px 20px;border-left:4px solid var(--warn);
           background:var(--card);border-radius:0 10px 10px 0}
blockquote p{margin:8px 0}
blockquote strong{color:var(--warn)}
.tablewrap{overflow-x:auto;margin:22px 0;border:1px solid var(--line);border-radius:10px;
           background:var(--card)}
table{border-collapse:collapse;width:100%;font-size:15px;min-width:0}
th,td{text-align:left;padding:11px 14px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-family:var(--font-mono);font-size:12px;letter-spacing:.08em;text-transform:uppercase;
   color:var(--muted);font-weight:500}
tr:last-child td{border-bottom:none}
td:last-child{font-variant-numeric:tabular-nums;white-space:nowrap}
figure{margin:26px 0}
figure img{display:block;width:auto;max-width:100%;max-height:620px;height:auto;
           margin:0 auto;border-radius:10px;border:1px solid var(--line);background:#fff}
figure.plan img{width:100%;max-height:none}
figure.plan img{border-radius:6px;padding:10px}
figure.plan a{display:block}
.strip figure img{width:100%;max-height:420px;object-fit:contain}
figcaption{font-size:14px;color:var(--muted);margin-top:8px}
.strip{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));margin:26px 0}
.strip figure{margin:0}
.download{display:flex;flex-wrap:wrap;align-items:center;gap:16px;margin:26px 0;
          padding:18px 20px;border:2px solid var(--accent);border-radius:12px;
          background:var(--accent-soft)}
.download .label{font-family:var(--font-mono);font-size:13px;color:var(--muted)}
.download a{font-family:var(--font-display);font-size:18px;font-weight:600}
footer{border-top:1px solid var(--line);padding-block:32px 60px;color:var(--muted);font-size:15px}
@media (max-width:520px){ body{font-size:16px} header.top{padding-block:36px 28px} }
"""

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
         'family=Archivo:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500&'
         'family=IBM+Plex+Sans:wght@400;500;600&display=swap">')


def inline(s: str) -> str:
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
               lambda m: f'<a href="{link(m.group(2))}"{ext(m.group(2))}>{m.group(1)}</a>', s)
    s = re.sub(r"<(https?://[^>]+)>", r'<a href="\1" target="_blank" rel="noopener">\1</a>', s)
    return s


def link(href: str) -> str:
    if href == "pi-mount.stl":
        return STL_URL
    if href == "../README.de.md":
        return "https://github.com/eventpics/photobooth/blob/main/README.de.md"
    return href


def ext(href: str) -> str:
    return ' target="_blank" rel="noopener"' if href.startswith("http") or href.endswith(
        (".stl", ".md")) else ""


def convert(md: str) -> tuple[str, str, str]:
    lines = md.split("\n")
    out, i = [], 0
    title, lede, hero = "", "", ""
    pending_figs = []

    def flush_figs():
        if not pending_figs:
            return
        if len(pending_figs) == 1:
            out.append(pending_figs[0])
        else:
            out.append('<div class="strip">' + "".join(pending_figs) + "</div>")
        pending_figs.clear()

    while i < len(lines):
        ln = lines[i]
        if ln.startswith("# "):
            title = ln[2:].strip()
            i += 1
            continue
        m = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$", ln)
        if m:
            alt, src = m.group(1), m.group(2)
            if not hero:
                hero = src
                i += 1
                continue
            plan = src.endswith(".svg")
            cls = ' class="plan"' if plan or src.endswith(".png") else ""
            img = f'<img src="{src}" alt="{html.escape(alt)}" loading="lazy">'
            if plan:
                img = f'<a href="{src}" target="_blank" rel="noopener">{img}</a>'
            cap = html.escape(alt) + (" (anklicken f\u00fcr gro\u00df)" if plan else "")
            pending_figs.append(f'<figure{cls}>{img}<figcaption>{cap}</figcaption></figure>')
            i += 1
            continue
        flush_figs()
        if ln.startswith("## "):
            out.append(f"<h2>{inline(ln[3:].strip())}</h2>")
        elif ln.startswith("### "):
            out.append(f"<h3>{inline(ln[4:].strip())}</h3>")
        elif ln.startswith("```"):
            code, i = [], i + 1
            while i < len(lines) and not lines[i].startswith("```"):
                code.append(lines[i]); i += 1
            out.append("<pre><code>" + html.escape("\n".join(code)) + "</code></pre>")
        elif ln.startswith("> "):
            quote = []
            while i < len(lines) and lines[i].startswith(">"):
                quote.append(lines[i].lstrip("> ").rstrip()); i += 1
            text = " ".join(q for q in quote if q)
            out.append(f"<blockquote><p>{inline(text)}</p></blockquote>")
            continue
        elif ln.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip("|").split("|")]); i += 1
            head, body = None, rows
            if len(rows) > 1 and set("".join(rows[1]).replace(" ", "")) <= set("-:"):
                head, body = rows[0], rows[2:]
            t = ['<div class="tablewrap"><table>']
            if head and any(h for h in head):
                t.append("<thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr></thead>")
            t.append("<tbody>")
            for r in body:
                t.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
            t.append("</tbody></table></div>")
            out.append("".join(t))
            continue
        elif re.match(r"^\d+\. ", ln) or ln.startswith("- "):
            ordered = bool(re.match(r"^\d+\. ", ln))
            items = []
            while i < len(lines) and (re.match(r"^\d+\. ", lines[i]) or lines[i].startswith("- ")
                                      or (items and lines[i].startswith("   ") and lines[i].strip())):
                s = lines[i]
                if s.startswith("   ") and items:
                    items[-1] += " " + s.strip()
                else:
                    items.append(re.sub(r"^(\d+\.|-)\s+", "", s))
                i += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{inline(x)}</li>" for x in items) + f"</{tag}>")
            continue
        elif ln.strip() == "":
            pass
        elif ln.startswith("**Datei:"):
            m2 = re.search(r"\[([^\]]+)\]\(([^)]+)\)", ln)
            out.append('<div class="download"><span class="label">3D-Druckteil</span>'
                       f'<a href="{STL_URL}" target="_blank" rel="noopener">'
                       f'{m2.group(1)} herunterladen</a>'
                       '<span class="label">ASCII-STL, 108 × 66 × 11,6 mm</span></div>')
        else:
            para = [ln]
            while i + 1 < len(lines) and lines[i + 1].strip() and not re.match(
                    r"^(#|!\[|\||```|> |- |\d+\. )", lines[i + 1]):
                i += 1; para.append(lines[i])
            text = " ".join(p.strip() for p in para)
            if not lede:
                lede = text
            out.append(f"<p>{inline(text)}</p>")
        i += 1
    flush_figs()
    return title, lede, hero, "\n".join(out)


md = SRC.read_text(encoding="utf-8")
title, lede, hero, body = convert(md)
facts = ["410 × 290 × 180 mm", "Eiche 15 mm", "Raspberry Pi 4B",
         "15,6″ Touch", "Selphy CP1500", "rund 700 Euro"]
page = f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="claude:viewport-fit-sides" content="cover">
<title>Fotobox selber bauen</title>
<meta name="description" content="Bauanleitung für die EventPics Fotobox: Gehäuse, Einbau, Elektrik und die Software auf dem Raspberry Pi.">
{FONTS}
<style>{CSS}</style>
</head>
<body>
<header class="top"><div class="wrap">
  <div class="eyebrow">EventPics Fotobox</div>
  <h1>{html.escape(title)}</h1>
  <p class="lede">{inline(lede)}</p>
  <div class="facts">{"".join(f'<span class="fact">{f}</span>' for f in facts)}</div>
</div></header>
<main><div class="wrap">
<figure><img src="{hero}" alt="Die fertige Box auf dem Ständer"></figure>
{body}
</div></main>
<footer><div class="wrap">
  Software, Zeichnungen und Druckteil liegen unter der MIT-Lizenz im Repository
  <a href="https://github.com/eventpics/photobooth" target="_blank" rel="noopener">github.com/eventpics/photobooth</a>.
</div></footer>
</body>
</html>
"""
OUT.write_text(page, encoding="utf-8")
print("geschrieben:", OUT, len(page), "Zeichen")
