"""
AI-слой: речевая аналитика звонков и автоматизация follow-up.

Здесь две задачи из вакансии:
  1) analyze_transcript() — по тексту звонка вернуть саммари, намерение (intent)
     и тональность (sentiment). Это «речевая аналитика».
  2) decide_followup()    — по результату анализа решить, нужна ли авто-задача
     менеджеру. Это «AI-автоматизация бизнес-процессов».

Сейчас analyze_transcript работает как rule-based заглушка (без внешних вызовов),
чтобы проект запускался офлайн и без ключей. НО функция специально построена вокруг
шва `_call_llm()` — единственного места, куда подключается настоящая модель
(OpenRouter / Claude / GPT). Заменить мок на реальный LLM — это переписать одну
функцию, не трогая остальной код.
"""
from __future__ import annotations

import json
import os
import re

# Допустимые значения — держим в одном месте, чтобы и БД, и фронтенд опирались на них.
INTENTS = ("interested", "not_interested", "callback_requested", "question", "other")
SENTIMENTS = ("positive", "neutral", "negative")

# Ключевые слова для мок-анализа. В реальной системе это заменяет LLM.
# Порядок важен: более «сильные» намерения проверяются первыми
# (явный отказ/просьба перезвонить/вопрос важнее общего интереса).
_INTENT_KEYWORDS = {
    "callback_requested": ["перезвон", "перезвоните", "наберите позже", "позже", "неудобно говорить"],
    "not_interested": ["не интересно", "не нужно", "не актуально", "отказ", "дорого"],
    "question": ["вопрос", "можно ли", "уточнить", "подскажите", "правда ли"],
    "interested": ["интересно", "готов", "давайте", "хочу", "оформить", "сколько стоит", "цена", "тариф"],
}
_NEGATIVE_WORDS = ["не интересно", "не нужно", "дорого", "отказ", "плохо", "недоволен", "жалоба"]
_POSITIVE_WORDS = ["интересно", "отлично", "спасибо", "готов", "супер", "хорошо", "давайте"]


def _mentions(text: str, phrase: str) -> bool:
    """Совпадение по границам слов, а не по подстроке.

    Иначе «не интересно» ошибочно находится внутри «мне интересно» —
    именно этот баг ловят тесты. \\b под Unicode корректно работает с кириллицей.
    """
    return re.search(r"\b" + re.escape(phrase) + r"\b", text) is not None


def _call_llm(transcript: str) -> dict | None:
    """Единственная точка интеграции с настоящей моделью.

    Возвращает dict вида {"summary": str, "intent": str, "sentiment": str}
    либо None, если LLM недоступен (тогда вызывающий код откатывается на rule-based мок).

    Чтобы включить реальную модель — задайте переменную окружения OPENROUTER_API_KEY
    (или CLAUDE_API_KEY) и реализуйте вызов ниже. Ниже — заготовка запроса к OpenRouter,
    оставленная закомментированной, чтобы не тянуть сетевые зависимости в тестовый проект.
    """
    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("CLAUDE_API_KEY")
    if not api_key:
        return None

    # --- Реальная интеграция (пример для OpenRouter, требует пакета requests) ---
    # import requests
    # prompt = (
    #     "Ты — аналитик звонков отдела продаж. Верни строго JSON с полями "
    #     "summary (1-2 предложения), intent (одно из "
    #     f"{list(INTENTS)}), sentiment (одно из {list(SENTIMENTS)}).\n\n"
    #     f"Транскрипт звонка:\n{transcript}"
    # )
    # resp = requests.post(
    #     "https://openrouter.ai/api/v1/chat/completions",
    #     headers={"Authorization": f"Bearer {api_key}"},
    #     json={
    #         "model": "anthropic/claude-sonnet-4",
    #         "messages": [{"role": "user", "content": prompt}],
    #         "response_format": {"type": "json_object"},
    #     },
    #     timeout=30,
    # )
    # data = json.loads(resp.json()["choices"][0]["message"]["content"])
    # return _validate_llm_output(data)
    return None


def _validate_llm_output(data: dict) -> dict:
    """Не доверяем ответу модели вслепую — приводим к допустимым значениям."""
    intent = data.get("intent")
    sentiment = data.get("sentiment")
    return {
        "summary": (data.get("summary") or "").strip(),
        "intent": intent if intent in INTENTS else "other",
        "sentiment": sentiment if sentiment in SENTIMENTS else "neutral",
    }


def _mock_analyze(transcript: str) -> dict:
    """Rule-based запасной вариант: без сети, детерминированный, для офлайн-демо и тестов."""
    text = (transcript or "").lower()

    intent = "other"
    for candidate, keywords in _INTENT_KEYWORDS.items():
        if any(_mentions(text, kw) for kw in keywords):
            intent = candidate
            break

    if any(_mentions(text, w) for w in _NEGATIVE_WORDS):
        sentiment = "negative"
    elif any(_mentions(text, w) for w in _POSITIVE_WORDS):
        sentiment = "positive"
    else:
        sentiment = "neutral"

    # Простое «саммари»: первое предложение транскрипта, обрезанное по длине.
    first_sentence = transcript.strip().split(".")[0].strip() if transcript else ""
    summary = (first_sentence[:120] + "…") if len(first_sentence) > 120 else first_sentence

    return {"summary": summary, "intent": intent, "sentiment": sentiment}


def analyze_transcript(transcript: str) -> dict:
    """Главная функция речевой аналитики.

    Пытается сходить в настоящий LLM; если ключа нет или модель недоступна —
    прозрачно откатывается на rule-based мок. Вызывающий код не знает разницы.
    """
    llm_result = _call_llm(transcript)
    if llm_result is not None:
        return llm_result
    return _mock_analyze(transcript)


# Человекочитаемые заголовки для авто-задач по каждому намерению.
_FOLLOWUP_TITLES = {
    "callback_requested": "Перезвонить клиенту (просил связаться позже)",
    "interested": "Отправить КП / счёт — клиент заинтересован",
    "question": "Ответить на вопрос клиента по звонку",
}


def decide_followup(analysis: dict) -> str | None:
    """AI-автоматизация: по результату анализа решаем, нужна ли задача менеджеру.

    Возвращает заголовок задачи (str) либо None, если follow-up не нужен
    (например, клиенту не интересно). Заголовок затем уходит в create_task(created_by='ai').
    """
    return _FOLLOWUP_TITLES.get(analysis.get("intent"))
