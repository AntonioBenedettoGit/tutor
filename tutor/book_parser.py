"""Analisi del libro A1-C1 dal testo ricco: blocchi della teoria, tabelle, esempi ✓/✗,
coppie ✗ → ✓, soluzioni divise in risposta/spiegazione, esercizi composti.

Modulo di sola build. Non importa PyMuPDF direttamente: lavora sulle righe e sulle
tabelle prodotte da tutor.pdf_rich.
"""
import hashlib
import re

from tutor.pdf_rich import MARKS, clean_book_markup, plain, rich_join, runs, strip_chars, to_html, to_plain

STRUCTURAL = re.compile(r'^(?:[•✓✗]|\d+\.\s|[A-F]\.\s)')
CALLOUT = re.compile(r'^(?:Rule|Tip|Remember|Note|Common mistake|Watch out|Good to know|Quick test|Key idea|British / American note)\b')
SECTION_TITLES = ('Practice', 'Answers', 'Quick Review')
PARA_GAP = 5.0          # misurato: righe dello stesso paragrafo 3.5–4.4 pt, paragrafi ≥ 6 pt
SENT_END = '.?!…'
CLOSERS = '”’"\')]'


# ---------------------------------------------------------------------------
# Blocchi della teoria
# ---------------------------------------------------------------------------

def _in_table(line, tables):
    for idx, t in enumerate(tables.get(line.page, [])):
        x0, y0, x1, y1 = t['bbox']
        if line.y >= y0 - 1 and line.bottom <= y1 + 1:
            return idx
    return None


def _join_lines(lines):
    chars = []
    for line in lines:
        if chars:
            chars.append(('\n', '', line.page))
        chars.extend(line.chars)
    return rich_join(chars)


def chapter_blocks(lines, tables):
    """Ripete la logica di pdf_source.paragraphs() con lo stile e con le tabelle intere.

    Tipi: heading, para, bullet, table, pre. Le righe dentro una tabella vengono sostituite
    dalla tabella letta cella per cella, inserita nel punto in cui inizia.
    """
    blocks, pending, pre = [], [], []
    emitted = set()
    prev = None

    def flush():
        nonlocal pending
        if pending:
            chars = _join_lines(pending)
            kind = 'bullet' if plain(chars).startswith('•') else 'para'
            blocks.append({'type': kind, 'chars': chars, 'page': pending[0].page})
            pending = []

    def flush_pre():
        nonlocal pre
        if pre:
            blocks.append({'type': 'pre', 'lines': [l.text for l in pre], 'page': pre[0].page})
            pre = []

    for line in lines:
        t_idx = _in_table(line, tables)
        if t_idx is not None:
            flush(); flush_pre()
            key = (line.page, t_idx)
            if key not in emitted:
                emitted.add(key)
                blocks.append({'type': 'table', 'rows': tables[line.page][t_idx]['rows'], 'page': line.page})
            prev = line
            continue
        if line.mono:
            flush()
            pre.append(line)
            prev = line
            continue
        flush_pre()
        heading = line.heading and line.size >= 11
        if heading or line.text in SECTION_TITLES:
            flush()
            last = blocks[-1] if blocks else None
            if (heading and last and last['type'] == 'heading' and last.get('size') == round(line.size, 1)
                    and prev is not None and prev.page == line.page and line.y - prev.bottom < 8):
                last['chars'] = rich_join(last['chars'] + [(' ', '', line.page)] + list(line.chars))
            else:
                blocks.append({'type': 'heading', 'chars': list(line.chars), 'page': line.page,
                               'size': round(line.size, 1)})
            prev = line
            continue
        structural = bool(STRUCTURAL.match(line.text)) or bool(CALLOUT.match(line.text))
        if structural and pending and pending[-1].text.rstrip().endswith('→') and line.text[:1] in MARKS:
            structural = False       # «✗ errore →» a fine riga, «✓ correzione» a capo: stessa coppia
        tail = pending[-1].text.rstrip() if pending else ''
        continues = bool(tail) and tail[-1] in MARKS + '→'   # simbolo a fine riga, esempio a capo
        if prev is not None and line.page == prev.page:
            gap = line.y - prev.bottom > PARA_GAP
        else:
            # cambio pagina: il paragrafo prosegue se la riga precedente non chiude una frase
            gap = bool(pending) and bool(re.search(r'[.?!:…”)]$', pending[-1].text.strip()))
        small = line.size <= 9.5
        if pending and (structural or gap or small) and not continues:
            flush()
        pending.append(line)
        if small:
            flush()
        prev = line
    flush(); flush_pre()
    return blocks


def _is_header_row(row):
    cells = [c for c in row if c]
    return bool(cells) and all(all('b' in s for ch, s, _ in c if not ch.isspace()) for c in cells)


def table_model(rows, previous_header=None):
    """Riga di intestazione (tutta in grassetto) e righe di dati, celle vuote rimosse."""
    rows = [r for r in rows if any(c and plain(c).strip() for c in r)]
    header = None
    if rows and _is_header_row(rows[0]):
        header, rows = rows[0], rows[1:]
    elif previous_header is not None and rows and len(previous_header) == len(rows[0]):
        header = previous_header           # tabella che prosegue dalla pagina precedente
    return header, rows


def render_table(header, rows, html=False):
    fmt = (lambda c: to_html(c) if c else '') if html else (lambda c: to_plain(c) if c else '')
    bold = (lambda s: f'<b>{s}</b>' if s else s) if html else (lambda s: s)
    out = []
    head = [fmt(c) for c in header] if header else None
    if head:
        out.append(bold(' · '.join(h for h in head if h)))
    for row in rows:
        cells = [fmt(c) for c in row]
        if not any(cells):
            continue
        first = cells[0] or '—'
        rest = cells[1:]
        if len(row) == 2:
            out.append(f'▸ {bold(first)} — {rest[0]}' if rest[0] else f'▸ {bold(first)}')
        else:
            lines = [f'▸ {bold(first)}']
            for i, value in enumerate(rest, 1):
                if not value:
                    continue
                label = head[i] if head and i < len(head) and head[i] else ''
                lines.append(f'   {label}: {value}' if label else f'   {value}')
            out.append('\n'.join(lines))
    return out


def render_blocks(blocks):
    """Per ogni blocco: testo semplice e HTML Telegram. Le tabelle diventano righe leggibili."""
    rendered, prev_header = [], None
    for b in blocks:
        if b['type'] == 'table':
            header, rows = table_model(b['rows'], prev_header if rendered and rendered[-1]['type'] == 'table' else None)
            prev_header = header
            text_rows, html_rows = render_table(header, rows), render_table(header, rows, html=True)
            rendered.append({'type': 'table', 'page': b['page'],
                             'text': '\n'.join(text_rows), 'html': '\n'.join(html_rows)})
        elif b['type'] == 'pre':
            body = '\n'.join(b['lines'])
            import html as _h
            rendered.append({'type': 'pre', 'page': b['page'], 'text': body,
                             'html': '<pre>' + _h.escape(body, quote=False) + '</pre>'})
        else:
            text = to_plain(b['chars'])
            if not text:
                continue
            h = to_html(b['chars'])
            if b['type'] == 'heading':
                h = '<b>' + re.sub(r'</?b>', '', h) + '</b>'
            rendered.append({'type': b['type'], 'page': b['page'], 'text': text, 'html': h})
    return [r for r in rendered if r['text'].strip()]


# ---------------------------------------------------------------------------
# Esempi ✓/✗ e coppie ✗ → ✓
# ---------------------------------------------------------------------------

def _alnum(c):
    return c.isalnum()


def _italic(ch):
    return 'i' in ch[1]


def _trim_example(chars):
    chars = strip_chars(chars, ' ')
    # «(✓ Dogs are loyal).»: la parentesi chiusa appartiene al testo intorno
    text = plain(chars)
    m = re.search(r'\)([.?!…]?)$', text)
    if m and text.count('(') < text.count(')'):
        chars = chars[:m.start()] + chars[m.end() - len(m[1]):] if m[1] else chars[:m.start()]
    changed = True
    while chars and changed:
        changed = False
        text = plain(chars)
        for tail in (', not', ' not', ' or', ' but', ' and', ' vs', ' vs.', ' —', ' –', ' -', ',', ';', ':', '/', '(', '='):
            if text.endswith(tail) and len(text) > len(tail):
                if tail == ' not' and ' ' not in text[:-len(tail)].strip():
                    continue                 # «do not → don’t»: è l'esempio, non un raccordo
                chars = strip_chars(chars[:len(chars) - len(tail)], ' ')
                changed = True
                break
    return chars


def _paren_end(text, start):
    depth = 0
    for p in range(start, len(text)):
        if text[p] == '(':
            depth += 1
        elif text[p] == ')':
            depth -= 1
            if depth == 0:
                return p + 1
    return None


def _mostly_italic(chars):
    letters = [c for c in chars if c[0].isalnum()]
    return bool(letters) and sum('i' in c[1] for c in letters) * 2 >= len(letters)


def _styled(ch):
    return 'i' in ch[1] or 'b' in ch[1]


def _sentence_end(text, chars, j, hard):
    """Fine della frase d'esempio; prosegue su più frasi solo se il corsivo continua (dialoghi).

    L'enfasi del libro è irregolare (residui di asterischi: grassetto, corsivo e tondo
    mescolati nella stessa frase). Se l'esempio comincia in corsivo/grassetto e poi passa
    al tondo, il tratto in tondo è un commento quando:
      - arriva a fine frase dopo una virgola/trattino/due punti, oppure
      - è lungo almeno 3 parole e poi lo stile riprende (commento con citazioni).
    Altrimenti fa parte dell'esempio (parola chiave in corsivo, enfasi spezzata).
    """
    first = next((x for x in range(j, hard) if text[x].isalnum()), None)
    starts_styled = first is not None and _styled(chars[first])
    depth, p, last_st = 0, j, None
    while p < hard:
        c = text[p]
        if c == '(':
            depth += 1
        elif c == ')':
            depth = max(0, depth - 1)
        elif depth == 0 and c.isalnum():
            if _styled(chars[p]):
                last_st = p
            elif starts_styled and last_st is not None:
                between = text[last_st + 1:p]
                d, x, resume = 0, p, None
                while x < hard:
                    cx = text[x]
                    if cx == '(':
                        d += 1
                    elif cx == ')':
                        d = max(0, d - 1)
                    elif d == 0 and cx in SENT_END and (x + 1 >= hard or text[x + 1] in ' ' + CLOSERS):
                        break
                    elif d == 0 and cx.isalnum() and _styled(chars[x]):
                        resume = x
                        break
                    x += 1
                words = len(re.findall(r"[\w’']+", text[p:x]))
                if resume is None:
                    if re.search(r'[,;:—–]', between):
                        return _close(text, last_st + 1, hard, j)
                    starts_styled = False       # parola chiave evidenziata, frase in tondo
                elif words >= 3:
                    return _close(text, last_st + 1, hard, j)
                else:
                    p = resume
                    continue
        elif depth == 0 and c in SENT_END and (p + 1 >= hard or text[p + 1] == ' ' or text[p + 1] in CLOSERS):
            q = p + 1
            while q < hard and text[q] in CLOSERS:
                if text[q] == ')' and text[j:q].count('(') <= text[j:q].count(')'):
                    break
                q += 1
            r = next((x for x in range(q, hard) if text[x].isalnum() or text[x] == '('), None)
            if (r is not None and text[r] != '(' and _italic(chars[r]) and _mostly_italic(chars[j:q])
                    and not re.match(r'\s*[A-Z][a-z]+:', text[q:hard])):
                p = q
                continue
            return q
        p += 1
    return hard


def _close(text, end, hard, j):
    while end < hard and text[end] in SENT_END + CLOSERS:
        if text[end] == ')' and text[j:end].count('(') <= text[j:end].count(')'):
            break
        end += 1
    return end


def _italic_end(text, chars, f, hard):
    end, p, depth = f + 1, f + 1, 0
    while p < hard:
        c = text[p]
        if c == '(':
            close = _paren_end(text, p)
            if close and close <= hard:
                after = next((x for x in range(close, hard) if text[x].isalnum()), None)
                inner_italic = any(_italic(ch) for ch in chars[p:close] if ch[0].isalnum())
                if after is not None and _italic(chars[after]) and not inner_italic:
                    p = close            # etichetta in tondo dentro la frase: (S), (manner)...
                    continue
            break
        if c.isalnum():
            if not _italic(chars[p]):
                break
            end = p + 1
        p += 1
    while end < hard and text[end] in SENT_END + CLOSERS:
        if text[end] == ')' and text[f:end].count('(') <= text[f:end].count(')'):
            break
        end += 1
    return end


def _phrase_end(text, j, hard):
    depth = 0
    for p in range(j, hard):
        c = text[p]
        if c == '(':
            if depth == 0 and p > j and text[p - 1] == ' ':
                return p
            depth += 1
        elif c == ')':
            depth = max(0, depth - 1)
        elif depth == 0 and (text.startswith(' — ', p) or c == ';'):
            return p
    return hard


MENTION = re.compile(r'(?:\b(?:the|a|an|and|or|with|by|of)\s*|\()$', re.I)


def _symbol_mention(text, i, t):
    """«Notice the ✓ and ✗ examples»: il simbolo è citato nella prosa, non introduce un esempio."""
    left, right = text[:i].rstrip(' '), text[i + 1:].lstrip(' ')
    if (left.endswith('/') and left[:-1].rstrip(' ')[-1:] in tuple(MARKS)) or (
            right.startswith('/') and right[1:].lstrip(' ')[:1] in tuple(MARKS)):
        return True                      # «a ✓/✗ example»
    if re.fullmatch(r'\([^()]*\)', t):
        return True                      # cella di tabella «✓ (singular)»: etichetta, non esempio
    before = text[max(0, i - 12):i]
    if MENTION.search(before) and (re.match(r'^(?:and|or|examples?|marks?|symbols?)\b', t) or len(t) <= 3):
        return True
    return bool(re.match(r'^[)\],.;:]', t)) or t.lower() in ('and', 'or', 'and the', 'examples')


def segment_marks(chars, broken=False):
    """Trova ogni ✓/✗ e separa l'esempio dalla nota del libro.

    Frasi (maiuscola iniziale): fino alla fine della frase, anche se l'enfasi del libro è
    irregolare. Espressioni: la parte in corsivo. Frecce, barre e trattini di elenco
    chiudono sempre l'esempio; ciò che segue una freccia senza segno è il risultato.
    """
    text = plain(chars)
    marks = [i for i, c in enumerate(text) if c in MARKS]
    items = []
    for k, i in enumerate(marks):
        limit = marks[k + 1] if k + 1 < len(marks) else len(text)
        j = i + 1
        while j < limit and text[j] == ' ':
            j += 1
        hard, depth, arrow = limit, 0, False
        for p in range(j, limit):
            c = text[p]
            if c == '(':
                depth += 1
            elif c == ')':
                depth = max(0, depth - 1)
            elif depth == 0 and (c in '→|•' or text.startswith(' - ', p)):
                hard, arrow = p, c == '→'
                break
        first = next((p for p in range(j, hard) if _alnum(text[p])), None)
        if first is None:
            continue
        if re.match(r'[“"‘(]?[A-Z0-9]', text[j:hard]) and not (_italic(chars[first]) and text[first].islower()):
            end, mode = _sentence_end(text, chars, j, hard), 'frase'
            if not re.search(r'[.?!…]', text[j:end]):
                # nome proprio o titolo senza punto finale: niente commento attaccato
                end = _italic_end(text, chars, first, hard) if _italic(chars[first]) else _phrase_end(text, j, hard)
        elif _italic(chars[first]) and broken:
            # residui di asterischi: l'enfasi è spezzata (corsivo/grassetto/tondo alternati),
            # quindi l'espressione arriva fino alla fine del tratto, non del corsivo
            end, mode = _phrase_end(text, j, hard), 'tondo'
        elif _italic(chars[first]):
            end, mode = _italic_end(text, chars, first, hard), 'corsivo'
        else:
            end, mode = _phrase_end(text, j, hard), 'tondo'
        ex = _trim_example(chars[j:end])
        if not ex or not any(_alnum(c[0]) for c in ex):
            continue
        if _symbol_mention(text, i, plain(ex)):
            continue
        lead_sp = len(text[j:end]) - len(text[j:end].lstrip(' '))
        end = j + lead_sp + len(ex)
        note, pos = '', end
        rest = text[end:limit]
        lead = len(rest) - len(rest.lstrip())
        if rest.strip().startswith('('):
            pe = _paren_end(text, end + lead)
            if pe and pe <= limit:
                note = text[end + lead + 1:pe - 1].strip()
                pos = pe
        gap = text[pos:limit].strip()
        item = {'mark': text[i], 'chars': ex, 'note': note, 'gap': gap, 'mode': mode, 'page': ex[0][2]}
        if arrow and hard < limit:
            after = text[hard + 1:limit].strip()
            if after and not re.match(r'^[✓✗]', after):
                a0 = hard + 1 + (len(text[hard + 1:limit]) - len(text[hard + 1:limit].lstrip()))
                a_end = _sentence_end(text, chars, a0, limit)
                result = to_plain(_trim_example(chars[a0:a_end]))
                f0 = next((x for x in range(a0, a_end) if text[x].isalnum()), None)
                if result and f0 is not None and _styled(chars[f0]):
                    item['result'] = result          # es. discorso diretto → indiretto
                elif result and not note:
                    item['note'] = result            # commento del libro dopo la freccia
        items.append(item)
    return items


def example_kind(t):
    if re.match(r'^[“"‘(]?[A-Z0-9]', t) and re.search(r'[.?!…][”’"\')]*$', t):
        return 'frase'
    return 'espressione'


def stable_id(prefix, *parts):
    return prefix + hashlib.sha256('\x1f'.join(map(str, parts)).encode('utf-8')).hexdigest()[:10]


def extract_examples(num, blocks):
    """Esempi e coppie del capitolo, con sezione, pagina, nota del libro e origine."""
    examples, fixes = [], []
    section = ''
    sources = []
    for b in blocks:
        if b['type'] == 'heading':
            title = to_plain(b['chars'])
            if title not in ('Practice', 'Answers', 'Quick Review'):
                section = title
            else:
                section = title
            continue
        if b['type'] in ('para', 'bullet'):
            sources.append((section, 'testo', b['chars']))
        elif b['type'] == 'table':
            for row in b['rows']:
                for cell in row:
                    if cell:
                        sources.append((section, 'tabella', cell))
    seen = set()
    for section, origin, chars in sources:
        if section in ('Practice', 'Answers'):
            continue                       # gli esercizi hanno una sezione dedicata
        items = segment_marks(clean_book_markup(chars), broken=bool(re.search(r'\w\*|\*\w', plain(chars))))
        for idx, it in enumerate(items):
            t = to_plain(it['chars'])
            if not t or len(t) > 300:
                continue
            ok = it['mark'] == '✓'
            key = (num, t, ok)
            ex = {'id': stable_id('ex-', num, t, ok), 't': t, 'ok': ok, 'ch': num,
                  'kind': example_kind(t), 'section': section, 'page': it['page'], 'origin': origin}
            if it['note']:
                ex['note'] = book_text(it['note'])
            if it.get('result'):
                ex['result'] = it['result']
            th = to_html(it['chars'])
            if '<' in th:
                ex['t_html'] = th
            if key not in seen:
                seen.add(key)
                examples.append(ex)
        for bad_items, good_items in _pair_runs(items):
            for b_it, g_it in zip(bad_items, good_items):
                t, good = to_plain(b_it['chars']), to_plain(g_it['chars'])
                if not t or not good:
                    continue
                fx = {'id': stable_id('fix-', num, t, good), 'bad': t, 'good': good, 'ch': num,
                      'section': section, 'page': b_it['page'], 'origin': origin}
                note = g_it['note'] or b_it['note']
                if note:
                    fx['note'] = book_text(note)
                if not any(f['bad'] == t and f['good'] == good for f in fixes):
                    fixes.append(fx)
    return examples, fixes


def complete_good(bad, good):
    """Il libro a volte corregge solo la parte finale: «✗ The dog wagged it’s tail. → ✓ its tail.»
    o la risposta di un dialogo: «✗ Do you like it? — Yes, I like. → ✓ Yes, I do.».
    Ricostruisce la frase corretta intera; restituisce None se la correzione è già completa."""
    if ' — ' in bad and ' — ' not in good:
        head, tail = bad.rsplit(' — ', 1)
        if good[:1].isupper() and tail[:1].isupper() and good.split()[0].lower() == tail.split()[0].lower():
            return head + ' — ' + good
    if good[:1].islower() and not bad[:1].islower():
        bw, gw = bad.split(), good.split()
        if len(gw) < len(bw) and gw[-1].lower() == bw[-1].lower():
            return ' '.join(bw[:len(bw) - len(gw)] + gw)
    return None


def _norm_key(t):
    return re.sub(r'[^\w]+', ' ', t.lower().replace('’', "'")).strip()


def finalize_items(examples, fixes):
    """Dopo l'estrazione di tutto il libro: frasi corrette complete, duplicati rimossi
    nello stesso capitolo (resta la prima occorrenza; le altre pagine finiscono in «also_pages»).
    Tra capitoli diversi i doppioni restano: ogni capitolo è un contesto a sé (il quiz li unisce)."""
    for f in fixes:
        full = complete_good(f['bad'], f['good'])
        if full:
            f['good_book'] = f['good']
            f['good'] = full
    out_f, seen = [], {}
    for f in fixes:
        k = (f['ch'], _norm_key(f['bad']), _norm_key(f['good']))
        if k in seen:
            seen[k].setdefault('also_pages', []).append(f['page'])
            continue
        seen[k] = f
        out_f.append(f)
    out_e, seen = [], {}
    for e in examples:
        k = (e['ch'], _norm_key(e['t']), e['ok'])
        if k in seen:
            if e['page'] != seen[k]['page']:
                seen[k].setdefault('also_pages', []).append(e['page'])
            continue
        seen[k] = e
        out_e.append(e)
    return out_e, out_f


def _pair_runs(items):
    """«✗ A → ✓ B» e anche «✗ A / ✗ B → ✓ C / ✓ D» (A→C, B→D). Conteggi diversi: nessuna coppia."""
    k, out = 0, []
    while k < len(items):
        if items[k]['mark'] != '✗':
            k += 1
            continue
        bad = [items[k]]
        while bad[-1]['gap'] == '/' and k + len(bad) < len(items) and items[k + len(bad)]['mark'] == '✗':
            bad.append(items[k + len(bad)])
        nxt = k + len(bad)
        if bad[-1]['gap'] == '→' and nxt < len(items) and items[nxt]['mark'] == '✓':
            good = [items[nxt]]
            while good[-1]['gap'] == '/' and nxt + len(good) < len(items) and items[nxt + len(good)]['mark'] == '✓':
                good.append(items[nxt + len(good)])
            if len(good) == len(bad) or len(bad) == 1:
                out.append((bad, good[:len(bad)]))
            k = nxt + len(good)
            continue
        k = nxt
    return out


def book_text(text):
    return ' '.join(text.replace('**', '').replace('~~', '').split())


# ---------------------------------------------------------------------------
# Esercizi: testo ricco, risposta/spiegazione, parola evidenziata, parti a) b) c)
# ---------------------------------------------------------------------------

def _section(lines):
    text, chars, offsets = '', [], []
    for idx, line in enumerate(lines):
        offsets.append(len(text))
        text += line.text + '\n'
        chars.extend(line.chars)
        chars.append(('\n', '', line.page))
    if len(text) != len(chars):
        raise ValueError('Allineamento testo/stile perso')
    return text, chars


def _numbered(text, start, end):
    chunk = text[start:end]
    matches = list(re.finditer(r'(?<!\w)(\d{1,2})\.\s+', chunk))
    prefix = (start, start + (matches[0].start() if matches else len(chunk)))
    items = []
    for i, m in enumerate(matches):
        e = start + (matches[i + 1].start() if i + 1 < len(matches) else len(chunk))
        items.append({'number': int(m[1]), 'start': start + m.end(), 'end': e})
    return prefix, items


def rich_groups(lines):
    text, chars = _section(lines)
    found = list(re.finditer(r'(?m)^([A-F])\.\s+', text))
    chunks = ([(m[1], m.end(), found[i + 1].start() if i + 1 < len(found) else len(text))
               for i, m in enumerate(found)] if found else [('', 0, len(text))])
    out = []
    for letter, s, e in chunks:
        prefix, items = _numbered(text, s, e)
        out.append({'group': letter, 'prefix': prefix, 'items': items})
    return text, chars, out


def rich_exercises(chapter, practice, answers):
    """{source_id: {'instr','q','answer'}} con caratteri ricchi, stesso abbinamento di parse_exercises."""
    qt, qc, qg = rich_groups(practice)
    at, ac, ag = rich_groups(answers)
    grouped = any(g['group'] for g in ag)
    flat = ag[0]['items'] if not grouped else []
    out, cumulative = {}, 0
    for pos, g in enumerate(qg):
        items = g['items']
        s, e = g['prefix']
        instr = rich_join(qc[s:e])
        if not items:
            m = re.search(r'\bRewrite:\s*', qt[s:e])
            instr = rich_join(qc[s:s + m.end()])
            items = [{'number': None, 'start': s + m.end(), 'end': e}]
            sg = ag[pos]
            sel = [{'number': None, 'start': sg['prefix'][0], 'end': sg['prefix'][1]}]
        elif grouped:
            sel = ag[pos]['items']
        else:
            sel = flat[cumulative:cumulative + len(items)]
        for item, ans in zip(items, sel):
            key = f"ch{chapter:02d}-{g['group'] or 'main'}-{item['number'] if item['number'] is not None else 'single'}"
            out[key] = {'instr': instr, 'q': rich_join(qc[item['start']:item['end']]),
                        'answer': rich_join(ac[ans['start']:ans['end']])}
        cumulative += len(items)
    return out


def split_answer(chars):
    """La chiave del libro usa tre formati:

    1. risposta in grassetto/corsivo + spiegazione in tondo (dopo «—» o fra parentesi);
    2. «✓ frase corretta» in corsivo + nota fra parentesi;
    3. frase intera in tondo, parola chiave evidenziata, nota fra parentesi.
    Restituisce (risposta, spiegazione, schema, parole_chiave).
    """
    chars = list(clean_book_markup(list(chars)))
    while chars and chars[0][0] in '✓ ':
        chars.pop(0)
    rs = runs(chars)
    if not rs:
        return '', '', 'vuota', []
    core, i = [], 0
    while i < len(rs):
        text, s = rs[i]
        if s.replace('s', ''):
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
        text = plain(chars)
        m = re.match(r'(.+?)(?:\s+—\s*(.*)|\s+(\(.*\))\s*(.*))?$', text, flags=re.S)
        answer = m[1].strip().rstrip('—').strip()
        rest = (m[2] or ((m[3] or '') + ' ' + (m[4] or ''))).strip()
        keys = [t.strip(' .,;:') for t, s in runs(chars[:len(m[1])]) if s and t.strip(' .,;:—')]
        scheme = 'frase_con_parola_chiave' if keys else 'testo_semplice'
    explanation = re.sub(r'^(?:—|–|-|:)\s*', '', rest).strip()
    if explanation.startswith('(') and explanation.endswith(')') and _paren_end(explanation, 0) == len(explanation):
        explanation = explanation[1:-1].strip()
    if scheme == 'risposta_e_spiegazione' and not explanation:
        scheme = 'solo_risposta'
    if scheme == 'risposta_e_spiegazione':
        answer, rest2 = _realign_core(book_text(answer), plain(chars))
        if rest2 is not None:
            explanation = re.sub(r'^(?:—|–|-|:)\s*', '', rest2).strip()
    if scheme in ('risposta_e_spiegazione', 'solo_risposta') and book_text(answer).strip() in ('—', '–', '-'):
        return ZERO_ANSWER, book_text(explanation), scheme, keys     # «— (no article)»: nessuna parola
    answer = book_text(answer).rstrip('—').strip()
    return answer, book_text(explanation), scheme, keys


def _realign_core(core, full):
    """L'enfasi del libro a volte è spostata di una parola («Who did» «you» call…; «No.» «That» is…).
    Riallinea la risposta alla frase che precede il primo « — », o la taglia al primo punto fermo."""
    full = ' '.join(full.split())
    head = full.split(' — ', 1)[0].strip()
    if ' — ' in full and re.search(r'[.?!”]$', head) and head != core and (head.startswith(core) or core.startswith(head)):
        return head, full[len(head):].strip()
    m = re.match(r'^(.+?[.?!])\s+(\S+(?:\s+\S+)?)$', core)
    if m and full.startswith(core):
        rest = full[len(m[1]):].strip()
        if rest[:1].isupper() and re.match(r'^\S+\s+[a-z]', rest):
            return m[1], rest
    return core, None


ZERO_ANSWER = '—'
# Risposte accettate quando la soluzione del libro è «nessuna parola» (articolo zero).
ZERO_VARIANTS = ['—', '-', '–', 'x', '0', '/', 'no article', 'nessun articolo', 'niente', 'nothing',
                 'zero', 'zero article', 'none']


FORMAT_INSTR = re.compile(r'\b(bold|underlined?)\b', re.I)


def derive_target(instr, q, a_chars, answer):
    """Parola evidenziata richiesta dalla consegna ma assente nel PDF: si ricava dalla soluzione."""
    if not FORMAT_INSTR.search(instr):
        return None
    if 'underline' in instr.lower():
        qw = q.rstrip('.?!').split()
        aw = answer.split('(')[0].strip().rstrip('.?!').split()
        i = 0
        while i < min(len(qw), len(aw)) and qw[i].lower() == aw[i].lower():
            i += 1
        j = 0
        while j < min(len(qw), len(aw)) - i and qw[-1 - j].lower() == aw[-1 - j].lower():
            j += 1
        removed = qw[i:len(qw) - j]
        added = [w.lower() for w in aw[i:len(aw) - j]]
        if removed and set(added) & {'it', 'them', 'him', 'her', 'us', 'me', 'you'}:
            removed = [w for w in removed if w.lower() not in added]
            return ' '.join(removed)
        return None
    for text, s in runs(a_chars):
        word = text.strip(' .,;:')
        if 'i' in s and word and re.search(r'(?<!\w)' + re.escape(word) + r'(?!\w)', q):
            return word
    return None


LABEL = re.compile(r'(?:(?<=\s)|^)([a-h])\)\s')


def split_parts(q_chars, a_chars):
    """Esercizi composti a) b) c): parti con la propria domanda e la propria soluzione."""
    qt, at = plain(q_chars), plain(a_chars)
    qm, am = list(LABEL.finditer(qt)), list(LABEL.finditer(at))
    ql, al = [m[1] for m in qm], [m[1] for m in am]
    if len(ql) < 2 or ql != al or ql != [chr(ord('a') + i) for i in range(len(ql))]:
        return None, None
    stem = to_plain(q_chars[:qm[0].start()])
    parts = []
    for k, (m, n) in enumerate(zip(qm, am)):
        qe = qm[k + 1].start() if k + 1 < len(qm) else len(qt)
        ae = am[k + 1].start() if k + 1 < len(am) else len(at)
        qc, ac = strip_chars(q_chars[m.end():qe]), strip_chars(a_chars[n.end():ae])
        core, expl, scheme, keys = split_answer(ac)
        part = {'label': m[1], 'q': to_plain(qc), 'answer': to_plain(ac),
                'answer_core': core, 'answer_explanation': expl}
        if '<' in to_html(qc):
            part['q_html'] = to_html(qc)
        parts.append(part)
    return stem, parts


def check_mode(e, core):
    if e.get('kind') == 'mcq':
        return 'scelta_multipla'
    if e.get('parts'):
        return 'parti'
    if core == ZERO_ANSWER:
        return 'automatico'
    words = len(core.split()) if core else 99
    if core and words <= 4 and not re.search(r'(?i)answers may vary|\bor\b|(?<!^)/(?!$)', core):
        return 'automatico'
    if core and words <= 8 and re.search(r'_+|\(\w[^()]*\)', e['source_q']):
        return 'automatico_con_varianti'
    return 'autovalutazione'


def enrich_exercise(e, rich):
    """Aggiunge campi ricchi senza cambiare i campi già approvati (q, answer, instr...)."""
    if plain(rich['q']) and ' '.join(plain(rich['q']).split()) != e['source_q']:
        raise ValueError('Testo ricco non allineato: ' + e['source_id'])
    if ' '.join(plain(rich['answer']).split()) != e['answer']:
        raise ValueError('Soluzione ricca non allineata: ' + e['source_id'])
    core, expl, scheme, keys = split_answer(rich['answer'])
    gaps = len(re.findall(r'_{1,}', e['source_q']))
    styled = [t for t, st in runs(clean_book_markup(list(rich['answer']))) if st and t.strip()]
    full = ' '.join(plain(rich['answer']).split())
    if gaps >= 2 and len(styled) >= 2 and ' (' in full and core == styled[0].strip():
        # «at 9 o’clock on Monday morning. (clock time → at…)»: risposta = frase prima della nota
        head, note = full.split(' (', 1)
        core, expl = book_text(head), book_text('(' + note).strip()
        if expl.startswith('(') and expl.endswith(')'):
            expl = expl[1:-1].strip()
    e['instr_html'] = to_html(rich['instr'])
    e['q_html'] = to_html(rich['q'])
    e['answer_html'] = to_html(rich['answer'])
    e['answer_core'] = core
    e['answer_explanation'] = expl
    e['answer_scheme'] = scheme
    if keys:
        e['answer_keywords'] = keys
    target = derive_target(e['instr'], e['source_q'], rich['answer'], core)
    if target:
        e['target'] = target
    if e['kind'] == 'compound':
        stem, parts = split_parts(rich['q'], rich['answer'])
        if parts:
            e['stem'] = stem
            e['parts'] = parts
    if core == ZERO_ANSWER:
        e['answer_variants'] = list(ZERO_VARIANTS)
    e['check_mode'] = check_mode(e, core)
    return e
