"""Testi HTML (Telegram) per quiz ed esercizi del libro — funzioni pure, senza rete.

Regole:
- il contenuto del libro si mostra così com'è (con grassetto/corsivo del PDF), mai corretto;
- dopo ogni risposta: spiegazione del libro, pagina/sezione, poi la breve nota in italiano
  (solo nell'interfaccia italiana: la nota è scritta in italiano);
- ogni testo libero dello studente o del libro passa da escape().
"""
from html import escape as _escape
import re

from tutor.book_quiz import note_for
from tutor.texts import progress_bar, tr

LETTERS = 'ABCDEF'
TAG = re.compile(r'<(/?)(b|i|s|u|code|pre)>')


def clean_for_display(text):
    """Pulisce i glitch di formattazione ereditati dal PDF/parsing:
    separatori di tabella '| | | |' e spazi doppi."""
    text = re.sub(r"\s*\|+\s*", " ", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def esc(text):
    return _escape(text or '', quote=False)


def tidy_html(html):
    """Telegram rifiuta tag non bilanciati; il libro a volte annida lo stesso stile (<b><b>…</b></b>).
    Toglie i tag ridondanti/non bilanciati e ripara l'annidamento, senza toccare il testo."""
    html = html or ''
    out, stack, pos = [], [], 0          # stack: [emesso?, nome]
    for m in TAG.finditer(html):
        out.append(html[pos:m.start()])
        pos = m.end()
        closing, name = m[1] == '/', m[2]
        if not closing:
            emitted = not any(e and n == name for e, n in stack)
            if emitted:
                out.append(f'<{name}>')
            stack.append([emitted, name])
            continue
        idx = next((k for k in range(len(stack) - 1, -1, -1) if stack[k][1] == name), None)
        if idx is None:
            continue                      # chiusura senza apertura: si scarta
        emitted = stack[idx][0]
        del stack[idx]
        if not emitted:
            continue
        inner = stack[idx:]
        out.extend(f'</{n}>' for e, n in reversed(inner) if e)
        out.append(f'</{name}>')
        for entry in inner:
            if entry[1] == name or entry[0]:
                entry[0] = True
                out.append(f'<{entry[1]}>')
    out.append(html[pos:])
    out.extend(f'</{n}>' for e, n in reversed(stack) if e)
    return ''.join(out)


def chapter_title(kb, ch):
    return kb['_chapters'][ch]['title']


def source_line(kb, lang, item, kind):
    ch = item['ch']
    parts = [tr(lang, 'src_chapter', n=ch, t=esc(chapter_title(kb, ch)))]
    if kind == 'exercise':
        pages = sorted({item['pdf_page'], item['answer_pdf_page']})
        label = f"{esc(item['group'])}-{item['source_number']}" if item.get('group') else str(item['source_number'])
        parts.append(tr(lang, 'src_exercise', n=label))
        parts.append(tr(lang, 'src_pages', p='–'.join(map(str, pages))))
    elif kind == 'reviewed':
        pages = sorted({p for c in item['source']['citations'] for p in c['pages']})
        parts.append(tr(lang, 'src_pages', p=', '.join(map(str, pages))))
    else:
        if item.get('section'):
            parts.append(esc(item['section']))
        pages = [item['page']] + list(item.get('also_pages') or [])
        parts.append(tr(lang, 'src_pages', p=', '.join(map(str, pages))))
    return '<i>📖 ' + ' · '.join(parts) + '</i>'


def it_note(kb, lang, item, kind):
    if lang != 'it':
        return ''
    note = note_for(kb, item, kind)
    return f"\n<blockquote expandable>🇮🇹 <i>{esc(note)}</i></blockquote>" if note else ''


def quote(html):
    """Contenuto del libro in un riquadro citazione (Telegram <blockquote>)."""
    html = (html or '').strip()
    return f"<blockquote>{html}</blockquote>" if html else ''


def example_html(e):
    body = tidy_html(e.get('t_html') or esc(e['t']))
    if e.get('result'):
        body += ' → ' + esc(e['result'])
    return body


# --------------------------------------------------------------------------- quiz
def quiz_head(lang, i, n):
    return tr(lang, 'quiz_head', i=i, n=n, bar=progress_bar(i, n))


def quiz_question_parts(kb, lang, ref_item, item):
    """(consegna, riga in corsivo, testo nel riquadro) della domanda — senza intestazione né opzioni.
    Usata dalla chat (quiz_question) e dalla mini app, così il contenuto è lo stesso."""
    kind = ref_item['type']
    if kind == 'tf':
        where = esc(item.get('section') or chapter_title(kb, item['ch']))
        return tr(lang, 'quiz_tf'), tr(lang, 'src_chapter', n=item['ch'], t=where), example_html(item)
    if kind == 'fix':
        return tr(lang, 'quiz_which'), '', ''
    if 'source' in item:                      # domanda ricostruita dal libro (fase 3)
        return tr(lang, 'quiz_fill'), esc(item.get('context', {}).get(lang, '')), esc(item['q'])
    instr = tidy_html(item.get('instr_html') or esc(item.get('instr')))
    return tr(lang, 'quiz_fill'), instr, tidy_html(item.get('q_html') or esc(item['q']))


def quiz_question(kb, lang, ref_item, item, i, n, fix_opts=None):
    kind = ref_item['type']
    head = quiz_head(lang, i, n)
    ask, sub, text = quiz_question_parts(kb, lang, ref_item, item)
    if kind == 'tf':
        return f"{head}\n{ask}\n<i>{sub}</i>\n\n{quote(text)}"
    if kind == 'fix':
        a, b = fix_opts
        return f"{head}\n{ask}\n\n<b>A)</b> {esc(a)}\n<b>B)</b> {esc(b)}"
    opts = '\n'.join(f"<b>{LETTERS[j]})</b> {esc(o)}" for j, o in enumerate(item['options']))
    sub = f"\n<i>{sub}</i>" if sub else ''
    return f"{head}\n{ask}{sub}\n\n{quote(text)}\n{opts}"


def feedback_head(lang, good, score, total, right_key='quiz_right', wrong_key='quiz_wrong'):
    verdict = tr(lang, right_key if good else wrong_key)
    return f"<b>{verdict}</b>  ·  {tr(lang, 'score', c=score, t=total)}"


def quiz_feedback(kb, lang, ref_item, item, good, score, total, given=None):
    """Esito, poi riquadro con la risposta/spiegazione del libro, fonte e nota italiana."""
    head = feedback_head(lang, good, score, total)
    return f"{head}\n\n{quiz_feedback_body(kb, lang, ref_item, item)}"


def quiz_feedback_body(kb, lang, ref_item, item):
    """Risposta/spiegazione del libro, fonte e nota italiana (uguale per chat e mini app)."""
    kind = ref_item['type']
    if kind == 'tf':
        verdict = tr(lang, 'tf_is_ok' if item['ok'] else 'tf_is_bad')
        body = f"{verdict}\n{'✓' if item['ok'] else '✗'} {example_html(item)}"
        if item.get('note'):
            body += '\n\n' + tr(lang, 'book_note', a=esc(item['note']))
        return f"{quote(body)}\n{source_line(kb, lang, item, 'item')}{it_note(kb, lang, item, 'item')}"
    if kind == 'fix':
        body = tr(lang, 'quiz_fix', good=esc(item['good']), bad=esc(item['bad']))
        if item.get('good_book'):
            body += '\n' + tr(lang, 'fix_book_form', a=esc(item['good_book']))
        if item.get('note'):
            body += '\n\n' + tr(lang, 'book_note', a=esc(item['note']))
        return f"{quote(body)}\n{source_line(kb, lang, item, 'item')}{it_note(kb, lang, item, 'item')}"
    if 'source' in item:
        body = tr(lang, 'book_answer', a=f"<b>{esc(item['options'][item['answer_idx']])}</b>")
        body += '\n\n' + esc(item['explanation'][lang])
        return f"{quote(body)}\n{source_line(kb, lang, item, 'reviewed')}"
    return solution_html(kb, lang, item)


def quiz_snippet(kb, ref_item, item, width=70):
    """Riga breve per il riepilogo finale: la frase/domanda sbagliata, troncata."""
    if ref_item['type'] == 'tf':
        text = item.get('t') or ''
    elif ref_item['type'] == 'fix':
        text = item.get('bad') or ''
    else:
        text = item.get('q') or ''
    text = ' '.join(text.split())
    if len(text) > width:
        text = text[:width - 1].rstrip() + '…'
    return esc(text)


# --------------------------------------------------------------------------- esercizi
def exercise_parts(kb, lang, item):
    """(consegna, testo) dell'esercizio, con il bersaglio sottolineato: uguale per chat e mini app."""
    from tutor.content import target_span
    instr = tidy_html(item.get('instr_html') or esc(item.get('instr')))
    if item.get('group'):
        instr = f"{esc(item['group'])}. {instr}" if instr else esc(item['group'])
    q = tidy_html(item.get('q_html') or esc(item['q']))
    if item.get('target'):
        a, b = target_span(item['q'], item['target'])
        q = esc(item['q'][:a]) + '<b><u>' + esc(item['q'][a:b]) + '</u></b>' + esc(item['q'][b:])
        key = 'ex_target_pronoun' if 'underlined' in item['instr'] else 'ex_target_pos'
        instr = tr(lang, key, target=f"<b>{esc(item['target'])}</b>")
    return instr, q


def exercise_prompt(kb, lang, item, i, n):
    instr, q = exercise_parts(kb, lang, item)
    from tutor.texts import chapter_title as local_title
    head = tr(lang, 'ex_head', i=i, n=n, bar=progress_bar(i, n), ch=item['ch'],
              title=esc(local_title(kb, item['ch'], lang)))
    how = tr(lang, 'ex_how_' + item['check_mode'].replace('automatico_con_varianti', 'automatico'))
    body = quote(q)
    if item['check_mode'] == 'scelta_multipla':
        body += '\n' + '\n'.join(f"<b>{LETTERS[j]})</b> {esc(o)}" for j, o in enumerate(item['options']))
    instr = f"{instr}\n\n" if instr else ''
    return f"{head}\n\n{instr}{body}\n<i>{how}</i>"


def solution_html(kb, lang, item):
    """Soluzione del libro (con la sua spiegazione), fonte e nota italiana."""
    answer = tidy_html(item.get('answer_html') or esc(item['answer']))
    return (f"{tr(lang, 'book_solution')}\n{quote(answer)}\n"
            f"{source_line(kb, lang, item, 'exercise')}{it_note(kb, lang, item, 'exercise')}")


def parts_report(lang, results):
    lines = []
    for label, typed, ok in results:
        mark = '✓' if ok else '✗'
        lines.append(f"{mark} {esc(label)}) {esc(typed) if typed else '—'}")
    return '\n'.join(lines)
