#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Баттл-тесты скоринга WLP v2: 5 боевых кейсов против реального score_post.
Каждый — проверка конкретной границы: идеал, ловушка смежности, rescue-токсик,
древность/любопытство, word-boundary. Ожидание vs факт."""
import sys, os
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import warm_lead_parser as wlp

MSK = timezone(timedelta(hours=3))
now = datetime.now(MSK)

def T(hours_ago):
    return (now - timedelta(hours=hours_ago)).isoformat()

# ключи ниши для тестов — чат-боты (как в niches-50.json)
kws = wlp.build_kws({"name": "Чат-боты и мессенджеры",
                      "queries": ["чат-бот", "телеграм бот", "telegram bot", "бот для бизнеса"]})

battles = [
    {
        "id": "BT-1 ИДЕАЛ",
        "post": {"text": "Нужен чат-бот для приёма заявок в автосервис, ТЗ есть, детали в ЛС. Бюджет 80 000 ₽, срочно — запустить до конца недели", "time": T(3)},
        "expect": "HOT 90-100: strong+деньги+срочно+готов+бюджет+свежесть",
    },
    {
        "id": "BT-2 СМЫСЛОВАЯ ЛОВУШКА",
        "post": {"text": "#вакансия Ищем SMM-менеджера вести наш телеграм канал и контент, удалёнка, от 70 000 ₽", "time": T(5)},
        "expect": "мимо (<40): наём персонала — не заказ бота; слово «телеграм» не должно тянуть 40 баллов",
    },
    {
        "id": "BT-3 RESCUE-ТОКСИК",
        "post": {"text": "Срочно доделать телеграм бот, предыдущий исполнитель пропал на середине, бюджет 10 000 ₽", "time": T(2)},
        "expect": "HOT по баллу — но смотрите на 'предыдущий исполнитель' глазами: чужой код",
    },
    {
        "id": "BT-4 ДРЕВНОСТЬ",
        "post": {"text": "Рассматриваю внедрение чат-бота в процессы записи клиентов, посоветуйте с чего начать", "time": T(900)},
        "expect": "<40: праздное любопытство + 37 дней = актив не заказ",
    },
    {
        "id": "BT-5 WORD-BOUNDARY",
        "post": {"text": "Требуется уборщица в ботанический центр, забота о растениях, оплата 25 000 руб, работа ежедневно", "time": T(4)},
        "expect": "0 «не ниша»: работа/ботанической/забота не должны матчить бота",
    },
]

print("=" * 72)
for b in battles:
    score, why = wlp.score_post(b["post"], kws)
    tier = "🔥 HOT" if score >= 60 else ("🌤 WARM" if score >= 40 else "— мимо")
    print(f'\n[{b["id"]}] ожидание: {b["expect"]}')
    print(f"  факт: {score} → {tier} | {why}")
print("\n" + "=" * 72)
