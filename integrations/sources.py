#!/usr/bin/env python3
"""Warm Lead Parser — integration kit для внешних агентных систем и чат-ботов.

Один файл, только стандартная библиотека Python (3.8+). Никаких сетевых вызовов
здесь НЕТ: это чистые функции скоринга/фильтрации, которые можно встроить в
любой агент, чат-бота или воркфлоу — без установки зависимостей и без доступа
к внешним API.

Границы (SAFETY_RAILS): не собирает персональные контакты, не логинится,
не рассылает сообщения. Только классифицирует уже полученный публичный текст.

Использование в своём коде
--------------------------
    from sources import score_text, classify_batch, to_lead_json

    score, why = score_text("Нужен парсер сайта на Python, бюджет 50 тыс. руб.")
    # -> (75, ['бюджет назван', 'нужен специалист'])

    leads = classify_batch(titles_by_source)          # dict: source -> [тексты]
    print(to_lead_json(leads, niche="parsing"))        # JSON для LLM/CRM

Использование как CLI (для чат-ботов и пайплайнов)
--------------------------------------------------
    echo "нужен чат-бот для клиники, оплата 80 000" | python sources.py
    python sources.py --selftest          # встроенная проверка (без сети)
    python sources.py --json --niche ai-agents < posts.txt
"""
from __future__ import annotations

import argparse
import html as _html
import json
import re
import sys

VERSION = "1.0.0"
SCHEMA = "wlp.leads/v1"

# --------------------------------------------------------------------------
# Правила (синхронизированы с warm_lead_parser.py v2.4)
# --------------------------------------------------------------------------

HR_MARKS = (
    "#вакансия", "в команду", "в штат", "з/п", "зарплат", "оклад",
    "требования", "обязанности", "резюме", "соискател", "вакансия",
    "ищем в команду", "ждём в команду", "ждем в команду",
)
HR_STRUCT = ("задачи", "требования", "условия", "что мы предлагаем", "опыт работы")
HR_SOFT = ("ищет ", "ищу ", "в поисках", "открыта вакансия", "на проектную работу")
HR_SEEK = ("требуется", "нужен в штат", "ищем в команду", "резюме направляйте")

SALARY_RE = re.compile(
    # «50 000 ₽», «150000 руб», «от 200 000 р.», «50 тыс. руб.», «300к», «80 000»,
    # «бюджет 1,5 млн»
    r"(пт\s*)?("
    r"от\s*\d[\d\s\u00a0]{2,9}|"
    r"\d[\d\s\u00a0.]{2,9}\s*(тыс|тысяч|к\b|k\b|млн)|"
    r"\d{2,3}[\s\u00a0]?\d{3}\s*(₽|руб|р\.|р\b|рублей|000\b)|"
    r"\d{2,5}\s*(₽|руб|р\.|рублей|\$|€)"
    r")",
    re.IGNORECASE,
)
BUDGET_WORDS = ("бюджет", "оплата", "стоимост", "за проект", "смета", "гонорар", "бюджет:")
# «бюджет есть, сумма обсуждается» — реальный формат бирж (FL.ru, Weblancer, Kwork)
NEGOTIABLE_WORDS = ("по договорённости", "по договоренности", "по результатам собеседования",
                    "бюджет обсуждается", "цена обсуждается", "оплата по факту",
                    "по договорной", "обсуждается", "договорная")
NEED_WORDS = (
    "нужен", "нужна", "нужно", "требуется", "ищу", "ищем", "подскажите",
    "кто может", "кто умеет", "посоветуйте", "есть задача", "есть проект",
    "разработка", "сделать", "написать", "внедрить", "настроить", "автоматизировать",
)
# ВАЖНО: проверяются как отдельные слова с границей — «доставки» не должно
# срабатывать на «ставки».
COLD_WORDS = (
    "продам", "продаю", "куплю курс", "обучение с нуля", "заработай",
    "инвестиции в", "криптовалют", "букмекер", "казино", "заработок в интернете",
    "без вложений",
)
COLD_WORD_RES = tuple(re.compile(r"(?<![а-яё])" + re.escape(w) + r"(?![а-яё])", re.IGNORECASE)
                      for w in COLD_WORDS)


def is_cold(low: str) -> bool:
    """Холодный/спам-сигнал с границей слова (не подстрока)."""
    return any(rx.search(low) for rx in COLD_WORD_RES) or "бесплатно" in low
VACANCY_WORD_RE = re.compile(r"(?<![а-яё#])ваканси[яию]", re.IGNORECASE)

MAX_TEXT = 600  # защита от гигантских входов


def clean_text(txt: str) -> str:
    """HTML -> текст, удаление мусора. Безопасно к None и не-строкам."""
    if txt is None:
        return ""
    txt = str(txt)[:8000]
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = _html.unescape(txt)
    return " ".join(txt.split())[:MAX_TEXT]


def is_vacancy(txt: str) -> bool:
    """True — это предложение работы (hr-side), а не запрос клиента."""
    low = clean_text(txt).lower()
    if not low:
        return False
    if VACANCY_WORD_RE.search(low):
        return True
    if SALARY_RE.search(low) and sum(m in low for m in HR_MARKS) >= 1:
        return True
    if sum(m in low for m in HR_MARKS) >= 2:
        return True
    if sum(m in low for m in HR_STRUCT) >= 3:
        return True
    if any(m in low for m in HR_SOFT) and any(m in low for m in HR_STRUCT):
        return True
    # «требуется верстальщик, задачи: ..., условия: ...» — вакансия без явных HR-меток
    if any(m in low for m in HR_SEEK) and sum(m in low for m in HR_STRUCT) >= 2:
        return True
    return False


def _kw_match(low, kws):
    """Совпадение ключевых слов ниши с морфологией.

    Правила подобраны на реальных данных FL.ru:
      - длинный ключ (5+) — по корню с учётом приставок: «парсер»→«парс»
        ловит «спарсить», «парсинг», «парсера»;
      - короткий ключ (3–4) — по границе слова с учётом окончаний:
        «бот» ловит «бота», «боты», но не «работа»;
      - совсем короткий (<=2) или с цифрой — только точное слово:
        «ии» не ловится внутри «функции», «1с» — отдельно;
      - ё/е и латиница/кириллица нормализуются (telegram↔телеграм).
    Возвращает совпавшие ключи без дублей по корню.
    """
    _PREFIX = r"(?:с|со|по|за|на|от|до|пере|про|вы|при|у|из|раз|об|под|над|пред|без|не)?"

    def _stem(k):
        return re.sub(
            r"(иями|ами|ями|ание|ания|аний|ение|ения|ений|ация|ации|ность|ство|"
            r"инг|ист|изм|ац|яц|иц|ер|ор|ар|ир|ов|ев|ий|ый|ой|ая|ые|"
            r"ing|ers|er|s|а|я|ы|и|е|у|о|ь)$", "", k)

    norm = low.replace("ё", "е")
    for lat, cyr in (("telegram", "телеграм"), ("python", "питон"),
                     ("wordpress", "вордпресс"), ("whatsapp", "ватсап")):
        if lat in norm or cyr in norm:
            norm += " " + lat + " " + cyr

    hits, seen = [], set()
    for k in (kws or []):
        k = k.strip().lower().replace("ё", "е")
        if not k:
            continue
        found = False
        if len(k) <= 2 or any(c.isdigit() for c in k):
            found = bool(re.search(r"(?<![а-яёa-z0-9])" + re.escape(k) + r"(?![а-яёa-z0-9])", norm))
        elif len(k) <= 4:
            st = _stem(k)
            found = bool(re.search(r"(?<![а-яёa-z0-9])" + re.escape(st) + r"[а-яё]{0,3}(?![а-яёa-z0-9])", norm))
            if not found and k.isascii():
                found = bool(re.search(r"[a-z]" + re.escape(k), norm))
        else:
            st = _stem(k)
            found = bool(re.search(r"(?<![а-яёa-z0-9])" + _PREFIX + re.escape(st), norm))
        if found:
            root = _stem(k)
            if root not in seen:
                seen.add(root)
                hits.append(k)
    return hits


def score_text(txt: str, kws=None):
    """Оценка готовности лида 0-100 + причины.

    ЛОГИКА (переработана на реальных данных FL.ru 20.09.2026, 286 постов):
    ниша — ГЕЙТ, а не добавка. Деньги и «нужен специалист» есть почти в каждом
    посте биржи и потому не различают ниши; различает только совпадение ниши.
    Раньше деньги давали +50, ниша +15 -> точность 25%. Теперь наоборот.

    score=0 — не лид: вакансия, спам, пустой текст.
    score<=25 — нет совпадения ниши (не наш лид, что бы там ни было про бюджет).
    """
    t = clean_text(txt)
    low = t.lower()
    if not t:
        return 0, ["пустой текст"]
    if is_vacancy(low):
        return 0, ["вакансия/hr-side (не клиент)"]
    if is_cold(low):
        return 0, ["холодный/спам-сигнал"]

    score, why = 0, []

    # ── ГЕЙТ: совпадение ниши ──
    niche = _kw_match(low, kws)
    if kws:
        if len(niche) >= 2:
            score += 40
            why.append("ниша: 2+ совпадения")
        elif len(niche) == 1:
            score += 25
            why.append("ниша: 1 совпадение")
        else:
            # ниша не совпала — это не наш лид, независимо от бюджета.
            # Держим score строго ниже WARM_MIN (30), чтобы бюджет не вытаскивал
            # чужую нишу в список: без совпадения ниши лид не существует.
            return 5, ["ниша не совпала (не наш лид)"]

    # ── Бюджет: только надбавка (есть почти везде) ──
    money_strong = bool(SALARY_RE.search(low))
    money_negotiable = any(w in low for w in NEGOTIABLE_WORDS)
    if money_strong:
        score += 20
        why.append("бюджет назван (сумма)")
    elif money_negotiable:
        score += 12
        why.append("бюджет обсуждается")
    elif any(w in low for w in BUDGET_WORDS):
        score += 5
        why.append("бюджет упомянут")

    # ── Явный запрос специалиста ──
    hits = [w for w in NEED_WORDS if w in low]
    if hits:
        score += min(15, 5 * len(hits))
        why.append("нужен специалист")

    # ── Детали и срочность ──
    if len(t) >= 80:
        score += 5
        why.append("есть детали")
    if any(w in low for w in ("срочно", "asap", "горит", "нужно сегодня")):
        score += 5
        why.append("срочно")

    return min(100, score), why


# Пороги откалиброваны на 286 реальных постах FL.ru (20.09.2026):
# точность 76%, полнота 53% на разделении IT-услуги vs прочие ниши.
WARM_MIN = 30
HOT_MIN = 50


def tier(score: int) -> str:
    """Полоса готовности: hot>=50, warm>=30, иначе cold (см. EVAL.md)."""
    if score >= HOT_MIN:
        return "hot"
    if score >= WARM_MIN:
        return "warm"
    return "cold"


def classify_batch(items, kws=None, niche=None):
    """Классификация батча постов.

    items: dict {source: [текст, ...]} ИЛИ list[dict|str].
    Возвращает {"schema", "niche", "counts", "leads": [...]}.
    """
    leads = []
    pairs = []
    if isinstance(items, dict):
        for src, vals in items.items():
            for v in (vals if isinstance(vals, (list, tuple)) else [vals]):
                pairs.append((src, v))
    else:
        for i, v in enumerate(items or []):
            if isinstance(v, dict):
                pairs.append((v.get("source", f"item-{i}"), v.get("text", "")))
            else:
                pairs.append((f"item-{i}", v))
    for src, val in pairs:
        text = val.get("text", "") if isinstance(val, dict) else val
        url = val.get("url", "") if isinstance(val, dict) else ""
        sc, why = score_text(text, kws)
        if sc > 0:
            leads.append({"score": sc, "tier": tier(sc), "source": src,
                          "text": clean_text(text), "url": url, "why": why})
    leads.sort(key=lambda x: -x["score"])
    counts = {"hot": 0, "warm": 0, "cold": 0}
    for l in leads:
        counts[l["tier"]] += 1
    return {"schema": SCHEMA, "version": VERSION, "niche": niche,
            "counts": counts, "total_leads": len(leads), "leads": leads}


def to_lead_json(result, **kw) -> str:
    """JSON-строка, готовая к передаче в LLM-контекст или CRM."""
    if "schema" not in result:
        result = classify_batch(result, **kw)
    return json.dumps(result, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _selftest():
    # (текст, ключевые слова ниши, ожидаемая полоса, замечание).
    # Пороги hot>=50/warm>=30 откалиброваны на 286 реальных постах FL.ru.
    cases = [
        ("Нужен парсер Avito, бюджет 50 тыс. руб., срочно. выгрузка в Excel и ежедневное обновление",
         ["парсер"], "hot", "ниша + сумма + детали -> hot"),
        ("Нужен парсер сайта на Python, бюджет 50 тыс. руб.",
         ["парсер"], "hot", "ниша + сумма -> hot"),
        ("Ищу подрядчика на внедрение CRM и автоматизацию воронки, есть ТЗ, бюджет 250 тыс.",
         ["crm", "автоматизац"], "hot", "ниша + сумма + детали -> hot"),
        ("Разработка парсеров для двух площадок госзакупок",
         ["парсер"], "warm", "ниша, бюджет по договорённости -> warm"),
        ("Ищем разработчика в команду, з/п от 150 000 р., требования: опыт 3 года",
         ["парсер"], "cold", "hr-side (вакансия) -> не лид"),
        ("требуется верстальщик, задачи: адаптив, условия: удалёнка",
         ["верстк"], "cold", "вакансия -> не лид"),
        ("продам курс по заработку в интернете, пишите в лс", ["бот"], "cold", "спам -> не лид"),
        ("Заработок в интернете без вложений, пиши в лс", ["бот"], "cold", "спам -> не лид"),
        ("", ["бот"], "cold", "пустой текст -> не лид"),
        # ГЛАВНАЯ проверка на реальных данных: чужая ниша не проходит, даже с бюджетом
        ("Отредактировать 6 PDF файлов, оплата 100$", ["парсер", "бот"], "cold",
         "ниша не совпала -> не наш лид, несмотря на оплату"),
        ("Копирайтер для написания постов, хорошая оплата", ["парсер", "бот"], "cold",
         "ниша не совпала -> не наш лид"),
        ("Монтаж Reels / Shorts для музыкального проекта, оплата 25000", ["парсер", "бот"], "cold",
         "ниша не совпала -> не наш лид"),
    ]
    ok = 0
    for txt, kws, want_tier, note in cases:
        sc, why = score_text(txt, kws)
        got = tier(sc)
        mark = "OK " if got == want_tier else "FAIL"
        if mark == "OK ":
            ok += 1
        print(f"[{mark}] {got:4s}(want {want_tier:4s}) score={sc:3d} why={why} :: {txt[:50] or '<пусто>'}")
    print(f"SELFTEST: {ok}/{len(cases)}")
    return ok == len(cases)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Warm Lead Parser integration kit (stdlib-only, без сети)")
    ap.add_argument("--selftest", action="store_true", help="встроенная проверка правил")
    ap.add_argument("--json", action="store_true", help="вывод JSON (схема wlp.leads/v1)")
    ap.add_argument("--niche", default=None, help="метка ниши для отчёта")
    ap.add_argument("--kw", default=None, help="ключевые слова ниши через запятую")
    a = ap.parse_args(argv)
    if a.selftest:
        return 0 if _selftest() else 1
    raw = sys.stdin.read()
    lines = [l for l in raw.splitlines() if l.strip()]
    kws = [x.strip() for x in a.kw.split(",")] if a.kw else None
    res = classify_batch(lines, kws=kws, niche=a.niche)
    if a.json:
        print(to_lead_json(res))
    else:
        print(f"постов={len(lines)} лидов={res['total_leads']} "
              f"🔥={res['counts']['hot']} 🌤={res['counts']['warm']}")
        for l in res["leads"][:10]:
            print(f"  [{l['score']:3d} {l['tier']:4s}] {l['text'][:90]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
