"""Build deterministica e validata per lo specifico libro A1-C1.

Esempi vero/falso e coppie vengono conservati dalla baseline: non si ricrea un
pool valutato da semplici simboli ✓/✗. Una revisione editoriale è separata dal
parsing geometrico di capitoli, esercizi, glossario e tabella dei verbi.
"""
import copy
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


def build_candidate(pdf, baseline, profile, chapters_spec, parts, synonyms):
    pdf = Path(pdf)
    if profile.get('schema_version') != 1:
        raise BuildError('Versione del profilo non supportata')
    if digest(pdf.read_bytes()) != profile['pdf_sha256']:
        raise BuildError('PDF diverso da quello approvato nel profilo del libro')
    pages, backend = extract_pages(pdf)
    if backend['version'] != profile['extractor_version']:
        raise BuildError('Versione estrattore diversa da quella approvata')
    if len(pages) != profile['pdf_pages']:
        raise BuildError('Numero di pagine PDF inatteso')
    sections, appendix_a, appendix_b = partition_book(pages)
    chapters, exercises = [], []
    for num,title,part in chapters_spec:
        lines = sections[num]
        practice, answers = practice_sections(lines)
        items = parse_exercises(num,practice,answers)
        chapters.append({'num':num,'title':title,'part':parts[part],
                         'text':f'Chapter {num} — {title}\n\n'+paragraphs(lines),
                         'pdf_page_start':lines[0].page,'pdf_page_end':lines[-1].page})
        exercises.extend(items)
    apply_mcq_policy(exercises,profile['mcq_allowlist'])
    verbs, verb_pages = extract_reference_verbs(appendix_a)
    candidate = {'meta':{'schema_version':2,'title':baseline['meta']['title'],
                        'source':pdf.name,'built':str(date.today()),
                        'source_pdf_sha256':profile['pdf_sha256'],'source_pdf_pages':len(pages),
                        'extractor':backend,'builder_version':2,
                        'legacy_quiz_policy':'Examples and fixes preserved from baseline; no automatic re-extraction.'},
                 'chapters':chapters,'exercises':exercises,'verbs':verbs,'verb_pages':verb_pages,
                 'glossary':extract_glossary(appendix_b),'synonyms':copy.deepcopy(synonyms),
                 'examples':copy.deepcopy(baseline['examples']),'fixes':copy.deepcopy(baseline['fixes'])}
    candidate['meta']['counts'] = counts(candidate)
    return candidate


def validate_candidate(kb, profile, baseline):
    try:
        return _validate_candidate(kb, profile, baseline)
    except (KeyError, TypeError, AttributeError, IndexError) as exc:
        raise BuildError('Struttura KB/profilo non valida: ' + type(exc).__name__) from exc


def _validate_candidate(kb, profile, baseline):
    errors = []
    if kb['meta'].get('schema_version') != 2 or kb['meta'].get('builder_version') != 2:
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
    if digest(json.dumps(kb['glossary'],ensure_ascii=False,sort_keys=True)) != profile['glossary_sha256']:
        errors.append('Definizioni glossario diverse dal riferimento approvato')
    if digest(json.dumps({s:kb[s] for s in ['examples','fixes']},ensure_ascii=False,sort_keys=True)) != profile['legacy_sha256']:
        errors.append('Pool legacy diverso dal riferimento approvato')
    if kb['examples'] != baseline['examples'] or kb['fixes'] != baseline['fixes']:
        errors.append('Pool legacy modificato senza revisione editoriale separata')
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
    if errors:
        raise BuildError('\n'.join(errors))
    # Anche le correzioni runtime della prima fase devono restare applicabili.
    from tutor.content import prepare_content
    prepared = prepare_content(copy.deepcopy(kb))
    return {'status':'passed','counts':actual,'exercises_by_chapter':by_chapter,
            'quiz_eligible':{'examples':sum(e.get('quiz_eligible',True) for e in prepared['examples']),
                             'fixes':sum(e.get('quiz_eligible',True) for e in prepared['fixes']),
                             'mcq':sum(bool(e['options']) and e.get('quiz_eligible',True) for e in prepared['exercises'])},
            'reviewed_quiz_count':len(prepared['_reviewed_quiz']),
            'limitations':['Raw examples/fixes/exercises are consultation-only; scored quizzes use the separate editorial register.',
                           'Assistant review is not human certification of the full book.',
                           'Compound exercises kept together, never converted to a single MCQ.']}


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
