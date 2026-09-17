#!/usr/bin/env python3
"""Generate static/testplan.html from TESTPLAN.md.

The markdown is the source of truth. Keeping a hand-written HTML copy beside it
is how `lab_hub/tools/convert` and `toolbox/convert_epub` drifted apart, and
AGENTS.md says not to do it again — so this is a generator, `build_app.sh` runs
it, and `tests/test_testplan_page.py` fails if the two fall out of step.

What the page adds over the markdown is the thing a file cannot do: it remembers
which cases you have passed or failed, across sessions, in the browser's own
storage. Eighty cases is more than one sitting.
"""

from __future__ import annotations

import html
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = ROOT / "TESTPLAN.md"
TARGET = ROOT / "static" / "testplan.html"

STYLE = """
  :root{
    --bg:#080b11; --panel:#0d131d; --panel2:#0a0f17; --border:#1a2431;
    --ink:#e6edf3; --muted:#8b98a5; --faint:#4a5867;
    --up:#3ea6ff; --down:#ff6a54; --gold:#e8b84b; --grid:#141d29;
    --pass:#3fb950;
  }
  *{box-sizing:border-box}
  html,body{margin:0;background:var(--bg);color:var(--ink);
    font:14px/1.65 ui-monospace,"SF Mono",Menlo,Consolas,monospace;
    -webkit-font-smoothing:antialiased}
  .wrap{max-width:1000px;margin:0 auto;padding:28px 20px 90px}
  a{color:var(--up);text-decoration:none} a:hover{text-decoration:underline}
  code{background:var(--panel2);border:1px solid var(--border);border-radius:4px;
    padding:1px 5px;font-size:.9em;color:#cfe3ff}
  pre{background:var(--panel2);border:1px solid var(--border);border-radius:8px;
    padding:12px 14px;overflow-x:auto;font-size:12.5px}
  pre code{background:none;border:none;padding:0}

  header{display:flex;align-items:center;gap:14px;flex-wrap:wrap;
    padding:14px 18px;border:1px solid var(--border);border-radius:10px;
    background:linear-gradient(180deg,#0e141e,#0a0f17);margin-bottom:18px}
  .brand{font-size:17px;font-weight:700;letter-spacing:.16em}
  .brand b{color:var(--gold)}
  .back{margin-left:auto;font-size:11px;letter-spacing:.12em;text-transform:uppercase;
    padding:6px 12px;border:1px solid rgba(62,166,255,.4);border-radius:6px;color:var(--up)}

  h1{font-size:22px;margin:6px 0 4px}
  h2{font-size:15px;margin:30px 0 8px;padding-bottom:6px;
    border-bottom:1px solid var(--border);letter-spacing:.06em}
  h2 .n{color:var(--gold);margin-right:8px}
  p{margin:8px 0} ul,ol{margin:8px 0;padding-left:22px}

  .callout{border:1px solid rgba(232,184,75,.35);background:rgba(232,184,75,.06);
    border-radius:8px;padding:12px 15px;margin:14px 0;color:#f0d99a}
  .callout b{color:var(--gold)}

  table{width:100%;border-collapse:collapse;margin:10px 0;font-size:12.5px}
  th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--grid);
    vertical-align:top}
  th{color:var(--faint);text-transform:uppercase;font-size:10px;letter-spacing:.1em}
  tr[data-case]{cursor:default}
  tr[data-case].pass{background:rgba(63,185,80,.09)}
  tr[data-case].fail{background:rgba(255,106,84,.10)}
  td.id{color:var(--up);white-space:nowrap;font-weight:700}
  td.flag{white-space:nowrap;color:var(--gold);text-align:center}
  td.mark{white-space:nowrap;width:86px}
  .mark button{background:var(--panel2);border:1px solid var(--border);color:var(--muted);
    border-radius:5px;width:30px;height:24px;font:inherit;font-size:13px;cursor:pointer;
    margin-right:4px;line-height:1}
  .mark button:hover{border-color:var(--up)}
  tr.pass .mark button.mark-pass{background:rgba(63,185,80,.25);border-color:var(--pass);color:var(--pass)}
  tr.fail .mark button.mark-fail{background:rgba(255,106,84,.22);border-color:var(--down);color:var(--down)}

  .bar{position:sticky;top:0;z-index:5;display:flex;align-items:center;gap:16px;
    flex-wrap:wrap;padding:11px 16px;margin:0 0 18px;border:1px solid var(--border);
    border-radius:10px;background:rgba(13,19,29,.96);backdrop-filter:blur(8px)}
  .bar .count{font-size:12.5px;color:var(--muted)}
  .bar .count b{color:var(--ink)}
  .bar .ok{color:var(--pass)} .bar .bad{color:var(--down)}
  .track{flex:1;min-width:140px;height:7px;border-radius:4px;background:var(--grid);
    overflow:hidden;display:flex}
  .track i{display:block;height:100%}
  .track .p{background:var(--pass)} .track .f{background:var(--down)}
  .bar button{background:var(--panel2);border:1px solid var(--border);color:var(--muted);
    border-radius:6px;padding:5px 11px;font:inherit;font-size:11.5px;cursor:pointer}
  .bar button:hover{border-color:var(--down);color:var(--down)}
  .only{color:var(--muted);font-size:11.5px;display:flex;align-items:center;gap:6px}
  body.hide-done tr[data-case].pass{display:none}

  .warnstore{flex-basis:100%;color:var(--down);font-size:11.5px}
  footer{margin-top:36px;padding-top:14px;border-top:1px solid var(--border);
    color:var(--faint);font-size:11.5px;line-height:1.7}
"""

SCRIPT = """
  const KEY = 'sonar.testplan.v2';

  // Whether results will actually survive a reload. The app opens this page as
  // a file:// URL, and some browsers refuse storage on that origin — Safari
  // allows it, Chrome has historically not. Failing silently would be the worst
  // outcome: you work through eighty cases and lose them without warning. So
  // the page probes once and says so.
  const canStore = (() => {
    try {
      localStorage.setItem(KEY + '.probe', '1');
      localStorage.removeItem(KEY + '.probe');
      return true;
    } catch (e) { return false; }
  })();

  const load = () => { try { return JSON.parse(localStorage.getItem(KEY)) || {}; }
                       catch (e) { return {}; } };
  const save = s => { try { localStorage.setItem(KEY, JSON.stringify(s)); }
                      catch (e) {} };
  let state = load();

  if (!canStore) {
    const note = document.getElementById('storage-note');
    note.hidden = false;
    note.textContent = 'results will not be saved in this browser \u2014 '
      + 'open the page in Safari, or keep this tab open until you finish';
  }

  function paint() {
    const rows = document.querySelectorAll('tr[data-case]');
    let pass = 0, fail = 0;
    rows.forEach(tr => {
      const v = state[tr.dataset.case];
      tr.classList.toggle('pass', v === 'pass');
      tr.classList.toggle('fail', v === 'fail');
      if (v === 'pass') pass++; else if (v === 'fail') fail++;
    });
    const total = rows.length;
    document.getElementById('done').textContent = pass + fail;
    document.getElementById('total').textContent = total;
    document.getElementById('passed').textContent = pass;
    document.getElementById('failed').textContent = fail;
    document.getElementById('pbar').style.width = (100 * pass / total) + '%';
    document.getElementById('fbar').style.width = (100 * fail / total) + '%';
  }

  document.addEventListener('click', e => {
    const b = e.target.closest('.mark button');
    if (b) {
      const id = b.closest('tr').dataset.case;
      const want = b.classList.contains('mark-pass') ? 'pass' : 'fail';
      state[id] = (state[id] === want) ? undefined : want;
      if (!state[id]) delete state[id];
      save(state); paint();
    }
  });

  document.getElementById('reset').addEventListener('click', () => {
    if (confirm('Clear every result and start the pass again?')) {
      state = {}; save(state); paint();
    }
  });
  document.getElementById('hide').addEventListener('change', e => {
    document.body.classList.toggle('hide-done', e.target.checked);
  });
  paint();
"""


def inline(text: str) -> str:
    """Markdown inline formatting, escaped first so the source cannot inject."""
    out = html.escape(text, quote=False)
    out = re.sub(r'`([^`]+)`', r'<code>\1</code>', out)
    out = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', out)
    out = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<em>\1</em>', out)
    out = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', out)
    return out


def split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip('|').split('|')]


def render(md: str) -> str:
    body: list[str] = []
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]

        if line.startswith('# '):
            i += 1
            continue

        if line.startswith('## '):
            title = line[3:].strip()
            m = re.match(r'(\d+)\.\s+(.*)', title)
            body.append(f'<h2><span class="n">{m.group(1)}</span>{inline(m.group(2))}</h2>'
                        if m else f'<h2>{inline(title)}</h2>')
            i += 1
            continue

        if line.startswith('|'):
            table, header = [], split_row(line)
            i += 2                                   # skip the separator row
            while i < len(lines) and lines[i].startswith('|'):
                table.append(split_row(lines[i]))
                i += 1
            body.append(render_table(header, table))
            continue

        if line.startswith('- [ ] ') or line.startswith('- '):
            items = []
            while i < len(lines) and lines[i].startswith('- '):
                items.append(re.sub(r'^- (\[ \] )?', '', lines[i]))
                i += 1
            body.append('<ul>' + ''.join(f'<li>{inline(x)}</li>' for x in items) + '</ul>')
            continue

        if line.startswith('```'):
            i += 1
            block = []
            while i < len(lines) and not lines[i].startswith('```'):
                block.append(lines[i])
                i += 1
            i += 1
            body.append('<pre><code>' + html.escape('\n'.join(block)) + '</code></pre>')
            continue

        if line.startswith('---') or not line.strip():
            i += 1
            continue

        para = []
        while i < len(lines) and lines[i].strip() and not lines[i].startswith(('#', '|', '- ', '```', '---')):
            para.append(lines[i].strip())
            i += 1
        text = ' '.join(para)
        klass = ' class="callout"' if text.startswith('**Run it against') else ''
        body.append(f'<p{klass}>{inline(text)}</p>')

    return '\n'.join(body)


def render_table(header: list[str], rows: list[list[str]]) -> str:
    """A table of test cases gets pass/fail controls; anything else renders plain."""
    is_cases = header and header[0] == '#'
    head = ''.join(f'<th>{inline(h)}</th>' for h in header)
    if is_cases:
        head = '<th>Result</th>' + head
    out = [f'<table><tr>{head}</tr>']
    for row in rows:
        if is_cases and re.match(r'^\d+\.\d+$', row[0]):
            case = row[0]
            cells = [f'<td class="id">{case}</td>']
            for n, cell in enumerate(row[1:], start=1):
                klass = ' class="flag"' if header[n] == '⚠' else ''
                cells.append(f'<td{klass}>{inline(cell)}</td>')
            mark = ('<td class="mark">'
                    '<button class="mark-pass" title="pass">&#10003;</button>'
                    '<button class="mark-fail" title="fail">&#10007;</button></td>')
            out.append(f'<tr data-case="{case}">{mark}{"".join(cells)}</tr>')
        else:
            pad = '<td></td>' if is_cases else ''
            out.append('<tr>' + pad + ''.join(f'<td>{inline(c)}</td>' for c in row) + '</tr>')
    out.append('</table>')
    return '\n'.join(out)


def build() -> str:
    md = SOURCE.read_text()
    total = len(re.findall(r'^\| \d+\.\d+ ', md, re.M))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SONAR · v2 test plan</title>
<!-- Generated from TESTPLAN.md by scripts/build_testplan.py. Do not edit. -->
<style>{STYLE}</style>
</head>
<body>
<div class="wrap">
  <header>
    <span class="brand">&#9671; <b>SONAR</b> &middot; TEST PLAN</span>
    <a class="back" href="docs.html">&larr; Documentation</a>
  </header>

  <h1>v2 acceptance test plan</h1>

  <div class="bar">
    <span class="count"><b id="done">0</b> / <b id="total">{total}</b> checked
      &middot; <span class="ok"><b id="passed">0</b> passed</span>
      &middot; <span class="bad"><b id="failed">0</b> failed</span></span>
    <span class="track"><i class="p" id="pbar"></i><i class="f" id="fbar"></i></span>
    <label class="only"><input type="checkbox" id="hide"> hide passed</label>
    <button id="reset">reset</button>
    <span class="warnstore" id="storage-note" hidden></span>
  </div>

{render(md)}

  <footer>
    Generated from <code>TESTPLAN.md</code> &mdash; edit the markdown, not this page.
    Results are stored in this browser only: they survive a reload and a restart,
    they are never uploaded anywhere, and <b>reset</b> clears them.
  </footer>
</div>
<script>{SCRIPT}</script>
</body>
</html>
"""


def main() -> int:
    generated = build()
    if "--check" in sys.argv:
        current = TARGET.read_text() if TARGET.exists() else ""
        if current != generated:
            print("static/testplan.html is out of date — run scripts/build_testplan.py")
            return 1
        print("static/testplan.html is up to date")
        return 0
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(generated)
    cases = generated.count('data-case="')
    print(f"wrote {TARGET.relative_to(ROOT)} — {cases} cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
