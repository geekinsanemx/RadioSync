"""radiosync names: shorten channel names to a radio's name length.

Keeps the last token with digits (REP-ABC-123 -> ABC123), drops Spanish and English
stopwords and vowels from words, and numbers collisions so every fitted name in a list
stays distinct.

Changelog:
- 0.1.11 (2026-11-02): English stopwords (of, the, and) alongside the Spanish ones.
- 0.1.9 (2026-11-01): generic example in the module description.
- 0.1.4 (2026-11-01): initial version.
"""

import re

SEPARATORS = re.compile(r"[\s\-_/]+")
STOPWORDS = frozenset({"de", "del", "la", "las", "el", "los", "y", "e", "of", "the", "and"})
VOWELS = frozenset("aeiouAEIOU")


def _squeeze(word: str) -> str:
    return word[:1] + "".join(c for c in word[1:] if c not in VOWELS)


def _fit_words(words: list[str], limit: int) -> str:
    words = [w for w in words if w.lower() not in STOPWORDS] or list(words)
    if len("".join(words)) <= limit:
        return "".join(words)
    for i in reversed(range(len(words))):
        words[i] = _squeeze(words[i])
        if len("".join(words)) <= limit:
            return "".join(words)
    for i in reversed(range(len(words))):
        excess = len("".join(words)) - limit
        if excess <= 0:
            break
        words[i] = words[i][:max(1, len(words[i]) - excess)]
    return "".join(words)[:limit]


def fit_name(name: str, limit: int) -> str:
    """@name unchanged when it fits in @limit characters, otherwise a shortened form."""
    name = name.strip()
    if limit <= 0 or len(name) <= limit:
        return name
    tokens = [t for t in SEPARATORS.split(name) if t]
    numeric = [i for i, t in enumerate(tokens) if any(c.isdigit() for c in t)]
    if not numeric:
        return _fit_words(tokens, limit)
    k = numeric[-1]
    tail = tokens[k]
    if len(tail) >= limit:
        return tail[:limit]
    room = limit - len(tail)
    chosen: list[str] = []
    for token in reversed(tokens[:k]):
        if len(token) <= room - sum(map(len, chosen)):
            chosen.insert(0, token)
        else:
            break
    if chosen:
        return "".join(chosen) + tail
    if k > 0:
        return _fit_words([tokens[k - 1]], room) + tail
    return tail


def clean_name(name: str, charset: str | None) -> str:
    """Upper-case for upper-case-only radios; characters outside @charset become separators."""
    if not charset:
        return name
    if charset == charset.upper():
        name = name.upper()
    cleaned = "".join(c if c in charset else " " for c in name)
    cleaned = " ".join(cleaned.split())
    if " " not in charset:
        cleaned = "-".join(cleaned.split()) if "-" in charset else "".join(cleaned.split())
    return cleaned


def fit_names(names: list[str], limit: int, charset: str | None = None) -> list[str]:
    """Fit every name; shortened names that collide with another name get a numeric suffix."""
    names = [clean_name(n, charset) for n in names]
    fitted = [fit_name(n, limit) for n in names]
    owners: dict[str, str] = {}
    for original, short in zip(names, fitted):
        if short == original.strip():
            owners.setdefault(short.upper(), original.strip())
    result = []
    for original, short in zip(names, fitted):
        original = original.strip()
        key = short.upper()
        if short != original and owners.get(key, original) != original:
            counter = 2
            while True:
                suffix = str(counter)
                candidate = short[:max(0, limit - len(suffix))] + suffix
                if candidate.upper() not in owners:
                    short, key = candidate, candidate.upper()
                    break
                counter += 1
        owners.setdefault(key, original)
        result.append(short)
    return result
