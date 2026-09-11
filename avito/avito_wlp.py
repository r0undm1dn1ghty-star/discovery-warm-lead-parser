"""WLP v1.2: Авито-сборщик через Camoufox — финальные селекторы titleStep."""
import sys, time, json
from urllib.parse import quote
from camoufox.sync_api import Camoufox

JS_EXTRACT = """() => {
    const out = [];
    document.querySelectorAll('div[class*="titleStep"] a').forEach(a => {
        const title = (a.title || a.innerText || '').trim().replace(/[\\t ]+/g, ' ');
        if (title.length < 10) return;
        const card = a.closest('div[data-marker="item"]') || a.closest('div[class*="ivaItem"]');
        let price = '', city = '', date = '';
        if (card) {
            const pe = card.querySelector('[class*="price"]');
            if (pe) price = (pe.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 30);
            const ce = card.querySelector('[class*="geo"]');
            if (ce) city = (ce.innerText || '').split('\\n')[0].trim().slice(0, 40);
            const de = card.querySelector('[class*="date"]');
            if (de) date = (de.innerText || '').trim().slice(0, 20);
        }
        out.push({title: title, url: a.href.split('?')[0], price: price, city: city, date: date});
    });
    return out;
}"""

QUERIES = {
    "default": ["нужен бот", "внедрение нейросети в бизнес", "настроить чат-бот"],
    "ai": ["автоматизация бизнеса ии", "искусственный интеллект для бизнеса", "нейросеть под ключ"],
}

def scrape(query: str, region: str = "all", max_items: int = 50) -> list:
    url = f"https://www.avito.ru/{region}/predlozheniya_uslug?q={quote(query)}"
    res = []
    with Camoufox() as browser:
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        for _ in range(6):  # антибот: ждём саморассасывания
            t = page.title() or ""
            if "Авито" in t and "доступ" not in t.lower():
                break
            page.wait_for_timeout(5000)
        page.wait_for_timeout(4000)
        data = page.evaluate(JS_EXTRACT)
        seen = set()
        for it in data or []:
            u = it["url"]
            if u in seen: continue
            if not u.rstrip("/").split("_")[-1].isdigit(): continue
            seen.add(u)
            res.append(it)
            if len(res) >= max_items: break
        page.wait_for_timeout(3000)  # антибан-пауза
    return res

if __name__ == "__main__":
    qs = sys.argv[1:] or QUERIES["default"]
    all_res = []
    for q in qs:
        try:
            r = scrape(q)
            print(f"[{q}] карточек: {len(r)}")
            for x in r[:3]:
                print(f"   {x['title'][:50]} | {x['price'][:16]} | {x['city'][:22]}")
            all_res.extend({"query": q, **x} for x in r)
        except Exception as e:
            print(f"[{q}] ERR {str(e)[:60]}")
        time.sleep(5)
    json.dump(all_res, open("avito_wlp_results.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"Итого: {len(all_res)} -> avito_wlp_results.json")
