#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Discovery Warm Lead Parser v2.2 — мульти-нишевой движок.
Один файл, stdlib-only. 53 ниши из niches-50.json (все источники фактчек-2026-09-11).

Запуск:
  python warm_lead_parser.py                        # все ниши (быстрый режим: FL+WL+TG+биржи, без Авито)
  python warm_lead_parser.py --niche chatbots       # одна ниша (полный режим с Kwork)
  python warm_lead_parser.py --list                 # список ниш
  python warm_lead_parser.py --full chatbots        # одна ниша, все источники включая Авито (3-4 мин)
Источники: FL.ru (категории) · Weblancer (категории) · Kwork (c=ID через r.jina.ai) ·
           TG-каналы (t.me/s/ превью) · Kadrof · poisk-pro.ru · searchengines.guru ·
           illustrators.ru · Авито (Camoufox стелс, market-signal).
freelance.ru исключён: пер-нишевой фильтрации нет (фактчек 09-11).
"""
import json, re, html, sys, os, time
import urllib.request
from datetime import datetime, timezone, timedelta
from urllib.parse import quote

MSK = timezone(timedelta(hours=3))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0",
      "Accept-Language": "ru,en;q=0.8"}
HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- конфиг ниш
def load_niches():
    for fn in ("niches-50.json",):
        p = os.path.join(HERE, fn)
        if os.path.exists(p):
            return json.load(open(p, encoding="utf-8"))
    print("!! niches-50.json не найден рядом с движком"); sys.exit(1)

# ---------------------------------------------------------------- http
def get(u, timeout=25, headers=None):
    req = urllib.request.Request(u, headers=headers or UA)
    return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "ignore")

# ---------------------------------------------------------------- сборщики
def fetch_fl(category, niche_key):
    out = []
    raw = get(f"https://www.fl.ru/projects/category/{category}/")
    pairs = re.findall(r'href="(/projects/\d+/[^"]+)"[^>]*>([^<]{20,})</a>', raw)
    seen = set()
    for u, t in pairs:
        if u in seen: continue
        seen.add(u)
        out.append({"source": f"fl.ru/{niche_key}", "time": "",
                    "text": html.unescape(re.sub(r'\s+', ' ', t)).strip(),
                    "url": "https://www.fl.ru" + u})
    return out

def fetch_weblancer(slug, niche_key):
    out = []
    raw = get(f"https://www.weblancer.net/freelance/{slug}/")
    cards = re.findall(r'href="(/freelance/[^"]+)"[^>]*>([^<]+)</a></h2></div><p[^>]*>([^<]+)</p>', raw)
    for u, t, d in cards[:50]:
        out.append({"source": f"weblancer/{niche_key}", "time": "",
                    "text": html.unescape(t).strip() + " | " + html.unescape(d).strip()[:250],
                    "url": "https://www.weblancer.net" + u})
    return out

def fetch_kwork(cat_id, niche_key):
    out = []
    req = urllib.request.Request(f"https://r.jina.ai/https://kwork.ru/projects?c={cat_id}",
                                 headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "ignore")
    items = re.findall(r'\[([^\]]{20,100})\]\(https://kwork\.ru/projects/(\d+)[^)]*\)', raw)
    seen = set()
    for t, pid in items:
        if pid in seen or len(t.strip()) < 20: continue
        seen.add(pid)
        out.append({"source": f"kwork/{niche_key}", "time": "", "text": t.strip(),
                    "url": "https://kwork.ru/projects/" + pid})
    return out

def fetch_poisk_pro(pages=2, niche_key="engineering"):
    """poisk-pro.ru — биржа проектировщиков: заявки с датами и бюджетами 20-233К₽ (фактчек 09-11)."""
    out = []
    for page in range(1, pages + 1):
        try:
            raw = get(f"https://poisk-pro.ru/orders/russia/rabota-dlya-proektirovshchikov?page={page}")
        except Exception:
            break
        # карточка: ссылка+заголовок, затем short-text-<id> с описанием и бюджетом, затем дата
        cards = re.findall(
            r'<a href="(/order/(\d+)/[^"]+)">([^<]{8,120})</a>.*?'
            r'<div class="short-text-\2">(.*?)</div>.*?'
            r'(\d{2}\.\d{2}\.\d{4})',
            raw, re.S)
        seen = set()
        for u, oid, title, desc, date in cards:
            if oid in seen or title.strip() == 'Откликнуться': continue
            seen.add(oid)
            desc_c = html.unescape(re.sub(r'<[^>]+>', ' ', desc))
            desc_c = ' '.join(desc_c.split())
            text = f"{title.strip()} | {desc_c[:220]} | {date}"
            out.append({"source": f"poisk-pro/{niche_key}", "time": "",
                        "text": text[:400],
                        "url": "https://poisk-pro.ru" + u})
        if not cards: break
    return out

def fetch_se_guru(forum="optimizators-exchange", niche_key="seo"):
    """searchengines.guru — биржа SEO/контекст/таргет: темы-заказы, фильтр по дате автора (фактчек 09-11)."""
    out = []
    try:
        raw = get(f"https://searchengines.guru/ru/forum/{forum}")
    except Exception:
        return out
    blocks = re.findall(r'<div class="topics-list__title">\s*<a[^>]*href="(/ru/forum/\d+)"[^>]*>(.*?)</a>.*?'
                        r'<a href="/ru/users/\d+" title="(\d{4})\.(\d{2})\.(\d{2})', raw, re.S)
    seen = set()
    for u, txt, y, m, d in blocks:
        if u in seen: continue
        seen.add(u)
        clean = html.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', txt))).strip()
        if not clean or len(clean) < 10: continue
        out.append({"source": f"se_guru/{niche_key}", "time": f"{y}-{m}-{d}",
                    "text": clean[:130],
                    "url": "https://searchengines.guru" + u})
    return out

def fetch_illustrators(niche_key="illustration-3d"):
    """illustrators.ru/jobs — заказы иллюстраций с бюджетами, без логина (фактчек 09-11)."""
    out = []
    try:
        raw = get("https://illustrators.ru/jobs")
    except Exception:
        return out
    cards = re.findall(r'<a class="job-card__link" href="(/jobs/[^"]+)">\s*'
                       r'<div class="job-card__title">([^<]+)</div>\s*'
                       r'(?:<div class="job-card__description">(.*?)</div>)?\s*'
                       r'(?:<div class="job-card__cost">\s*(?:<span[^>]*>([^<]*)</span>)?\s*([^<]*)</div>)?', raw, re.S)
    for u, title, desc, cost1, cost2 in cards[:40]:
        cost = (cost1 or "").strip() + " " + (cost2 or "").strip()
        text = html.unescape(re.sub(r'<[^>]+>', ' ', title)).strip()
        if desc:
            text += " | " + html.unescape(re.sub(r'<[^>]+>', ' ', desc)).strip()[:180]
        if cost.strip():
            text += " | " + ' '.join(cost.split())
        out.append({"source": f"illustrators/{niche_key}", "time": "",
                    "text": text[:250],
                    "url": "https://illustrators.ru" + u})
    return out

def fetch_tg(channels, niche_key):
    out = []
    for ch in channels:
        try:
            raw = get(f"https://t.me/s/{ch}")
        except Exception:
            continue
        posts = re.findall(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', raw, flags=re.S)
        times = re.findall(r'<time datetime="([^"]+)"', raw)
        for p, t in zip(posts, times):
            txt = html.unescape(re.sub(r'<[^>]+>', '', re.sub(r'<br/?>', chr(10), p))).strip()
            out.append({"source": f"tg/{niche_key}", "time": t, "text": txt,
                        "url": f"https://t.me/s/{ch}"})
    return out

def fetch_avito(queries, niche_key):
    """Авито через Camoufox — market-signal (оферты исполнителей): разведка цен.
    Требует: pip install camoufox && python -m camoufox fetch (см. avito/README.md)."""
    import subprocess
    script = os.path.join(HERE, "avito", "avito_wlp.py")
    out_file = os.path.join(HERE, "avito", "avito_wlp_results.json")
    if not os.path.exists(script):
        return []
    try:
        subprocess.run([sys.executable, script] + queries[:2], timeout=240, check=False, capture_output=True)
        data = json.load(open(out_file, encoding="utf-8"))
        return [{"source": f"avito/{niche_key}", "time": "",
                 "text": d.get("title", "") + (" | " + str(d["price"]) if d.get("price") else ""),
                 "url": d.get("url", "")} for d in data]
    except Exception:
        return []



def fetch_kadrof(pages=3, niche_key="mix"):
    """Kadrof.ru — свежие заказы и вакансии с датами и бюджетами, без логина (фактчек 09-11)."""
    out = []
    for page in range(1, pages + 1):
        try:
            raw = get(f"https://www.kadrof.ru/work?page={page}")
        except Exception:
            break
        cards = re.findall(r'href="(/work/\d+)"[^>]*>(?:\s*<[^>]*>)*\s*([^<]{8,100})', raw)
        dates = re.findall(r'(\d{2}\.\d{2}\.\d{4} в \d{2}:\d{2})', raw)
        for (u, t), d in zip(cards, dates + [""] * len(cards)):
            out.append({"source": f"kadrof/{niche_key}", "time": "",
                        "text": f"{t.strip()} | {d}" if d else t.strip(),
                        "url": "https://www.kadrof.ru" + u})
        if len(cards) < 5:
            break
    return out

# ---------------------------------------------------------------- скоринг
KW_CACHE = {}

# маркеры наёма персонала: 2+ = вакансия, не заказ (даже при точном попадании в нишу).
# «требуется/нужен» в списке НЕТ сознательно: на биржах заказов это стиль клиента
# («Требуется дизайнер для айдентики» — заказ). Наём выдают связки: ищем + в команду,
# вилка «от N ₽», з/п, оформление.
HR_MARKS = ("#вакансия", "в команду", "в штат", "з/п", "зарплат", "оклад",
            "собеседовани", "оформление по", "тк рф", "график работ", "ищем",
            "оплату обсуждаем при собеседовании")

def is_vacancy(txt):
    if "#вакансия" in txt: return True   # джоб-борд сам себя обозначил
    n = sum(1 for m in HR_MARKS if m in txt)
    if re.search(r"от [\d\s]{2,7} ?(₽|руб)", txt):
        n += 1
    return n >= 2

def kw_search(txt, kws):
    return [k for k in kws if re.search(r'(?<![а-яa-z0-9])' + re.escape(k) + r'(?![а-яa-z0-9])', txt)]

def build_kws(niche):
    """Ключевые слова ниши = имя + queries. strong = точные формулировки ниши."""
    kws = {"strong": [], "medium": []}
    name = niche["name"].lower()
    strong_src = [name] + [q.lower() for q in niche.get("queries", [])]
    # срезаем очевидные стоп-слова из формулировок
    stop = ("и ", " и", " на", " на ", " для", " с ", " под ", "в ")
    kws["strong"] = list({s.strip() for s in strong_src if 3 < len(s.strip()) < 30})
    # medium — отдельные слова из имени и queries
    words = set()
    for s in strong_src:
        for w in re.findall(r'[а-яa-z]{4,}', s.lower()):
            words.add(w)
    common_ru = {"данные", "системы", "бизнеса", "бизнес", "сайта", "сайт", "услуги", "заказ", "менеджер"}
    kws["medium"] = list(words - common_ru)
    return kws

def score_post(p, kws):
    txt = re.sub(r'\s+', ' ', p.get("text", "").lower().replace('ё', 'е'))
    if len(txt) < 30: return 0, "коротко"
    if re.search(r'#резюме|#resume|ищу работу|в поиске работы', txt): return 0, "резюме (не заказ)"
    if is_vacancy(txt): return 0, "вакансия (наём, не заказ)"
    strong, med = kw_search(txt, kws["strong"]), kw_search(txt, kws["medium"])
    s, why = 0, []
    if strong: s += 40; why.append(f"точное: {', '.join(strong[:3])}")
    elif med: s += 15; why.append(f"смежное: {', '.join(med[:3])}")
    else: return 0, "не ниша"
    for cat, keys, pts in (("urgent", ["срочно", "сегодня", "завтра", "asap", "горящ"], 15),
                           ("money", ["бюджет", "оплата", "₽", "руб", "вилка", "стоимост"], 25),
                           ("scope", ["тз есть", "детали в лс", "в лс", "примеры работ"], 10)):
        h = [k for k in keys if k in txt]
        if h: s += pts; why.append(h[0])
    m = re.search(r'(\d[\d\s]{2,9})\s*(?:₽|руб|тыс)', txt)
    if m:
        val = int(re.sub(r'\s', '', m.group(1)))
        if 1000 <= val <= 600000: s += 10; why.append(f"бюджет ~{val}₽")
    if p.get("time"):
        try:
            age_h = (datetime.now(MSK) - datetime.fromisoformat(p["time"])).total_seconds() / 3600
            if age_h <= 24: s += 10; why.append("<24ч")
            elif age_h <= 72: s += 5
            elif age_h > 400: s -= 15; why.append(f"{int(age_h/24)}дн")
        except Exception: pass
    return max(0, min(100, s)), "; ".join(why)

# ---------------------------------------------------------------- run
def run_niche(key, niche, full=False):
    t0 = time.time()
    posts = []
    if niche.get("fl"):
        try: posts += fetch_fl(niche["fl"], key); print(f"  [fl] +{len(posts)}")
        except Exception as e: print(f"  [fl] ERR {str(e)[:50]}")
    if niche.get("wl"):
        try: n = len(posts); posts += fetch_weblancer(niche["wl"], key); print(f"  [wl] +{len(posts)-n}")
        except Exception as e: print(f"  [wl] ERR {str(e)[:50]}")
    if niche.get("kw") is not None:
        try: n = len(posts); posts += fetch_kwork(niche["kw"], key); print(f"  [kw] +{len(posts)-n}")
        except Exception as e: print(f"  [kw] ERR {str(e)[:50]}")
    if niche.get("tg"):
        try: n = len(posts); posts += fetch_tg(niche["tg"], key); print(f"  [tg] +{len(posts)-n}")
        except Exception as e: print(f"  [tg] ERR {str(e)[:50]}")
    if "kadrof" in (niche.get("sources_extra") or []):
        try: n = len(posts); posts += fetch_kadrof(pages=2, niche_key=key); print(f"  [kadrof] +{len(posts)-n}")
        except Exception as e: print(f"  [kadrof] ERR {str(e)[:50]}")
    extras = niche.get("sources_extra") or []
    if "poisk-pro" in extras:
        try: n = len(posts); posts += fetch_poisk_pro(niche_key=key); print(f"  [poisk-pro] +{len(posts)-n}")
        except Exception as e: print(f"  [poisk-pro] ERR {str(e)[:50]}")
    if "se-guru" in extras:
        try: n = len(posts); posts += fetch_se_guru(niche_key=key); print(f"  [se-guru] +{len(posts)-n}")
        except Exception as e: print(f"  [se-guru] ERR {str(e)[:50]}")
    if "illustrators" in extras:
        try: n = len(posts); posts += fetch_illustrators(niche_key=key); print(f"  [illustrators] +{len(posts)-n}")
        except Exception as e: print(f"  [illustrators] ERR {str(e)[:50]}")
    if key == "freelance-mix":
        try: n = len(posts); posts += fetch_kadrof(pages=4, niche_key=key); print(f"  [kadrof] +{len(posts)-n}")
        except Exception as e: print(f"  [kadrof] ERR {str(e)[:50]}")
    if full and niche.get("queries"):
        try: n = len(posts); posts += fetch_avito(niche["queries"], key); print(f"  [avito] +{len(posts)-n}")
        except Exception as e: print(f"  [avito] ERR {str(e)[:50]}")
    kws = build_kws(niche)
    scored = []
    for p in posts:
        sc, why = score_post(p, kws)
        if sc > 0: scored.append({**p, "score": sc, "why": why})
    scored.sort(key=lambda x: -x["score"])
    leads = [p for p in scored if not p["source"].startswith("avito/")]
    market = [p for p in scored if p["source"].startswith("avito/")]
    hot = [p for p in leads if p["score"] >= 60]
    warm = [p for p in leads if 40 <= p["score"] < 60]
    dt = time.time() - t0
    print(f"  → {niche['name']}: {len(posts)} постов → {len(leads)} в нише → 🔥{len(hot)} 🌤{len(warm)} | "
          f"авито-сигналов {len(market)} | {dt:.0f}с")
    return {"key": key, "name": niche["name"], "total": len(posts), "leads": len(leads),
            "hot": len(hot), "warm": len(warm), "market": len(market), "sec": round(dt),
            "hot_items": [{k: p[k] for k in ("score", "source", "text", "url", "why")} for p in hot[:5]],
            "warm_items": [{k: p[k] for k in ("score", "source", "text", "url", "why")} for p in warm[:5]]}

def render_report(results):
    ts = datetime.now(MSK).strftime("%Y-%m-%d %H:%M")
    rep = [f"# Warm Lead Report — мульти-ниша — {ts} (MSK)", ""]
    tot = sum(r["total"] for r in results); led = sum(r["leads"] for r in results)
    hot = sum(r["hot"] for r in results); mkt = sum(r["market"] for r in results)
    sec = max(r["sec"] for r in results)
    rep.append(f"Ниш: {len(results)} | Собрано: {tot} | В нише: {led} | 🔥 {hot} | Авито-сигналов: {mkt} | время {sec}с")
    # экономика прогона: разбор отчёта + отклик каждому тёплому (см. docs/ru/economics.md)
    rate = int(os.environ.get("WLP_HOURLY", "1500"))
    my_min = 20 + 15 * hot
    cost = my_min / 60 * rate
    cpl = (cost / hot) if hot else None
    rep.append(f"Экономика: ~{my_min} мин работы ({cost:.0f}₽ при ставке {rate}₽/ч; своя ставка — WLP_HOURLY) · "
               f"цена тёплого лида ≈ " + (f"{cpl:.0f}₽" if cpl else "∞ (0 тёплых)"))
    rep.append("")
    rep.append("| Ниша | Всего | В нише | 🔥 | 🌤 | Авито | сек |")
    rep.append("|---|---|---|---|---|---|---|")
    for r in sorted(results, key=lambda x: -(x["hot"] * 10 + x["warm"])):
        rep.append(f"| {r['name']} | {r['total']} | {r['leads']} | {r['hot']} | {r['warm']} | {r['market']} | {r['sec']} |")
    rep.append("")
    for r in results:
        if r["hot_items"]:
            rep.append(f"## 🔥 {r['name']}")
            for p in r["hot_items"]:
                rep.append(f"- **[{p['score']}]** {p['source']} | {p['text'][:100]}")
                rep.append(f"  - {p['url']}")
                rep.append(f"  - {p['why']}")
            rep.append("")
    return "\n".join(rep)

def main():
    niches = load_niches()
    args = sys.argv[1:]
    if "--list" in args:
        for i, (k, v) in enumerate(niches.items(), 1):
            print(f"{i:2}. {k:30} {v['name']}")
        return
    full = "--full" in args
    args = [a for a in args if not a.startswith("--")]
    keys = [args[0]] if args and args[0] in niches else list(niches.keys())
    if args and args[0] not in niches:
        print(f"!! ниша '{args[0]}' не найдена (--list для списка)"); return
    results = []
    print(f"== Warm Lead Parser v2.0: {len(keys)} ниш, режим {'полный' if full else 'быстрый'} ==")
    for k in keys:
        print(f"\n— {niches[k]['name']} —")
        results.append(run_niche(k, niches[k], full=full))
    report = render_report(results)
    fn = os.path.join(HERE, f"warm-lead-report-{datetime.now(MSK).strftime('%Y-%m-%d_%H%M')}.md")
    open(fn, "w", encoding="utf-8").write(report)
    print(f"\n→ Отчёт: {fn}")

if __name__ == "__main__":
    main()
