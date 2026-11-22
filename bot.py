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
import json
import logging
import os
import random
import sys
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, MessageHandler, filters)

sys.path.insert(0, str(Path(__file__).resolve().parent))
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

QUIZ_SIZE = 10          # domande per sessione di quiz
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


async def send(update, ctx, text, keyboard=None):
    await update.effective_chat.send_message(text[:4096],
                                             reply_markup=keyboard)


def chapter_label(kb, num, lang):
    c = kb["_chapters"][num]
    return f"{num}. {c['title']}"


def pages_keyboard(lang, idx, total):
    row = []
    if idx + 1 < total:
        row.append(InlineKeyboardButton(tr(lang, "btn_nextpage"),
                                        callback_data=f"page:{idx + 1}"))
    row.append(InlineKeyboardButton(tr(lang, "btn_menu"), callback_data="back:menu"))
    return InlineKeyboardMarkup([row]) if row else None


# ------------------------------------------------------------------ quiz
def build_quiz_pool(kb, chapter=None, limit=QUIZ_SIZE):
    """Mescola tre tipi di domanda: vero/falso, quale è corretta, scelta multipla.
    Garantisce fino a 3 domande a scelta multipla per quiz quando esistono."""
    mcq = [e for e in kb["exercises"]
           if e["options"] and e["answer_idx"] is not None
           and (chapter is None or e["ch"] == chapter)]
    tf = [{"type": "tf", "t": e["t"], "ok": e["ok"], "ch": e["ch"]}
          for e in kb["examples"] if chapter is None or e["ch"] == chapter]
    fix = [{"type": "fix", "bad": f["bad"], "good": f["good"], "ch": f["ch"]}
           for f in kb["fixes"] if chapter is None or f["ch"] == chapter]
    random.shuffle(mcq)
    pool = [{"type": "mcq", **e} for e in mcq[:3]]
    rest = tf + fix
    random.shuffle(rest)
    pool.extend(rest[:max(limit - len(pool), 0)])
    if chapter is not None and len(pool) < 4:
        return build_quiz_pool(kb, None, limit)
    random.shuffle(pool)
    return pool[:limit]


def quiz_question_text(lang, q, i, n):
    if q["type"] == "tf":
        head = tr(lang, "quiz_tf", i=i, n=n)
        return f"{head}\n\n«{q['t']}»"
    if q["type"] == "fix":
        head = tr(lang, "quiz_which", i=i, n=n)
        return (f"{head}\n\nA) {q['opts'][0]}\nB) {q['opts'][1]}")
    instr = (q.get("instr") or "").strip()
    head = tr(lang, "quiz_fill", i=i, n=n)
    extra = f"\n({instr})" if instr and instr.lower() not in (
        "choose the correct form",) else ""
    letters = ["A", "B", "C", "D", "E", "F"]
    opts = "\n".join(f"{letters[j]}) {o}" for j, o in enumerate(q["options"]))
    return f"{head}{extra}\n\n{q['q']}\n\n{opts}"


def quiz_keyboard(lang, q):
    if q["type"] == "tf":
        return InlineKeyboardMarkup([[
            InlineKeyboardButton(tr(lang, "btn_correct"), callback_data="quiz:tf:1"),
            InlineKeyboardButton(tr(lang, "btn_wrong"), callback_data="quiz:tf:0"),
        ], [InlineKeyboardButton(tr(lang, "btn_stop_quiz"), callback_data="quiz:stop")]])
    options = q.get("options") or q.get("opts") or []
    letters = ["A", "B", "C", "D", "E", "F"]
    btns = [[InlineKeyboardButton(letters[i], callback_data=f"quiz:ans:{i}")]
            for i in range(min(len(options), len(letters)))]
    btns.append([InlineKeyboardButton(tr(lang, "btn_stop_quiz"),
                                      callback_data="quiz:stop")])
    return InlineKeyboardMarkup(btns)


async def start_quiz(update, ctx, chat_id, chapter=None, pre_pool=None):
    s = st(chat_id)
    lang = s["lang"] or "it"
    pool = pre_pool if pre_pool is not None else build_quiz_pool(KB, chapter)
    if not pool:
        await send(update, ctx, tr(lang, "exp_notfound"))
        return
    s["mode"] = "quiz"
    s["quiz"] = {"pool": pool, "idx": 0, "score": 0, "answered": False}
    n = len(pool)
    await send(update, ctx, tr(lang, "quiz_start", n=n),
               menu_keyboard(lang))
    await send_next_question(update, ctx, chat_id)


async def send_next_question(update, ctx, chat_id):
    s = st(chat_id)
    lang = s["lang"] or "it"
    qz = s["quiz"]
    if qz["idx"] >= len(qz["pool"]):
        await send(update, ctx, tr(lang, "quiz_done", c=qz["score"], t=len(qz["pool"])),
                   InlineKeyboardMarkup([[
                       InlineKeyboardButton(tr(lang, "quiz_again"),
                                            callback_data="menu:quiz"),
                       InlineKeyboardButton(tr(lang, "btn_menu"),
                                            callback_data="back:menu")]]))
        s["quiz"] = None
        s["mode"] = None
        return
    q = qz["pool"][qz["idx"]]
    # prepara le opzioni per le domande "quale è corretta"
    if q["type"] == "fix":
        opts = [q["bad"], q["good"]]
        random.shuffle(opts)
        q["opts"] = opts
        q["answer_idx"] = opts.index(q["good"])
    await send(update, ctx,
               quiz_question_text(lang, q, qz["idx"] + 1, len(qz["pool"])),
               quiz_keyboard(lang, q))


async def quiz_feedback(update, ctx, chat_id, given=None):
    """given: per tf -> bool previsto; per ans -> indice opzione scelto."""
    s = st(chat_id)
    lang = s["lang"] or "it"
    qz = s["quiz"]
    if qz is None or qz.get("answered"):
        q2 = update.callback_query
        if q2:
            await q2.answer()
        await send(update, ctx, tr(lang, "already"))
        return
    q = qz["pool"][qz["idx"]]
    qz["answered"] = True
    src = f"Capitolo {q['ch']}" if lang == "it" else f"Chapter {q['ch']}"
    if q["type"] == "tf":
        good = (given is q["ok"])
        if good:
            qz["score"] += 1
        why = (tr(lang, "quiz_tf_ok", ch=q["ch"]) if q["ok"]
               else tr(lang, "quiz_tf_bad", ch=q["ch"]))
        text = (f"{tr(lang, 'quiz_right') if good else tr(lang, 'quiz_wrong')} "
                f"{tr(lang, 'score', c=qz['score'], t=len(qz['pool']))}\n{why}")
    else:
        gi = q.get("answer_idx")
        good = (given == gi)
        if good:
            qz["score"] += 1
        if q["type"] == "fix":
            body = tr(lang, "quiz_fix", good=q["good"], bad=q["bad"], ch=q["ch"])
        else:
            body = tr(lang, "quiz_book_answer",
                      a=f"{q['options'][gi]} — {q['answer']}")
        text = (f"{tr(lang, 'quiz_right') if good else tr(lang, 'quiz_wrong')} "
                f"{tr(lang, 'score', c=qz['score'], t=len(qz['pool']))}\n\n{body}\n\n{src}")
    text += "\n\n" + tr(lang, "exp_source", n=q["ch"],
                        t=KB["_chapters"][q["ch"]]["title"])
    kb_btn = InlineKeyboardMarkup([[
        InlineKeyboardButton(tr(lang, "btn_next"), callback_data="quiz:next"),
        InlineKeyboardButton(tr(lang, "btn_stop_quiz"), callback_data="quiz:stop"),
    ]])
    await send(update, ctx, text, kb_btn)


async def query_answer_guard(update):
    q = update.callback_query
    await q.answer()


# ------------------------------------------------------------- esercizi
async def start_exercises(update, ctx, chat_id):
    s = st(chat_id)
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
    s = st(chat_id)
    lang = s["lang"] or "it"
    items = [e for e in KB["exercises"] if e["ch"] == num]
    if not items:
        await send(update, ctx, tr(lang, "exp_notfound"))
        return
    s["ex"] = {"ch": num, "items": items, "idx": 0}
    await send_exercise(update, ctx, chat_id)


async def send_exercise(update, ctx, chat_id):
    s = st(chat_id)
    lang = s["lang"] or "it"
    ex = s["ex"]
    if ex["idx"] >= len(ex["items"]):
        await send(update, ctx, tr(lang, "ex_done", n=ex["ch"]),
                   menu_keyboard(lang))
        s["ex"] = None
        s["mode"] = None
        return
    e = ex["items"][ex["idx"]]
    title = KB["_chapters"][ex["ch"]]["title"]
    instr = (e["group"] + ". " if e["group"] else "") + (e["instr"] or "")
    text = tr(lang, "ex_q", i=ex["idx"] + 1, n=len(ex["items"]), ch=ex["ch"],
              title=title, instr=instr, q=e["q"])
    kbd = InlineKeyboardMarkup([[
        InlineKeyboardButton(tr(lang, "btn_show"), callback_data="ex:show"),
        InlineKeyboardButton(tr(lang, "btn_skip"), callback_data="ex:skip"),
        InlineKeyboardButton(tr(lang, "btn_menu"), callback_data="back:menu"),
    ]])
    await send(update, ctx, text, kbd)


async def ex_show_answer(update, ctx, chat_id, typed=None):
    s = st(chat_id)
    lang = s["lang"] or "it"
    ex = s.get("ex")
    if not ex or ex["idx"] >= len(ex["items"]):
        return
    e = ex["items"][ex["idx"]]
    key = "ex_typed" if typed else "ex_answer"
    await send(update, ctx, tr(lang, key, a=e["answer"]),
               InlineKeyboardMarkup([[
                   InlineKeyboardButton(tr(lang, "btn_next"), callback_data="ex:next"),
                   InlineKeyboardButton(tr(lang, "btn_menu"), callback_data="back:menu"),
               ]]))


# ------------------------------------------------------- spiegazioni ecc.
async def explain(update, ctx, chat_id, query):
    s = st(chat_id)
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
    s["mode"] = "exp"
    head = tr(lang, "exp_source", n=num, t=c["title"])
    text = f"{head}\n\n{pages[0]}"
    kbd = InlineKeyboardMarkup([[
        InlineKeyboardButton(tr(lang, "btn_full"), callback_data=f"chap:{num}"),
        InlineKeyboardButton(tr(lang, "btn_quiz_ch"), callback_data=f"exquiz:{num}"),
    ], [InlineKeyboardButton(tr(lang, "btn_menu"), callback_data="back:menu")]])
    if len(pages) > 1:
        kbd.inline_keyboard.insert(1, [
            InlineKeyboardButton(tr(lang, "btn_nextpage"), callback_data="page:1")])
    await send(update, ctx, text[:4096], kbd)


async def send_chapter(update, ctx, chat_id, num):
    s = st(chat_id)
    lang = s["lang"] or "it"
    pages = kbmod.chapter_pages(KB, num)
    s["pages"] = pages
    head = tr(lang, "exp_source", n=num, t=KB["_chapters"][num]["title"])
    text = f"{head}\n\n{pages[0]}"
    await send(update, ctx, text[:4096], pages_keyboard(lang, 0, len(pages)))


async def send_page(update, ctx, chat_id, idx):
    s = st(chat_id)
    lang = s["lang"] or "it"
    pages = s.get("pages") or []
    if not pages or idx >= len(pages):
        await send(update, ctx, tr(lang, "exp_notfound"))
        return
    if idx == 0:
        await send(update, ctx, pages[0][:4096], pages_keyboard(lang, 0, len(pages)))
    else:
        await send(update, ctx,
                   f"[{tr(lang, 'page_of', i=idx + 1, n=len(pages))}]\n\n{pages[idx]}"[:4096],
                   pages_keyboard(lang, idx, len(pages)))


async def verbs_lookup(update, ctx, chat_id, word):
    s = st(chat_id)
    lang = s["lang"] or "it"
    hit = kbmod.verb_lookup(KB, word)
    if hit:
        base, forms = hit
        await send(update, ctx, tr(lang, "verbs_res", b=base, p=forms[0], pp=forms[1]),
                   menu_keyboard(lang))
    else:
        await send(update, ctx, tr(lang, "verbs_nf", w=word.strip()), menu_keyboard(lang))


async def start_glossary(update, ctx, chat_id):
    s = st(chat_id)
    s["mode"] = "glos"
    await send(update, ctx, tr(s["lang"] or "it", "glos_ask"))


async def start_glossary_query(update, ctx, chat_id, query):
    s = st(chat_id)
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
    rows = [[InlineKeyboardButton(g["term"][:60], callback_data=f"gl:{i}")]
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
    await update.effective_chat.send_message(tr("it", "lang_choose"),
                                             reply_markup=lang_keyboard())
    await update.effective_chat.send_message(tr("en", "lang_choose"),
                                             reply_markup=lang_keyboard())


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    lang = st(chat_id).get("lang") or "it"
    s = st(chat_id)
    s["mode"] = None
    await send(update, ctx, tr(lang, "help"), menu_keyboard(lang))


async def cmd_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    lang = st(chat_id).get("lang") or "it"
    s = st(chat_id)
    s["mode"] = None
    s["quiz"] = None
    s["ex"] = None
    await send(update, ctx, tr(lang, "menu"), menu_keyboard(lang))


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
        s["mode"] = "exp"
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
    st(chat_id)["mode"] = "verbs"
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
    await send(update, ctx, tr("it", "lang_choose"), lang_keyboard())


async def chapters_menu(update, ctx, chat_id):
    s = st(chat_id)
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
    q = update.callback_query
    if q is None:
        return
    chat_id = update.effective_chat.id
    s = st(chat_id)
    data = q.data or ""
    await q.answer()

    if data.startswith("lang:"):
        s["lang"] = data.split(":", 1)[1]
        lang = s["lang"]
        await send(update, ctx, tr(lang, "welcome"))
        await send(update, ctx, tr(lang, "menu"), menu_keyboard(lang))
        return

    if s.get("lang") is None:  # prima della scelta lingua ignora il resto
        await send(update, ctx, tr("it", "lang_choose"), lang_keyboard())
        return
    lang = s["lang"]

    if data == "back:menu":
        s["mode"] = None
        s["quiz"] = None
        s["ex"] = None
        await send(update, ctx, tr(lang, "menu"), menu_keyboard(lang))
    elif data == "menu:quiz":
        await start_quiz(update, ctx, chat_id)
    elif data == "menu:ex":
        await start_exercises(update, ctx, chat_id)
    elif data == "menu:exp":
        s["mode"] = "exp"
        await send(update, ctx, tr(lang, "exp_ask"))
    elif data == "menu:chap":
        await chapters_menu(update, ctx, chat_id)
    elif data == "menu:verbs":
        s["mode"] = "verbs"
        await send(update, ctx, tr(lang, "verbs_ask"))
    elif data == "menu:glos":
        await start_glossary(update, ctx, chat_id)
    elif data == "menu:help":
        await send(update, ctx, tr(lang, "help"), menu_keyboard(lang))
    elif data == "quiz:next":
        if s.get("quiz"):
            s["quiz"]["answered"] = False
            s["quiz"]["idx"] += 1
            await send_next_question(update, ctx, chat_id)
    elif data == "quiz:stop":
        s["mode"] = None
        s["quiz"] = None
        await send(update, ctx, tr(lang, "menu"), menu_keyboard(lang))
    elif data.startswith("quiz:tf:"):
        if s.get("quiz"):
            await quiz_feedback(update, ctx, chat_id,
                                given=data.endswith("1"))
    elif data.startswith("quiz:ans:"):
        if s.get("quiz"):
            await quiz_feedback(update, ctx, chat_id,
                                given=int(data.split(":", 2)[2]))
    elif data.startswith("exquiz:"):
        num = int(data.split(":", 1)[1])
        pool = build_quiz_pool(KB, num)
        if len(pool) < 4:
            await send(update, ctx, tr(lang, "quiz_few", n=len(pool)))
        await start_quiz(update, ctx, chat_id, pre_pool=pool)
    elif data.startswith("ex:chap:"):
        await ex_chapter(update, ctx, chat_id, int(data.split(":", 2)[2]))
    elif data == "ex:show":
        await ex_show_answer(update, ctx, chat_id)
    elif data == "ex:next":
        if s.get("ex"):
            s["ex"]["idx"] += 1
            await send_exercise(update, ctx, chat_id)
    elif data == "ex:skip":
        if s.get("ex"):
            s["ex"]["idx"] += 1
            await send_exercise(update, ctx, chat_id)
    elif data.startswith("chap:"):
        await send_chapter(update, ctx, chat_id, int(data.split(":", 1)[1]))
    elif data.startswith("page:"):
        await send_page(update, ctx, chat_id, int(data.split(":", 1)[1]))
    elif data.startswith("gl:"):
        idx = int(data.split(":", 1)[1])
        g = KB["glossary"][idx]
        await send(update, ctx, f"{g['term']} — {g['def']}", menu_keyboard(lang))
        s["glos"] = None
        s["mode"] = None


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
        # l'utente prova a rispondere: mostro la risposta ufficiale del libro
        await ex_show_answer(update, ctx, chat_id, typed=True)
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
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = Application.builder().token(token).build()

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
