"""Mini app di Telegram (fase 5.2): pagina /app e API /api/*, servite dallo stesso server del webhook.

- La chat non cambia: la mini app è una seconda interfaccia sugli stessi dati (data/kb.json).
- Ogni chiamata API deve portare l'initData firmato da Telegram (header «Authorization: tma <initData>»):
  senza firma valida → 401. Così i contenuti restano riservati agli utenti del bot.
- Nessun dato dello studente viene salvato sul server: i progressi della mini app (fasi successive)
  staranno nello spazio dati di Telegram dell'utente (CloudStorage), separati dalla chat.
"""
import hashlib
import hmac
import json
import time
from pathlib import Path
from urllib.parse import parse_qsl

from tornado.web import RequestHandler

ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "webapp" / "index.html"
MAX_AGE = 24 * 3600          # una sessione della mini app può restare aperta a lungo
MAX_INIT_DATA = 8192

CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline' https://telegram.org; "
       "style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; "
       "base-uri 'none'; form-action 'none'; object-src 'none'")


class InvalidInitData(ValueError):
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


# ------------------------------------------------------------------ dati
def reference_payload(kb):
    """Verbi irregolari e glossario del libro, così come sono nella KB."""
    verb_pages = kb.get("verb_pages") or {}          # verbo base → pagina del PDF
    verbs = [{"b": base, "p": forms[0], "pp": forms[1], "pg": verb_pages.get(base)}
             for base, forms in kb["verbs"].items()]
    pages = sorted({p for p in verb_pages.values() if isinstance(p, int)})
    glossary = [{"t": g["term"], "d": g["def"], "p": g.get("pdf_page")} for g in kb["glossary"]]
    return {
        "book": kb["meta"].get("title") or "English Grammar: A Complete Guide (A1-C1)",
        "verbs": verbs,
        "verb_pages": [pages[0], pages[-1]] if pages else [],
        "glossary": glossary,
        "counts": {"verbs": len(verbs), "glossary": len(glossary),
                   "chapters": len(kb["chapters"]), "exercises": len(kb["exercises"])},
    }


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
    def initialize(self, token, payload):
        self.token = token
        self.payload = payload

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
            import logging
            logging.getLogger("tutor-web").info("API mini app rifiutata: %s", exc)
            self.set_status(401)
            self.finish({"error": "unauthorized"})


class ReferenceHandler(ApiHandler):
    def get(self):
        user = self.tg.get("user") or {}
        body = dict(self.payload)
        body["user"] = {"first_name": user.get("first_name", ""),
                        "language_code": user.get("language_code", "")}
        self.finish(body)


def routes(token, kb):
    html = INDEX_HTML.read_text(encoding="utf-8")
    payload = reference_payload(kb)
    return [
        ("/app", AppPageHandler, {"html": html}),
        ("/api/reference", ReferenceHandler, {"token": token, "payload": payload}),
    ]
