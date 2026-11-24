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
from tutor.texts import tr

LETTERS = 'ABCDEF'
TAG = re.compile(r'<(/?)(b|i|s|u|code|pre)>')


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
    return '📖 ' + ' · '.join(parts)


def it_note(kb, lang, item, kind):
    if lang != 'it':
        return ''
    note = note_for(kb, item, kind)
    return f"\n\n🇮🇹 <i>{esc(note)}</i>" if note else ''


def example_html(e):
    body = tidy_html(e.get('t_html') or esc(e['t']))
    if e.get('result'):
        body += ' → ' + esc(e['result'])
    return body


# --------------------------------------------------------------------------- quiz
def quiz_question(kb, lang, ref_item, item, i, n, fix_opts=None):
    kind = ref_item['type']
    if kind == 'tf':
        where = esc(item.get('section') or chapter_title(kb, item['ch']))
        return (f"{tr(lang, 'quiz_tf', i=i, n=n)}\n<i>{tr(lang, 'src_chapter', n=item['ch'], t=where)}</i>"
                f"\n\n«{example_html(item)}»")
    if kind == 'fix':
        a, b = fix_opts
        return f"{tr(lang, 'quiz_which', i=i, n=n)}\n\nA) {esc(a)}\nB) {esc(b)}"
    opts = '\n'.join(f"{LETTERS[j]}) {esc(o)}" for j, o in enumerate(item['options']))
    if 'source' in item:                      # domanda ricostruita dal libro (fase 3)
        ctx = item.get('context', {}).get(lang, '')
        return (f"{tr(lang, 'quiz_fill', i=i, n=n)}\n\n{esc(ctx)}\n\n«{esc(item['q'])}»\n\n{opts}").replace('\n\n\n\n', '\n\n')
    instr = tidy_html(item.get('instr_html') or esc(item.get('instr')))
    q = tidy_html(item.get('q_html') or esc(item['q']))
    head = tr(lang, 'quiz_fill', i=i, n=n)
    return f"{head}\n<i>{instr}</i>\n\n{q}\n\n{opts}" if instr else f"{head}\n\n{q}\n\n{opts}"


def quiz_feedback(kb, lang, ref_item, item, good, score, total, given=None):
    head = f"{tr(lang, 'quiz_right' if good else 'quiz_wrong')} {tr(lang, 'score', c=score, t=total)}"
    kind = ref_item['type']
    if kind == 'tf':
        verdict = tr(lang, 'tf_is_ok' if item['ok'] else 'tf_is_bad')
        body = f"{verdict}\n{'✓' if item['ok'] else '✗'} {example_html(item)}"
        if item.get('note'):
            body += '\n' + tr(lang, 'book_note', a=esc(item['note']))
        return f"{head}\n\n{body}\n\n{source_line(kb, lang, item, 'item')}{it_note(kb, lang, item, 'item')}"
    if kind == 'fix':
        body = tr(lang, 'quiz_fix', good=esc(item['good']), bad=esc(item['bad']))
        if item.get('good_book'):
            body += '\n' + tr(lang, 'fix_book_form', a=esc(item['good_book']))
        if item.get('note'):
            body += '\n' + tr(lang, 'book_note', a=esc(item['note']))
        return f"{head}\n\n{body}\n\n{source_line(kb, lang, item, 'item')}{it_note(kb, lang, item, 'item')}"
    if 'source' in item:
        body = tr(lang, 'book_answer', a=esc(item['options'][item['answer_idx']]))
        body += '\n\n' + esc(item['explanation'][lang])
        return f"{head}\n\n{body}\n\n{source_line(kb, lang, item, 'reviewed')}"
    return f"{head}\n\n{solution_html(kb, lang, item)}"


# --------------------------------------------------------------------------- esercizi
def exercise_prompt(kb, lang, item, i, n):
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
    head = tr(lang, 'ex_head', i=i, n=n, ch=item['ch'], title=esc(chapter_title(kb, item['ch'])))
    how = tr(lang, 'ex_how_' + item['check_mode'].replace('automatico_con_varianti', 'automatico'))
    if item['check_mode'] == 'scelta_multipla':
        q += '\n\n' + '\n'.join(f"{LETTERS[j]}) {esc(o)}" for j, o in enumerate(item['options']))
    return f"{head}\n\n{instr}\n\n{q}\n\n<i>{how}</i>" if instr else f"{head}\n\n{q}\n\n<i>{how}</i>"


def solution_html(kb, lang, item):
    """Soluzione del libro (con la sua spiegazione), fonte e nota italiana."""
    body = tr(lang, 'book_solution', a=tidy_html(item.get('answer_html') or esc(item['answer'])))
    return f"{body}\n\n{source_line(kb, lang, item, 'exercise')}{it_note(kb, lang, item, 'exercise')}"


def parts_report(lang, results):
    lines = []
    for label, typed, ok in results:
        mark = '✓' if ok else '✗'
        lines.append(f"{mark} {esc(label)}) {esc(typed) if typed else '—'}")
    return '\n'.join(lines)
