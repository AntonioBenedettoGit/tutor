"""Controllo manuale (facoltativo) della mini app in un browser vero, con un Telegram simulato.
Non fa parte della CI: richiede `pip install playwright && python -m playwright install chromium`.
Uso: python tools/check_webapp_browser.py   (dalla cartella del progetto)
Avvia il server su localhost con una firma initData di prova, prova verbi, glossario, lingua,
tasto Indietro, tema chiaro/scuro e il rifiuto di firme errate; salva screenshot in /tmp."""
import asyncio, json, socket, sys, time, hashlib, hmac
from urllib.parse import urlencode
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from types import SimpleNamespace
from unittest.mock import AsyncMock
import app
from playwright.async_api import async_playwright
TOKEN='123456:BROWSER_TEST'
def sign(fields, token=TOKEN):
    check='\n'.join(f'{k}={fields[k]}' for k in sorted(fields))
    secret=hmac.new(b'WebAppData', token.encode(), hashlib.sha256).digest()
    return urlencode({**fields,'hash':hmac.new(secret,check.encode(),hashlib.sha256).hexdigest()})
class FakeApp:
    def __init__(s): s.update_queue=asyncio.Queue(); s.bot=SimpleNamespace(set_webhook=AsyncMock()); s.post_init=None
    async def __aenter__(s): return s
    async def __aexit__(s,*a): pass
    async def start(s): pass
    async def stop(s): pass
def fake_tg(init_data, dark):
    theme = {'bg_color':'#17212b','secondary_bg_color':'#0e1621','section_bg_color':'#17212b','text_color':'#f5f5f5',
             'hint_color':'#708499','link_color':'#6ab3f3','button_color':'#5288c1','button_text_color':'#ffffff',
             'section_separator_color':'#0b1218'} if dark else {'bg_color':'#ffffff','secondary_bg_color':'#efeff3',
             'section_bg_color':'#ffffff','text_color':'#000000','hint_color':'#999999','link_color':'#2481cc',
             'button_color':'#2481cc','button_text_color':'#ffffff','section_separator_color':'#e7e7e7'}
    css=''.join(f"document.documentElement.style.setProperty('--tg-theme-{k.replace('_','-')}','{v}');" for k,v in theme.items())
    return f"""{css}
window.__log=[];
window.Telegram={{WebApp:{{initData:{json.dumps(init_data)},initDataUnsafe:{{user:{{language_code:'it'}}}},
 ready(){{__log.push('ready')}},expand(){{__log.push('expand')}},setHeaderColor(){{}},setBackgroundColor(){{}},
 HapticFeedback:{{selectionChanged(){{__log.push('haptic')}}}},
 BackButton:{{_cb:null,visible:false,show(){{this.visible=true}},hide(){{this.visible=false}},onClick(f){{this._cb=f}}}}}}}};"""
async def main():
    s=socket.socket(); s.bind(('127.0.0.1',0)); port=s.getsockname()[1]; s.close()
    stop=asyncio.Event()
    task=asyncio.create_task(app.serve_webhook(TOKEN,'https://x.onrender.com',port,stop,FakeApp()))
    await asyncio.sleep(0.3)
    base=f'http://127.0.0.1:{port}'
    fields={'auth_date':str(int(time.time())),'query_id':'Q1','user':json.dumps({'id':7,'first_name':'Giulia','language_code':'it'},separators=(',',':')),'signature':'s1'}
    results=[]
    async with async_playwright() as p:
        b=await p.chromium.launch()
        for dark, init in ((False, sign(fields)), (True, sign(fields)), (False, sign(fields,'999:WRONG')), (False, '')):
            ctx=await b.new_context(viewport={'width':390,'height':780}, device_scale_factor=2)
            page=await ctx.new_page()
            errors=[]; page.on('pageerror', lambda e: errors.append(str(e)))
            page.on('console', lambda m: errors.append(m.text) if m.type=='error' else None)
            await page.route('https://telegram.org/js/telegram-web-app.js',
                             lambda r, _req=None, d=dark, i=init: r.fulfill(content_type='application/javascript', body=fake_tg(i, d)))
            await page.goto(base+'/app?lang=it')
            tag = 'dark' if dark else ('light' if init and 'WRONG' not in str(init) and init==sign(fields) else 'err')
            if init==sign(fields):
                await page.wait_for_selector('#home:not(.hidden)', timeout=5000)
                hello=await page.text_content('#hello')
                await page.screenshot(path=f'/tmp/shot_home_{"dark" if dark else "light"}.png', full_page=True)
                await page.click('[data-go="verbs"]')
                await page.fill('#verbs-q','went')
                rows=await page.locator('#verbs-list .verb').all_text_contents()
                back_visible=await page.evaluate('Telegram.WebApp.BackButton.visible')
                await page.screenshot(path=f'/tmp/shot_verbs_{"dark" if dark else "light"}.png')
                await page.fill('#verbs-q','walked')
                none=await page.text_content('#verbs-list')
                await page.evaluate('Telegram.WebApp.BackButton._cb()')
                await page.wait_for_selector('#home:not(.hidden)')
                await page.click('[data-go="glossary"]')
                await page.fill('#glossary-q','gerund')
                gl=await page.locator('#glossary-list .term.open').all_text_contents()
                await page.screenshot(path=f'/tmp/shot_glossary_{"dark" if dark else "light"}.png')
                await page.evaluate('history.back()'); await page.wait_for_selector('#home:not(.hidden)')
                await page.click('[data-lang="en"]')
                en=await page.text_content('#verbs-sub')
                results.append({'case':'ok-dark' if dark else 'ok-light','hello':hello,'went':rows[:2],'back':back_visible,
                                'regular':none[:60],'glossary_open':[g[:70] for g in gl],'en':en,'errors':errors,
                                'log':await page.evaluate('__log.slice(0,3)')})
            else:
                await page.wait_for_function("document.getElementById('state-text').textContent.length>0 && !document.getElementById('state-text').textContent.startsWith('Caric')", timeout=5000)
                results.append({'case':'bad-signature' if init else 'no-telegram','msg':await page.text_content('#state-text'),
                                'retry_visible':await page.is_visible('#retry'),'errors':[e for e in errors if '401' not in e]})
                if init: await page.screenshot(path='/tmp/shot_error.png')
            await ctx.close()
        await b.close()
    stop.set(); await task
    print(json.dumps(results, ensure_ascii=False, indent=1))
asyncio.run(main())
