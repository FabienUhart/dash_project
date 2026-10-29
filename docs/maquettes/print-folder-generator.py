import json, sys, html, re, datetime
S = sys.argv[1]
d = json.load(open(S + '/page1.json'))
t = json.load(open(S + '/tree.json'))
memos = [m for m in d['items'] if not m.get('deleted_at')]
by = {f['id']: f for f in t['folders']}
def path(i):
    p = []
    while i:
        f = by[i]; p.append(f['name']); i = f.get('parent_id')
    return ' › '.join(reversed(p))
def fname(i):
    f = by.get(i); return (f.get('emoji') or '') + ' ' + f['name'] if f else 'Inbox'
MONTHS = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.']
DAYS = ['lun.', 'mar.', 'mer.', 'jeu.', 'ven.', 'sam.', 'dim.']
def fd(s):
    if not s: return ''
    y, m, dd = map(int, s[:10].split('-')); dt = datetime.date(y, m, dd)
    return f"{DAYS[dt.weekday()]} {dd} {MONTHS[m-1]}"
def esc(s): return html.escape(str(s or ''))
def memo_block(m, show_folder=True):
    out = ['<article class="memo">']
    date = ''
    if m.get('due_date'):
        date = fd(m['due_date'])
        if m.get('due_end') and m['due_end'] > m['due_date']: date += ' → ' + fd(m['due_end'])
        if m.get('due_time'): date += ' · ' + m['due_time']
        if m.get('end_time'): date += '–' + m['end_time']
    head = f"<h3>{esc(m.get('emoji') or '')} {esc(m.get('title') or '(sans titre)')}</h3>"
    meta = []
    if date: meta.append('📅 ' + esc(date))
    if show_folder: meta.append('📁 ' + esc(fname(m.get('project_id'))))
    loc = m.get('location') or {}
    if isinstance(loc, dict) and loc.get('label'): meta.append('📍 ' + esc(loc['label']))
    if m.get('assignees'): meta.append('👤 ' + esc(', '.join(m['assignees'])))
    if m.get('priority'): meta.append('P' + str(m['priority']))
    out.append(head)
    if meta: out.append('<div class="meta">' + ' &nbsp;·&nbsp; '.join(meta) + '</div>')
    c = m.get('content') or ''
    c = re.sub(r'<img[^>]*>', '', c)
    if c.strip(): out.append('<div class="body">' + c + '</div>')
    st = m.get('subtasks') or []
    if st:
        out.append('<ul class="sub">' + ''.join(f"<li>{'☑' if s.get('done') else '☐'} {esc(s.get('content'))}</li>" for s in st) + '</ul>')
    urls = m.get('urls') or []
    if urls:
        out.append('<ul class="urls">' + ''.join(f"<li>🔗 {esc(u.get('title') or u.get('url'))}<br><small>{esc(u.get('url'))}</small></li>" for u in urls) + '</ul>')
    if m.get('images') or m.get('attachments'):
        n = len(m.get('images') or []) + len(m.get('attachments') or [])
        out.append(f'<div class="meta">📎 {n} fichier(s) sur le dashboard (non inclus)</div>')
    out.append('</article>')
    return '\n'.join(out)

dated = sorted([m for m in memos if m.get('due_date')], key=lambda m: (m['due_date'], m.get('due_time') or ''))
undated = [m for m in memos if not m.get('due_date')]
# folder order: tree position, Voyage Japon first
def subtree(root):
    ids = [root]; i = 0
    while i < len(ids):
        for f in sorted(t['folders'], key=lambda f: f.get('position', 0)):
            if f.get('parent_id') == ids[i]: ids.append(f['id'])
        i += 1
    return ids
order = subtree(3)
parts = []
parts.append(f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Voyage Japon — mémos hors ligne</title>
<style>
@page {{ size: A5; margin: 12mm 11mm; }}
body {{ font: 10.5pt/1.4 -apple-system, "Segoe UI", Roboto, "Noto Sans", "Noto Sans CJK JP", sans-serif; color: #111; max-width: 560px; margin: 0 auto; padding: 12px; }}
h1 {{ font-size: 1.7rem; margin: .2rem 0 0; }} .sub1 {{ color: #666; margin: 0 0 1.2rem; }}
h2 {{ font-size: 1.25rem; border-bottom: 2px solid #111; padding-bottom: .15rem; margin: 1.6rem 0 .6rem; page-break-before: always; }}
h2.first {{ page-break-before: auto; }}
h3 {{ font-size: 1.02rem; margin: 0 0 .15rem; }}
.memo {{ border-left: 3px solid #bbb; padding: .35rem 0 .35rem .6rem; margin: 0 0 .9rem; page-break-inside: avoid; }}
.meta {{ color: #555; font-size: .82rem; margin: 0 0 .3rem; }}
.body p {{ margin: .15rem 0; }} .body ul, .body ol {{ margin: .2rem 0 .2rem 1.1rem; padding: 0; }}
.body table {{ border-collapse: collapse; font-size: .85rem; }} .body td, .body th {{ border: 1px solid #ccc; padding: 2px 5px; }}
.body pre {{ white-space: pre-wrap; font-size: .8rem; background: #f3f3f3; padding: 4px 6px; }}
.sub, .urls {{ list-style: none; margin: .25rem 0 0; padding: 0; font-size: .9rem; }} .urls small {{ color: #666; word-break: break-all; }}
.day {{ font-weight: 700; margin: 1rem 0 .3rem; color: #333; border-bottom: 1px dashed #bbb; }}
.toc li {{ margin: .15rem 0; }} a {{ color: #0b5; text-decoration: none; }}
</style></head><body>
<h1>🗻 Voyage Japon</h1><p class="sub1">Mémos du dashboard, export hors ligne du {datetime.date.today().strftime('%d/%m/%Y')} — {len(memos)} mémos, {len(order)} dossiers.</p>
<h2 class="first">Sommaire</h2><ul class="toc"><li><a href="#jour">1 · Jour par jour</a></li>""")
for i, fid in enumerate(order, 2):
    n = sum(1 for m in memos if m.get('project_id') == fid)
    if n: parts.append(f'<li><a href="#f{fid}">{i} · {esc(fname(fid))} ({n})</a></li>')
parts.append('</ul>')
parts.append('<h2 id="jour">1 · Jour par jour</h2>')
cur = None
for m in dated:
    if m['due_date'] != cur:
        cur = m['due_date']; parts.append(f'<div class="day">{esc(fd(cur))}</div>')
    parts.append(memo_block(m, True))
for i, fid in enumerate(order, 2):
    ms = [m for m in memos if m.get('project_id') == fid]
    if not ms: continue
    ms.sort(key=lambda m: (m.get('due_date') or '9999', m.get('position') or 0))
    parts.append(f'<h2 id="f{fid}">{i} · {esc(fname(fid))}</h2><div class="meta">{esc(path(fid))}</div>')
    parts.extend(memo_block(m, False) for m in ms)
parts.append('</body></html>')
open(S + '/voyage-japon-memos.html', 'w', encoding='utf-8').write('\n'.join(parts))
print(len(memos), len(dated), len(undated))
