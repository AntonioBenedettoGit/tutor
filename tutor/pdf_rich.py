"""Lettura del PDF con stile per carattere (grassetto/corsivo/monospazio) e tabelle cella per cella.

Dipendenza opzionale usata SOLO durante la build. Le righe hanno lo stesso testo di
pdf_source.extract_pages: le funzioni esistenti (capitoli, esercizi, verbi, glossario)
lavorano invariate; in più ogni riga porta lo stile di ciascun carattere.

Un carattere "ricco" è la tupla (carattere, stile, pagina), con stile ⊆ {'b','i','m'}.
"""
from dataclasses import dataclass, field
import html
import re

from tutor.pdf_source import Line

MARKS = '✓✗'
HYPHENS = '\u2010\u00ad'
TOP, BOTTOM = 42, 38          # stessi margini di pdf_source: niente testatine/piè di pagina


@dataclass
class RichLine(Line):
    chars: list = field(default_factory=list)
    x0: float = 0.0
    x1: float = 0.0
    mono: bool = False


def style_of(font):
    if not font:
        return ''
    s = ''
    if 'Bold' in font or 'Semi' in font:
        s += 'b'
    if 'Italic' in font or 'Ital' in font or 'Oblique' in font:
        s += 'i'
    if 'Menlo' in font or 'Courier' in font or 'Mono' in font:
        s += 'm'
    return s


def _group_baselines(spans):
    groups = []
    for span in sorted(spans, key=lambda s: (s['origin'][1], s['bbox'][0])):
        baseline = span['origin'][1]
        if not groups or abs(baseline - groups[-1][0]) > 2:
            groups.append((baseline, [span]))
        else:
            groups[-1][1].append(span)
    return groups


def _line_chars(parts, page_num):
    parts.sort(key=lambda s: s['bbox'][0])
    chars, right = [], None
    for span in parts:
        if right is not None and span['bbox'][0] - right > 1.5:
            chars.append((' ', '', page_num))
        st = style_of(span['font'])
        chars.extend((c, st, page_num) for c in span['text'])
        right = span['bbox'][2]
    while chars and chars[0][0].isspace():
        chars.pop(0)
    while chars and chars[-1][0].isspace():
        chars.pop()
    fixed = []
    for i, ch in enumerate(chars):
        fixed.append(ch)
        if ch[0] in MARKS and i + 1 < len(chars) and not chars[i + 1][0].isspace():
            fixed.append((' ', '', page_num))
    return fixed


def extract_rich(path):
    try:
        import pymupdf
    except ImportError as exc:
        raise RuntimeError('Installa le dipendenze di build: pip install -r requirements-build.txt') from exc
    pages = []
    with pymupdf.open(str(path)) as document:
        for page_num, page in enumerate(document, 1):
            spans = [span for block in page.get_text('dict')['blocks']
                     for line in block.get('lines', []) for span in line['spans']
                     if span['bbox'][1] >= TOP and span['bbox'][3] <= page.rect.height - BOTTOM]
            lines = []
            for _, parts in _group_baselines(spans):
                chars = _line_chars(parts, page_num)
                text = ''.join(c for c, _, _ in chars)
                if not text:
                    continue
                lines.append(RichLine(
                    text, page_num, min(s['bbox'][1] for s in parts), max(s['bbox'][3] for s in parts),
                    max(s['size'] for s in parts),
                    all('Helvetica' in s['font'] and 'Bold' in s['font'] for s in parts),
                    tuple((round(s['bbox'][0], 2), s['text']) for s in parts), chars,
                    min(s['bbox'][0] for s in parts), max(s['bbox'][2] for s in parts),
                    all('m' in style_of(s['font']) for s in parts if s['text'].strip())))
            pages.append(lines)
    return pages, {'backend': 'pymupdf', 'version': pymupdf.__version__}


def extract_tables(path, page_numbers):
    """{pagina: [{'bbox': (x0,y0,x1,y1), 'rows': [[chars|None, ...], ...]}]}.

    Ogni cella è letta dai soli caratteri il cui centro cade nella cella, riga per
    riga, così le colonne non si mescolano e le parole spezzate a fine cella si riuniscono.
    """
    import pymupdf
    out = {}
    with pymupdf.open(str(path)) as doc:
        for pn in page_numbers:
            page = doc[pn - 1]
            found = page.find_tables().tables
            if not found:
                continue
            raw = page.get_text('rawdict')
            spans = []
            for block in raw['blocks']:
                for line in block.get('lines', []):
                    for span in line['spans']:
                        st = style_of(span['font'])
                        glyphs = [((ch['bbox'][0] + ch['bbox'][2]) / 2, (ch['bbox'][1] + ch['bbox'][3]) / 2,
                                   ch['c']) for ch in span['chars']]
                        if glyphs:
                            spans.append((span['origin'][1], span['bbox'][0], span['bbox'][2], st, glyphs))
            tables = []
            for t in found:
                rows = []
                for row in t.rows:
                    cells = []
                    for c in row.cells:
                        if c is None:
                            cells.append(None)
                            continue
                        cx0, cy0, cx1, cy1 = c
                        inside = []
                        for base, x0, x1, st, glyphs in spans:
                            # ordine dei caratteri dello span conservato (legature ff/fi incluse)
                            sel = [g[2] for g in glyphs if cx0 <= g[0] <= cx1 and cy0 <= g[1] <= cy1]
                            if sel:
                                inside.append((base, x0, x1, st, ''.join(sel)))
                        cells.append(_cell_chars(inside, pn))
                    rows.append(cells)
                tables.append({'bbox': tuple(t.bbox), 'rows': rows})
            out[pn] = tables
    return out


def _cell_chars(spans, pn):
    lines = []
    for sp in sorted(spans, key=lambda s: (s[0], s[1])):
        if not lines or abs(sp[0] - lines[-1][0]) > 2:
            lines.append([sp[0], [sp]])
        else:
            lines[-1][1].append(sp)
    chars = []
    for _, sps in lines:
        sps.sort(key=lambda s: s[1])
        if chars:
            chars.append(('\n', '', pn))
        right = None
        for base, x0, x1, st, text in sps:
            if right is not None and x0 - right > 1.5 and chars and chars[-1][0] != ' ':
                chars.append((' ', '', pn))
            chars.extend((c, st, pn) for c in text)
            right = x1
    return rich_join(chars)


# ---------------------------------------------------------------------------
# Operazioni sul testo ricco
# ---------------------------------------------------------------------------

def rich_join(chars):
    """Equivalente di pdf_source.join_text con lo stile: riunisce parole spezzate, comprime spazi."""
    out, i = [], 0
    while i < len(chars):
        c = chars[i][0]
        if c in HYPHENS:
            j = i + 1
            while j < len(chars) and chars[j][0] in ' \t':
                j += 1
            if j < len(chars) and chars[j][0] == '\n':
                j += 1
                while j < len(chars) and chars[j][0] in ' \t':
                    j += 1
                i = j
                continue
        if c == '-' and out and out[-1][0].isalpha():
            # trattino vero a fine riga (all-|important): resta, senza spazio
            j = i + 1
            while j < len(chars) and chars[j][0] in ' \t':
                j += 1
            if j < len(chars) and chars[j][0] == '\n':
                j += 1
                while j < len(chars) and chars[j][0] in ' \t':
                    j += 1
                if j < len(chars) and chars[j][0].isalpha():
                    out.append(chars[i])
                    i = j
                    continue
        out.append(chars[i])
        i += 1
    norm = []
    for ch in out:
        if ch[0].isspace():
            if norm and norm[-1][0] != ' ':
                norm.append((' ', '', ch[2]))
        else:
            norm.append(ch)
    while norm and norm[0][0] == ' ':
        norm.pop(0)
    while norm and norm[-1][0] == ' ':
        norm.pop()
    # spazio dopo ✓/✗ come nelle righe di pdf_source
    fixed = []
    for i, ch in enumerate(norm):
        fixed.append(ch)
        if ch[0] in MARKS and i + 1 < len(norm) and norm[i + 1][0] != ' ':
            fixed.append((' ', '', ch[2]))
    return fixed


def plain(chars):
    return ''.join(c[0] for c in chars)


def strip_chars(chars, chars_to_strip=' '):
    a, b = 0, len(chars)
    while a < b and chars[a][0] in chars_to_strip:
        a += 1
    while b > a and chars[b - 1][0] in chars_to_strip:
        b -= 1
    return chars[a:b]


def runs(chars):
    """[(testo, stile)]; gli spazi restano col segmento precedente."""
    result = []
    for c, s, _ in chars:
        st = result[-1][1] if (c == ' ' and result) else s
        if result and result[-1][1] == st:
            result[-1][0] += c
        else:
            result.append([c, st])
    return [(t, s) for t, s in result]


def clean_book_markup(chars):
    """Il libro contiene residui letterali di formattazione: ~~barrato~~ e asterischi d'enfasi.

    ~~x~~ diventa x con stile 's' (barrato); tutti i marcatori vengono tolti a livello
    di carattere, così l'HTML generato resta sempre ben annidato.
    """
    text = plain(chars)
    strike = set()
    for m in re.finditer(r'~~(.+?)~~', text):
        strike.update(range(m.start(1), m.end(1)))
    drop = set()
    for m in re.finditer(r'~~|\*+', text):
        drop.update(range(m.start(), m.end()))
    out = []
    for i, (c, s, p) in enumerate(chars):
        if i in drop:
            continue
        out.append((c, s + 's' if i in strike and 's' not in s else s, p))
    return rich_join(out) if out else out


def to_plain(chars):
    text = plain(clean_book_markup(chars))
    return re.sub(r'[ \t]{2,}', ' ', text).strip()


def to_html(chars, styles=True):
    """HTML compatibile con Telegram (<b>, <i>, <s>, <code>), testo sempre con escape."""
    parts = []
    for text, s in runs(clean_book_markup(chars)):
        t = html.escape(text, quote=False)
        if styles and t.strip():
            lead = t[:len(t) - len(t.lstrip())]
            trail = t[len(t.rstrip()):]
            core = t.strip()
            if 'm' in s:
                core = f'<code>{core}</code>'
            else:
                if 'i' in s:
                    core = f'<i>{core}</i>'
                if 'b' in s:
                    core = f'<b>{core}</b>'
                if 's' in s:
                    core = f'<s>{core}</s>'
            t = lead + core + trail
        parts.append(t)
    return re.sub(r'[ \t]{2,}', ' ', ''.join(parts)).strip()
