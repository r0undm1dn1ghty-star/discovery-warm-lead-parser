#!/usr/bin/env python3
"""MCP-сервер Warm Lead Parser — классификация лидов для любых LLM-клиентов.

Чистый Python (stdlib), JSON-RPC 2.0 по stdio (Model Context Protocol).
Никакой сети, никаких зависимостей, никаких логинов и рассылок.

Подключение (любой MCP-клиент: Claude Desktop/Code, Cursor, Cline, Continue,
свой агент):  command = python, args = ["<путь>/mcp_server.py"]

Инструменты:
  score_lead      — оценка одного текста 0-100 (+ причины, полоса hot/warm/cold)
  classify_batch  — батч постов {source: [тексты]} -> лиды, JSON с schema wlp.leads/v1
  explain_rules   — какие правила срабатывают (для отладки и прозрачности)
  selftest        — проверка правил (9 согласованных кейсов)
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import sources  # noqa: E402  (локальный модуль, лежит рядом)

TOOLS = [
    {
        "name": "score_lead",
        "description": "Оценить готовность одного поста/сообщения как лида (0-100) и получить причины. "
                       "Отсеивает вакансии (hr-side) и спам. Не требует сети.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Текст поста или сообщения"},
                "keywords": {"type": "array", "items": {"type": "string"},
                             "description": "Ключевые слова ниши (повышают точность)"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "classify_batch",
        "description": "Классифицировать пачку постов: dict {source: [тексты]} или список. "
                       "Возвращает лиды JSON-схемы wlp.leads/v1, отсортированные по готовности.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "items": {"type": "object", "description": "{source: [тексты]} или {source: текст}"},
                "keywords": {"type": "array", "items": {"type": "string"}},
                "niche": {"type": "string", "description": "Метка нишы для отчёта"},
            },
            "required": ["items"],
        },
    },
    {
        "name": "explain_rules",
        "description": "Показать, какие правила скоринга сработали на тексте (прозрачность, без сети).",
        "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}},
                        "required": ["text"]},
    },
    {
        "name": "selftest",
        "description": "Встроенная проверка правил скоринга (9 согласованных кейсов). Без сети.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def call_tool(name, args):
    args = args or {}
    if name == "score_lead":
        sc, why = sources.score_text(args.get("text", ""), args.get("keywords"))
        return {"score": sc, "tier": sources.tier(sc), "reasons": why,
                "schema": sources.SCHEMA, "version": sources.VERSION}
    if name == "classify_batch":
        res = sources.classify_batch(args.get("items", {}), kws=args.get("keywords"),
                                     niche=args.get("niche"))
        return res
    if name == "explain_rules":
        t = sources.clean_text(args.get("text", ""))
        low = t.lower()
        return {
            "cleaned": t,
            "is_vacancy": sources.is_vacancy(low),
            "money_match": bool(sources.SALARY_RE.search(low)),
            "money_words": [w for w in sources.BUDGET_WORDS if w in low],
            "need_hits": [w for w in sources.NEED_WORDS if w in low],
            "cold_hits": [w for w in sources.COLD_WORDS if w in low],
            "score": sources.score_text(t)[0],
        }
    if name == "selftest":
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            ok = sources._selftest()
        return {"passed": ok, "log": buf.getvalue()}
    raise ValueError(f"Unknown tool: {name}")


def respond(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue
        mid = msg.get("id")
        method = msg.get("method")
        if method == "initialize":
            respond({"jsonrpc": "2.0", "id": mid, "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "warm-lead-parser", "version": sources.VERSION},
            }})
        elif method == "tools/list":
            respond({"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}})
        elif method == "tools/call":
            p = msg.get("params") or {}
            try:
                out = call_tool(p.get("name"), p.get("arguments"))
                respond({"jsonrpc": "2.0", "id": mid, "result": {
                    "content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False, indent=2)}],
                    "isError": False}})
            except Exception as e:
                respond({"jsonrpc": "2.0", "id": mid, "result": {
                    "content": [{"type": "text", "text": f"error: {e}"}], "isError": True}})
        elif method in ("notifications/initialized", "notifications/cancelled"):
            continue
        elif mid is not None:
            respond({"jsonrpc": "2.0", "id": mid,
                     "error": {"code": -32601, "message": f"Method not found: {method}"}})


if __name__ == "__main__":
    main()
