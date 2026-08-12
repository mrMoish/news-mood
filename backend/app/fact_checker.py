"""Эвристическая проверка сохранения фактов после переписывания.

Идея: до отправки текста в LLM мы вытаскиваем из ОРИГИНАЛА "факты" —
числа, даты/годы, прямые цитаты в кавычках и стемы имён собственных —
а после получения переписанного текста проверяем, что каждый из них
всё ещё присутствует в результате. Если что-то пропало — это явный
сигнал, что модель могла исказить факты, и мы показываем это в UI.

Это намеренно простая (regex-based) проверка, а не полноценный NLP —
для новостной заметки в несколько предложений она уже даёт полезный
сигнал, а её логика полностью прозрачна и объяснима.
"""
import re

MONTHS = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]

_NUMBER_RE = re.compile(r"\d[\d\s]*[.,]?\d*\s*%?")
_DATE_RE = re.compile(r"\b\d{1,2}\s+(?:" + "|".join(MONTHS) + r")(?:\s+\d{4})?\b", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_QUOTE_RE = re.compile(r"«([^»]{3,150})»|\"([^\"]{3,150})\"")
# Заглавное кириллическое слово, которое не стоит в самом начале строки —
# грубое, но рабочее приближение к "имени собственному".
_PROPER_NOUN_RE = re.compile(r"(?<!^)(?<=[а-яё,;:\s])\b([А-ЯЁ][а-яё]{2,})\b")


def _extract_numbers(text: str) -> set[str]:
    found = {m.strip() for m in _NUMBER_RE.findall(text)}
    return {f for f in found if any(ch.isdigit() for ch in f) and f.strip(" %.,")}


def _extract_dates(text: str) -> set[str]:
    dates = {m.group(0).strip() for m in _DATE_RE.finditer(text)}
    years = {m.group(0) for m in _YEAR_RE.finditer(text)}
    return dates | years


def _extract_quotes(text: str) -> set[str]:
    quotes = set()
    for m in _QUOTE_RE.finditer(text):
        q = (m.group(1) or m.group(2) or "").strip()
        if q:
            quotes.add(q)
    return quotes


def _extract_proper_noun_stems(text: str) -> set[str]:
    """Из-за русских падежей ('Путин' -> 'Путина', 'Путиным') сравнивать
    слова целиком ненадёжно, поэтому берём начальный стем слова (4-5 букв),
    который обычно переживает изменение окончания."""
    stems = set()
    for w in _PROPER_NOUN_RE.findall(text):
        stem = w[:5] if len(w) > 5 else w[:4]
        if len(stem) >= 3:
            stems.add(stem.lower())
    return stems


def check_facts(original: str, rewritten: str) -> dict:
    rewritten_flat = rewritten.lower()
    rewritten_no_spaces = rewritten.replace(" ", "")

    numbers = _extract_numbers(original)
    dates = _extract_dates(original)
    quotes = _extract_quotes(original)
    stems = _extract_proper_noun_stems(original)

    missing_numbers = sorted(n for n in numbers if n.replace(" ", "") not in rewritten_no_spaces)
    missing_dates = sorted(d for d in dates if d.lower() not in rewritten_flat)
    missing_quotes = sorted(q for q in quotes if q.lower() not in rewritten_flat)
    missing_names = sorted(s for s in stems if s not in rewritten_flat)

    total = len(numbers) + len(dates) + len(quotes) + len(stems)
    missing = len(missing_numbers) + len(missing_dates) + len(missing_quotes) + len(missing_names)
    score = round((total - missing) / total, 2) if total else 1.0

    return {
        "score": score,
        "passed": missing == 0,
        "checked": {
            "numbers": sorted(numbers),
            "dates": sorted(dates),
            "quotes": sorted(quotes),
            "name_stems": sorted(stems),
        },
        "missing": {
            "numbers": missing_numbers,
            "dates": missing_dates,
            "quotes": missing_quotes,
            "name_stems": missing_names,
        },
    }
