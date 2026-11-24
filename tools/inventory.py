"""Inventario di fedeltà PDF → KB (fase 4.1). Solo lettura: non modifica la KB né il bot.

Uso:
    python tools/inventory.py "/percorso/english A1-C1.pdf" OUTPUT_DIR

Richiede le dipendenze di build (PyMuPDF). Produce:
    OUTPUT_DIR/inventario.json   dati completi, una scheda per ogni contenuto
    OUTPUT_DIR/INVENTARIO.md     riepilogo con conteggi ed esempi
    OUTPUT_DIR/verifica/*.html   confronto visivo bot ↔ ritaglio PDF, per capitolo

L'output contiene ritagli del libro: è materiale di lavoro privato, da non
pubblicare né includere nel repository.
"""
import base64
from collections import Counter, defaultdict
from dataclasses import dataclass, field
import hashlib
import html
import json
from pathlib import Path
import re
import sys
import unicodedata

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tutor.pdf_source import Line, extract_pages, partition_book, practice_sections  # noqa: E402

MARKS = '✓✗'
HYPHENS = '\u2010\u00ad'


# ---------------------------------------------------------------------------
# Estrazione "ricca": stesse righe di pdf_source.extract_pages + font per carattere
# ---------------------------------------------------------------------------

@dataclass
class RichLine(Line):
    chars: list = field(default_factory=list)   # [(carattere, stile)] allineato a text
    x0: float = 0.0
    x1: float = 0.0


def style_of(font):
    if font is None:
        return ''
    bold = 'Bold' in font or 'Semi' in font
    italic = 'Italic' in font or 'Ital' in font or 'Oblique' in font
    return ('b' if bold else '') + ('i' if italic else '')


def extract_rich(path):
    import pymupdf
    pages = []
    with pymupdf.open(str(path)) as document:
        for page_num, page in enumerate(document, 1):
            spans = []
            for block in page.get_text('dict')['blocks']:
                for line in block.get('lines', []):
                    for span in line['spans']:
                        if span['bbox'][1] >= 42 and span['bbox'][3] <= page.rect.height - 38:
                            spans.append(span)
            groups = []
            for span in sorted(spans, key=lambda s: (s['origin'][1], s['bbox'][0])):
                baseline = span['origin'][1]
                if not groups or abs(baseline - groups[-1][0]) > 2:
                    groups.append((baseline, [span]))
                else:
                    groups[-1][1].append(span)
            lines = []
            for _, parts in groups:
                parts.sort(key=lambda s: s['bbox'][0])
                chars, right, cells = [], None, []
                for span in parts:
                    if right is not None and span['bbox'][0] - right > 1.5:
                        chars.append((' ', None))
                    chars.extend((c, style_of(span['font'])) for c in span['text'])
                    right = span['bbox'][2]
                    cells.append((round(span['bbox'][0], 2), span['text']))
                # stesso strip + spazio dopo ✓/✗ di extract_pages, mantenendo l'allineamento
                while chars and chars[0][0].isspace():
                    chars.pop(0)
                while chars and chars[-1][0].isspace():
                    chars.pop()
                fixed = []
                for i, (c, s) in enumerate(chars):
                    fixed.append((c, s))
                    if c in MARKS and i + 1 < len(chars) and not chars[i + 1][0].isspace():
                        fixed.append((' ', None))
                text = ''.join(c for c, _ in fixed)
                if text:
                    lines.append(RichLine(text, page_num, min(s['bbox'][1] for s in parts),
                                          max(s['bbox'][3] for s in parts),
                                          max(s['size'] for s in parts),
                                          all('Helvetica' in s['font'] and 'Bold' in s['font'] for s in parts),
                                          tuple(cells), fixed,
                                          min(s['bbox'][0] for s in parts),
                                          max(s['bbox'][2] for s in parts)))
            pages.append(lines)
    return pages


# ---------------------------------------------------------------------------
# Testo con stile: unione righe identica a pdf_source.join_text
# ---------------------------------------------------------------------------

def rich_join(chars):
    """chars: [(c, stile)] con '\n' fra righe. Replica join_text() conservando lo stile."""
    out, i = [], 0
    while i < len(chars):
        c, s = chars[i]
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
        out.append((c, s))
        i += 1
    norm = []
    for c, s in out:
        if c.isspace():
            if norm and norm[-1][0] != ' ':
                norm.append((' ', None))
        else:
            norm.append((c, s))
    while norm and norm[0][0] == ' ':
        norm.pop(0)
    while norm and norm[-1][0] == ' ':
        norm.pop()
    return norm


def plain(chars):
    return ''.join(c for c, _ in chars)


def runs(chars):
    """Segmenti consecutivi con lo stesso stile; gli spazi seguono il segmento precedente."""
    result = []
    for c, s in chars:
        st = result[-1][1] if (c == ' ' and result) else (s or '')
        if result and result[-1][1] == st:
            result[-1][0] += c
        else:
            result.append([c, st])
    return [(t, s) for t, s in result]


def markup(chars):
    """Markdown leggero per il report: **grassetto**, _corsivo_."""
    out = []
    for text, s in runs(chars):
        core = text.strip()
        if not core or not s:
            out.append(text)
            continue
        lead = text[:len(text) - len(text.lstrip())]
        trail = text[len(text.rstrip()):]
        tag = {'b': '**', 'i': '_', 'bi': '**_'}[s]
        end = {'b': '**', 'i': '_', 'bi': '_**'}[s]
        out.append(f'{lead}{tag}{core}{end}{trail}')
    return ''.join(out)


def html_markup(chars):
    out = []
    for text, s in runs(chars):
        t = html.escape(text)
        if 'b' in s and t.strip():
            t = f'<b>{t}</b>'
        if 'i' in s and t.strip():
            t = f'<i>{t}</i>'
        out.append(t)
    return ''.join(out)


# ---------------------------------------------------------------------------
# Sezioni numerate con offset → righe (replica di kb_builder.group_sections)
# ---------------------------------------------------------------------------

def section_text(lines):
    text, chars, offsets = '', [], []
    for idx, line in enumerate(lines):
        offsets.append((len(text), idx))
        text += line.text + '\n'
        chars.extend(line.chars)
        chars.append(('\n', None))
    assert len(text) == len(chars) and text == ''.join(c for c, _ in chars)
    return text, chars, offsets


def lines_for(offsets, lines, start, end):
    idxs = [idx for off, idx in offsets if off < end and off + len(lines[idx].text) + 1 > start]
    return [lines[i] for i in idxs]


def numbered(text, start, end):
    chunk = text[start:end]
    matches = list(re.finditer(r'(?<!\w)(\d{1,2})\.\s+', chunk))
    prefix_end = start + (matches[0].start() if matches else len(chunk))
    items = []
    for i, m in enumerate(matches):
        s = start + m.end()
        e = start + (matches[i + 1].start() if i + 1 < len(matches) else len(chunk))
        items.append({'number': int(m[1]), 'start': s, 'end': e, 'num_start': start + m.start()})
    return (start, prefix_end), items


def groups(lines):
    text, chars, offsets = section_text(lines)
    found = list(re.finditer(r'(?m)^([A-F])\.\s+', text))
    chunks = [(m[1], m.end(), found[i + 1].start() if i + 1 < len(found) else len(text))
              for i, m in enumerate(found)] if found else [('', 0, len(text))]
    out = []
    for letter, s, e in chunks:
        prefix, items = numbered(text, s, e)
        out.append({'group': letter, 'prefix': prefix, 'items': items, 'start': s, 'end': e})
    return text, chars, offsets, out


# ---------------------------------------------------------------------------
# Analisi delle soluzioni: risposta (formattata) + spiegazione (tondo)
# ---------------------------------------------------------------------------

def split_answer(chars):
    """La chiave del libro usa tre formati:

    1. risposta in grassetto/corsivo + spiegazione in tondo (dopo «—» o fra parentesi);
    2. «✓ frase corretta» in corsivo + nota fra parentesi;
    3. frase intera in tondo con la parola chiave evidenziata + nota fra parentesi.
    Restituisce (risposta, spiegazione, schema, parole_chiave).
    """
    chars = list(chars)
    while chars and (chars[0][0] in '✓ '):
        chars.pop(0)
    rs = runs(chars)
    if not rs:
        return '', '', 'vuota', []
    core, i = [], 0
    while i < len(rs):
        text, s = rs[i]
        if s:
            core.append(text)
            i += 1
            continue
        if core and i + 1 < len(rs) and rs[i + 1][1] and re.fullmatch(r'\s*(?:/|…|\.\.\.|,|or|and|\+|·)?\s*', text):
            core.append(text)
            i += 1
            continue
        break
    answer = ''.join(core).strip()
    rest = ''.join(t for t, _ in rs[i:]).strip()
    keys = []
    if answer:
        scheme = 'risposta_e_spiegazione'
    else:
        # formato 3 (o etichette come "Subject:"): la risposta arriva fino alla nota
        text = plain(chars)
        m = re.match(r'(.+?)(?:\s+—\s*(.*)|\s+(\(.*\))\s*(.*))?$', text, flags=re.S)
        answer = m[1].strip().rstrip('—').strip()
        rest = (m[2] or ((m[3] or '') + ' ' + (m[4] or ''))).strip()
        keys = [t.strip(' .,;:') for t, s in runs(chars[:len(m[1])]) if s and t.strip(' .,;:—')]
        scheme = 'frase_con_parola_chiave' if keys else 'senza_marcatura'
    explanation = re.sub(r'^(?:—|–|-|:)\s*', '', rest).strip()
    if explanation.startswith('(') and explanation.endswith(')') and explanation.count('(') == 1:
        explanation = explanation[1:-1].strip()
    if scheme == 'risposta_e_spiegazione' and not explanation:
        scheme = 'solo_risposta'
    return answer, explanation, scheme, keys


def norm_key(s):
    s = unicodedata.normalize('NFKC', s).replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"')
    return ' '.join(s.split())


def loose(s):
    s = norm_key(s).casefold()
    return re.sub(r'[^\w]+', ' ', s).strip()


FORMAT_INSTR = re.compile(r'\b(bold|underlined?|italic|highlighted)\b', re.I)


def analyse_exercise(e, q_chars, a_chars, instr):
    flags = []
    q_plain, a_plain = plain(q_chars), plain(a_chars)
    if norm_key(q_plain) != norm_key(e['source_q']):
        flags.append('q_diversa_dal_pdf')
    if norm_key(a_plain) != norm_key(e['answer'] if 'source_answer' not in e else e['source_answer']):
        flags.append('soluzione_diversa_dal_pdf')
    q_styles = {s for c, s in q_chars if not c.isspace() and c not in '.,;:!?“”"\'’()'}
    answer, explanation, scheme, keys = split_answer(a_chars)
    info = {'q_markup': markup(q_chars), 'answer_markup': markup(a_chars),
            'answer_core': answer, 'answer_explanation': explanation, 'answer_scheme': scheme,
            'answer_keywords': keys,
            'q_styles': sorted(q_styles)}
    # Parola evidenziata richiesta dall'istruzione ma assente nel PDF
    if FORMAT_INSTR.search(instr):
        if len(q_styles) > 1:
            info['target'] = {'status': 'presente_nel_pdf'}
        else:
            italics = [t.strip(' .,;:') for t, s in runs(a_chars) if 'i' in s and t.strip()]
            hits = [w for w in italics if re.search(r'(?<!\w)' + re.escape(w) + r'(?!\w)', q_plain, re.I)]
            if 'underlined' in instr.lower() or 'underline' in instr.lower():
                cand = underlined_from_rewrite(q_plain, answer or a_plain)
                if cand:
                    hits = [cand]
            if hits:
                info['target'] = {'status': 'recuperabile_dalla_soluzione', 'word': hits[0]}
                flags.append('evidenziazione_persa_recuperabile')
            else:
                info['target'] = {'status': 'non_recuperabile'}
                flags.append('evidenziazione_persa_non_recuperabile')
    if re.search(r'\*\*|~~|`', q_plain + a_plain + instr):
        flags.append('residui_markdown_nel_libro')
    if re.search(r'[\u2010\u00ad]', q_plain + a_plain):
        flags.append('trattino_di_a_capo_residuo')
    if len(q_plain.split()) > 4 and e.get('kind') != 'compound' and not re.search(r'[.?!…”"’)\]_]$|__+$|→\s*_*$', q_plain.strip()):
        flags.append('domanda_senza_chiusura')
    if re.sub(r'(?:(?<=\s)|^)[a-z]\)', '', q_plain).count('(') != re.sub(r'(?:(?<=\s)|^)[a-z]\)', '', q_plain).count(')'):
        flags.append('parentesi_sbilanciate')
    if (q_plain.count('“') != q_plain.count('”')) or q_plain.count('"') % 2:
        flags.append('virgolette_sbilanciate')
    if re.search(r'(^|\s)[AB]:\s|—\s*[A-Z][a-z]+:', q_plain):
        flags.append('dialogo')
    if e.get('kind') == 'compound':
        flags.append('esercizio_composto')
    if e.get('kind') == 'mcq':
        opts = e.get('options') or []
        idx = e.get('answer_idx')
        if not opts or idx is None:
            flags.append('mcq_senza_opzioni')
        else:
            correct = opts[idx]
            if loose(correct) not in loose(answer or a_plain)[:max(len(loose(correct)) + 40, 60)]:
                flags.append('mcq_risposta_non_confermata')
    if not answer:
        flags.append('risposta_non_separabile')
    words = len(answer.split()) if answer else 99
    blanks = bool(re.search(r'_{2,}|\(\w[^()]*\)', q_plain))
    if e.get('kind') == 'mcq':
        mode = 'scelta_multipla'
    elif answer and words <= 4 and not re.search(r'(?i)answers may vary|\bor\b|(?<!^)/(?!$)', answer):
        mode = 'controllo_automatico'
    elif answer and blanks and words <= 8:
        mode = 'controllo_automatico_con_varianti'
    else:
        mode = 'autovalutazione'
    info['mode'] = mode
    info['flags'] = flags
    return info


def underlined_from_rewrite(q, a):
    """Per 'replace the underlined object with a pronoun': l'oggetto è la parte di q che sparisce."""
    qw, aw = q.rstrip('.?!').split(), a.split('(')[0].strip().rstrip('.?!').split()
    i = 0
    while i < min(len(qw), len(aw)) and qw[i].lower() == aw[i].lower():
        i += 1
    j = 0
    while j < min(len(qw), len(aw)) - i and qw[-1 - j].lower() == aw[-1 - j].lower():
        j += 1
    removed = qw[i:len(qw) - j]
    pronouns = {'it', 'them', 'him', 'her', 'us', 'me', 'you'}
    rest_a = [w.lower() for w in aw[i:len(aw) - j]]
    removed = [w for w in removed if w.lower() not in rest_a]
    if removed and any(w in pronouns for w in rest_a):
        return ' '.join(removed)
    return None


# ---------------------------------------------------------------------------
# Tabelle: cella per cella (la lettura lineare mescola le colonne)
# ---------------------------------------------------------------------------

def extract_tables(path, page_numbers):
    """{pagina: [{'bbox': (x0,y0,x1,y1), 'rows': [[testo cella|None]]}]}"""
    import pymupdf
    out = {}
    with pymupdf.open(str(path)) as doc:
        for pn in page_numbers:
            page = doc[pn - 1]
            found = []
            for t in page.find_tables().tables:
                rows = []
                for row in t.rows:
                    cells = []
                    for c in row.cells:
                        if c is None:
                            cells.append(None)
                            continue
                        words = page.get_text('words', clip=pymupdf.Rect(c))
                        words.sort(key=lambda w: (round(w[3]), w[0]))
                        txt = ' '.join(w[4] for w in words)
                        txt = re.sub(r'(\w)[\u2010\u00ad] (\w)', r'\1\2', txt)
                        txt = re.sub(r'([✓✗])(?=\S)', r'\1 ', txt)
                        cells.append(txt)
                    rows.append(cells)
                found.append({'bbox': tuple(t.bbox), 'rows': rows})
            if found:
                out[pn] = found
    return out


def in_table(line, tables):
    for t in tables.get(line.page, []):
        x0, y0, x1, y1 = t['bbox']
        if line.y >= y0 - 1 and line.bottom <= y1 + 1:
            return True
    return False


# ---------------------------------------------------------------------------
# Esempi ✓/✗ e coppie ✗ → ✓
# ---------------------------------------------------------------------------

def chapter_flat(lines, tables=None):
    if tables:
        lines = [l for l in lines if not in_table(l, tables)]
    text, chars, _ = section_text(lines)
    rich = rich_join(chars)
    return plain(rich), rich


def mark_segments(flat):
    """Ogni ✓/✗ del testo e il frammento che lo segue (fino al simbolo/freccia successivo)."""
    segs = []
    for m in re.finditer(r'[✓✗]', flat):
        start = m.end()
        nxt = re.search(r'[✓✗→|]| - (?=[✓✗A-Z])|•', flat[start:])
        end = start + (nxt.start() if nxt else min(len(flat) - start, 200))
        segs.append({'pos': m.start(), 'mark': m[0], 'text': flat[start:end].strip()})
    return segs


SENTENCE_END = re.compile(r'[.?!…]')


def classify_example(ex, flat, flat_norm, positions, cells=()):
    mark = '✓' if ex['ok'] else '✗'
    t = norm_key(ex['t'])
    best = None
    for m in re.finditer(re.escape(t), flat_norm):
        before = flat_norm[max(0, m.start() - 3):m.start()]
        after = flat_norm[m.end():m.end() + 2]
        has_mark = mark in before
        other_mark = ({'✓', '✗'} - {mark}).pop() in before
        cand = {'pos': m.start(), 'mark_ok': has_mark, 'wrong_mark': other_mark and not has_mark,
                'after': after}
        if best is None or (cand['mark_ok'] and not best['mark_ok']):
            best = cand
    if best is None:
        lk = loose(ex['t'])
        for cell in cells:
            if lk and lk in loose(cell):
                return {'status': 'confermato_in_tabella'}
        status = 'trovato_solo_normalizzando' if lk and lk in loose(flat) else 'non_trovato_nel_pdf'
        return {'status': status}
    flags = []
    if not best['mark_ok']:
        flags.append('segno_errato' if best['wrong_mark'] else 'senza_segno_nel_pdf')
    nxt = best['after']
    if nxt and nxt[0].isalnum() and not t[-1:] in '.?!…':
        flags.append('parola_tagliata')
    elif nxt.startswith(' ') and len(nxt) > 1 and nxt[1].isalpha() and nxt[1].islower() and t[-1:] not in '.?!…':
        flags.append('frase_troncata')
    positions.add(best['pos'])
    return {'status': 'confermato' if not flags else 'da_verificare', 'flags': flags, 'pos': best['pos']}


def classify_fix(fx, flat_norm):
    bad, good = norm_key(fx['bad']), norm_key(fx['good'])
    pb = [m.start() for m in re.finditer(re.escape(bad), flat_norm)]
    pg = [m.start() for m in re.finditer(re.escape(good), flat_norm)]
    if not pb or not pg:
        return {'status': 'non_trovata_nel_pdf', 'bad_found': bool(pb), 'good_found': bool(pg)}
    for b in pb:
        for g in pg:
            between = flat_norm[b + len(bad):g]
            if 0 <= g - (b + len(bad)) <= 12 and ('→' in between or '✓' in between):
                return {'status': 'coppia_confermata', 'pos': b}
    return {'status': 'testi_trovati_non_adiacenti'}


# ---------------------------------------------------------------------------
# Ritagli PDF per la verifica visiva
# ---------------------------------------------------------------------------

class Cropper:
    def __init__(self, path):
        import pymupdf
        self.doc = pymupdf.open(str(path))
        self.pymupdf = pymupdf

    def crop(self, lines, pad=3, dpi=110):
        """Un'immagine per pagina coinvolta, larga come la colonna del testo."""
        by_page = defaultdict(list)
        for line in lines:
            by_page[line.page].append(line)
        out = []
        for page, ls in sorted(by_page.items()):
            p = self.doc[page - 1]
            rect = self.pymupdf.Rect(min(l.x0 for l in ls) - pad, min(l.y for l in ls) - pad,
                                     max(max(l.x1 for l in ls) + pad, p.rect.width - 50),
                                     max(l.bottom for l in ls) + pad)
            rect.x0 = max(rect.x0 - 20, 0)
            pix = p.get_pixmap(clip=rect, dpi=dpi)
            data = pix.tobytes('jpeg', jpg_quality=62)
            out.append((page, base64.b64encode(data).decode('ascii')))
        return out


# ---------------------------------------------------------------------------
# Esecuzione
# ---------------------------------------------------------------------------

def main(pdf, out_dir):
    pdf, out_dir = Path(pdf), Path(out_dir)
    profile = json.loads((ROOT / 'data/book_profile.json').read_text(encoding='utf-8'))
    if hashlib.sha256(pdf.read_bytes()).hexdigest() != profile['pdf_sha256']:
        raise SystemExit('PDF diverso da quello approvato nel profilo del libro')
    kb = json.loads((ROOT / 'data/kb.json').read_text(encoding='utf-8'))
    overrides = json.loads((ROOT / 'data/content_overrides.json').read_text(encoding='utf-8'))

    rich_pages = extract_rich(pdf)
    plain_pages, _ = extract_pages(pdf)
    for rp, pp in zip(rich_pages, plain_pages):
        assert [l.text for l in rp] == [l.text for l in pp], 'estrazione ricca non allineata'
    sections, _, _ = partition_book(rich_pages)
    cropper = Cropper(pdf)

    by_id = {e['id']: e for e in kb['exercises']}
    patched = defaultdict(list)
    for p in overrides.get('exercises', []):
        patched[p.get('id') or p.get('match', {}).get('id')].append(p)

    ex_report, crops = {}, defaultdict(dict)
    for num in range(1, 26):
        lines = sections[num]
        practice, answers = practice_sections(lines)
        qt, qc, qo, qg = groups(practice)
        at, ac, ao, ag = groups(answers)
        grouped = any(g['group'] for g in ag)
        flat_answers = ag[0]['items'] if not grouped else []
        cumulative = 0
        for pos, g in enumerate(qg):
            items = g['items']
            singleton = not items
            if singleton:
                s, e = g['prefix']
                m = re.search(r'\bRewrite:\s*', qt[s:e])
                items = [{'number': None, 'start': s + m.end(), 'end': e, 'num_start': s}]
                instr_chars = rich_join(qc[s:s + m.end()])
            else:
                instr_chars = rich_join(qc[g['prefix'][0]:g['prefix'][1]])
            if grouped:
                sg = ag[pos]
                if singleton:
                    s, e = sg['prefix']
                    sel = [{'number': None, 'start': s, 'end': e, 'num_start': s}]
                else:
                    sel = sg['items']
            else:
                sel = flat_answers[cumulative:cumulative + len(items)]
            for item, ans in zip(items, sel):
                key = f"ch{num:02d}-{g['group'] or 'main'}-{item['number'] if item['number'] is not None else 'single'}"
                e = by_id.get(key)
                if e is None:
                    ex_report[key] = {'id': key, 'flags': ['non_presente_nella_kb']}
                    continue
                q_chars = rich_join(qc[item['start']:item['end']])
                a_chars = rich_join(ac[ans['start']:ans['end']])
                info = analyse_exercise(e, q_chars, a_chars, plain(instr_chars))
                if key in patched:
                    info['flags'].append('corretto_da_override')
                info.update({'id': key, 'ch': num, 'group': g['group'], 'number': item['number'],
                             'kind': e['kind'], 'instr': plain(instr_chars), 'pdf_page': e['pdf_page'],
                             'answer_pdf_page': e['answer_pdf_page'],
                             'kb_q': e['source_q'], 'kb_answer': e['answer'],
                             'html_q': html_markup(q_chars), 'html_answer': html_markup(a_chars),
                             'html_instr': html_markup(instr_chars)})
                ex_report[key] = info
                ql = lines_for(qo, practice, item['num_start'], item['end'])
                al = lines_for(ao, answers, ans['num_start'], ans['end'])
                crops[num][key] = (cropper.crop(ql), cropper.crop(al))
            cumulative += len(items)
    missing_in_pdf = sorted(set(by_id) - set(ex_report))

    # Esempi e coppie (tabelle lette cella per cella, il resto come testo continuo)
    all_pages = sorted({l.page for num in range(1, 26) for l in sections[num]})
    tables = extract_tables(pdf, all_pages)
    ch_cells = {num: [c for pn in sorted({l.page for l in sections[num]}) for t in tables.get(pn, [])
                      for row in t['rows'] for c in row if c] for num in range(1, 26)}
    flats = {num: chapter_flat(sections[num], tables) for num in range(1, 26)}
    flat_norm = {num: norm_key(flats[num][0]) for num in flats}
    ex_items, covered = [], defaultdict(set)
    seen = Counter()
    for i, ex in enumerate(kb['examples']):
        seen[(ex['ch'], ex['t'], ex['ok'])] += 1
        res = classify_example(ex, flats[ex['ch']][0], flat_norm[ex['ch']], covered[ex['ch']], ch_cells[ex['ch']])
        res.update({'i': i, 'ch': ex['ch'], 't': ex['t'], 'ok': ex['ok']})
        if seen[(ex['ch'], ex['t'], ex['ok'])] > 1:
            res.setdefault('flags', []).append('duplicato')
        if re.search(r'\*\*|~~', ex['t']):
            res.setdefault('flags', []).append('residui_markdown_nel_libro')
        ex_items.append(res)
    # Sezione (ultimo titolo) in cui compare ogni esempio
    for num in range(1, 26):
        heads, cur = [], ''
        for l in sections[num]:
            if l.heading and l.size >= 12 and l.text not in ('Practice', 'Answers'):
                cur = l.text
            heads.append((norm_key(l.text), cur, l.page))
        for res in ex_items:
            if res['ch'] != num:
                continue
            probe = norm_key(res['t'])[:24]
            hit = next(((h, pg) for t, h, pg in heads if probe and probe in t), None)
            if hit:
                res['section'], res['page'] = hit
            else:
                res['section'], res['page'] = '', None
    fix_items = []
    for i, fx in enumerate(kb['fixes']):
        res = classify_fix(fx, flat_norm[fx['ch']])
        res.update({'i': i, 'ch': fx['ch'], 'bad': fx['bad'], 'good': fx['good']})
        fix_items.append(res)

    # Segni del libro non coperti da alcun esempio della KB
    uncovered = []
    ex_loose = defaultdict(list)
    for ex in kb['examples']:
        ex_loose[(ex['ch'], '✓' if ex['ok'] else '✗')].append(loose(ex['t']))
    fix_loose = defaultdict(set)
    for fx in kb['fixes']:
        fix_loose[(fx['ch'], '✗')].add(loose(fx['bad']))
        fix_loose[(fx['ch'], '✓')].add(loose(fx['good']))

    def is_covered(num, mark, text):
        lt = loose(text)
        if len(lt) < 3:
            return None
        for cand in ex_loose[(num, mark)] + list(fix_loose[(num, mark)]):
            if cand and (lt.startswith(cand) or (len(lt) >= 8 and cand.startswith(lt))):
                return True
        return False

    for num in range(1, 26):
        sources = [('testo', seg) for seg in mark_segments(flat_norm[num])]
        sources += [('tabella', seg) for cell in ch_cells[num] for seg in mark_segments(norm_key(cell))]
        for where, seg in sources:
            cov = is_covered(num, seg['mark'], seg['text'])
            if cov:
                continue
            kind = 'simbolo_senza_frase' if cov is None else 'non_estratto'
            uncovered.append({'ch': num, 'mark': seg['mark'], 'text': seg['text'][:160], 'kind': kind, 'where': where})
    pairs_pdf = []
    for num in range(1, 26):
        for m in re.finditer(r'✗\s*([^✓✗→|]{2,120}?)\s*→\s*✓\s*([^✓✗→|]{2,120}?)(?=\s*(?:[✓✗|•]| - |$))', flat_norm[num]):
            pairs_pdf.append((num, m[1].strip(), m[2].strip()))
    known = {(f['ch'], norm_key(f['bad'])) for f in kb['fixes']}
    pairs_new = [p for p in pairs_pdf if (p[0], norm_key(p[1]).rstrip('.')) not in {(k[0], k[1].rstrip('.')) for k in known}]

    # Testo teorico dei capitoli: residui e tabelle
    theory = []
    for ch in kb['chapters']:
        t = ch['text']
        tbl_pages = sorted({pn for pn in {l.page for l in sections[ch['num']]} if pn in tables})
        theory.append({'ch': ch['num'], 'markdown_residui': len(re.findall(r'\*\*|~~', t)),
                       'trattini_residui': len(re.findall(r'\w[\u2010\u00ad] \w', t)),
                       'pagine_con_tabelle': tbl_pages,
                       'tabelle': sum(len(tables[pn]) for pn in tbl_pages)})

    # ---- Riepilogo
    exf = Counter(f for r in ex_report.values() for f in r.get('flags', []))
    modes = Counter(r.get('mode') for r in ex_report.values() if r.get('mode'))
    schemes = Counter(r.get('answer_scheme') for r in ex_report.values() if r.get('answer_scheme'))
    targets = Counter(r['target']['status'] for r in ex_report.values() if r.get('target'))
    exs = Counter(r['status'] for r in ex_items)
    exflags = Counter(f for r in ex_items for f in r.get('flags', []))
    fxs = Counter(r['status'] for r in fix_items)
    unc = Counter(u['kind'] for u in uncovered)
    summary = {
        'esercizi': {'totale_kb': len(by_id), 'mappati_sul_pdf': len(by_id) - len(missing_in_pdf),
                     'non_mappati': missing_in_pdf, 'segnalazioni': dict(exf.most_common()),
                     'modalita_proposta': dict(modes), 'schema_soluzioni': dict(schemes),
                     'evidenziazioni': dict(targets),
                     'puliti': sum(1 for r in ex_report.values() if not set(r.get('flags', [])) - {'corretto_da_override', 'esercizio_composto', 'dialogo'})},
        'esempi': {'totale_kb': len(ex_items), 'stato': dict(exs), 'segnalazioni': dict(exflags),
                   'con_sezione': sum(1 for r in ex_items if r.get('section')),
                   'sezioni_distinte': len({(r['ch'], r.get('section')) for r in ex_items if r.get('section')}),
                   'segni_del_libro_non_estratti': dict(unc),
                   'non_estratti_per_origine': dict(Counter(u['where'] for u in uncovered if u['kind'] == 'non_estratto'))},
        'coppie': {'totale_kb': len(fix_items), 'stato': dict(fxs),
                   'coppie_nel_pdf_rilevate': len(pairs_pdf), 'coppie_nel_pdf_non_in_kb': len(pairs_new)},
        'teoria': {'residui_markdown': sum(t['markdown_residui'] for t in theory),
                   'trattini_residui': sum(t['trattini_residui'] for t in theory),
                   'pagine_con_tabelle': sum(len(t['pagine_con_tabelle']) for t in theory),
                   'tabelle': sum(t['tabelle'] for t in theory)},
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    data = {'summary': summary, 'exercises': list(ex_report.values()), 'examples': ex_items,
            'fixes': fix_items, 'uncovered_marks': uncovered, 'pdf_pairs_not_in_kb': pairs_new,
            'theory': theory,
            'source': {'pdf_sha256': profile['pdf_sha256'],
                       'kb_sha256': hashlib.sha256((ROOT / 'data/kb.json').read_bytes()).hexdigest()}}
    slim = json.loads(json.dumps(data, ensure_ascii=False))
    for r in slim['exercises']:
        for k in ('html_q', 'html_answer', 'html_instr'):
            r.pop(k, None)
    (out_dir / 'inventario.json').write_text(json.dumps(slim, ensure_ascii=False, indent=1), encoding='utf-8')
    write_html(out_dir / 'verifica', ex_report, crops, ex_items, fix_items, uncovered, kb)
    return data


# ---------------------------------------------------------------------------
# Pagine HTML di verifica
# ---------------------------------------------------------------------------

CSS = """body{font:15px/1.45 -apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:#f5f5f2;color:#222}
header{background:#1f3a5f;color:#fff;padding:14px 22px}header a{color:#cfe1ff}
main{padding:12px 22px;max-width:1500px}
.card{background:#fff;border:1px solid #ddd;border-radius:8px;margin:14px 0;display:grid;grid-template-columns:1fr 1fr;gap:0}
.card>div{padding:10px 14px}.card .pdf{border-left:1px solid #eee;background:#fafafa}
.card img{max-width:100%;display:block;margin:4px 0;border:1px solid #e3e3e3}
.id{font-family:monospace;font-size:13px;color:#555}.lbl{font-size:12px;text-transform:uppercase;color:#888;margin-top:8px}
.flag{display:inline-block;font-size:12px;padding:1px 7px;border-radius:10px;margin:2px 3px 2px 0;background:#e8eefc;color:#234}
.flag.warn{background:#fde8c8;color:#7a4300}.flag.bad{background:#f9d4d4;color:#7a0000}.flag.ok{background:#d9f2dc;color:#1c5a24}
.core{background:#fff6c9;padding:0 3px}table{border-collapse:collapse;background:#fff}td,th{border:1px solid #ddd;padding:4px 8px;font-size:14px;vertical-align:top}
nav a{margin-right:10px}"""

BAD = {'q_diversa_dal_pdf', 'soluzione_diversa_dal_pdf', 'evidenziazione_persa_non_recuperabile',
       'mcq_risposta_non_confermata', 'mcq_senza_opzioni', 'non_presente_nella_kb'}
WARN = {'evidenziazione_persa_recuperabile', 'residui_markdown_nel_libro', 'trattino_di_a_capo_residuo',
        'domanda_senza_chiusura', 'parentesi_sbilanciate', 'virgolette_sbilanciate', 'soluzione_senza_marcatura'}


def flag_html(f):
    cls = 'bad' if f in BAD else 'warn' if f in WARN else ''
    return f'<span class="flag {cls}">{html.escape(f.replace("_", " "))}</span>'


def write_html(folder, ex_report, crops, ex_items, fix_items, uncovered, kb):
    folder.mkdir(parents=True, exist_ok=True)
    titles = {c['num']: c['title'] for c in kb['chapters']}
    index_rows = []
    for num in range(1, 26):
        items = [r for r in ex_report.values() if r.get('ch') == num]
        exs = [r for r in ex_items if r['ch'] == num]
        fxs = [r for r in fix_items if r['ch'] == num]
        unc = [u for u in uncovered if u['ch'] == num and u['kind'] == 'non_estratto']
        warn = sum(1 for r in items if set(r.get('flags', [])) & (BAD | WARN))
        index_rows.append(f'<tr><td><a href="cap{num:02d}.html">Cap. {num}</a></td><td>{html.escape(titles[num])}</td>'
                          f'<td>{len(items)}</td><td>{warn}</td><td>{len(exs)}</td>'
                          f'<td>{sum(1 for r in exs if r["status"] not in ("confermato", "confermato_in_tabella"))}</td><td>{len(unc)}</td>'
                          f'<td>{len(fxs)}</td></tr>')
        parts = [f'<html><head><meta charset="utf-8"><title>Cap. {num}</title><style>{CSS}</style></head><body>',
                 f'<header><b>Capitolo {num} — {html.escape(titles[num])}</b> · '
                 f'<a href="index.html">indice</a>'
                 + (f' · <a href="cap{num - 1:02d}.html">← cap. {num - 1}</a>' if num > 1 else '')
                 + (f' · <a href="cap{num + 1:02d}.html">cap. {num + 1} →</a>' if num < 25 else '')
                 + '</header><main>',
                 '<p>A sinistra: come il bot legge l’esercizio (grassetto/corsivo come nel PDF; '
                 '<span class="core">evidenziato</span> = risposta separata dalla spiegazione). '
                 'A destra: il ritaglio della pagina del libro. Controlla che coincidano.</p>',
                 f'<h2>Esercizi ({len(items)})</h2>']
        for r in sorted(items, key=lambda r: (r['group'] or '', r['number'] or 0)):
            flags = ''.join(flag_html(f) for f in r.get('flags', [])) or '<span class="flag ok">nessuna segnalazione</span>'
            tgt = ''
            if r.get('target'):
                t = r['target']
                tgt = (f'<div class="lbl">parola evidenziata</div>'
                       + (f'<b>{html.escape(t["word"])}</b> (ricavata dalla soluzione)' if t.get('word') else html.escape(t['status'].replace('_', ' '))))
            qimgs, aimgs = crops.get(num, {}).get(r['id'], ([], []))
            img = lambda ims: ''.join(f'<div class="id">p. {p}</div><img src="data:image/jpeg;base64,{b}">' for p, b in ims)
            parts.append(
                f'<div class="card"><div><div class="id">{r["id"]} · {html.escape(r.get("mode", "").replace("_", " "))} · p. {r["pdf_page"]}/{r["answer_pdf_page"]}</div>'
                f'<div class="lbl">consegna</div>{r.get("html_instr", "")}'
                f'<div class="lbl">domanda</div>{r.get("html_q", "")}{tgt}'
                f'<div class="lbl">soluzione del libro</div>{r.get("html_answer", "")}'
                f'<div class="lbl">risposta / spiegazione separate</div><span class="core">{html.escape(r.get("answer_core", ""))}</span>'
                f' — {html.escape(r.get("answer_explanation", ""))}'
                f'<div class="lbl">segnalazioni</div>{flags}</div>'
                f'<div class="pdf"><div class="lbl">libro — domanda</div>{img(qimgs)}'
                f'<div class="lbl">libro — soluzione</div>{img(aimgs)}</div></div>')
        bad_ex = [r for r in exs if r['status'] not in ('confermato', 'confermato_in_tabella') or r.get('flags')]
        parts.append(f'<h2>Esempi ✓/✗ da verificare ({len(bad_ex)} su {len(exs)})</h2><table><tr><th>#</th><th>segno</th><th>testo nella KB</th><th>esito</th></tr>')
        for r in bad_ex:
            parts.append(f'<tr><td>{r["i"]}</td><td>{"✓" if r["ok"] else "✗"}</td><td>{html.escape(r["t"])}</td>'
                         f'<td>{flag_html(r["status"])}{"".join(flag_html(f) for f in r.get("flags", []))}</td></tr>')
        parts.append('</table>')
        parts.append(f'<h2>Frasi ✓/✗ del libro non presenti nella KB ({len(unc)})</h2><table><tr><th>segno</th><th>testo nel libro</th></tr>')
        for u in unc:
            parts.append(f'<tr><td>{u["mark"]}</td><td>{html.escape(u["text"])}</td></tr>')
        parts.append('</table>')
        parts.append(f'<h2>Coppie errore → correzione ({len(fxs)})</h2><table><tr><th>✗</th><th>✓</th><th>esito</th></tr>')
        for r in fxs:
            parts.append(f'<tr><td>{html.escape(r["bad"])}</td><td>{html.escape(r["good"])}</td><td>{flag_html(r["status"])}</td></tr>')
        parts.append('</table></main></body></html>')
        (folder / f'cap{num:02d}.html').write_text(''.join(parts), encoding='utf-8')
    (folder / 'index.html').write_text(
        f'<html><head><meta charset="utf-8"><title>Verifica lettura PDF</title><style>{CSS}</style></head><body>'
        '<header><b>Verifica della lettura del libro — fase 4.1</b></header><main>'
        '<p>Materiale di lavoro privato: contiene ritagli del libro. Non pubblicare.</p>'
        '<table><tr><th>capitolo</th><th>titolo</th><th>esercizi</th><th>esercizi con segnalazioni</th>'
        '<th>esempi KB</th><th>esempi da verificare</th><th>frasi ✓/✗ non estratte</th><th>coppie</th></tr>'
        + ''.join(index_rows) + '</table></main></body></html>', encoding='utf-8')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    result = main(sys.argv[1], sys.argv[2])
    print(json.dumps(result['summary'], ensure_ascii=False, indent=1))
