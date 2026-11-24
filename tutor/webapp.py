"""Mini app di Telegram (fasi 5.2–5.3): pagina /app e API /api/*, servite dallo stesso server del webhook.

- La chat non cambia: la mini app è una seconda interfaccia sugli stessi dati (data/kb.json).
- Contenuti e correzione sono gli stessi della chat: teoria (kb._theory_blocks/_block_html), testi di
  domande, esercizi e soluzioni (tutor.render), verifica delle risposte (tutor.book_quiz). Il server
  trasforma l'HTML di Telegram in un albero di nodi JSON: la pagina costruisce il DOM solo con nodi di
  testo, mai con HTML preso dai dati.
- Ogni chiamata API deve portare l'initData firmato da Telegram (header «Authorization: tma <initData>»):
  senza firma valida → 401. Così i contenuti restano riservati agli utenti del bot.
- Nessun dato dello studente viene salvato sul server: i progressi della mini app stanno nello spazio
  dati di Telegram dell'utente (CloudStorage), separati da quelli della chat. Le API sono senza stato.
"""
import hashlib
import hmac
import json
import logging
import random
import time
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qsl

from tornado.web import RequestHandler

from tutor import book_quiz, render
from tutor import kb as kbmod
from tutor.texts import CHAPTER_IT, PARTS, part_of

ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "webapp" / "index.html"
MAX_AGE = 24 * 3600          # una sessione della mini app può restare aperta a lungo
MAX_INIT_DATA = 8192
MAX_BODY = 8192              # corpo JSON delle richieste POST
MAX_ANSWER = 2000            # risposta scritta dallo studente
LANGS = ("it", "en")
log = logging.getLogger("tutor-web")

CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline' https://telegram.org; "
       "style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; "
       "base-uri 'none'; form-action 'none'; object-src 'none'")


class InvalidInitData(ValueError):
    pass


class BadRequest(ValueError):
    pass


def validate_init_data(init_data, token, max_age=MAX_AGE, now=None):
    """Verifica la firma di Telegram.WebApp.initData (procedura ufficiale delle Mini App):
    data-check-string = campi tranne «hash», ordinati, «chiave=valore» uniti da \\n;
    chiave segreta = HMAC-SHA256(chiave="WebAppData", messaggio=token);
    hash atteso = HMAC-SHA256(chiave segreta, data-check-string) in esadecimale.
    Ritorna i campi decodificati (user come dict) oppure solleva InvalidInitData."""
    if not init_data or len(init_data) > MAX_INIT_DATA:
        raise InvalidInitData("vuoto o troppo lungo")
    try:
        pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise InvalidInitData("formato") from exc
    fields = {}
    for key, value in pairs:
        if key in fields:
            raise InvalidInitData("campo ripetuto")
        fields[key] = value
    received = fields.pop("hash", "")
    if not received:
        raise InvalidInitData("hash assente")
    check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received.lower()):
        raise InvalidInitData("firma non valida")
    try:
        auth_date = int(fields.get("auth_date", ""))
    except ValueError as exc:
        raise InvalidInitData("auth_date") from exc
    now = time.time() if now is None else now
    if now - auth_date > max_age or auth_date - now > 300:
        raise InvalidInitData("scaduto")
    if "user" in fields:
        try:
            user = json.loads(fields["user"])
        except ValueError as exc:
            raise InvalidInitData("user") from exc
        if not isinstance(user, dict) or not isinstance(user.get("id"), int):
            raise InvalidInitData("user")
        fields["user"] = user
    return fields


# ------------------------------------------------------------------ HTML di Telegram → nodi JSON
NODE_TAGS = {"b": "b", "strong": "b", "i": "i", "em": "i", "u": "u", "ins": "u", "s": "s",
             "strike": "s", "del": "s", "code": "code", "pre": "pre", "blockquote": "bq"}


class _NodeParser(HTMLParser):
    """Albero di nodi: una stringa è testo; [tag, figli] è un elemento tra quelli di NODE_TAGS
    (blockquote espandibile → «bqx»). Tag sconosciuti: si tiene il testo, si scarta il tag."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = []
        self.stack = [("", self.root)]

    def handle_starttag(self, tag, attrs):
        name = NODE_TAGS.get(tag)
        if not name:
            return
        if name == "bq" and any(k == "expandable" for k, _ in attrs):
            name = "bqx"
        children = []
        self.stack[-1][1].append([name, children])
        self.stack.append((tag, children))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        kids = self.stack[-1][1]
        if kids and isinstance(kids[-1], str):
            kids[-1] += data
        else:
            kids.append(data)


def _trim_around_quotes(nodes):
    """Un riquadro è già un blocco: niente a capo subito prima o subito dopo."""
    out = []
    for i, n in enumerate(nodes):
        if isinstance(n, str):
            if i + 1 < len(nodes) and isinstance(nodes[i + 1], list) and nodes[i + 1][0] in ("bq", "bqx"):
                n = n.rstrip("\n")
            if i > 0 and isinstance(nodes[i - 1], list) and nodes[i - 1][0] in ("bq", "bqx"):
                n = n.lstrip("\n")
            if n:
                out.append(n)
        else:
            out.append([n[0], _trim_around_quotes(n[1])])
    return out


def html_nodes(html):
    """HTML di Telegram (lo stesso che riceve la chat, con la stessa pulizia) → nodi JSON."""
    parser = _NodeParser()
    parser.feed(render.clean_for_display(html or ""))
    parser.close()
    return _trim_around_quotes(parser.root)


def nodes_text(nodes):
    return "".join(n if isinstance(n, str) else nodes_text(n[1]) for n in nodes)


# ------------------------------------------------------------------ dati
def chapter_list(kb):
    quiz_counts, ex_counts = {}, {}
    for ref in book_quiz.quiz_items(kb):
        quiz_counts[ref["ch"]] = quiz_counts.get(ref["ch"], 0) + 1
    for e in exercise_items(kb):
        ex_counts[e["ch"]] = ex_counts.get(e["ch"], 0) + 1
    out = []
    for n in sorted(kb["_chapters"]):
        ch = kb["_chapters"][n]
        out.append({"n": n, "it": CHAPTER_IT.get(n, ch["title"]), "en": ch["title"], "part": part_of(ch),
                    "ex": ex_counts.get(n, 0), "q": quiz_counts.get(n, 0),
                    "pp": [ch.get("pdf_page_start"), ch.get("pdf_page_end")]})
    return out


def reference_payload(kb):
    """Verbi irregolari, glossario e indice dei capitoli del libro, così come sono nella KB."""
    verb_pages = kb.get("verb_pages") or {}          # verbo base → pagina del PDF
    verbs = [{"b": base, "p": forms[0], "pp": forms[1], "pg": verb_pages.get(base)}
             for base, forms in kb["verbs"].items()]
    pages = sorted({p for p in verb_pages.values() if isinstance(p, int)})
    glossary = [{"t": g["term"], "d": g["def"], "p": g.get("pdf_page")} for g in kb["glossary"]]
    chapters = chapter_list(kb)
    return {
        "book": kb["meta"].get("title") or "English Grammar: A Complete Guide (A1-C1)",
        "verbs": verbs,
        "verb_pages": [pages[0], pages[-1]] if pages else [],
        "glossary": glossary,
        "chapters": chapters,
        "parts": [{"id": p, "it": PARTS[p][0], "en": PARTS[p][1]} for p in PARTS],
        "quiz_size": book_quiz.QUIZ_SIZE,
        "counts": {"verbs": len(verbs), "glossary": len(glossary),
                   "chapters": len(kb["chapters"]), "exercises": sum(c["ex"] for c in chapters)},
    }


def theory_payload(kb, n):
    """Teoria completa del capitolo: gli stessi blocchi (e la stessa formattazione) della chat."""
    if n not in kb["_chapters"]:
        raise BadRequest("capitolo")
    blocks = []
    source = kbmod._theory_blocks(kb, n)
    for b in source:
        nodes = html_nodes(kbmod._block_html(b))
        if nodes:
            blocks.append({"k": b["type"], "p": b.get("page"), "h": nodes})
    if not source:                                   # come chapter_pages: testo semplice
        for para in kb["_chapters"][n]["text"].split("\n\n"):
            if para.strip():
                blocks.append({"k": "para", "p": None, "h": [render.clean_for_display(para)]})
    ch = kb["_chapters"][n]
    return {"n": n, "blocks": blocks, "pp": [ch.get("pdf_page_start"), ch.get("pdf_page_end")]}


def exercise_items(kb, chapter=None):
    """Gli esercizi di un capitolo, nello stesso ordine e con lo stesso filtro della chat."""
    return [e for e in kb["exercises"]
            if (chapter is None or e["ch"] == chapter) and e.get("quiz_eligible", True)]


def exercise_label(e):
    return f"{e['group']}-{e['source_number']}" if e.get("group") else str(e["source_number"])


def exercises_payload(kb, n, lang):
    if n not in kb["_chapters"]:
        raise BadRequest("capitolo")
    items = []
    for e in exercise_items(kb, n):
        instr, q = render.exercise_parts(kb, lang, e)
        items.append({"id": e["source_id"], "mode": e["check_mode"], "label": exercise_label(e),
                      "instr": html_nodes(instr), "q": html_nodes(q),
                      "options": list(e.get("options") or []),
                      "parts": [p["label"] for p in e.get("parts") or []]})
    return {"n": n, "lang": lang, "items": items}


def _exercise(kb, ex_id):
    index = kb.get("_webapp_ex")
    if index is None:
        index = kb["_webapp_ex"] = {e["source_id"]: e for e in exercise_items(kb)}
    e = index.get(ex_id) if isinstance(ex_id, str) else None
    if e is None:
        raise BadRequest("esercizio")
    return e


def grade_exercise(kb, lang, ex_id, action, value=None):
    """Stessa correzione di bot.ex_answer_typed / ex_grade_choice / ex_reveal.
    Ritorna l'esito (good: True/False, oppure self=True per l'autovalutazione) e la soluzione del libro."""
    e = _exercise(kb, ex_id)
    mode = e["check_mode"]
    out = {"id": e["source_id"], "mode": mode}
    if action == "answer":
        typed = value if isinstance(value, str) else ""
        if not typed.strip() or len(typed) > MAX_ANSWER:
            raise BadRequest("risposta")
        out["yours"] = typed
        if mode in ("automatico", "automatico_con_varianti"):
            out["good"] = book_quiz.check_answer(e, typed)
        elif mode == "parti":
            results = book_quiz.check_parts(e, typed)
            right = sum(ok for _, _, ok in results)
            out["good"] = bool(results) and right == len(results)
            out["parts"] = [{"label": label, "typed": answer, "ok": ok} for label, answer, ok in results]
            out["right"], out["total"] = right, len(results)
        elif mode == "scelta_multipla":
            choice = typed.strip().rstrip(').').upper()
            options = e.get("options") or []
            idx = render.LETTERS.find(choice) if len(choice) == 1 else -1
            if not 0 <= idx < len(options):
                idx = next((j for j, o in enumerate(options) if book_quiz.norm(o) == book_quiz.norm(typed)), -1)
            if idx < 0:
                raise BadRequest("usa i bottoni")
            return grade_exercise(kb, lang, ex_id, "choice", idx)
        else:
            out["self"] = True
    elif action == "choice":
        options = e.get("options") or []
        if mode != "scelta_multipla" or not isinstance(value, int) or isinstance(value, bool) \
                or not 0 <= value < len(options):
            raise BadRequest("scelta")
        out["good"] = value == e["answer_idx"]
        out["chosen"] = value
        out["answer"] = e["answer_idx"]
    elif action == "reveal":
        if mode == "autovalutazione":
            out["self"] = True
        else:
            out["good"] = False
            out["shown"] = True
    else:
        raise BadRequest("azione")
    out["solution"] = html_nodes(render.solution_html(kb, lang, e))
    return out


# ------------------------------------------------------------------ quiz
def _quiz_index(kb):
    index = kb.get("_webapp_quiz")
    if index is None:
        index = kb["_webapp_quiz"] = {(r["type"], r["ref"]): r for r in book_quiz.quiz_items(kb)}
    return index


def quiz_question(kb, lang, ref_item, rng=random):
    item = book_quiz.resolve(kb, ref_item)
    ask, sub, text = render.quiz_question_parts(kb, lang, ref_item, item)
    if ref_item["type"] == "fix":
        options = [item["bad"], item["good"]]
        rng.shuffle(options)
    elif ref_item["type"] == "mcq":
        options = list(item.get("options") or [])
    else:
        options = []
    snippet = unescape(render.quiz_snippet(kb, ref_item, item))
    return {"ref": ref_item["ref"], "type": ref_item["type"], "ch": ref_item["ch"],
            "ask": html_nodes(ask), "sub": html_nodes(sub), "text": html_nodes(text),
            "options": options, "snippet": snippet}


def quiz_payload(kb, lang, chapter=None, rng=random):
    """Come bot.start_quiz: book_quiz.build_pool (stesso mix di vero/falso, coppie e scelte multiple)."""
    if chapter is not None and chapter not in kb["_chapters"]:
        raise BadRequest("capitolo")
    pool = book_quiz.build_pool(kb, chapter, book_quiz.QUIZ_SIZE, rng)
    return {"chapter": chapter, "lang": lang, "questions": [quiz_question(kb, lang, r, rng) for r in pool]}


def grade_quiz(kb, lang, kind, ref, given, options=None):
    """Stessa correzione di bot.quiz_feedback; il corpo della risposta è render.quiz_feedback_body."""
    ref_item = _quiz_index(kb).get((kind, ref)) if isinstance(kind, str) and isinstance(ref, str) else None
    if ref_item is None:
        raise BadRequest("domanda")
    item = book_quiz.resolve(kb, ref_item)
    out = {"ref": ref, "type": kind}
    if kind == "tf":
        if not isinstance(given, bool):
            raise BadRequest("risposta")
        good = given is item["ok"]
    elif kind == "fix":
        if (not isinstance(options, list) or len(options) != 2 or sorted(options) != sorted([item["bad"], item["good"]])
                or not isinstance(given, int) or isinstance(given, bool) or given not in (0, 1)):
            raise BadRequest("risposta")
        answer_idx = options.index(item["good"])
        good = given == answer_idx
        out["answer"] = answer_idx
    else:
        opts = item.get("options") or []
        if not isinstance(given, int) or isinstance(given, bool) or not 0 <= given < len(opts):
            raise BadRequest("risposta")
        good = given == item["answer_idx"]
        out["answer"] = item["answer_idx"]
    out["good"] = good
    out["body"] = html_nodes(render.quiz_feedback_body(kb, lang, ref_item, item))
    return out


def search_payload(kb, query):
    """Come /spiega: capitolo, verbi o glossario (kb.search)."""
    if not isinstance(query, str) or len(query) > 200:
        raise BadRequest("ricerca")
    (kind, value), _how = kbmod.search(kb, query)
    if kind == "chapter":
        return {"kind": "chapter", "n": value}
    if kind == "verbs":
        return {"kind": "verbs", "q": value if isinstance(value, str) else ""}
    if kind == "glossary":
        return {"kind": "glossary", "q": query.strip()}
    return {"kind": "none"}


# ------------------------------------------------------------------ handler tornado
class AppPageHandler(RequestHandler):
    """La pagina della mini app (un unico file HTML con CSS e JS in linea)."""
    def initialize(self, html):
        self.html = html

    def _page_headers(self):
        self.set_header("Content-Type", "text/html; charset=utf-8")
        self.set_header("Cache-Control", "no-cache")
        self.set_header("Content-Security-Policy", CSP)
        self.set_header("X-Content-Type-Options", "nosniff")
        self.set_header("Referrer-Policy", "no-referrer")

    def get(self):
        self._page_headers()
        self.write(self.html)

    def head(self):
        self._page_headers()


class ApiHandler(RequestHandler):
    def initialize(self, token, kb, payload=None, cache=None):
        self.token = token
        self.kb = kb
        self.payload = payload
        self.cache = cache if cache is not None else {}

    def prepare(self):
        self.set_header("Cache-Control", "no-store")
        self.set_header("X-Content-Type-Options", "nosniff")
        auth = self.request.headers.get("Authorization", "")
        scheme, _, init_data = auth.partition(" ")
        try:
            if scheme.lower() != "tma":
                raise InvalidInitData("schema")
            self.tg = validate_init_data(init_data.strip(), self.token)
        except InvalidInitData as exc:
            log.info("API mini app rifiutata: %s", exc)
            self.set_status(401)
            self.finish({"error": "unauthorized"})

    # --- utilità
    def lang(self, value=None):
        value = value if value is not None else self.get_query_argument("lang", "it")
        return value if value in LANGS else "it"

    def chapter_arg(self, name="n", required=True):
        raw = self.get_query_argument(name, "")
        if not raw and not required:
            return None
        if not raw.isdigit() or len(raw) > 3:
            raise BadRequest(name)
        return int(raw)

    def json_body(self):
        if len(self.request.body or b"") > MAX_BODY:
            raise BadRequest("corpo troppo grande")
        ctype = self.request.headers.get("Content-Type", "").split(";")[0].strip().lower()
        if ctype != "application/json":
            raise BadRequest("content-type")
        try:
            body = json.loads(self.request.body or b"{}")
        except ValueError as exc:
            raise BadRequest("json") from exc
        if not isinstance(body, dict):
            raise BadRequest("json")
        return body

    def answer(self, fn):
        try:
            result = fn()
        except BadRequest as exc:
            log.info("API mini app: richiesta non valida (%s)", exc)
            self.set_status(400)
            self.finish({"error": "bad_request"})
            return
        self.finish(result)

    def cached(self, key, fn):
        if key not in self.cache:
            self.cache[key] = fn()
        return self.cache[key]


class ReferenceHandler(ApiHandler):
    def get(self):
        user = self.tg.get("user") or {}
        body = dict(self.payload)
        body["user"] = {"first_name": user.get("first_name", ""),
                        "language_code": user.get("language_code", "")}
        self.finish(body)


class TheoryHandler(ApiHandler):
    def get(self):
        def run():
            n = self.chapter_arg()
            return self.cached(("theory", n), lambda: theory_payload(self.kb, n))
        self.answer(run)


class ExercisesHandler(ApiHandler):
    def get(self):
        def run():
            n, lang = self.chapter_arg(), self.lang()
            return self.cached(("ex", n, lang), lambda: exercises_payload(self.kb, n, lang))
        self.answer(run)


class ExerciseCheckHandler(ApiHandler):
    def post(self):
        def run():
            body = self.json_body()
            return grade_exercise(self.kb, self.lang(body.get("lang")), body.get("id"),
                                  body.get("action"), body.get("value"))
        self.answer(run)


class QuizHandler(ApiHandler):
    def get(self):
        self.answer(lambda: quiz_payload(self.kb, self.lang(), self.chapter_arg("ch", required=False)))


class QuizCheckHandler(ApiHandler):
    def post(self):
        def run():
            body = self.json_body()
            return grade_quiz(self.kb, self.lang(body.get("lang")), body.get("type"), body.get("ref"),
                              body.get("given"), body.get("options"))
        self.answer(run)


class SearchHandler(ApiHandler):
    def get(self):
        self.answer(lambda: search_payload(self.kb, self.get_query_argument("q", "")))


def routes(token, kb):
    html = INDEX_HTML.read_text(encoding="utf-8")
    common = {"token": token, "kb": kb, "cache": {}}
    return [
        ("/app", AppPageHandler, {"html": html}),
        ("/api/reference", ReferenceHandler, {**common, "payload": reference_payload(kb)}),
        ("/api/theory", TheoryHandler, common),
        ("/api/exercises", ExercisesHandler, common),
        ("/api/exercise/check", ExerciseCheckHandler, common),
        ("/api/quiz", QuizHandler, common),
        ("/api/quiz/check", QuizCheckHandler, common),
        ("/api/search", SearchHandler, common),
    ]
