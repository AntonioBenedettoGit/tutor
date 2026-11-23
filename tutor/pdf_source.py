"""Lettura geometrica del libro: dipendenza opzionale usata SOLO durante la build.

Nessun fallback testuale silenzioso: backend e versione sono registrati nell'output.
Il profilo del libro fissa le pagine/margini attesi; non è un parser PDF universale.
"""
from dataclasses import dataclass
import re


@dataclass
class Line:
    text: str
    page: int
    y: float
    bottom: float
    size: float
    heading: bool
    cells: tuple


def extract_pages(path):
    try:
        import pymupdf
    except ImportError as exc:
        raise RuntimeError('Installa le dipendenze di build: pip install -r requirements-build.txt') from exc
    pages = []
    with pymupdf.open(str(path)) as document:
        for page_num, page in enumerate(document, 1):
            spans = []
            for block in page.get_text('dict')['blocks']:
                for line in block.get('lines', []):
                    for span in line['spans']:
                        # Esclude header e footer prima di ricostruire l'ordine di lettura.
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
                text = ''
                right = None
                cells = []
                for span in parts:
                    if right is not None and span['bbox'][0] - right > 1.5:
                        text += ' '
                    text += span['text']
                    right = span['bbox'][2]
                    cells.append((round(span['bbox'][0], 2), span['text']))
                text = re.sub(r'([✓✗])(?=\S)', r'\1 ', text.strip())
                if text:
                    lines.append(Line(text, page_num, min(s['bbox'][1] for s in parts),
                                      max(s['bbox'][3] for s in parts),
                                      max(s['size'] for s in parts),
                                      all('Helvetica' in s['font'] and 'Bold' in s['font'] for s in parts),
                                      tuple(cells)))
            pages.append(lines)
    return pages, {'backend': 'pymupdf', 'version': pymupdf.__version__}


def join_text(parts):
    """Riunisce righe conservando parole, apostrofi e punteggiatura."""
    text = '\n'.join(parts)
    text = re.sub(r'[\u2010\u00ad][ \t]*\n[ \t]*', '', text)
    return ' '.join(text.split())


def partition_book(pages):
    chapters, appendix_a, appendix_b = {}, [], []
    current = None
    for lines in pages:
        # Le pagine divisorie non devono finire nell'ultima risposta del capitolo.
        if any(re.fullmatch(r'PART[IV]+', re.sub(r'\s+', '', l.text)) for l in lines):
            continue
        for line in lines:
            if line.size >= 20:
                match = re.match(r'^Chapter (\d+) —', line.text)
                if match:
                    num = int(match[1])
                    if num in chapters:
                        raise ValueError(f'Capitolo duplicato nel PDF: {num}')
                    chapters[num] = []
                    current = chapters[num]
                elif line.text.startswith('Appendix A —'):
                    current = appendix_a
                elif line.text.startswith('Appendix B —'):
                    current = appendix_b
                # Tutte le righe dei titoli sono metadati, non prosa.
                continue
            if current is not None:
                current.append(line)
    if set(chapters) != set(range(1, 26)) or not appendix_a or not appendix_b:
        raise ValueError('Struttura del libro inattesa: capitoli o appendici mancanti')
    return chapters, appendix_a, appendix_b


def paragraphs(lines):
    blocks, pending = [], []
    prev = None
    for line in lines:
        structural = bool(re.match(r'^(?:[•✓✗]|\d+\.\s|[A-F]\.\s)', line.text))
        heading = line.heading and line.size >= 12
        gap = prev is not None and line.page == prev.page and line.y - prev.bottom > 4
        table_row = line.size <= 9.5
        if pending and (structural or heading or gap or table_row):
            blocks.append(join_text(pending)); pending = []
        pending.append(line.text)
        if heading or table_row or line.text in ('Practice','Answers','Quick Review'):
            blocks.append(join_text(pending)); pending = []
        prev = line
    if pending:
        blocks.append(join_text(pending))
    return '\n\n'.join(blocks)


def practice_sections(lines):
    starts = [i for i,l in enumerate(lines) if l.text == 'Practice']
    if len(starts) != 1:
        raise ValueError('Sezione Practice mancante o ambigua')
    start = starts[0]
    answers = [i for i,l in enumerate(lines) if i > start and l.text == 'Answers']
    if len(answers) != 1:
        raise ValueError('Sezione Answers mancante o ambigua')
    end = answers[0]
    return lines[start+1:end], lines[end+1:]
