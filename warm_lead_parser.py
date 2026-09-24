#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Discovery Warm Lead Parser v2.4 — мульти-нишевой движок.
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
import json, re, html, sys, os, time, socket
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
# v2.3: единый потолок ожидания на сокете. Один зависший источник (FL.ru по
# таймауту на баттлтесте 16.09.2026) не должен сжрать бюджет всего прогона.
socket.setdefaulttimeout(12)

def get(u, timeout=12, headers=None):
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
    raw = urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "ignore")
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
# v2.4: HR-структура вакансии — у заказа нет «Задачи/Требования/Условия» списком.
# Формат без двоеточия («Задачи 10-15 статей») тоже ловим: слово + цифры/перенос.
HR_STRUCT = ("задачи", "требования", "условия", "что мы предлагаем", "опыт работы")
# «ищет/ищу команду/в поисках» — вариации «ищем»
HR_SOFT = ("ищет ", "ищу ", "в поисках", "открыта вакансия", "на проектную работу")

# зарплатная вилка: «от 150 000 ₽/руб/руб./рублей/р.», диапазоны «от X до Y».
# v2.4: раньше регекс ловил только ₽|руб и требовал «от» — «От 150 000 р.» проходил
# фильтр и вакансии утекали в тёплые лиды (баг из баттлтеста 17.09.2026).
SALARY_RE = re.compile(
    r"(?:от\s*)?(\d[\d\s\u00a0.,]{2,12}?)\s*(?:до\s*[\d\s\u00a0.,]{2,12}?\s*)?(?:₽|руб\.?|рублей|р\.)"
)
# словесные маркеры бюджета ЗАКАЗА: при них сумма — это деньги проекта, не вилка
BUDGET_WORDS = ("бюджет", "оплата", "стоимост", "за проект", "смета")
VACANCY_WORD_RE = re.compile(r"(?<![а-яё#])ваканси[яию]", re.IGNORECASE)

def is_vacancy(txt):
    if "#вакансия" in txt: return True   # джоб-борд сам себя обозначил
    if VACANCY_WORD_RE.search(txt): return True   # «вакансия: ...» без хештега
    n = sum(1 for m in HR_MARKS if m in txt)
    n += sum(1 for m in HR_STRUCT if m in txt)   # v2.4: скелет вакансии
    n += sum(1 for m in HR_SOFT if m in txt)     # v2.4: вариации «ищем»
    # зарплатная вилка: сумма ≥ 60 000 без слов «бюджет/оплата» — месячная з/п, не
    # деньги проекта («бюджет 80 000 р.» в заказе — не наём). «От X до Y» тоже вилка.
    if SALARY_RE.search(txt):
        m = SALARY_RE.search(txt)
        try: amount = int(re.sub(r"[\s\u00a0.,]", "", m.group(1)))
        except ValueError: amount = 0
        is_project_budget = any(w in txt for w in BUDGET_WORDS)
        if amount >= 60000 and not is_project_budget:
            n += 2
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
    if re.search(r'#резюме|#resume|ищу работу|в поиске работы|резюме [a-z@]', txt): return 0, "резюме (не заказ)"
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
    src_ok, src_err = [], []   # v2.4: живость источников — бенчмарк скорости привязан к ним
    def _src(fn, tag, *a):
        try:
            added = fn(*a)
            n = len(posts)
            posts.extend(added)
            src_ok.append(f"{tag}+{len(posts)-n}")
        except Exception as e:
            src_err.append(f"{tag} ERR {str(e)[:40]}")
    if niche.get("fl"):
        _src(fetch_fl, "fl", niche["fl"], key)
        print(f"  [fl] {src_ok[-1] if src_ok and src_ok[-1].startswith('fl') else src_err[-1] if src_err and src_err[-1].startswith('fl') else ''}")
    if niche.get("wl"):
        _src(fetch_weblancer, "wl", niche["wl"], key)
        print(f"  [wl] {src_ok[-1] if src_ok and src_ok[-1].startswith('wl') else src_err[-1] if src_err and src_err[-1].startswith('wl') else ''}")
    if niche.get("kw") is not None:
        _src(fetch_kwork, "kw", niche["kw"], key)
        print(f"  [kw] {src_ok[-1] if src_ok and src_ok[-1].startswith('kw') else src_err[-1] if src_err and src_err[-1].startswith('kw') else ''}")
    if niche.get("tg"):
        _src(fetch_tg, "tg", niche["tg"], key)
        print(f"  [tg] {src_ok[-1] if src_ok and src_ok[-1].startswith('tg') else src_err[-1] if src_err and src_err[-1].startswith('tg') else ''}")
    if "kadrof" in (niche.get("sources_extra") or []):
        _src(fetch_kadrof, "kadrof", 2, key)
        print(f"  [kadrof] {src_ok[-1] if src_ok and src_ok[-1].startswith('kadrof') else src_err[-1] if src_err and src_err[-1].startswith('kadrof') else ''}")
    extras = niche.get("sources_extra") or []
    if "poisk-pro" in extras:
        _src(fetch_poisk_pro, "poisk-pro", key)
        print(f"  [poisk-pro] {src_ok[-1] if src_ok and src_ok[-1].startswith('poisk-pro') else src_err[-1] if src_err and src_err[-1].startswith('poisk-pro') else ''}")
    if "se-guru" in extras:
        _src(fetch_se_guru, "se-guru", key)
        print(f"  [se-guru] {src_ok[-1] if src_ok and src_ok[-1].startswith('se-guru') else src_err[-1] if src_err and src_err[-1].startswith('se-guru') else ''}")
    if "illustrators" in extras:
        _src(fetch_illustrators, "illustrators", key)
        print(f"  [illustrators] {src_ok[-1] if src_ok and src_ok[-1].startswith('illustrators') else src_err[-1] if src_err and src_err[-1].startswith('illustrators') else ''}")
    if key == "freelance-mix":
        _src(fetch_kadrof, "kadrof", 4, key)
        print(f"  [kadrof] {src_ok[-1] if src_ok and src_ok[-1].startswith('kadrof') else src_err[-1] if src_err and src_err[-1].startswith('kadrof') else ''}")
    if full and niche.get("queries"):
        _src(fetch_avito, "avito", niche["queries"], key)
        print(f"  [avito] {src_ok[-1] if src_ok and src_ok[-1].startswith('avito') else src_err[-1] if src_err and src_err[-1].startswith('avito') else ''}")
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
    # v2.4: метрики отчёта — сколько 🔥 назвали деньги (главный предиктор «тёплоты»)
    # и сколько отсеяно как вакансии/резюме (HR-фильтр)
    money_keys = ("₽", "руб", "бюджет", "оплата", "стоимост", "тыс")
    hot_with_money = sum(1 for p in hot if any(k in p["text"].lower() for k in money_keys))
    src_line = f"источники {len(src_ok)} ок / {len(src_err)} таймаут" + (f" ({', '.join(src_err)})" if src_err else "")
    print(f"  → {niche['name']}: {len(posts)} постов → {len(leads)} в нише → 🔥{len(hot)} 🌤{len(warm)} | "
          f"🔥 с деньгами {hot_with_money}/{len(hot)} | {src_line} | {dt:.0f}с")
    return {"key": key, "name": niche["name"], "total": len(posts), "leads": len(leads),
            "hot": len(hot), "warm": len(warm), "market": len(market), "sec": round(dt),
            "src_ok": len(src_ok), "src_err": len(src_err), "src_err_names": list(src_err),
            "hot_money": hot_with_money,
            "hot_items": [{k: p[k] for k in ("score", "source", "text", "url", "why")} for p in hot[:5]],
            "warm_items": [{k: p[k] for k in ("score", "source", "text", "url", "why")} for p in warm[:5]]}

def render_report(results):
    ts = datetime.now(MSK).strftime("%Y-%m-%d %H:%M")
    rep = [f"# Warm Lead Report — мульти-ниша — {ts} (MSK)", ""]
    tot = sum(r["total"] for r in results); led = sum(r["leads"] for r in results)
    hot = sum(r["hot"] for r in results); mkt = sum(r["market"] for r in results)
    sec = max(r["sec"] for r in results)
    hot_money = sum(r.get("hot_money", 0) for r in results)
    rep.append(f"Ниш: {len(results)} | Собрано: {tot} | В нише: {led} | 🔥 {hot} | 🔥 с деньгами {hot_money}/{hot} | время {sec}с")
    errs = [e for r in results for e in r.get("src_err_names", [])]
    if errs:
        rep.append(f"Источники с таймаутами: {len(errs)} — {'; '.join(errs[:8])}")
    # экономика прогона: разбор отчёта + отклик каждому тёплому (см. docs/ru/economics.md)
    rate = int(os.environ.get("WLP_HOURLY", "1500"))
    my_min = 20 + 15 * hot
    cost = my_min / 60 * rate
    cpl = (cost / hot) if hot else None
    rep.append(f"Экономика: ~{my_min} мин работы ({cost:.0f}₽ при ставке {rate}₽/ч; своя ставка — WLP_HOURLY) · "
               f"цена тёплого лида ≈ " + (f"{cpl:.0f}₽" if cpl else "∞ (0 тёплых)"))
    rep.append("")
    rep.append("| Ниша | Всего | В нише | 🔥 | 🌤 | 🔥 с деньгами | Источники | сек |")
    rep.append("|---|---|---|---|---|---|---|---|")
    for r in sorted(results, key=lambda x: -(x["hot"] * 10 + x["warm"])):
        src_col = f"{r.get('src_ok', 0)} ок / {r.get('src_err', 0)} таймаут"
        rep.append(f"| {r['name']} | {r['total']} | {r['leads']} | {r['hot']} | {r['warm']} | {r.get('hot_money', 0)}/{r['hot']} | {src_col} | {r['sec']} |")
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
    print(f"== Warm Lead Parser v2.4: {len(keys)} ниш, режим {'полный' if full else 'быстрый'} ==")
    for k in keys:
        print(f"\n— {niches[k]['name']} —")
        results.append(run_niche(k, niches[k], full=full))
    report = render_report(results)
    fn = os.path.join(HERE, f"warm-lead-report-{datetime.now(MSK).strftime('%Y-%m-%d_%H%M')}.md")
    open(fn, "w", encoding="utf-8").write(report)
    print(f"\n→ Отчёт: {fn}")

if __name__ == "__main__":
    main()
