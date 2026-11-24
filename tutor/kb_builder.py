"""Build deterministica e validata per lo specifico libro A1-C1.

Versione 3 (fase 4.2): teoria, esempi ✓/✗, coppie ✗ → ✓ e soluzioni degli esercizi
sono estratti dal PDF conservando grassetto/corsivo/barrato (tutor.pdf_rich,
tutor.book_parser). Gli esercizi restano vincolati alle impronte già approvate;
ogni nuovo contenuto è vincolato al profilo v2, rigenerato solo dopo i controlli.
"""
import copy
from collections import Counter
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from tutor.pdf_source import extract_pages, join_text, paragraphs, partition_book, practice_sections


class BuildError(ValueError):
    pass


def digest(data):
    if not isinstance(data, bytes):
        data = data.encode('utf-8')
    return hashlib.sha256(data).hexdigest()


def numbered_items(text):
    """Non ignora numeri saltati/ripetuti: un disallineamento deve bloccare la build."""
    matches = list(re.finditer(r'(?<!\w)(\d{1,2})\.\s+', text))
    numbers = [int(m[1]) for m in matches]
    if numbers and (numbers[0] < 1 or numbers != list(range(numbers[0], numbers[0] + len(numbers)))):
        raise BuildError(f'Numerazione non consecutiva: {numbers}')
    prefix = text[:matches[0].start()] if matches else text
    items = []
    for i, m in enumerate(matches):
        end = matches[i+1].start() if i+1 < len(matches) else len(text)
        body = join_text(text[m.end():end].splitlines()).strip()
        if not body:
            raise BuildError('Item numerato vuoto')
        items.append({'number': int(m[1]), 'text': body, 'offset': m.start()})
    return join_text(prefix.splitlines()), items


def group_sections(lines):
    text, offsets = '', []
    for line in lines:
        offsets.append((len(text), line.page))
        text += line.text + '\n'
    groups = list(re.finditer(r'(?m)^([A-F])\.\s+', text))
    if groups and text[:groups[0].start()].strip():
        raise BuildError('Testo inatteso prima del primo gruppo')
    chunks = [(m[1], m.end(), groups[i+1].start() if i+1 < len(groups) else len(text))
              for i,m in enumerate(groups)] if groups else [('', 0, len(text))]
    names = [c[0] for c in chunks]
    if len(set(names)) != len(names):
        raise BuildError('Gruppi duplicati')
    result = []
    for letter,start,end in chunks:
        prefix,items = numbered_items(text[start:end])
        for item in items:
            pos = start + item['offset']
            item['pdf_page'] = next(page for offset,page in reversed(offsets) if offset <= pos)
        result.append({'group':letter,'prefix':prefix,'items':items,
                       'pdf_page':next(page for offset,page in reversed(offsets) if offset <= start)})
    return result


def parse_exercises(chapter, practice, answers):
    questions = group_sections(practice)
    solutions = group_sections(answers)
    grouped_answers = any(g['group'] for g in solutions)
    if grouped_answers and [g['group'] for g in questions] != [g['group'] for g in solutions]:
        raise BuildError(f'Capitolo {chapter}: gruppi domanda/risposta diversi')
    if not grouped_answers and (len(solutions) != 1 or solutions[0]['prefix']):
        raise BuildError('Soluzioni senza struttura univoca o con prefisso inatteso')
    out, cumulative = [], 0
    flat_answers = solutions[0]['items'] if not grouped_answers else []
    for position, group in enumerate(questions):
        instr = group['prefix']
        items = group['items']
        singleton = not items
        if singleton:
            match = re.fullmatch(r'(.*?\bRewrite:)\s*(.+)', instr, flags=re.S)
            if not match or not grouped_answers:
                raise BuildError(f"Capitolo {chapter}: gruppo {group['group']} non numerato non riconosciuto")
            instr = match[1]
            items = [{'number':None,'text':match[2],'pdf_page':group['pdf_page']}]
        if grouped_answers:
            solution_group = solutions[position]
            if singleton:
                if solution_group['items'] or not solution_group['prefix']:
                    raise BuildError('Soluzione singola assente o ambigua')
                selected = [{'number':None,'text':solution_group['prefix'],
                             'pdf_page':solution_group['pdf_page']}]
            else:
                selected = solution_group['items']
                # Il prefisso puo contenere una nota esplicita, mai una risposta nascosta.
                if solution_group['prefix'] and not re.fullmatch(r'\(answers may vary slightly\)', solution_group['prefix']):
                    raise BuildError('Prefisso di soluzione inatteso: ' + solution_group['prefix'])
        else:
            selected = flat_answers[cumulative:cumulative+len(items)]
        if len(selected) != len(items):
            raise BuildError(f"Capitolo {chapter}, gruppo {group['group']}: conteggi domanda/risposta diversi")
        if not singleton:
            actual = [x['number'] for x in selected]
            local = [x['number'] for x in items]
            global_numbers = list(range(cumulative+1, cumulative+len(items)+1))
            if actual != local and actual != global_numbers:
                raise BuildError(f'Capitolo {chapter}: numeri delle risposte incompatibili {actual} / {local}')
        for item, answer in zip(items, selected):
            group_key = group['group'] or 'main'
            number_key = str(item['number']) if item['number'] is not None else 'single'
            source_id = f'ch{chapter:02d}-{group_key}-{number_key}'
            out.append({'id':source_id,'source_id':source_id,'ch':chapter,'group':group['group'],
                        'source_number':item['number'],'answer_number':answer['number'],
                        'instr':instr,'q':item['text'],'source_q':item['text'],
                        'answer':answer['text'],'options':None,'answer_idx':None,
                        'kind':'compound' if re.search(r'\ba\)',item['text']) and re.search(r'\bb\)',item['text']) else 'open',
                        'pdf_page':item['pdf_page'],'answer_pdf_page':answer['pdf_page']})
        cumulative += len(items)
    if not grouped_answers and cumulative != len(flat_answers):
        raise BuildError(f'Capitolo {chapter}: soluzioni non utilizzate')
    return out


def option_question(question, options):
    """Conversione SOLO di un insieme di opzioni approvato, mai dedotto da uno slash."""
    matching = [m for m in re.finditer(r'\(([^()]+)\)', question)
                if [s.strip() for s in m[1].split('/')] == options]
    if len(matching) != 1:
        raise BuildError('Opzioni approvate assenti/ambigue nel PDF')
    m = matching[0]
    replacement = '' if re.search(r'_{2,}',question) else '_____'
    q = question[:m.start()] + replacement + question[m.end():]
    q = re.sub(r'_{2,}', '_____', q)
    return ' '.join(q.split())


def apply_mcq_policy(exercises, policy):
    by_id = {e['source_id']:e for e in exercises}
    for source_id, approved in policy.items():
        if source_id not in by_id:
            raise BuildError('MCQ approvata non trovata: ' + source_id)
        e = by_id[source_id]
        if e['kind'] == 'compound':
            raise BuildError('Una domanda composta non puo diventare una singola MCQ')
        options = approved['options']
        if (not 2 <= len(options) <= 6 or len(set(options)) != len(options)
                or approved['correct'] not in options):
            raise BuildError('Politica MCQ non valida: ' + source_id)
        # Le prime MCQ del capitolo 3 sono classificazioni con opzioni nella consegna.
        if approved.get('from_instruction'):
            q = e['q']
            if not all(option in e['instr'] for option in options):
                raise BuildError('Opzioni non presenti nella consegna')
        else:
            q = option_question(e['source_q'],options)
        e.update(q=q,options=options,answer_idx=options.index(approved['correct']),kind='mcq')


def extract_reference_verbs(lines):
    """Riunisce celle su piu righe nella tabella alfabetica a quattro colonne."""
    active = False
    starts = None
    current = None
    verbs, provenance = {}, {}
    def flush():
        nonlocal current
        if current is None:
            return
        base_parts, forms, page = current
        base = join_text(base_parts)
        if not re.fullmatch(r"[a-z][a-z'-]*",base):
            raise BuildError('Forma base incompleta: ' + base)
        forms = [join_text(parts) for parts in forms]
        if base in verbs:
            raise BuildError('Verbo duplicato nella tabella: ' + base)
        for form in forms:
            if not re.fullmatch(r"[a-z'-]+(?:\s*/\s*[a-z'-]+)*",form):
                raise BuildError(f'Cella verbale incompleta: {base} / {form}')
        verbs[base] = forms
        provenance[base] = page
        current = None
    for line in lines:
        if 'Comprehensive Reference Table (alphabetical)' in line.text:
            active = True
            continue
        if not active:
            continue
        if line.text == 'A note on tricky pairs':
            flush()
            break
        header = {text.strip(): x for x,text in line.cells}
        if all(s in header for s in ['Base form','Past simple','Past participle','Notes / meaning']):
            flush()
            starts = [header[s] for s in ['Base form','Past simple','Past participle','Notes / meaning']]
            continue
        if starts is None:
            continue
        cells = ['', '', '', '']
        for x,text in line.cells:
            column = max((i for i,start in enumerate(starts) if x >= start-1), default=0)
            cells[column] += text
        cells = [c.strip() for c in cells]
        if cells[0]:
            if not re.fullmatch(r"[a-z][a-z'-]*[\u2010\u00ad]?",cells[0]):
                raise BuildError('Riga verbale inattesa: ' + line.text)
            if current and current[0][-1].endswith(('\u2010','\u00ad')):
                current[0].append(cells[0])
            else:
                flush()
                current = ([cells[0]], [[],[]], line.page)
        if current:
            for col in (1,2):
                if cells[col]:
                    current[1][col-1].append(cells[col])
        elif any(cells[1:3]):
            raise BuildError('Continuazione verbale senza riga iniziale')
    flush()
    if not active or not verbs:
        raise BuildError('Tabella alfabetica dei verbi non trovata')
    return verbs, provenance


def extract_glossary(lines):
    entries, current = [], None
    for line in lines:
        text = line.text
        if re.fullmatch(r'[A-Z]',text):
            continue
        m = re.match(r'^([A-Z][A-Za-z’\' ()/-]{1,45}) — (.*)$',text)
        if m:
            if current:
                current['def'] = join_text(current['def'])
                entries.append(current)
            current = {'term':m[1],'def':[m[2]],'pdf_page':line.page}
        elif current:
            current['def'].append(text)
    if current:
        current['def'] = join_text(current['def'])
        entries.append(current)
    return entries


def counts(kb):
    return {'chapters':len(kb['chapters']),
            'examples_ok':sum(e['ok'] for e in kb['examples']),
            'examples_bad':sum(not e['ok'] for e in kb['examples']),
            'fixes':len(kb['fixes']),'exercises':len(kb['exercises']),
            'exercises_mcq':sum(bool(e['options']) for e in kb['exercises']),
            'verbs':len(kb['verbs']),'glossary':len(kb['glossary'])}


def exercise_fingerprint(e):
    fields = ['ch','group','source_number','answer_number','source_q','answer','instr','pdf_page','answer_pdf_page']
    return digest(json.dumps({key:e[key] for key in fields},ensure_ascii=False,sort_keys=True))


SCHEMA_VERSION = 3
BUILDER_VERSION = 3
ALLOWED_TAGS = re.compile(r'</?(?:b|i|s|u|code|pre)>')
RESIDUE = re.compile(r'\*\*|~~|(?<!\w)\*|\*(?!\w)')
SYMBOLS = re.compile(r'[✓✗→|]')
EXAMPLE_KEYS = {'id', 't', 'ok', 'ch', 'kind', 'section', 'page', 'origin'}
FIX_KEYS = {'id', 'bad', 'good', 'ch', 'section', 'page', 'origin'}
RICH_EXERCISE_KEYS = {'instr_html', 'q_html', 'answer_html', 'answer_core', 'answer_explanation',
                      'answer_scheme', 'check_mode'}


def items_digest(kb):
    return digest(json.dumps({s: kb[s] for s in ['examples', 'fixes']}, ensure_ascii=False, sort_keys=True))


def blocks_digest(chapter):
    return digest(json.dumps(chapter['blocks'], ensure_ascii=False, sort_keys=True))


def extract_book(pdf):
    """Estrazione ricca (stili + tabelle). Le tabelle si cercano solo nelle pagine con righe
    in corpo piccolo: nel libro ogni tabella ha intestazioni a 8.7pt (censimento fase 4.2)."""
    from tutor.pdf_rich import extract_rich, extract_tables
    pages, backend = extract_rich(pdf)
    small = [i + 1 for i, p in enumerate(pages) if any(l.size <= 9.5 for l in p)]
    return pages, extract_tables(pdf, small), backend


def build_candidate(pdf, baseline, profile, chapters_spec, parts, synonyms, extracted=None):
    """KB v3 dal PDF: teoria con formattazione, esempi/coppie e soluzioni ricche estratti dal libro.

    `extracted` permette di riusare un'estrazione già fatta (pagine, tabelle, backend)."""
    from tutor.book_parser import (chapter_blocks, enrich_exercise, extract_examples, finalize_items,
                                   render_blocks, rich_exercises)
    pdf = Path(pdf)
    if profile.get('schema_version') != 2:
        raise BuildError('Versione del profilo non supportata')
    if digest(pdf.read_bytes()) != profile['pdf_sha256']:
        raise BuildError('PDF diverso da quello approvato nel profilo del libro')
    pages, tables, backend = extracted if extracted is not None else extract_book(pdf)
    if backend['version'] != profile['extractor_version']:
        raise BuildError('Versione estrattore diversa da quella approvata')
    if len(pages) != profile['pdf_pages']:
        raise BuildError('Numero di pagine PDF inatteso')
    sections, appendix_a, appendix_b = partition_book(pages)
    chapters, exercises, examples, fixes, rich = [], [], [], [], {}
    for num, title, part in chapters_spec:
        lines = sections[num]
        practice, answers = practice_sections(lines)
        items = parse_exercises(num, practice, answers)
        rich.update(rich_exercises(num, practice, answers))
        blocks = chapter_blocks(lines, tables)
        rendered = render_blocks(blocks)
        head = f'Chapter {num} — {title}'
        chapters.append({'num': num, 'title': title, 'part': parts[part],
                         'text': head + '\n\n' + '\n\n'.join(r['text'] for r in rendered),
                         'blocks': rendered,
                         'pdf_page_start': lines[0].page, 'pdf_page_end': lines[-1].page})
        exercises.extend(items)
        ex, fx = extract_examples(num, blocks)
        examples.extend(ex)
        fixes.extend(fx)
    examples, fixes = finalize_items(examples, fixes)
    apply_mcq_policy(exercises, profile['mcq_allowlist'])
    for e in exercises:                    # dopo la politica MCQ: il tipo è definitivo
        if e['id'] not in rich:
            raise BuildError('Esercizio senza testo ricco: ' + e['id'])
        try:
            enrich_exercise(e, rich[e['id']])
        except ValueError as exc:
            raise BuildError(str(exc)) from exc
    verbs, verb_pages = extract_reference_verbs(appendix_a)
    candidate = {'meta': {'schema_version': SCHEMA_VERSION, 'title': baseline['meta']['title'],
                          'source': pdf.name, 'built': str(date.today()),
                          'source_pdf_sha256': profile['pdf_sha256'], 'source_pdf_pages': len(pages),
                          'extractor': backend, 'builder_version': BUILDER_VERSION,
                          'formatting': 'Telegram HTML subset: b, i, s, u, code, pre.',
                          'book_items_policy': 'Examples, fixes, exercises and solutions extracted from the PDF '
                                               'with formatting; damaged items repaired from the PDF, not excluded.'},
                 'chapters': chapters, 'exercises': exercises, 'verbs': verbs, 'verb_pages': verb_pages,
                 'glossary': extract_glossary(appendix_b), 'synonyms': copy.deepcopy(synonyms),
                 'examples': examples, 'fixes': fixes}
    candidate['meta']['counts'] = counts(candidate)
    return candidate


def _html_ok(value):
    """Solo i tag ammessi, bilanciati e annidati correttamente."""
    stack = []
    for m in re.finditer(r'<(/?)([a-z]+)>|<', value):
        if m[0] == '<' or not ALLOWED_TAGS.fullmatch(m[0]):
            return False
        if m[1]:
            if not stack or stack.pop() != m[2]:
                return False
        else:
            stack.append(m[2])
    return not stack


def content_errors(kb):
    """Controlli che non dipendono dal profilo: forma e pulizia di ciò che il bot mostrerà."""
    errors = []
    chapters = {c['num']: c for c in kb['chapters']}
    for c in kb['chapters']:
        if not c.get('blocks') or any(set(b) != {'type', 'page', 'text', 'html'} for b in c['blocks']):
            errors.append(f'Blocchi teoria mancanti/malformati: capitolo {c["num"]}')
            continue
        for b in c['blocks']:
            if not _html_ok(b['html']) or RESIDUE.search(b['text']):
                errors.append(f'Blocco teoria non pulito: capitolo {c["num"]} p.{b["page"]}')
            if not c['pdf_page_start'] <= b['page'] <= c['pdf_page_end']:
                errors.append(f'Blocco teoria fuori dal capitolo: {c["num"]}')
    ids = set()
    for section, keys, fields in (('examples', EXAMPLE_KEYS, ('t',)), ('fixes', FIX_KEYS, ('bad', 'good'))):
        for e in kb[section]:
            name = f'{section} {e.get("id")}'
            if not keys <= set(e):
                errors.append('Campi mancanti: ' + name)
                continue
            if e['id'] in ids:
                errors.append('ID duplicato: ' + name)
            ids.add(e['id'])
            c = chapters.get(e['ch'])
            if not c or not c['pdf_page_start'] <= e['page'] <= c['pdf_page_end']:
                errors.append('Pagina/capitolo non validi: ' + name)
            for f in fields:
                t = e[f]
                if not isinstance(t, str) or not t.strip() or t != ' '.join(t.split()):
                    errors.append(f'Testo vuoto o con spazi anomali: {name}')
                elif RESIDUE.search(t) or SYMBOLS.search(t):
                    errors.append(f'Residui di markup/simboli: {name}: {t[:60]}')
                elif t.count('(') != t.count(')'):
                    errors.append(f'Parentesi sbilanciate: {name}: {t[:60]}')
            if 't_html' in e and (not _html_ok(e['t_html']) or
                                  re.sub(r'<[^>]+>', '', e['t_html']).replace('&lt;', '<').replace('&gt;', '>')
                                  .replace('&amp;', '&') != e['t']):
                errors.append('HTML non coerente col testo: ' + name)
        if section == 'fixes':
            for e in kb['fixes']:
                if e.get('bad') == e.get('good'):
                    errors.append('Coppia senza correzione: ' + str(e.get('id')))
    for e in kb['exercises']:
        missing = RICH_EXERCISE_KEYS - set(e)
        if missing:
            errors.append(f'Campi ricchi mancanti: {e["source_id"]} {sorted(missing)}')
            continue
        if not all(_html_ok(e[k]) for k in ('instr_html', 'q_html', 'answer_html')):
            errors.append('HTML esercizio non valido: ' + e['source_id'])
        if not e['answer_core'].strip():
            errors.append('Risposta vuota: ' + e['source_id'])
        if e['kind'] == 'compound' and e['check_mode'] == 'parti' and len(e.get('parts', [])) < 2:
            errors.append('Parti mancanti: ' + e['source_id'])
    return errors


def validate_candidate(kb, profile, baseline):
    try:
        return _validate_candidate(kb, profile, baseline)
    except (KeyError, TypeError, AttributeError, IndexError) as exc:
        raise BuildError('Struttura KB/profilo non valida: ' + type(exc).__name__) from exc


def _validate_candidate(kb, profile, baseline):
    errors = []
    if profile.get('schema_version') != 2:
        errors.append('Versione del profilo non supportata')
    if kb['meta'].get('schema_version') != SCHEMA_VERSION or kb['meta'].get('builder_version') != BUILDER_VERSION:
        errors.append('Versione dello schema/build non approvata')
    if kb['meta'].get('source_pdf_sha256') != profile['pdf_sha256']:
        errors.append('Provenienza PDF non approvata')
    if (kb['meta'].get('extractor',{}).get('backend') != 'pymupdf' or
            kb['meta'].get('extractor',{}).get('version') != profile['extractor_version']):
        errors.append('Backend/versione non approvati')
    if kb['meta'].get('source_pdf_pages') != profile['pdf_pages']:
        errors.append('Conteggio pagine PDF non approvato')
    actual = counts(kb)
    if actual != kb['meta']['counts']:
        errors.append('Conteggi nei metadati incoerenti')
    if actual != profile['counts']:
        errors.append('Conteggi diversi dal profilo approvato')
    if {c['num'] for c in kb['chapters']} != set(range(1,26)) or len(kb['chapters']) != 25:
        errors.append('Capitoli mancanti o duplicati')
    by_chapter = {str(n):sum(e['ch']==n for e in kb['exercises']) for n in range(1,26)}
    if by_chapter != profile['exercise_counts']:
        errors.append('Conteggi esercizi per capitolo diversi dal profilo approvato')
    ids = [e.get('source_id') for e in kb['exercises']]
    if len(ids) != len(set(ids)) or None in ids:
        errors.append('ID sorgente mancanti o duplicati')
    if {e.get('source_id'):exercise_fingerprint(e) for e in kb['exercises']} != profile['exercise_fingerprints']:
        errors.append('Contenuto/abbinamento esercizi diverso dal profilo approvato')
    if {e.get('source_id'):rich_fingerprint(e) for e in kb['exercises']} != profile['exercise_rich_fingerprints']:
        errors.append('Soluzioni/formattazione esercizi diverse dal profilo approvato')
    if set(kb['verbs']) != set(profile['verb_keys']):
        errors.append('Elenco verbi incompleto o inatteso')
    for base,forms in kb['verbs'].items():
        if len(forms) != 2 or any(not re.fullmatch(r"[a-z'-]+(?:\s*/\s*[a-z'-]+)*",f) for f in forms):
            errors.append('Forme verbali non valide: ' + base)
    if digest(json.dumps(kb['verbs'],sort_keys=True,ensure_ascii=False)) != profile['verbs_sha256']:
        errors.append('Forme verbali diverse dal riferimento approvato')
    if [g['term'] for g in kb['glossary']] != profile['glossary_terms']:
        errors.append('Glossario incompleto o inatteso')
    if {str(c['num']):digest(c['text']) for c in kb['chapters']} != profile['chapter_sha256']:
        errors.append('Testo dei capitoli diverso dal riferimento approvato')
    if {str(c['num']):blocks_digest(c) for c in kb['chapters'] if 'blocks' in c} != profile['chapter_blocks_sha256']:
        errors.append('Formattazione dei capitoli diversa dal riferimento approvato')
    if digest(json.dumps(kb['glossary'],ensure_ascii=False,sort_keys=True)) != profile['glossary_sha256']:
        errors.append('Definizioni glossario diverse dal riferimento approvato')
    if items_digest(kb) != profile['items_sha256']:
        errors.append('Esempi/coppie diversi dal riferimento approvato')
    header = re.compile(r'C\s+H\s+A\s+P\s+T\s+E\s+R|\bPART [IV]+\b')
    for e in kb['exercises']:
        if not e['q'].strip() or not e['answer'].strip() or header.search(e['q']+' '+e['answer']):
            errors.append('Esercizio vuoto/contaminato: ' + str(e.get('source_id')))
        if e.get('id') != e.get('source_id'):
            errors.append('ID di build non coerente con la sorgente')
        if e['options']:
            approved = profile['mcq_allowlist'].get(e['source_id'])
            if (not approved or e['options'] != approved['options'] or
                    type(e['answer_idx']) is not int or not 0 <= e['answer_idx'] < len(e['options']) or
                    e['options'][e['answer_idx']] != approved['correct'] or e.get('kind') != 'mcq'):
                errors.append('MCQ non approvata: ' + e['source_id'])
            elif e['q'] != (e['source_q'] if approved.get('from_instruction') else option_question(e['source_q'],e['options'])):
                errors.append('Testo MCQ diverso dalla sorgente: ' + e['source_id'])
        elif e['answer_idx'] is not None:
            errors.append('Indice MCQ senza opzioni')
        elif e['q'] != e['source_q']:
            errors.append('Consegna diversa dalla sorgente: ' + e['source_id'])
        if not (1 <= e['pdf_page'] <= profile['pdf_pages'] and 1 <= e['answer_pdf_page'] <= profile['pdf_pages']):
            errors.append('Provenienza fuori dal PDF')
    if actual['exercises_mcq'] != len(profile['mcq_allowlist']):
        errors.append('MCQ approvate perse o aggiunte')
    errors.extend(content_errors(kb))
    if errors:
        raise BuildError('\n'.join(errors[:40]) + (f'\n… e altri {len(errors) - 40}' if len(errors) > 40 else ''))
    # Correzioni runtime e registro editoriale (fase 3) devono restare applicabili.
    from tutor.content import prepare_content
    from tutor.book_quiz import load_notes
    try:
        prepared = prepare_content(copy.deepcopy(kb))
        notes = load_notes(prepared)
    except ValueError as exc:
        raise BuildError('Correzioni/registro/note IT non applicabili: ' + str(exc)) from exc
    return {'status':'passed','counts':actual,'exercises_by_chapter':by_chapter,
            'check_modes':dict(sorted(Counter(e['check_mode'] for e in kb['exercises']).items())),
            'quiz_eligible':{'examples':sum(e.get('quiz_eligible',True) for e in prepared['examples']),
                             'fixes':sum(e.get('quiz_eligible',True) for e in prepared['fixes']),
                             'mcq':sum(bool(e['options']) and e.get('quiz_eligible',True) for e in prepared['exercises'])},
            'quiz_excluded':sorted(f"{e.get('source_id') or e['id']}: {','.join(e['quiz_exclusion_reasons'])}"
                                   for sec in ('examples','fixes','exercises') for e in prepared[sec]
                                   if e.get('quiz_exclusion_reasons')),
            'reviewed_quiz_count':len(prepared['_reviewed_quiz']),
            'notes_it':{k: len(v) for k, v in notes.items()},
            'limitations':['Phase 4.3: the bot scores the book items directly; book errors are shown '
                           'in the original, without notes (user decision).',
                           'Assistant review is not human certification of the full book.',
                           'Compound exercises kept together, never converted to a single MCQ.']}


def rich_fingerprint(e):
    fields = ['instr_html', 'q_html', 'answer_html', 'answer_core', 'answer_explanation', 'answer_scheme',
              'answer_keywords', 'answer_variants', 'target', 'stem', 'parts', 'check_mode']
    return digest(json.dumps({k: e.get(k) for k in fields}, ensure_ascii=False, sort_keys=True))


def profile_from_candidate(kb, base_profile):
    """Profilo v2: riprende i riferimenti già approvati (PDF, esercizi, verbi, glossario, MCQ) e
    registra le nuove impronte di teoria, esempi/coppie e soluzioni ricche."""
    profile = {k: copy.deepcopy(base_profile[k]) for k in
               ('pdf_sha256', 'pdf_pages', 'extractor_version', 'mcq_allowlist', 'exercise_counts',
                'exercise_fingerprints', 'verb_keys', 'verbs_sha256', 'glossary_terms', 'glossary_sha256')}
    profile['schema_version'] = 2
    profile['counts'] = counts(kb)
    profile['chapter_sha256'] = {str(c['num']): digest(c['text']) for c in kb['chapters']}
    profile['chapter_blocks_sha256'] = {str(c['num']): blocks_digest(c) for c in kb['chapters']}
    profile['exercise_rich_fingerprints'] = {e['source_id']: rich_fingerprint(e) for e in kb['exercises']}
    profile['items_sha256'] = items_digest(kb)
    return dict(sorted(profile.items()))


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    payload = json.dumps(data,ensure_ascii=False,indent=1,allow_nan=False)+'\n'
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,
                                         prefix='.'+path.name+'.',suffix='.tmp',delete=False) as file:
            temp = Path(file.name)
            file.write(payload); file.flush(); os.fsync(file.fileno())
        os.replace(temp,path)
    finally:
        if temp is not None and temp.exists():
            temp.unlink()


def publish_candidate(candidate, profile, baseline, output, baseline_path, replace=False):
    """Valida PRIMA di qualunque scrittura. Sostituzione della baseline solo esplicita."""
    report = validate_candidate(candidate,profile,baseline)
    output,baseline_path = Path(output),Path(baseline_path)
    if output.resolve() == baseline_path.resolve():
        if not replace:
            raise BuildError('Per sostituire la KB attiva serve --replace; usa prima un file candidato')
        old = baseline_path.read_bytes()
        if json.loads(old) != baseline:
            raise BuildError('La baseline su disco è cambiata durante la build')
        backup = output.parent/'backups'/('kb-'+digest(old)[:16]+'.json')
        backup.parent.mkdir(parents=True,exist_ok=True)
        if backup.exists() and backup.read_bytes() != old:
            raise BuildError('Backup esistente non corrispondente')
        if not backup.exists():
            with backup.open('xb') as file:
                file.write(old)
        report['backup'] = str(backup)
    atomic_json(output,candidate)
    report['output_sha256'] = digest(output.read_bytes())
    return report
