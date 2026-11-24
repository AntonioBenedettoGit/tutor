#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot Telegram tutor di grammatica inglese — basato sul libro
"English Grammar: A Complete Guide (A1-C1)", SENZA AI.

Tutte le domande, le spiegazioni e le risposte vengono dalla knowledge
base generata dal PDF (data/kb.json, vedi build_kb.py). Nessun dato
dello studente viene inviato a servizi esterni.

Avvio:
    1. crea il bot su Telegram con @BotFather e copia il token
    2. copia .env.example in .env e incolla il token
    3. pip install -r requirements.txt
    4. python3 bot.py

Comandi: /menu /quiz /esercizi /spiega /capitoli /verbi /glossario /lang
"""
import asyncio
import copy
from html import escape
import secrets
import logging
import os
import random
import re
import sys
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, MessageHandler, filters)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tutor import book_quiz, render
from tutor.logging_config import configure_logging
from tutor import kb as kbmod                      # noqa: E402
from tutor.texts import lang_keyboard, menu_keyboard, tr  # noqa: E402

log = logging.getLogger("tutor-bot")

# ------------------------------------------------------------------ .env
def load_bot_token():
    token = os.environ.get("BOT_TOKEN")
    if token:
        return token.strip()
    env_file = Path(__file__).resolve().parent / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("BOT_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


KB_PATH = Path(__file__).resolve().parent / "data" / "kb.json"
KB = kbmod.load_kb(KB_PATH)
STATE = {}  # chat_id -> stato della conversazione (in memoria)
EXERCISES = {e["source_id"]: e for e in KB["exercises"]}
LETTERS = render.LETTERS

QUIZ_SIZE = book_quiz.QUIZ_SIZE   # domande per sessione di quiz
MAX_CHAPTER_BUTTONS_PER_ROW = 2


# ------------------------------------------------------------------ utils
def st(chat_id):
    if chat_id not in STATE:
        STATE[chat_id] = {"lang": None, "mode": None, "quiz": None,
                          "ex": None, "pages": None, "glos": None}
    return STATE[chat_id]


def lang_of(update_or_chat):
    chat_id = update_or_chat.effective_chat.id
    return st(chat_id).get("lang") or "it"


def clean_for_display(text):
    """Pulisce i glitch di formattazione ereditati dal PDF/parsing:
    separatori di tabella '| | | |' e spazi doppi."""
    text = re.sub(r"\s*\|+\s*", " ", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


async def send(update, ctx, text, keyboard=None, parse_mode=None):
    text = clean_for_display(text)
    # Non tagliare HTML a meta tag/entita: gli esercizi attuali sono sotto soglia.
    if parse_mode and len(text) > 4096:
        raise ValueError("Messaggio formattato troppo lungo")
    return await update.effective_chat.send_message(
        text[:4096], reply_markup=keyboard, parse_mode=parse_mode)


def chapter_label(kb, num, lang):
    c = kb["_chapters"][num]
    return f"{num}. {c['title']}"


def pages_keyboard(lang, idx, total, page_id):
    row = []
    if idx + 1 < total:
        row.append(InlineKeyboardButton(tr(lang, "btn_nextpage"),
                                        callback_data=f"page:{page_id}:{idx + 1}"))
    row.append(InlineKeyboardButton(tr(lang, "btn_menu"), callback_data="back:menu"))
    return InlineKeyboardMarkup([row]) if row else None


def enter_mode(chat_id, mode):
    """Ogni cambio di attivita invalida tutte le sessioni precedenti."""
    s = st(chat_id)
    for key in ("quiz", "ex", "pages", "glos", "page_id", "glos_id", "page_idx"):
        s[key] = None
    s["mode"] = mode
    return s


def session_data(kind, session, action):
    return f"{kind}:{session['id']}:{session['idx']}:{action}"


async def remove_callback_keyboard(update):
    q = update.callback_query
    if q is not None:
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except TelegramError as exc:
            # Un messaggio cancellato/non modificabile non deve fermare la sessione.
            log.warning("Impossibile rimuovere una tastiera: %s", type(exc).__name__)


# ------------------------------------------------------------------ quiz
def build_quiz_pool(kb, chapter=None, limit=QUIZ_SIZE):
    """Domande dal libro: esempi ✓/✗, coppie ✗ → ✓, scelte multiple (book_quiz.build_pool)."""
    return book_quiz.build_pool(kb, chapter, limit)


def quiz_keyboard(lang, ref_item, session):
    cb = lambda action: session_data("quiz", session, action)
    if ref_item["type"] == "tf":
        return InlineKeyboardMarkup([[
            InlineKeyboardButton(tr(lang, "btn_correct"), callback_data=cb("tf:1")),
            InlineKeyboardButton(tr(lang, "btn_wrong"), callback_data=cb("tf:0")),
        ], [InlineKeyboardButton(tr(lang, "btn_stop_quiz"), callback_data=cb("stop"))]])
    options = quiz_options(ref_item)
    btns = [[InlineKeyboardButton(LETTERS[i], callback_data=cb(f"ans:{i}"))
             for i in range(min(len(options), len(LETTERS)))]]
    btns.append([InlineKeyboardButton(tr(lang, "btn_stop_quiz"), callback_data=cb("stop"))])
    return InlineKeyboardMarkup(btns)


def quiz_options(ref_item):
    if ref_item["type"] == "fix":
        return ref_item.get("opts") or []
    if ref_item["type"] == "mcq":
        return book_quiz.resolve(KB, ref_item).get("options") or []
    return []


async def start_quiz(update, ctx, chat_id, chapter=None, pre_pool=None):
    s = st(chat_id)
    lang = s["lang"] or "it"
    pool = copy.deepcopy(pre_pool if pre_pool is not None else build_quiz_pool(KB, chapter))
    if not pool:
        await send(update, ctx, tr(lang, "exp_notfound"))
        return
    s = enter_mode(chat_id, "quiz")
    s["quiz"] = {"id": secrets.token_hex(4), "pool": pool, "idx": 0, "score": 0, "answered": False}
    await send(update, ctx, tr(lang, "quiz_start", n=len(pool)), menu_keyboard(lang))
    await send_next_question(update, ctx, chat_id)


async def send_next_question(update, ctx, chat_id):
    s = st(chat_id)
    lang = s["lang"] or "it"
    qz = s["quiz"]
    if qz["idx"] >= len(qz["pool"]):
        await send(update, ctx, tr(lang, "quiz_done", c=qz["score"], t=len(qz["pool"])),
                   InlineKeyboardMarkup([[
                       InlineKeyboardButton(tr(lang, "quiz_again"), callback_data="menu:quiz"),
                       InlineKeyboardButton(tr(lang, "btn_menu"), callback_data="back:menu")]]))
        s["quiz"] = None
        s["mode"] = None
        return
    ref_item = qz["pool"][qz["idx"]]
    item = book_quiz.resolve(KB, ref_item)
    fix_opts = None
    if ref_item["type"] == "fix":
        if "opts" not in ref_item:
            opts = [item["bad"], item["good"]]
            random.shuffle(opts)
            ref_item["opts"] = opts
            ref_item["answer_idx"] = opts.index(item["good"])
        fix_opts = ref_item["opts"]
    text = render.quiz_question(KB, lang, ref_item, item, qz["idx"] + 1, len(qz["pool"]), fix_opts)
    await send(update, ctx, text, quiz_keyboard(lang, ref_item, qz), parse_mode="HTML")


async def quiz_feedback(update, ctx, chat_id, given=None):
    """given: per tf -> bool previsto; per ans -> indice opzione scelto."""
    s = st(chat_id)
    lang = s["lang"] or "it"
    qz = s["quiz"]
    if s["mode"] != "quiz" or qz is None or qz.get("answered"):
        await send(update, ctx, tr(lang, "already"))
        return
    ref_item = qz["pool"][qz["idx"]]
    item = book_quiz.resolve(KB, ref_item)
    qz["answered"] = True
    if ref_item["type"] == "tf":
        good = given is item["ok"]
    elif ref_item["type"] == "fix":
        good = given == ref_item["answer_idx"]
    else:
        good = given == item["answer_idx"]
    if good:
        qz["score"] += 1
    text = render.quiz_feedback(KB, lang, ref_item, item, good, qz["score"], len(qz["pool"]), given)
    kb_btn = InlineKeyboardMarkup([[
        InlineKeyboardButton(tr(lang, "btn_next"), callback_data=session_data("quiz", qz, "next")),
        InlineKeyboardButton(tr(lang, "btn_stop_quiz"), callback_data=session_data("quiz", qz, "stop")),
    ]])
    await send(update, ctx, text, kb_btn, parse_mode="HTML")


async def handle_session_callback(update, ctx):
    """Callback legati a sessione e posizione. I vecchi formati sono rifiutati."""
    q = update.callback_query
    s = st(update.effective_chat.id)
    lang = s['lang'] or 'it'
    parts = (q.data or '').split(':')
    kind = parts[0]
    valid = False
    action = ''
    active = None
    if kind in ('quiz', 'ex') and len(parts) in (4, 5):
        active = s.get(kind)
        valid = bool(s['mode'] == kind and active and
                     parts[1] == active['id'] and parts[2] == str(active['idx']))
        action = ':'.join(parts[3:])
        if valid and kind == 'quiz':
            item = active['pool'][active['idx']]
            if action == 'next':
                valid = active['answered']
            elif action == 'stop':
                pass
            elif action in ('tf:0', 'tf:1'):
                valid = not active['answered'] and item['type'] == 'tf'
            elif action.startswith('ans:'):
                value = action[4:]
                valid = (not active['answered'] and item['type'] != 'tf'
                         and value in {str(i) for i in range(len(quiz_options(item)))})
            else:
                valid = False
        elif valid:
            e = current_exercise(active)
            mode = e['check_mode'] if e else None
            shown, graded = active.get('shown'), active.get('graded')
            if action in ('skip', 'show'):
                valid = e is not None and not shown
            elif action == 'next':
                valid = bool(shown and graded)
            elif action.startswith('ans:'):
                valid = (not shown and mode == 'scelta_multipla' and
                         action[4:] in {str(i) for i in range(len(e.get('options') or []))})
            elif action in ('self:1', 'self:0'):
                valid = bool(shown and not graded and mode == 'autovalutazione')
            else:
                valid = False
    elif kind == 'page' and len(parts) == 3:
        valid = bool(s['mode'] in ('chap', 'exp') and s.get('pages') and
                     parts[1] == s.get('page_id') and
                     parts[2] == str(s.get('page_idx', 0) + 1) and
                     int(parts[2]) < len(s['pages']))
    elif kind == 'gl' and len(parts) == 3:
        valid = bool(s['mode'] == 'glos' and s.get('glos') and
                     parts[1] == s.get('glos_id') and
                     parts[2] in {str(i) for i in s['glos']})
    if not valid:
        await q.answer(tr(lang, 'expired'))
        return
    await q.answer()
    await remove_callback_keyboard(update)
    chat_id = update.effective_chat.id
    if kind == 'quiz':
        if action == 'stop':
            await cmd_menu(update, ctx)
        elif action == 'next':
            active['idx'] += 1
            active['answered'] = False
            await send_next_question(update, ctx, chat_id)
        else:
            given = action == 'tf:1' if action.startswith('tf:') else int(action[4:])
            await quiz_feedback(update, ctx, chat_id, given)
    elif kind == 'ex':
        if action == 'show':
            await ex_reveal(update, ctx, chat_id)
        elif action.startswith('ans:'):
            await ex_grade_choice(update, ctx, chat_id, int(action[4:]))
        elif action.startswith('self:'):
            await ex_self_grade(update, ctx, chat_id, action == 'self:1')
        else:
            if action == 'skip':
                active['skipped'] += 1
            active['idx'] += 1
            active['shown'] = active['graded'] = False
            await send_exercise(update, ctx, chat_id)
    elif kind == 'page':
        await send_page(update, ctx, chat_id, int(parts[2]))
    else:
        g = KB['glossary'][int(parts[2])]
        enter_mode(chat_id, 'glos')
        await send(update, ctx, f"{g['term']} — {g['def']}", menu_keyboard(lang))


# ------------------------------------------------------------- esercizi
async def start_exercises(update, ctx, chat_id):
    s = enter_mode(chat_id, "ex")
    lang = s["lang"] or "it"
    s["mode"] = "ex"
    rows = []
    nums = sorted(KB["_chapters"].keys())
    for i in range(0, len(nums), MAX_CHAPTER_BUTTONS_PER_ROW):
        rows.append([
            InlineKeyboardButton(
                chapter_label(KB, num, lang)[:60],
                callback_data=f"ex:chap:{num}")
            for num in nums[i:i + MAX_CHAPTER_BUTTONS_PER_ROW]
        ])
    rows.append([InlineKeyboardButton(tr(lang, "btn_menu"), callback_data="back:menu")])
    await send(update, ctx, tr(lang, "ex_choose"), InlineKeyboardMarkup(rows))


async def ex_chapter(update, ctx, chat_id, num):
    s = enter_mode(chat_id, "ex")
    lang = s["lang"] or "it"
    items = [e["source_id"] for e in KB["exercises"] if e["ch"] == num and e.get("quiz_eligible", True)]
    if not items:
        await send(update, ctx, tr(lang, "exp_notfound"))
        return
    s["ex"] = {"id": secrets.token_hex(4), "ch": num, "items": items, "idx": 0, "shown": False,
               "graded": False, "score": 0, "done": 0, "skipped": 0}
    await send_exercise(update, ctx, chat_id)


def current_exercise(ex):
    if not ex or ex["idx"] >= len(ex["items"]):
        return None
    return EXERCISES[ex["items"][ex["idx"]]]


async def send_exercise(update, ctx, chat_id):
    s = st(chat_id)
    lang = s["lang"] or "it"
    ex = s["ex"]
    e = current_exercise(ex)
    if e is None:
        enter_mode(chat_id, None)
        await send(update, ctx, tr(lang, "ex_done", n=ex["ch"], c=ex["score"], t=ex["done"], s=ex["skipped"]),
                   menu_keyboard(lang))
        return
    text = render.exercise_prompt(KB, lang, e, ex["idx"] + 1, len(ex["items"]))
    cb = lambda action: session_data('ex', ex, action)
    rows = []
    if e["check_mode"] == "scelta_multipla":
        rows.append([InlineKeyboardButton(LETTERS[j], callback_data=cb(f"ans:{j}"))
                     for j in range(min(len(e["options"]), len(LETTERS)))])
    rows.append([
        InlineKeyboardButton(tr(lang, "btn_show"), callback_data=cb("show")),
        InlineKeyboardButton(tr(lang, "btn_skip"), callback_data=cb("skip")),
        InlineKeyboardButton(tr(lang, "btn_menu"), callback_data="back:menu"),
    ])
    await send(update, ctx, text, InlineKeyboardMarkup(rows), parse_mode='HTML')


def ex_next_keyboard(lang, ex):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(tr(lang, "btn_next_ex"), callback_data=session_data("ex", ex, "next")),
        InlineKeyboardButton(tr(lang, "btn_menu"), callback_data="back:menu"),
    ]])


def ex_self_keyboard(lang, ex):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(tr(lang, "btn_self_ok"), callback_data=session_data("ex", ex, "self:1")),
        InlineKeyboardButton(tr(lang, "btn_self_ko"), callback_data=session_data("ex", ex, "self:0")),
    ], [InlineKeyboardButton(tr(lang, "btn_menu"), callback_data="back:menu")]])


async def ex_finish(update, ctx, ex, lang, head, e, good):
    """Registra il punteggio e mostra la soluzione del libro con la sua spiegazione."""
    ex["shown"] = ex["graded"] = True
    ex["done"] += 1
    ex["score"] += int(bool(good))
    text = (f"{head}\n\n{render.solution_html(KB, lang, e)}\n\n"
            f"{tr(lang, 'ex_score', c=ex['score'], t=ex['done'])}")
    await send(update, ctx, text, ex_next_keyboard(lang, ex), parse_mode="HTML")


async def ex_answer_typed(update, ctx, chat_id, typed):
    s = st(chat_id)
    lang = s["lang"] or "it"
    ex = s.get("ex")
    e = current_exercise(ex)
    if e is None:
        return
    if ex.get("shown"):
        await send(update, ctx, tr(lang, "already"))
        return
    mode = e["check_mode"]
    yours = tr(lang, "ex_your", a=render.esc(typed))
    if mode in ("automatico", "automatico_con_varianti"):
        good = book_quiz.check_answer(e, typed)
        await ex_finish(update, ctx, ex, lang, f"{tr(lang, 'ex_right' if good else 'ex_wrong')}\n{yours}", e, good)
    elif mode == "parti":
        results = book_quiz.check_parts(e, typed)
        right = sum(ok for _, _, ok in results)
        good = bool(results) and right == len(results)
        head = (f"{tr(lang, 'ex_right' if good else 'ex_wrong')}\n{render.parts_report(lang, results)}\n"
                f"{tr(lang, 'ex_parts', c=right, t=len(results))}")
        await ex_finish(update, ctx, ex, lang, head, e, good)
    elif mode == "scelta_multipla":
        choice = typed.strip().rstrip(').').upper()
        options = e.get("options") or []
        idx = LETTERS.find(choice) if len(choice) == 1 else -1
        if not 0 <= idx < len(options):
            idx = next((j for j, o in enumerate(options) if book_quiz.norm(o) == book_quiz.norm(typed)), -1)
        if idx < 0:
            await send(update, ctx, tr(lang, "ex_use_buttons"))
            return
        await ex_grade_choice(update, ctx, chat_id, idx)
    else:
        ex["shown"] = True
        text = f"{yours}\n\n{render.solution_html(KB, lang, e)}\n\n{tr(lang, 'ex_self_ask')}"
        await send(update, ctx, text, ex_self_keyboard(lang, ex), parse_mode="HTML")


async def ex_grade_choice(update, ctx, chat_id, idx):
    s = st(chat_id)
    lang = s["lang"] or "it"
    ex = s.get("ex")
    e = current_exercise(ex)
    if e is None or ex.get("shown"):
        return
    good = idx == e["answer_idx"]
    head = (f"{tr(lang, 'ex_right' if good else 'ex_wrong')}\n"
            f"{tr(lang, 'ex_your', a=LETTERS[idx] + ') ' + render.esc(e['options'][idx]))}")
    await ex_finish(update, ctx, ex, lang, head, e, good)


async def ex_reveal(update, ctx, chat_id):
    """«Mostra la soluzione»: autovalutazione → chiede se hai risposto bene; altrimenti 0 punti."""
    s = st(chat_id)
    lang = s["lang"] or "it"
    ex = s.get("ex")
    e = current_exercise(ex)
    if e is None or ex.get("shown"):
        return
    if e["check_mode"] == "autovalutazione":
        ex["shown"] = True
        text = f"{render.solution_html(KB, lang, e)}\n\n{tr(lang, 'ex_self_ask')}"
        await send(update, ctx, text, ex_self_keyboard(lang, ex), parse_mode="HTML")
        return
    await ex_finish(update, ctx, ex, lang, tr(lang, "ex_shown"), e, False)


async def ex_self_grade(update, ctx, chat_id, good):
    s = st(chat_id)
    lang = s["lang"] or "it"
    ex = s.get("ex")
    if not ex or ex.get("graded"):
        return
    ex["graded"] = True
    ex["done"] += 1
    ex["score"] += int(good)
    await send(update, ctx, tr(lang, "ex_score", c=ex["score"], t=ex["done"]), ex_next_keyboard(lang, ex))


# ------------------------------------------------------- spiegazioni ecc.
async def explain(update, ctx, chat_id, query):
    s = enter_mode(chat_id, "exp")
    lang = s["lang"] or "it"
    (kind, num), how = kbmod.search(KB, query)
    if kind == "verbs":
        if num:
            await verbs_lookup(update, ctx, chat_id, num)
        else:
            s["mode"] = "verbs"
            await send(update, ctx, tr(lang, "verbs_ask"))
        return
    if kind == "glossary":
        await start_glossary_query(update, ctx, chat_id, query)
        return
    if kind == "none":
        await send(update, ctx, tr(lang, "exp_notfound"), menu_keyboard(lang))
        return
    c = KB["_chapters"][num]
    pages = kbmod.explain_summary(KB, num)
    s["pages"] = pages
    s["page_id"] = secrets.token_hex(4)
    s["page_idx"] = 0
    s["mode"] = "exp"
    head = escape(tr(lang, "exp_source", n=num, t=c["title"]), quote=False)
    text = f"<b>{head}</b>\n\n{pages[0]}"
    rows = [[
        InlineKeyboardButton(tr(lang, "btn_full"), callback_data=f"chap:{num}"),
        InlineKeyboardButton(tr(lang, "btn_quiz_ch"), callback_data=f"exquiz:{num}"),
    ], [InlineKeyboardButton(tr(lang, "btn_menu"), callback_data="back:menu")]]
    if len(pages) > 1:
        rows.insert(1, [InlineKeyboardButton(
            tr(lang, "btn_nextpage"), callback_data=f"page:{s['page_id']}:1")])
    await send(update, ctx, text, InlineKeyboardMarkup(rows), parse_mode="HTML")


async def send_chapter(update, ctx, chat_id, num):
    s = enter_mode(chat_id, "chap")
    lang = s["lang"] or "it"
    pages = kbmod.chapter_pages(KB, num)
    s["pages"] = pages
    s["page_id"] = secrets.token_hex(4)
    s["page_idx"] = 0
    head = escape(tr(lang, "exp_source", n=num, t=KB["_chapters"][num]["title"]), quote=False)
    text = f"<b>{head}</b>\n\n{pages[0]}"
    await send(update, ctx, text, pages_keyboard(lang, 0, len(pages), s["page_id"]), parse_mode="HTML")


async def send_page(update, ctx, chat_id, idx):
    s = st(chat_id)
    lang = s["lang"] or "it"
    pages = s.get("pages") or []
    if not pages or not 0 <= idx < len(pages):
        await send(update, ctx, tr(lang, "exp_notfound"))
        return
    s["page_idx"] = idx
    if idx == 0:
        await send(update, ctx, pages[0], pages_keyboard(lang, 0, len(pages), s["page_id"]), parse_mode="HTML")
    else:
        await send(update, ctx, f"[{tr(lang, 'page_of', i=idx + 1, n=len(pages))}]\n\n{pages[idx]}",
                   pages_keyboard(lang, idx, len(pages), s["page_id"]), parse_mode="HTML")


async def verbs_lookup(update, ctx, chat_id, word):
    s = enter_mode(chat_id, "verbs")
    lang = s["lang"] or "it"
    hit = kbmod.verb_lookup(KB, word)
    if hit:
        base, forms = hit
        await send(update, ctx, tr(lang, "verbs_res", b=base, p=forms[0], pp=forms[1]),
                   menu_keyboard(lang))
    else:
        await send(update, ctx, tr(lang, "verbs_nf", w=word.strip()), menu_keyboard(lang))


async def start_glossary(update, ctx, chat_id):
    s = enter_mode(chat_id, "glos")
    s["mode"] = "glos"
    await send(update, ctx, tr(s["lang"] or "it", "glos_ask"))


async def start_glossary_query(update, ctx, chat_id, query):
    s = enter_mode(chat_id, "glos")
    lang = s["lang"] or "it"
    hits = kbmod.glossary_search(KB, query)
    if not hits:
        await send(update, ctx, tr(lang, "glos_nf"), menu_keyboard(lang))
        return
    if len(hits) == 1:
        g = KB["glossary"][hits[0]]
        await send(update, ctx, f"{g['term']} — {g['def']}", menu_keyboard(lang))
        return
    s["glos"] = hits
    s["glos_id"] = secrets.token_hex(4)
    rows = [[InlineKeyboardButton(g["term"][:60], callback_data=f"gl:{s['glos_id']}:{i}")]
            for i, g in zip(hits, [KB["glossary"][i] for i in hits])][:12]
    await send(update, ctx, tr(lang, "glos_pick"), InlineKeyboardMarkup(rows))


# ------------------------------------------------------------- handlers
async def ensure_lang(update, ctx) -> bool:
    chat_id = update.effective_chat.id
    if st(chat_id).get("lang") is None:
        await send(update, ctx, tr("it", "lang_choose"), lang_keyboard())
        await send(update, ctx, tr("en", "lang_choose"), lang_keyboard())
        return False
    return True


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    enter_mode(update.effective_chat.id, None)
    await update.effective_chat.send_message(tr("it", "lang_choose"),
                                             reply_markup=lang_keyboard())
    await update.effective_chat.send_message(tr("en", "lang_choose"),
                                             reply_markup=lang_keyboard())


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    s = enter_mode(update.effective_chat.id, None)
    lang = s['lang'] or 'it'
    await send(update, ctx, tr(lang, 'help'), menu_keyboard(lang))


async def cmd_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    s = enter_mode(update.effective_chat.id, None)
    lang = s['lang'] or 'it'
    await send(update, ctx, tr(lang, 'menu'), menu_keyboard(lang))


async def cmd_quiz(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await ensure_lang(update, ctx):
        return
    await start_quiz(update, ctx, update.effective_chat.id)


async def cmd_ex(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await ensure_lang(update, ctx):
        return
    await start_exercises(update, ctx, update.effective_chat.id)


async def cmd_spiega(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await ensure_lang(update, ctx):
        return
    chat_id = update.effective_chat.id
    s = st(chat_id)
    lang = s["lang"] or "it"
    q = " ".join(ctx.args) if ctx.args else ""
    if not q:
        enter_mode(chat_id, "exp")
        await send(update, ctx, tr(lang, "exp_ask"))
        return
    await explain(update, ctx, chat_id, q)


async def cmd_capitoli(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await ensure_lang(update, ctx):
        return
    await chapters_menu(update, ctx, update.effective_chat.id)


async def cmd_verbi(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await ensure_lang(update, ctx):
        return
    chat_id = update.effective_chat.id
    enter_mode(chat_id, "verbs")
    await send(update, ctx, tr(st(chat_id)["lang"], "verbs_ask"))


async def cmd_glossario(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await ensure_lang(update, ctx):
        return
    chat_id = update.effective_chat.id
    q = " ".join(ctx.args) if ctx.args else ""
    if q:
        await start_glossary_query(update, ctx, chat_id, q)
        return
    await start_glossary(update, ctx, chat_id)


async def cmd_lang(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    enter_mode(update.effective_chat.id, None)
    await send(update, ctx, tr("it", "lang_choose"), lang_keyboard())


async def chapters_menu(update, ctx, chat_id):
    s = enter_mode(chat_id, "chap")
    lang = s["lang"] or "it"
    s["mode"] = "chap"
    nums = sorted(KB["_chapters"].keys())
    rows = []
    for i in range(0, len(nums), MAX_CHAPTER_BUTTONS_PER_ROW):
        rows.append([
            InlineKeyboardButton(chapter_label(KB, num, lang)[:60],
                                 callback_data=f"chap:{num}")
            for num in nums[i:i + MAX_CHAPTER_BUTTONS_PER_ROW]
        ])
    rows.append([InlineKeyboardButton(tr(lang, "btn_menu"), callback_data="back:menu")])
    await send(update, ctx, tr(lang, "chap_list"), InlineKeyboardMarkup(rows))


async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.callback_query is None:
        return
    # Protegge anche da due callback concorrenti; il launcher usa update sequenziali.
    s = st(update.effective_chat.id)
    lock = s.setdefault('_callback_lock', asyncio.Lock())
    async with lock:
        await dispatch_callback(update, ctx)


async def dispatch_callback(update, ctx):
    q = update.callback_query
    chat_id = update.effective_chat.id
    s = st(chat_id)
    data = q.data or ''
    if (data.startswith(('quiz:', 'page:', 'gl:')) or
            data.startswith('ex:') and not data.startswith('ex:chap:')):
        await handle_session_callback(update, ctx)
        return
    await q.answer()
    if data.startswith('lang:'):
        language = data.split(':', 1)[1]
        if language not in ('it', 'en'):
            return
        s = enter_mode(chat_id, None)
        s['lang'] = language
        await send(update, ctx, tr(language, 'welcome'))
        await send(update, ctx, tr(language, 'menu'), menu_keyboard(language))
        return
    if s.get('lang') is None:
        await send(update, ctx, tr('it', 'lang_choose'), lang_keyboard())
        return
    lang = s['lang']
    handlers = {
        'back:menu': cmd_menu, 'menu:quiz': cmd_quiz, 'menu:ex': cmd_ex,
        'menu:exp': cmd_spiega, 'menu:chap': cmd_capitoli,
        'menu:verbs': cmd_verbi, 'menu:glos': cmd_glossario, 'menu:help': cmd_help,
    }
    if data in ('menu:exp', 'menu:glos'):
        if data == 'menu:exp':
            enter_mode(chat_id, 'exp')
            await send(update, ctx, tr(lang, 'exp_ask'))
        else:
            await start_glossary(update, ctx, chat_id)
    elif data in handlers:
        await handlers[data](update, ctx)
    elif data.startswith(('exquiz:', 'ex:chap:', 'chap:')):
        try:
            num = int(data.rsplit(':', 1)[1])
        except ValueError:
            return
        if num not in KB['_chapters']:
            return
        if data.startswith('exquiz:'):
            pool = build_quiz_pool(KB, num)
            if len(pool) < QUIZ_SIZE:
                await send(update, ctx, tr(lang, 'quiz_few', n=len(pool)))
            await start_quiz(update, ctx, chat_id, pre_pool=pool)
        elif data.startswith('ex:chap:'):
            await ex_chapter(update, ctx, chat_id, num)
        else:
            await send_chapter(update, ctx, chat_id, num)


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    s = st(chat_id)
    if s.get("lang") is None:
        await cmd_start(update, ctx)
        return
    lang = s["lang"]
    text = (update.message.text or "").strip()
    if not text:
        return
    mode = s.get("mode")

    if mode == "exp":
        await explain(update, ctx, chat_id, text)
        return
    if mode == "verbs":
        await verbs_lookup(update, ctx, chat_id, text.split()[0])
        return
    if mode == "glos":
        await start_glossary_query(update, ctx, chat_id, text)
        return
    if mode == "quiz" and s.get("quiz"):
        await send(update, ctx, tr(lang, "already"))
        return
    if mode == "ex" and s.get("ex"):
        # risposta all'esercizio corrente: correzione automatica o autovalutazione
        await ex_answer_typed(update, ctx, chat_id, text)
        return
    if mode == "chap":
        (kind, num), _ = kbmod.search(KB, text)
        if kind == "chapter":
            await send_chapter(update, ctx, chat_id, num)
            return
    # fallback: prova a cercare l'argomento
    await explain(update, ctx, chat_id, text)


# ------------------------------------------------------------------ main
def main():
    token = load_bot_token()
    if not token:
        print("Token mancante. Crea il bot con @BotFather su Telegram, poi:\n"
              "  cp .env.example .env   # e incolla il token in BOT_TOKEN=\n"
              "oppure: export BOT_TOKEN=123456:ABC...")
        sys.exit(1)
    configure_logging(token)
    app = Application.builder().token(token).concurrent_updates(False).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("quiz", cmd_quiz))
    app.add_handler(CommandHandler("esercizi", cmd_ex))
    app.add_handler(CommandHandler("spiega", cmd_spiega))
    app.add_handler(CommandHandler("capitoli", cmd_capitoli))
    app.add_handler(CommandHandler("verbi", cmd_verbi))
    app.add_handler(CommandHandler("glossario", cmd_glossario))
    app.add_handler(CommandHandler("lang", cmd_lang))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    c = KB["meta"]["counts"]
    log.info("KB caricata: %s capitoli, %s esempi, %s esercizi (%s MCQ), "
             "%s verbi, %s voci di glossario",
             c["chapters"], c["examples_ok"] + c["examples_bad"],
             c["exercises"], c["exercises_mcq"], c["verbs"], c["glossary"])
    print(f"Tutor avviato. Contenuti: {c['chapters']} capitoli, "
          f"{c['examples_ok'] + c['examples_bad']} esempi, {c['exercises']} esercizi, "
          f"{c['verbs']} verbi irregolari, {c['glossary']} voci di glossario. "
          "Ctrl-C per fermare.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
