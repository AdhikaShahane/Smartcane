"""Voice-command intent matching.

Deliberately NOT an LLM. A 0.5B model on a Pi 4 runs at a few tokens/second and
would steal the core the ASR needs. rapidfuzz over a closed grammar is
sub-millisecond, deterministic and testable.

Design rule: directional words ("left", "right") are NEVER bare commands.
They are among the most common words in conversation, so every directional
intent requires a verb ("turn left", "move right"). This is the main defence
against false triggers while the microphone is always listening.
"""
from __future__ import annotations

from enum import Enum
from typing import List, Tuple

try:
    from rapidfuzz import fuzz
    _HAVE_RAPIDFUZZ = True
except ImportError:                                    # pragma: no cover
    import difflib
    fuzz = None                                        # type: ignore
    _HAVE_RAPIDFUZZ = False


class Intent(str, Enum):
    STOP = "stop"
    WHAT_AHEAD = "what_ahead"
    DESCRIBE = "describe"
    ALL_OBJECTS = "all_objects"
    WHERE_AM_I = "where_am_i"
    IS_SAFE = "is_safe"
    HOW_FAR = "how_far"
    REACH = "reach"
    PASSED = "passed"
    TURN = "turn"
    AROUND = "around"
    LEFT_CHECK = "left_check"
    RIGHT_CHECK = "right_check"
    REPEAT = "repeat"
    LEFT = "left"
    RIGHT = "right"
    STRAIGHT = "straight"
    SLOWER = "slower"
    FASTER = "faster"
    LOUDER = "louder"
    QUIETER = "quieter"
    BATTERY = "battery"
    WEATHER = "weather"
    HELP = "help"
    CANCEL = "cancel"
    UNKNOWN = "unknown"


# Phrase -> intent. Every entry here is also fed to the Vosk grammar, so the
# recogniser is only ever asked to distinguish these phrases.
PHRASES: List[Tuple[str, Intent]] = [
    ("stop", Intent.STOP),
    ("stop now", Intent.STOP),
    ("halt", Intent.STOP),
    ("freeze", Intent.STOP),
    ("wait", Intent.STOP),

    ("what is ahead", Intent.WHAT_AHEAD),
    ("what's ahead", Intent.WHAT_AHEAD),
    ("what is in front of me", Intent.WHAT_AHEAD),
    ("what is in front", Intent.WHAT_AHEAD),
    ("look ahead", Intent.WHAT_AHEAD),
    ("check ahead", Intent.WHAT_AHEAD),

    ("describe", Intent.DESCRIBE),
    ("describe the scene", Intent.DESCRIBE),
    ("describe what you see", Intent.DESCRIBE),
    ("what do you see", Intent.DESCRIBE),
    ("look around", Intent.DESCRIBE),

    ("what objects are around me", Intent.ALL_OBJECTS),
    ("what is around me", Intent.ALL_OBJECTS),
    ("what else is there", Intent.ALL_OBJECTS),
    ("list the objects", Intent.ALL_OBJECTS),
    ("what do you see around me", Intent.ALL_OBJECTS),

    # -- referring back to the object just described -----------------------
    ("how do i reach it", Intent.REACH),
    ("how do i get there", Intent.REACH),
    ("how do i get to it", Intent.REACH),
    ("guide me towards it", Intent.REACH),
    ("guide me to it", Intent.REACH),
    ("take me to it", Intent.REACH),

    ("have i passed it", Intent.PASSED),
    ("did i pass it", Intent.PASSED),
    ("am i past it", Intent.PASSED),
    ("is it behind me", Intent.PASSED),
    ("have i passed the obstacle", Intent.PASSED),

    ("which direction should i turn", Intent.TURN),
    ("which way should i go", Intent.TURN),
    ("which direction", Intent.TURN),
    ("where should i go", Intent.TURN),
    ("where do i go", Intent.TURN),

    ("guide me around it", Intent.AROUND),
    ("how do i get around it", Intent.AROUND),
    ("how do i go around", Intent.AROUND),
    ("help me around this obstacle", Intent.AROUND),
    ("take me around it", Intent.AROUND),

    ("is there an obstacle on my left", Intent.LEFT_CHECK),
    ("what is on my left", Intent.LEFT_CHECK),
    ("is my left clear", Intent.LEFT_CHECK),
    ("anything on my left", Intent.LEFT_CHECK),

    ("is there an obstacle on my right", Intent.RIGHT_CHECK),
    ("what is on my right", Intent.RIGHT_CHECK),
    ("is my right clear", Intent.RIGHT_CHECK),
    ("anything on my right", Intent.RIGHT_CHECK),

    ("where am i", Intent.WHERE_AM_I),
    ("what is my location", Intent.WHERE_AM_I),
    ("where are we", Intent.WHERE_AM_I),

    ("is it safe", Intent.IS_SAFE),
    ("is it safe to walk", Intent.IS_SAFE),
    ("can i walk", Intent.IS_SAFE),
    ("is the path clear", Intent.IS_SAFE),
    ("is the way clear", Intent.IS_SAFE),
    ("may i go", Intent.IS_SAFE),

    ("how far", Intent.HOW_FAR),
    ("how far is it", Intent.HOW_FAR),
    ("how many steps", Intent.HOW_FAR),
    ("how many steps to go", Intent.HOW_FAR),
    ("what is the distance", Intent.HOW_FAR),

    ("repeat", Intent.REPEAT),
    ("say again", Intent.REPEAT),
    ("say that again", Intent.REPEAT),
    ("what did you say", Intent.REPEAT),

    ("turn left", Intent.LEFT),
    ("move left", Intent.LEFT),
    ("go left", Intent.LEFT),
    ("walk left", Intent.LEFT),
    ("step left", Intent.LEFT),
    ("take left", Intent.LEFT),

    ("turn right", Intent.RIGHT),
    ("move right", Intent.RIGHT),
    ("go right", Intent.RIGHT),
    ("walk right", Intent.RIGHT),
    ("step right", Intent.RIGHT),
    ("take right", Intent.RIGHT),

    ("go straight", Intent.STRAIGHT),
    ("walk straight", Intent.STRAIGHT),
    ("keep going", Intent.STRAIGHT),
    ("continue", Intent.STRAIGHT),
    ("go forward", Intent.STRAIGHT),

    ("speak slower", Intent.SLOWER),
    ("slower", Intent.SLOWER),
    ("speak faster", Intent.FASTER),
    ("faster", Intent.FASTER),
    ("louder", Intent.LOUDER),
    ("speak louder", Intent.LOUDER),
    ("quieter", Intent.QUIETER),
    ("speak quieter", Intent.QUIETER),

    ("battery", Intent.BATTERY),
    ("battery status", Intent.BATTERY),
    ("how much battery", Intent.BATTERY),
    ("power", Intent.BATTERY),

    ("weather", Intent.WEATHER),
    ("what is the weather", Intent.WEATHER),

    ("help", Intent.HELP),
    ("call for help", Intent.HELP),
    ("emergency", Intent.HELP),
    ("call someone", Intent.HELP),

    ("cancel", Intent.CANCEL),
    ("never mind", Intent.CANCEL),
    ("forget it", Intent.CANCEL),
    ("stop listening", Intent.CANCEL),
]

MATCH_THRESHOLD = 82.0     # similarity required to accept a command
MIN_CHARS = 3              # ignore fragments shorter than this
MAX_EXTRA_CHARS = 12       # an utterance longer than phrase+this is a sentence

_PHRASE_LIST = [p for p, _ in PHRASES]
_INTENT_OF = {p: i for p, i in PHRASES}
# Token-sorted phrase strings, precomputed once. Sorting them on every call was
# costing ~9 ms per classification, which on a Pi 4 would be ~30 ms of avoidable
# delay before the cane even starts thinking about what to say.
_SORTED_PHRASES = [
    (p, " ".join(sorted(p.split())), set(p.split())) for p in _PHRASE_LIST
]


def grammar_words() -> List[str]:
    """Word list handed to Vosk. Restricting the vocabulary is the single
    biggest accuracy win for short commands: it turns 'transcribe English'
    into 'classify twenty things'."""
    words = set()
    for phrase in _PHRASE_LIST:
        words.update(phrase.split())
    return sorted(words)


def grammar_phrases() -> List[str]:
    return list(_PHRASE_LIST)


def _score_sorted(text_sorted: str, phrase_sorted: str) -> float:
    """Similarity of two already token-sorted strings.

    Deliberately NOT `partial_ratio` / `token_set_ratio`. Both score a phrase
    that is a *subset* of the text at 100, so `partial_ratio("left",
    "turn left") == 100` -- which makes a bare "left" heard in conversation
    trigger a turn command. That is the single most dangerous failure mode of
    an always-listening cane, so substring scorers are banned here.
    """
    if _HAVE_RAPIDFUZZ:
        return float(fuzz.ratio(text_sorted, phrase_sorted))
    return difflib.SequenceMatcher(None, text_sorted,
                                   phrase_sorted).ratio() * 100.0


def classify(text: str) -> Tuple[Intent, float, str]:
    """Return (intent, confidence 0-100, matched phrase)."""
    clean = " ".join(text.lower().strip().split())
    if len(clean) < MIN_CHARS:
        return Intent.UNKNOWN, 0.0, ""

    n_words = len(clean.split())
    text_words = set(clean.split())
    text_sorted = " ".join(sorted(clean.split()))
    text_len = len(clean)

    best_phrase, best_score = "", 0.0
    for phrase, phrase_sorted, phrase_words in _SORTED_PHRASES:
        # GUARD 1: a bare word must never match a multi-word command.
        # "left" alone is a preposition in conversation; "turn left" is a command.
        if n_words < len(phrase.split()):
            continue
        # GUARD 2: an utterance much longer than the phrase is a different
        # sentence that merely shares words ("i left my bag at home").
        if text_len > len(phrase) + MAX_EXTRA_CHARS:
            continue
        # CHEAP FILTER: a phrase sharing no word with the utterance cannot
        # reach the threshold anyway, and scoring all 100+ of them was the
        # single largest cost in the decision layer.
        if not (text_words & phrase_words):
            continue
        score = _score_sorted(text_sorted, phrase_sorted)
        if score > best_score:
            best_phrase, best_score = phrase, score

    if best_score < MATCH_THRESHOLD:
        return Intent.UNKNOWN, 0.0, ""
    return _INTENT_OF[best_phrase], best_score, best_phrase
