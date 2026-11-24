"""Controllo manuale (facoltativo) della mini app in un browser vero, con un Telegram simulato.
Non fa parte della CI: richiede `pip install playwright && python -m playwright install chromium`.
Uso: python tools/check_webapp_browser.py [cartella-screenshot]   (dalla cartella del progetto)

Avvia il server su localhost con una firma initData di prova e percorre la mini app come uno studente:
home, teoria (indice, ricerca, «letto»), esercizi di tutti i tipi (scrittura, parti, scelta multipla,
autovalutazione, soluzione mostrata, salto, ripresa), quiz con riepilogo e «rifai gli errori», progressi
salvati nel CloudStorage simulato e ritrovati alla riapertura, tema chiaro/scuro, inglese, firma errata.
Esce con codice 1 se qualcosa non va (compresi errori JavaScript)."""
import asyncio
import hashlib
import hmac
import json
import socket
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app  # noqa: E402
import bot  # noqa: E402
from playwright.async_api import async_playwright  # noqa: E402

TOKEN = '123456:BROWSER_TEST'
SHOTS = Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp/miniapp-shots')
LIGHT = {'bg_color': '#ffffff', 'secondary_bg_color': '#efeff3', 'section_bg_color': '#ffffff',
         'text_color': '#000000', 'hint_color': '#999999', 'link_color': '#2481cc', 'button_color': '#2481cc',
         'button_text_color': '#ffffff', 'section_separator_color': '#e7e7e7'}
DARK = {'bg_color': '#17212b', 'secondary_bg_color': '#0e1621', 'section_bg_color': '#17212b',
        'text_color': '#f5f5f5', 'hint_color': '#708499', 'link_color': '#6ab3f3', 'button_color': '#5288c1',
        'button_text_color': '#ffffff', 'section_separator_color': '#0b1218'}
problems = []


def check(cond, what):
    print(('  ok  ' if cond else '  NO  ') + what)
    if not cond:
        problems.append(what)


def sign(fields, token=TOKEN):
    data = '\n'.join(f'{k}={fields[k]}' for k in sorted(fields))
    secret = hmac.new(b'WebAppData', token.encode(), hashlib.sha256).digest()
    return urlencode({**fields, 'hash': hmac.new(secret, data.encode(), hashlib.sha256).hexdigest()})


class FakePTB:
    def __init__(self):
        self.update_queue = asyncio.Queue()
        self.bot = SimpleNamespace(set_webhook=AsyncMock())
        self.post_init = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass

    async def start(self):
        pass

    async def stop(self):
        pass


def fake_telegram(init_data, theme):
    """Telegram.WebApp simulato: tema, tasto Indietro, conferme, CloudStorage (su localStorage, così
    sopravvive alla riapertura della pagina come il vero CloudStorage)."""
    css = ''.join(f"document.documentElement.style.setProperty('--tg-theme-{k.replace('_', '-')}','{v}');"
                  for k, v in theme.items())
    return css + """
window.__log = [];
var cs = {
  getItems: function (keys, cb) { var o = {}; keys.forEach(function (k) { o[k] = localStorage.getItem('cs_' + k) || ''; });
    window.__log.push('getItems:' + keys.length); setTimeout(function () { cb(null, o); }, 20); },
  setItem: function (k, v, cb) { localStorage.setItem('cs_' + k, v); window.__log.push('set:' + k); cb && cb(null, true); },
  removeItems: function (keys, cb) { keys.forEach(function (k) { localStorage.removeItem('cs_' + k); }); cb && cb(null, true); }
};
window.Telegram = { WebApp: {
  initData: %s, initDataUnsafe: { user: { language_code: 'it' } }, version: '8.0',
  isVersionAtLeast: function (v) { return parseFloat(v) <= 8.0; },
  ready: function () { __log.push('ready'); }, expand: function () {}, setHeaderColor: function () {}, setBackgroundColor: function () {},
  showConfirm: function (msg, cb) { __log.push('confirm'); cb(true); },
  HapticFeedback: { selectionChanged: function () {}, notificationOccurred: function () {} },
  CloudStorage: cs,
  BackButton: { _cb: null, visible: false, show: function () { this.visible = true; }, hide: function () { this.visible = false; },
                onClick: function (f) { this._cb = f; } } } };
""" % json.dumps(init_data)


async def open_app(browser, base, init, theme=LIGHT, storage=None):
    ctx = await browser.new_context(viewport={'width': 390, 'height': 800}, device_scale_factor=2)
    if storage:
        await ctx.add_init_script('(' + json.dumps(storage) + ').forEach(function (kv) { localStorage.setItem(kv[0], kv[1]); });')
    page = await ctx.new_page()
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.on('console', lambda m: errors.append(m.text) if m.type == 'error' and '401' not in m.text else None)
    await page.route('https://telegram.org/js/telegram-web-app.js',
                     lambda route, _req=None: route.fulfill(content_type='application/javascript',
                                                            body=fake_telegram(init, theme)))
    await page.goto(base + '/app?lang=it')
    return ctx, page, errors


async def back(page):
    await page.evaluate('Telegram.WebApp.BackButton._cb()')
    await page.wait_for_timeout(150)


async def text(page, selector):
    return ' '.join((await page.locator(selector).all_inner_texts()))


async def run_exercise(page, mode_hint):
    """Risponde all'esercizio visibile secondo il suo tipo; ritorna il tipo riconosciuto."""
    if await page.locator('#page .opt').count():
        await page.locator('#page .opt').first.click()
        kind = 'mcq'
    elif await page.locator('#page textarea').count():
        await page.locator('#page textarea').fill('my answer')
        await page.get_by_role('button', name='Mostra la soluzione').click()
        await page.get_by_role('button', name='✓ Ho risposto bene').click()
        kind = 'self'
    elif await page.locator('#page .partrow').count():
        inputs = page.locator('#page .partrow input')
        for i in range(await inputs.count()):
            await inputs.nth(i).fill('x')
        await page.get_by_role('button', name='Controlla').click()
        kind = 'parts'
    else:
        await page.locator('#page input.field').fill(mode_hint or 'x')
        await page.locator('#page input.field').press('Enter')
        kind = 'auto'
    await page.get_by_role('button', name='Prossimo esercizio ▶️').wait_for()
    return kind


async def main():
    SHOTS.mkdir(parents=True, exist_ok=True)
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    stop = asyncio.Event()
    task = asyncio.create_task(app.serve_webhook(TOKEN, 'https://x.onrender.com', port, stop, FakePTB()))
    await asyncio.sleep(0.3)
    base = f'http://127.0.0.1:{port}'
    fields = {'auth_date': str(int(time.time())), 'query_id': 'Q1', 'signature': 's1',
              'user': json.dumps({'id': 7, 'first_name': 'Giulia', 'language_code': 'it'}, separators=(',', ':'))}
    good = sign(fields)
    async with async_playwright() as p:
        browser = await p.chromium.launch()

        print('Home, verbi, glossario')
        ctx, page, errors = await open_app(browser, base, good)
        await page.wait_for_selector('#home:not(.hidden)')
        check(await page.text_content('#hello') == 'Ciao Giulia!', 'saluto con il nome')
        check('letti 0' in await page.text_content('#theory-sub'), 'nessun capitolo letto all\'inizio')
        await page.screenshot(path=str(SHOTS / '01-home.png'), full_page=True)
        await page.click('[data-go="verbs"]')
        await page.fill('#verbs-q', 'went')
        check(await page.locator('#verbs-list .verb').first.text_content() == 'gowentgone', 'verbi: went → go/went/gone')
        await back(page)
        await page.click('[data-go="glossary"]')
        await page.fill('#glossary-q', 'gerund')
        check(await page.locator('#glossary-list .term.open').count() == 1, 'glossario: gerund aperto')
        await back(page)

        print('Teoria')
        await page.click('[data-go="theory"]')
        check(await page.locator('#page .row').count() == 25, '25 capitoli divisi per Parte')
        check(await page.locator('#page .group-title').count() == 5, '5 Parti')
        await page.screenshot(path=str(SHOTS / '02-teoria-capitoli.png'), full_page=False)
        await page.locator('#page .row', has_text='Articoli').click()
        await page.wait_for_selector('#page article.theory')
        n_blocks = await page.locator('#page article.theory > *').count()
        check(n_blocks > 50, f'capitolo 5 completo ({n_blocks} blocchi)')
        check(await page.locator('#page details.toc button').count() > 3, 'indice del capitolo')
        check(await page.locator('#page article strong').count() > 10 and await page.locator('#page article em').count() > 10,
              'grassetto e corsivo del libro')
        await page.screenshot(path=str(SHOTS / '03-teoria-capitolo.png'))
        await page.locator('#page details.toc summary').click()
        await page.locator('#page details.toc button').nth(2).click()
        await page.wait_for_timeout(400)
        check(await page.evaluate('window.scrollY') > 300, 'l\'indice porta al paragrafo')
        await page.locator('#page .pair').scroll_into_view_if_needed()
        await page.wait_for_timeout(300)
        await back(page)
        badge = await page.locator('#page .row', has_text='Articoli').locator('.badge').all_inner_texts()
        check(badge == ['✓'], 'capitolo segnato come letto')
        await page.fill('#page form input', 'present perfect')
        await page.press('#page form input', 'Enter')
        await page.wait_for_selector('#page article.theory')
        check('Capitolo 10' in await page.text_content('#page .top small'), 'ricerca «present perfect» → cap. 10')
        await back(page)
        await page.fill('#page form input', 'xyzzy')
        await page.press('#page form input', 'Enter')
        await page.wait_for_timeout(400)
        check('Non ho trovato' in await page.text_content('#page .count'), 'ricerca senza risultato')
        await back(page)

        print('Esercizi')
        await page.click('[data-go="exercises"]')
        await page.locator('#page .row', has_text='Come funziona').click()
        await page.get_by_role('button', name='Inizia').click()
        first_q = await page.text_content('#page .card')
        await page.locator('#page input.field').fill('noun')
        await page.screenshot(path=str(SHOTS / '04-esercizio.png'))
        await page.get_by_role('button', name='Controlla').click()
        await page.get_by_role('button', name='Prossimo esercizio ▶️').wait_for()
        verdict = await page.text_content('#page .feedback .verdict')
        check(verdict == '✅ Esatto!', f'cap.1 es.1 «noun» giusto ({first_q.strip()[:40]}…)')
        check('Soluzione del libro' in await page.text_content('#page .feedback'), 'soluzione del libro mostrata')
        check('🇮🇹' in await page.text_content('#page .feedback'), 'nota in italiano')
        await page.screenshot(path=str(SHOTS / '05-esercizio-giusto.png'), full_page=True)
        await page.get_by_role('button', name='Prossimo esercizio ▶️').click()
        await page.locator('#page input.field').fill('xyz')
        await page.get_by_role('button', name='Controlla').click()
        await page.get_by_role('button', name='Prossimo esercizio ▶️').wait_for()
        check('❌' in await page.text_content('#page .feedback .verdict'), 'risposta sbagliata riconosciuta')
        await page.get_by_role('button', name='Prossimo esercizio ▶️').click()
        await page.get_by_role('button', name='Mostra la soluzione').click()
        await page.get_by_role('button', name='Prossimo esercizio ▶️').wait_for()
        check('nessun punto' in await page.text_content('#page .feedback'), 'soluzione mostrata: 0 punti')
        check('Punteggio esercizi 1/3' in await page.text_content('#page .feedback'), 'punteggio 1/3')
        await page.get_by_role('button', name='Prossimo esercizio ▶️').click()
        await page.get_by_role('button', name='Salta').click()
        await back(page)
        intro = await page.text_content('#page .card')
        check('Fatti 4 su 8 · giusti 1' in intro, 'progressi del capitolo')
        check(await page.locator('#page .dots i.ok').count() == 1 and await page.locator('#page .dots i.sk').count() == 1,
              'pallini: 1 giusto, 1 saltato')
        check(await page.get_by_role('button', name="Continua dall'esercizio 5").count() == 1, 'riprende dall\'esercizio 5')
        await back(page)
        check(await page.locator('#page .row', has_text='Come funziona').locator('.badge').inner_text() == '1/8',
              'elenco capitoli: 1/8')
        await back(page)

        kinds = set()
        for chapter_name in ('Comparativi', 'Determinanti'):
            await page.click('[data-go="exercises"]')
            await page.locator('#page .row', has_text=chapter_name).click()
            await page.get_by_role('button', name='Inizia').click()
            total = int((await page.text_content('#page .top h2')).split('/')[-1])
            for i in range(total):
                kinds.add(await run_exercise(page, None))
                if i == 0 and chapter_name == 'Comparativi':
                    await page.screenshot(path=str(SHOTS / '06-esercizio-parti.png'), full_page=True)
                await page.get_by_role('button', name='Prossimo esercizio ▶️').click()
            await page.wait_for_selector('#page .big')
            summary = await page.text_content('#page .card')
            check('finiti' in summary and ('★' in summary or '☆' in summary), f'riepilogo esercizi {chapter_name}')
            if chapter_name == 'Comparativi':
                await page.screenshot(path=str(SHOTS / '07-esercizi-riepilogo.png'))
            await page.get_by_role('button', name='Torna alla home').click()
            await page.wait_for_selector('#home:not(.hidden)')
        check(kinds >= {'mcq', 'self', 'parts', 'auto'}, f'tutti i tipi di esercizio provati: {sorted(kinds)}')

        print('Quiz')
        await page.click('[data-go="quiz"]')
        await page.locator('#page .row', has_text='Quiz misto').click()
        await page.wait_for_selector('#page .opt')
        types = []
        for i in range(10):
            types.append(await page.locator('#page .opt').count())
            if i == 0:
                await page.screenshot(path=str(SHOTS / '08-quiz-domanda.png'))
            await page.locator('#page .opt').first.click()
            await page.wait_for_selector('#page .feedback .btn')
            if i == 0:
                await page.screenshot(path=str(SHOTS / '09-quiz-risposta.png'), full_page=True)
            check(await page.locator('#page .opt.right, #page .opt.wrong').count() >= 1, f'domanda {i + 1}: risposta evidenziata')
            await page.locator('#page .feedback .btn').click()
        await page.wait_for_selector('#page .big')
        result = await page.text_content('#page .result')
        score, n = map(int, result.split('/'))
        check(n == 10, f'quiz di 10 domande, risultato {result}')
        await page.screenshot(path=str(SHOTS / '10-quiz-riepilogo.png'), full_page=True)
        wrong = await page.locator('#page .wrongs .row').count()
        check(wrong == 10 - score, f'elenco «da ripassare» con {wrong} errori')
        if wrong:
            await page.get_by_role('button', name=f'🔁 Rifai gli errori ({wrong})').click()
            await page.wait_for_selector('#page .opt')
            check(f'1/{wrong}' in await page.text_content('#page .top h2'), 'rifai gli errori: solo le sbagliate')
            await back(page)                           # quiz appena iniziato: nessuna conferma
        stored = await page.evaluate("localStorage.getItem('cs_qzall')")
        check(stored is not None and stored.startswith(f'{score}/10;'), f'quiz salvato nel CloudStorage ({stored})')
        await page.evaluate("Telegram.WebApp.BackButton._cb()")
        await page.wait_for_timeout(150)
        # quiz a metà: il tasto Indietro chiede conferma
        await page.click('[data-go="quiz"]')
        await page.locator('#page .row', has_text='Articoli').click()
        await page.wait_for_selector('#page .opt')
        await page.locator('#page .opt').first.click()
        await page.wait_for_selector('#page .feedback .btn')
        await page.locator('#page .feedback .btn').click()
        await back(page)
        check('confirm' in await page.evaluate('__log'), 'uscita dal quiz a metà: conferma')
        logs = await page.evaluate('__log')
        check(any(x.startswith('getItems:') for x in logs), 'progressi letti dal CloudStorage')
        check(not errors, f'nessun errore JavaScript ({errors[:2]})')
        storage = await page.evaluate("Object.keys(localStorage).filter(k => k.startsWith('cs_')).map(k => [k, localStorage.getItem(k)])")
        await ctx.close()

        print('Riapertura: progressi ritrovati, inglese, tema scuro')
        ctx, page, errors = await open_app(browser, base, good, DARK, storage)
        await page.wait_for_selector('#home:not(.hidden)')
        check('letti 1' in await page.text_content('#theory-sub'), 'capitolo letto ritrovato (solo quello letto fino in fondo)')
        check('fatti 23' in await page.text_content('#exercises-sub'),         # 4 (cap. 1) + 8 (cap. 20) + 11 (cap. 6)
              'esercizi fatti ritrovati: ' + await page.text_content('#exercises-sub'))
        await page.screenshot(path=str(SHOTS / '11-home-scura-progressi.png'), full_page=True)
        await page.click('[data-lang="en"]')
        check('Study' in await page.text_content('#home'), 'interfaccia in inglese')
        await page.click('[data-go="theory"]')
        check(await page.locator('#page .row', has_text='Articles: a, an, the').count() == 1, 'titoli originali in inglese')
        await page.locator('#page .row', has_text='Articles').click()
        await page.wait_for_selector('#page article.theory')
        await page.screenshot(path=str(SHOTS / '12-teoria-scura-en.png'))
        check(not errors, f'nessun errore JavaScript ({errors[:2]})')
        await ctx.close()

        print('Firma errata')
        ctx, page, errors = await open_app(browser, base, sign(fields, '999:WRONG'))
        await page.wait_for_function("document.getElementById('state-text').textContent.indexOf('/app') > 0")
        check(await page.locator('#home:not(.hidden)').count() == 0, 'nessun contenuto senza firma valida')
        await ctx.close()
        await browser.close()
    stop.set()
    await task
    print(f'\nScreenshot in {SHOTS}')
    if problems:
        print('PROBLEMI:', *problems, sep='\n - ')
        sys.exit(1)
    print('Tutto a posto.')


if __name__ == '__main__':
    asyncio.run(main())
