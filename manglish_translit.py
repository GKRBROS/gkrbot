"""
manglish_translit.py — Manglish/Hinglish -> native script transliteration for TTS.

Why this exists:
    Edge neural voices (ml-IN-SobhanaNeural, hi-IN-SwaraNeural, etc.) read
    the SCRIPT they're built for. Feed "evideya" to the Malayalam voice and
    it reads it as English letters, not as "എവിടെയാ" — that's why Manglish
    text comes out mangled/wrong even though the right voice is selected.

    This module converts common Manglish/Hinglish words (typed in Latin
    letters) to their native-script spelling before the text is handed to
    the TTS engine, so the neural voice actually reads the intended word.

Strategy, per word:
    1. Exact dictionary lookup (curated, high-confidence spellings for the
       colloquial words this bot already recognizes for language detection).
    2. Phonetic fallback via the `indic_transliteration` package (ITRANS
       scheme), if installed — decent for words not in the dictionary.
    3. If neither applies, leave the word as-is.

Only touches text when the target language is "ml" or "hi" AND the text
has no native-script characters already (so real Malayalam/Hindi script
input passes through untouched).
"""

from __future__ import annotations

import re
from typing import Optional

# ---------------------------------------------------------------------------
# Malayalam (Manglish) dictionary — curated spellings for common Manglish
# words. Deliberately excludes slurs/profanity: those are left to the
# phonetic fallback rather than given an explicit "correct" spelling here.
# ---------------------------------------------------------------------------
MANGLISH_TO_MALAYALAM = {
    "evide": "എവിടെ",
    "evideya": "എവിടെയാ",
    "evideyannu": "എവിടെയാണ്",
    "aanu": "ആണ്",
    "aano": "ആണോ",
    "ano": "ആണോ",
    "undo": "ഉണ്ടോ",
    "und": "ഉണ്ട്",
    "entha": "എന്താ",
    "enthanu": "എന്താണ്",
    "enthokke": "എന്തൊക്കെ",
    "sugam": "സുഖം",
    "sugamano": "സുഖമാണോ",
    "sugamaano": "സുഖമാണോ",
    "sugamalle": "സുഖമല്ലേ",
    "njan": "ഞാൻ",
    "nammal": "നമ്മൾ",
    "cheyyan": "ചെയ്യാൻ",
    "cheyyuka": "ചെയ്യുക",
    "cheyyu": "ചെയ്യൂ",
    "parayu": "പറയൂ",
    "nokku": "നോക്കൂ",
    "kollam": "കൊള്ളാം",
    "adipoli": "അടിപൊളി",
    "machane": "മച്ചാനെ",
    "aliya": "അളിയാ",
    "alle": "അല്ലേ",
    "ullathu": "ഉള്ളത്",
    "poyi": "പോയി",
    "varum": "വരും",
    "aara": "ആരാ",
    "aaranu": "ആരാണ്",
    "pettannu": "പെട്ടെന്ന്",
    "ithu": "ഇത്",
    "ath": "അത്",
    "engane": "എങ്ങനെ",
    "enganeyanu": "എങ്ങനെയാണ്",
    "nalla": "നല്ല",
    "oru": "ഒരു",
    "pinne": "പിന്നെ",
    "ariyaamo": "അറിയാമോ",
    "ariyumo": "അറിയുമോ",
    "kurichu": "കുറിച്ച്",
    "kurich": "കുറിച്ച്",
    "patti": "പറ്റി",
    "eppol": "എപ്പോൾ",
    "eppozhanu": "എപ്പോഴാണ്",
    "nanni": "നന്ദി",
    "vegam": "വേഗം",
    "chaaya": "ചായ",
    "chaya": "ചായ",
    "kudicho": "കുടിച്ചോ",
    "kazhicho": "കഴിച്ചോ",
    "thante": "തന്റെ",
    "peru": "പേര്",
    "vishesham": "വിശേഷം",
    "paripaadi": "പരിപാടി",
    "enthund": "എന്തുണ്ട്",
}

# ---------------------------------------------------------------------------
# Hindi (Hinglish) dictionary — same idea, Devanagari.
# ---------------------------------------------------------------------------
HINGLISH_TO_HINDI = {
    "kya": "क्या",
    "kahan": "कहाँ",
    "kaise": "कैसे",
    "bhai": "भाई",
    "batao": "बताओ",
    "acha": "अच्छा",
    "achha": "अच्छा",
    "theek": "ठीक",
    "karo": "करो",
    "hoga": "होगा",
    "mera": "मेरा",
    "tera": "तेरा",
    "apna": "अपना",
    "naam": "नाम",
    "kaha": "कहा",
    "hai": "है",
    "hain": "हैं",
    "kaun": "कौन",
    "kyun": "क्यों",
    "kuch": "कुछ",
    "bolo": "बोलो",
    "yaar": "यार",
    "dost": "दोस्त",
    "samjhao": "समझाओ",
    "tha": "था",
    "the": "थे",
    "thi": "थी",
    "kisne": "किसने",
    "kab": "कब",
    "kisko": "किसको",
    "kiske": "किसके",
    "bare": "बारे",
    "mein": "में",
    "me": "में",
    "shukriya": "शुक्रिया",
}

_MALAYALAM_RANGE = ("\u0d00", "\u0d7f")
_DEVANAGARI_RANGE = ("\u0900", "\u097f")

_WORD_RE = re.compile(r"[A-Za-z]+")


def _has_script(text: str, lo: str, hi: str) -> bool:
    return any(lo <= ch <= hi for ch in text)


def _phonetic_fallback(word: str, target: str) -> Optional[str]:
    """Best-effort phonetic transliteration for words not in the dictionary.

    Uses the `indic_transliteration` package (ITRANS -> target script) if
    installed. Not perfect for casual slang spelling, but far better than
    leaving Latin letters for the voice to misread.
    """
    try:
        from indic_transliteration import sanscript
        scheme = sanscript.MALAYALAM if target == "ml" else sanscript.DEVANAGARI
        return sanscript.transliterate(word, sanscript.ITRANS, scheme)
    except Exception:
        return None


def transliterate_colloquial(text: str, lang: str) -> str:
    """Convert Manglish/Hinglish words in `text` to native script for `lang`.

    Only acts for lang in {"ml", "hi"}. If `text` already contains native
    script characters, it's assumed to already be correct and is returned
    unchanged (avoids mangling real Malayalam/Hindi input).
    """
    if lang not in ("ml", "hi"):
        return text

    if lang == "ml" and _has_script(text, *_MALAYALAM_RANGE):
        return text
    if lang == "hi" and _has_script(text, *_DEVANAGARI_RANGE):
        return text

    table = MANGLISH_TO_MALAYALAM if lang == "ml" else HINGLISH_TO_HINDI

    def repl(m: re.Match) -> str:
        word = m.group(0)
        mapped = table.get(word.lower())
        if mapped:
            return mapped
        fallback = _phonetic_fallback(word, lang)
        return fallback if fallback else word

    return _WORD_RE.sub(repl, text)
