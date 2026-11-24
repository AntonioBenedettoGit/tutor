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

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, MessageHandler, filters)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tutor import book_quiz, render
from tutor.logging_config import configure_logging
from tutor import kb as kbmod                      # noqa: E402
from tutor.texts import (COMMANDS, DESCRIPTION, ICON, PARTS, SHORT_DESCRIPTION, T,  # noqa: E402
                         chapter_title, help_text, lang_keyboard, menu_keyboard, part_of,
                         reply_keyboard, reply_labels, stars, tr, verdict)

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


# ------------------------------------------------------------------ utils
def st(chat_id):
    if chat_id not in STATE:
        STATE[chat_id] = {"lang": None, "mode": None, "quiz": None,
                          "ex": None, "pages": None, "glos": None, "redo": None,
                          "progress": {"ex": {}, "quiz": {}, "theory": set()}}
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


async def send(update, ctx, text, keyboard=None, parse_mode="HTML"):
    """Tutti i messaggi sono HTML Telegram: ogni testo dinamico passa da escape()."""
    text = clean_for_display(text)
    # Non tagliare HTML a meta tag/entita: gli esercizi attuali sono sotto soglia.
    if parse_mode and len(text) > 4096:
        raise ValueError("Messaggio formattato troppo lungo")
    return await update.effective_chat.send_message(
        text[:4096], reply_markup=keyboard, parse_mode=parse_mode)


def enter_mode(chat_id, mode):
    """Ogni cambio di attivita invalida tutte le sessioni precedenti."""
    s = st(chat_id)
    for key in ("quiz", "ex", "pages", "glos", "page_id", "glos_id", "page_idx", "page_ch", "page_summary"):
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


# ------------------------------------------------------------------ navigazione
NAV_PURPOSES = ("chap", "ex", "quiz")
PART_ORDER = list(PARTS)
REPLY_LABELS = reply_labels()                    # testo bottone fisso -> azione
LABEL_LANG = {T[l][k]: l for l in T for k in ("kb_quiz", "kb_ex", "kb_theory", "kb_menu")
              if T["it"][k] != T["en"][k]}       # etichette diverse tra IT e EN


def progress(s):
    """Progressi della sessione (solo in memoria: si azzerano al riavvio del bot)."""
    return s.setdefault("progress", {"ex": {}, "quiz": {}, "theory": set()})


def chapters_of_part(part):
    return [n for n in sorted(KB["_chapters"]) if part_of(KB["_chapters"][n]) == part]


def chapter_mark(s, purpose, num):
    prog = progress(s)
    if purpose == "theory":
        return "  ✓" if num in prog["theory"] else ""
    hit = prog[purpose].get(num)
    return f"  ✅ {hit[0]}/{hit[1]}" if hit else ""


def parts_keyboard(lang, purpose):
    rows = []
    col = 0 if lang == "it" else 1
    for p in PART_ORDER:
        nums = chapters_of_part(p)
        if not nums:
            continue
        rows.append([InlineKeyboardButton(
            tr(lang, "part_btn", p=p, t=PARTS[p][col], a=nums[0], b=nums[-1]),
            callback_data=f"part:{purpose}:{p}")])
    rows.append([InlineKeyboardButton(tr(lang, "btn_menu"), callback_data="back:menu")])
    return InlineKeyboardMarkup(rows)


def part_keyboard(s, lang, purpose, part):
    target = {"chap": "chap:{n}", "ex": "ex:chap:{n}", "quiz": "exquiz:{n}"}[purpose]
    mark_kind = {"chap": "theory", "ex": "ex", "quiz": "quiz"}[purpose]
    rows = [[InlineKeyboardButton(
        f"{n}. {chapter_title(KB, n, lang)}{chapter_mark(s, mark_kind, n)}"[:64],
        callback_data=target.format(n=n))] for n in chapters_of_part(part)]
    rows.append([InlineKeyboardButton(tr(lang, "btn_parts"), callback_data=f"pick:{purpose}"),
                 InlineKeyboardButton(tr(lang, "btn_menu"), callback_data="back:menu")])
    return InlineKeyboardMarkup(rows)


async def show(update, ctx, text, keyboard=None, edit=False):
    """Navigazione: se richiesto modifica il messaggio del bottone premuto, altrimenti ne invia uno nuovo."""
    q = update.callback_query
    if edit and q is not None:
        try:
            await q.edit_message_text(clean_for_display(text), parse_mode="HTML", reply_markup=keyboard)
            return
        except TelegramError as exc:
            log.info("Modifica non riuscita, invio un nuovo messaggio: %s", type(exc).__name__)
    await send(update, ctx, text, keyboard)


async def parts_menu(update, ctx, chat_id, purpose, edit=False):
    s = enter_mode(chat_id, {"chap": "chap", "ex": "ex", "quiz": None}[purpose])
    lang = s["lang"] or "it"
    await show(update, ctx, tr(lang, f"pick_part_{purpose}"), parts_keyboard(lang, purpose), edit)


async def part_menu(update, ctx, chat_id, purpose, part, edit=False):
    s = enter_mode(chat_id, {"chap": "chap", "ex": "ex", "quiz": None}[purpose])
    lang = s["lang"] or "it"
    icon = {"chap": ICON["theory"], "ex": ICON["ex"], "quiz": ICON["quiz"]}[purpose]
    title = PARTS[part][0 if lang == "it" else 1]
    await show(update, ctx, tr(lang, "pick_chapter", icon=icon, p=part, t=escape(title, quote=False)),
               part_keyboard(s, lang, purpose, part), edit)


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


async def start_quiz(update, ctx, chat_id, chapter=None, pre_pool=None, redo=False):
    s = st(chat_id)
    lang = s["lang"] or "it"
    pool = copy.deepcopy(pre_pool if pre_pool is not None else build_quiz_pool(KB, chapter))
    if not pool:
        await send(update, ctx, tr(lang, "exp_notfound"))
        return
    s = enter_mode(chat_id, "quiz")
    s["quiz"] = {"id": secrets.token_hex(4), "pool": pool, "idx": 0, "score": 0, "answered": False,
                 "wrong": [], "chapter": chapter, "redo": redo}
    await send(update, ctx, tr(lang, "quiz_start", n=len(pool)))
    await send_next_question(update, ctx, chat_id)


def quiz_summary(s, lang, qz):
    """Riepilogo finale: stelle, giudizio, domande sbagliate e capitoli da ripassare."""
    c, t = qz["score"], len(qz["pool"])
    lines = [tr(lang, "quiz_done"), "",
             tr(lang, "result_line", stars=stars(c, t), c=c, t=t), verdict(lang, c, t)]
    wrong = qz.get("wrong") or []
    chapters = []
    if wrong:
        lines += ["", tr(lang, "review_head")]
        for ref in wrong:
            item = book_quiz.resolve(KB, ref)
            lines.append(f"✗ {render.quiz_snippet(KB, ref, item)} <i>· {tr(lang, 'ch_short', n=ref['ch'])}</i>")
            if ref["ch"] not in chapters:
                chapters.append(ref["ch"])
    chapters.sort(key=lambda ch: -sum(r["ch"] == ch for r in wrong))
    rows = []
    if wrong:
        s["redo"] = {"id": secrets.token_hex(4), "chapter": qz.get("chapter"),
                     "pool": [{k: v for k, v in r.items() if k not in ("opts", "answer_idx")} for r in wrong]}
        rows.append([InlineKeyboardButton(tr(lang, "btn_redo", n=len(wrong)),
                                          callback_data=f"redo:{s['redo']['id']}")])
        rows.append([InlineKeyboardButton(tr(lang, "btn_review_ch", n=ch), callback_data=f"chap:{ch}")
                     for ch in chapters[:2]])
    else:
        s["redo"] = None
    again = f"exquiz:{qz['chapter']}" if qz.get("chapter") else "menu:quiz"
    rows.append([InlineKeyboardButton(tr(lang, "quiz_again"), callback_data=again),
                 InlineKeyboardButton(tr(lang, "btn_menu"), callback_data="back:menu")])
    return "\n".join(lines), InlineKeyboardMarkup(rows)


async def send_next_question(update, ctx, chat_id):
    s = st(chat_id)
    lang = s["lang"] or "it"
    qz = s["quiz"]
    if qz["idx"] >= len(qz["pool"]):
        if qz.get("chapter") and not qz.get("redo"):
            progress(s)["quiz"][qz["chapter"]] = (qz["score"], len(qz["pool"]))
        text, keyboard = quiz_summary(s, lang, qz)
        await send(update, ctx, text, keyboard)
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
    await send(update, ctx, text, quiz_keyboard(lang, ref_item, qz))


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
    else:
        qz.setdefault("wrong", []).append(ref_item)
    text = render.quiz_feedback(KB, lang, ref_item, item, good, qz["score"], qz["idx"] + 1, given)
    kb_btn = InlineKeyboardMarkup([[
        InlineKeyboardButton(tr(lang, "btn_next"), callback_data=session_data("quiz", qz, "next")),
        InlineKeyboardButton(tr(lang, "btn_stop_quiz"), callback_data=session_data("quiz", qz, "stop")),
    ]])
    await send(update, ctx, text, kb_btn)


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
        cur = s.get('page_idx', 0) or 0
        valid = bool(s['mode'] in ('chap', 'exp') and s.get('pages') and
                     parts[1] == s.get('page_id') and
                     parts[2] in (str(cur - 1), str(cur + 1)) and
                     parts[2].isdigit() and int(parts[2]) < len(s['pages']))
    elif kind == 'gl' and len(parts) == 3:
        valid = bool(s['mode'] == 'glos' and s.get('glos') and
                     parts[1] == s.get('glos_id') and
                     parts[2] in {str(i) for i in s['glos']})
    if not valid:
        await q.answer(tr(lang, 'expired'))
        return
    await q.answer()
    chat_id = update.effective_chat.id
    if kind == 'page':                      # le pagine di teoria si sfogliano nello stesso messaggio
        await send_page(update, ctx, chat_id, int(parts[2]), edit=True)
        return
    await remove_callback_keyboard(update)
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
    else:
        g = KB['glossary'][int(parts[2])]
        enter_mode(chat_id, 'glos')
        await send(update, ctx, glossary_html(lang, g), menu_keyboard(lang))


# ------------------------------------------------------------- esercizi
async def start_exercises(update, ctx, chat_id, edit=False):
    await parts_menu(update, ctx, chat_id, "ex", edit)


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


def ex_summary(s, lang, ex):
    n = ex["ch"]
    c, t = ex["score"], len(ex["items"])
    progress(s)["ex"][n] = (c, t)
    lines = [tr(lang, "ex_done", n=n), "",
             tr(lang, "result_line", stars=stars(c, t), c=c, t=t), verdict(lang, c, t)]
    if ex["skipped"]:
        lines.append(f"<i>{tr(lang, 'ex_skipped', s=ex['skipped'])}</i>")
    first = [InlineKeyboardButton(tr(lang, "btn_redo_ex"), callback_data=f"ex:chap:{n}")]
    if n + 1 in KB["_chapters"]:
        first.append(InlineKeyboardButton(tr(lang, "btn_next_chapter", n=n + 1), callback_data=f"ex:chap:{n + 1}"))
    rows = [first, [InlineKeyboardButton(tr(lang, "btn_theory_ch", n=n), callback_data=f"chap:{n}"),
                    InlineKeyboardButton(tr(lang, "btn_menu"), callback_data="back:menu")]]
    return "\n".join(lines), InlineKeyboardMarkup(rows)


async def send_exercise(update, ctx, chat_id):
    s = st(chat_id)
    lang = s["lang"] or "it"
    ex = s["ex"]
    e = current_exercise(ex)
    if e is None:
        text, keyboard = ex_summary(s, lang, ex)
        enter_mode(chat_id, None)
        await send(update, ctx, text, keyboard)
        return
    text = render.exercise_prompt(KB, lang, e, ex["idx"] + 1, len(ex["items"]))
    cb = lambda action: session_data('ex', ex, action)
    rows = []
    if e["check_mode"] == "scelta_multipla":
        rows.append([InlineKeyboardButton(LETTERS[j], callback_data=cb(f"ans:{j}"))
                     for j in range(min(len(e["options"]), len(LETTERS)))])
    rows.append([InlineKeyboardButton(tr(lang, "btn_show"), callback_data=cb("show"))])
    rows.append([
        InlineKeyboardButton(tr(lang, "btn_skip"), callback_data=cb("skip")),
        InlineKeyboardButton(tr(lang, "btn_menu"), callback_data="back:menu"),
    ])
    await send(update, ctx, text, InlineKeyboardMarkup(rows))


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


def ex_score_line(lang, ex):
    return f"<i>{tr(lang, 'ex_score', c=ex['score'], t=ex['done'])}</i>"


async def ex_finish(update, ctx, ex, lang, head, e, good):
    """Registra il punteggio e mostra la soluzione del libro con la sua spiegazione."""
    ex["shown"] = ex["graded"] = True
    ex["done"] += 1
    ex["score"] += int(bool(good))
    text = f"{head}\n\n{render.solution_html(KB, lang, e)}\n\n{ex_score_line(lang, ex)}"
    await send(update, ctx, text, ex_next_keyboard(lang, ex))


def verdict_head(lang, good):
    return f"<b>{tr(lang, 'ex_right' if good else 'ex_wrong')}</b>"


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
        await ex_finish(update, ctx, ex, lang, f"{verdict_head(lang, good)}\n{yours}", e, good)
    elif mode == "parti":
        results = book_quiz.check_parts(e, typed)
        right = sum(ok for _, _, ok in results)
        good = bool(results) and right == len(results)
        head = (f"{verdict_head(lang, good)}\n{render.parts_report(lang, results)}\n"
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
        text = f"{yours}\n\n{render.solution_html(KB, lang, e)}\n\n<b>{tr(lang, 'ex_self_ask')}</b>"
        await send(update, ctx, text, ex_self_keyboard(lang, ex))


async def ex_grade_choice(update, ctx, chat_id, idx):
    s = st(chat_id)
    lang = s["lang"] or "it"
    ex = s.get("ex")
    e = current_exercise(ex)
    if e is None or ex.get("shown"):
        return
    good = idx == e["answer_idx"]
    head = (f"{verdict_head(lang, good)}\n"
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
        text = f"{render.solution_html(KB, lang, e)}\n\n<b>{tr(lang, 'ex_self_ask')}</b>"
        await send(update, ctx, text, ex_self_keyboard(lang, ex))
        return
    await ex_finish(update, ctx, ex, lang, f"<i>{tr(lang, 'ex_shown')}</i>", e, False)


async def ex_self_grade(update, ctx, chat_id, good):
    s = st(chat_id)
    lang = s["lang"] or "it"
    ex = s.get("ex")
    if not ex or ex.get("graded"):
        return
    ex["graded"] = True
    ex["done"] += 1
    ex["score"] += int(good)
    await send(update, ctx, ex_score_line(lang, ex), ex_next_keyboard(lang, ex))


# ------------------------------------------------------- teoria, ricerca ecc.
def pages_keyboard(lang, idx, total, page_id, num=None, summary=False):
    rows = []
    nav = []
    if idx > 0:
        nav.append(InlineKeyboardButton(tr(lang, "btn_prev"), callback_data=f"page:{page_id}:{idx - 1}"))
    if idx + 1 < total:
        nav.append(InlineKeyboardButton(tr(lang, "btn_nextpage"), callback_data=f"page:{page_id}:{idx + 1}"))
    if nav:
        rows.append(nav)
    if num is not None:
        if summary:
            rows.append([InlineKeyboardButton(tr(lang, "btn_full"), callback_data=f"chap:{num}")])
        rows.append([InlineKeyboardButton(tr(lang, "btn_ex_ch"), callback_data=f"ex:chap:{num}"),
                     InlineKeyboardButton(tr(lang, "btn_quiz_ch"), callback_data=f"exquiz:{num}")])
        part = part_of(KB["_chapters"][num])
        rows.append([InlineKeyboardButton(tr(lang, "btn_back_part", p=part), callback_data=f"part:chap:{part}"),
                     InlineKeyboardButton(tr(lang, "btn_menu"), callback_data="back:menu")])
    else:
        rows.append([InlineKeyboardButton(tr(lang, "btn_menu"), callback_data="back:menu")])
    return InlineKeyboardMarkup(rows)


def page_text(s, lang, idx):
    num, pages = s.get("page_ch"), s["pages"]
    if num is None:
        return pages[idx]
    sub = ""
    if lang == "it":
        sub = escape(KB["_chapters"][num]["title"], quote=False) + " · "
    if s.get("page_summary"):
        sub += tr(lang, "summary_sub")
    head = tr(lang, "theory_head", n=num, t=escape(chapter_title(KB, num, lang), quote=False))
    return f"{head}\n{tr(lang, 'theory_sub', t=sub, i=idx + 1, k=len(pages))}\n\n{pages[idx]}"


async def open_pages(update, ctx, s, num, pages, summary):
    s["pages"] = pages
    s["page_id"] = secrets.token_hex(4)
    s["page_idx"] = 0
    s["page_ch"] = num
    s["page_summary"] = summary
    lang = s["lang"] or "it"
    await send(update, ctx, page_text(s, lang, 0),
               pages_keyboard(lang, 0, len(pages), s["page_id"], num, summary))


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
    s["mode"] = "exp"
    await open_pages(update, ctx, s, num, kbmod.explain_summary(KB, num), summary=True)


async def send_chapter(update, ctx, chat_id, num):
    s = enter_mode(chat_id, "chap")
    progress(s)["theory"].add(num)
    await open_pages(update, ctx, s, num, kbmod.chapter_pages(KB, num), summary=False)


async def send_page(update, ctx, chat_id, idx, edit=False):
    s = st(chat_id)
    lang = s["lang"] or "it"
    pages = s.get("pages") or []
    if not pages or not 0 <= idx < len(pages):
        await send(update, ctx, tr(lang, "exp_notfound"))
        return
    s["page_idx"] = idx
    await show(update, ctx, page_text(s, lang, idx),
               pages_keyboard(lang, idx, len(pages), s["page_id"], s.get("page_ch"), s.get("page_summary")),
               edit)


async def verbs_lookup(update, ctx, chat_id, word):
    s = enter_mode(chat_id, "verbs")
    lang = s["lang"] or "it"
    hit = kbmod.verb_lookup(KB, word)
    e = lambda t: escape(t, quote=False)
    if hit:
        base, forms = hit
        await send(update, ctx, tr(lang, "verbs_res", b=e(base), p=e(forms[0]), pp=e(forms[1])),
                   menu_keyboard(lang))
    else:
        await send(update, ctx, tr(lang, "verbs_nf", w=e(word.strip())), menu_keyboard(lang))


def glossary_html(lang, g):
    return tr(lang, "glos_res", t=escape(g["term"], quote=False), d=escape(g["def"], quote=False))


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
        await send(update, ctx, glossary_html(lang, KB["glossary"][hits[0]]), menu_keyboard(lang))
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
    await send(update, ctx, help_text(lang), menu_keyboard(lang))


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


async def chapters_menu(update, ctx, chat_id, edit=False):
    await parts_menu(update, ctx, chat_id, "chap", edit)


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
    if data.startswith('redo:'):
        redo = s.get('redo')
        if s.get('lang') is None or not redo or data != f"redo:{redo['id']}":
            await q.answer(tr(s.get('lang') or 'it', 'expired'))
            return
        await q.answer()
        s['redo'] = None
        await remove_callback_keyboard(update)
        await start_quiz(update, ctx, chat_id, chapter=redo['chapter'], pre_pool=redo['pool'], redo=True)
        return
    await q.answer()
    if data.startswith('lang:'):
        language = data.split(':', 1)[1]
        if language not in ('it', 'en'):
            return
        s = enter_mode(chat_id, None)
        s['lang'] = language
        await send(update, ctx, tr(language, 'welcome'), reply_keyboard(language))
        await send(update, ctx, tr(language, 'menu'), menu_keyboard(language))
        return
    if s.get('lang') is None:
        await send(update, ctx, tr('it', 'lang_choose'), lang_keyboard())
        return
    lang = s['lang']
    handlers = {
        'back:menu': cmd_menu, 'menu:quiz': cmd_quiz,
        'menu:exp': cmd_spiega, 'menu:verbs': cmd_verbi, 'menu:glos': cmd_glossario,
        'menu:help': cmd_help,
    }
    pick = {'menu:ex': 'ex', 'menu:chap': 'chap', 'menu:qpick': 'quiz', 'pick:ex': 'ex', 'pick:chap': 'chap', 'pick:quiz': 'quiz'}
    if data in ('menu:exp', 'menu:glos'):
        if data == 'menu:exp':
            enter_mode(chat_id, 'exp')
            await send(update, ctx, tr(lang, 'exp_ask'))
        else:
            await start_glossary(update, ctx, chat_id)
    elif data in pick:
        # dal menu: nuovo messaggio; «◀️ Parti» dentro la navigazione: stesso messaggio
        await parts_menu(update, ctx, chat_id, pick[data], edit=data.startswith('pick:'))
    elif data.startswith('part:'):
        bits = data.split(':')
        if len(bits) == 3 and bits[1] in NAV_PURPOSES and bits[2] in PARTS:
            # dal riepilogo di una pagina di teoria il messaggio resta: si apre la lista sotto
            from_page = bits[1] == 'chap' and s.get('mode') == 'chap' and s.get('pages')
            await part_menu(update, ctx, chat_id, bits[1], bits[2], edit=not from_page)
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
            await start_quiz(update, ctx, chat_id, chapter=num, pre_pool=pool)
        elif data.startswith('ex:chap:'):
            await ex_chapter(update, ctx, chat_id, num)
        else:
            await send_chapter(update, ctx, chat_id, num)


async def reply_button(update, ctx, chat_id, action):
    """Bottoni fissi in basso (tastiera di risposta)."""
    if action == "quiz":
        await start_quiz(update, ctx, chat_id)
    elif action == "ex":
        await start_exercises(update, ctx, chat_id)
    elif action == "theory":
        await chapters_menu(update, ctx, chat_id)
    else:
        await cmd_menu(update, ctx)


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    s = st(chat_id)
    text = (update.message.text or "").strip()
    if text in REPLY_LABELS:
        # Prima di tutto: un bottone fisso non è mai una risposta a un esercizio.
        if s.get("lang") is None:
            # dopo un riavvio del bot la lingua si ricava dal bottone (o dal telefono)
            user = getattr(update, "effective_user", None)
            code = (getattr(user, "language_code", None) or "it").lower()
            s["lang"] = LABEL_LANG.get(text) or ("it" if code.startswith("it") else "en")
        await reply_button(update, ctx, chat_id, REPLY_LABELS[text])
        return
    if s.get("lang") is None:
        await cmd_start(update, ctx)
        return
    lang = s["lang"]
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


# ------------------------------------------------------------------ avvio
async def _sync_profile(bot_api):
    """Menu «/» con descrizioni, testo prima di «Avvia» e descrizione breve, IT e EN.
    Scrive solo se il testo è cambiato; un errore qui non deve mai fermare il bot."""
    for code, col in ((None, 2), ("it", 1)):
        lang = "it" if code else "en"
        kw = {"language_code": code} if code else {}
        try:
            wanted = [BotCommand(c[0], c[col]) for c in COMMANDS]
            current = await bot_api.get_my_commands(**kw)
            if [(c.command, c.description) for c in current] != [(c.command, c.description) for c in wanted]:
                await bot_api.set_my_commands(wanted, **kw)
            if (await bot_api.get_my_description(**kw)).description != DESCRIPTION[lang]:
                await bot_api.set_my_description(DESCRIPTION[lang], **kw)
            if (await bot_api.get_my_short_description(**kw)).short_description != SHORT_DESCRIPTION[lang]:
                await bot_api.set_my_short_description(SHORT_DESCRIPTION[lang], **kw)
        except Exception as exc:  # noqa: BLE001 - solo estetica: si prosegue
            log.warning("Profilo bot (%s) non aggiornato: %s", lang, type(exc).__name__)


async def post_init(application):
    await _sync_profile(application.bot)


def register_handlers(app):
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
    return app


def main():
    token = load_bot_token()
    if not token:
        print("Token mancante. Crea il bot con @BotFather su Telegram, poi:\n"
              "  cp .env.example .env   # e incolla il token in BOT_TOKEN=\n"
              "oppure: export BOT_TOKEN=123456:ABC...")
        sys.exit(1)
    configure_logging(token)
    app = Application.builder().token(token).concurrent_updates(False).post_init(post_init).build()
    register_handlers(app)

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
