"""What she asked ABOUT a place, beyond naming it — the "focus" of a question.

Before this module, a message was reduced to one subject and nothing else:
"what landmarks are near JVC" became "JVC", and the reply was the standard
price/yield briefing with the landmarks nowhere in it. The words that made
the question a question were thrown away at parse time, so nothing
downstream could have answered them. Found in live use with the client.

A focus is a tuple of topic KEYS from the curated table below, in the order
she mentioned them. It is carried through the conversation state, steers
the web search, tells the extractor what to look for, and decides what the
reply leads with.

WHY ONLY CURATED KEYS, NEVER HER OWN WORDS. The focus is put into a Tavily
query and an OpenAI prompt, and what she sends is often a forwarded lead
carrying a stranger's name and phone number — which is why her raw message
has never been sent to either service. A topic key like "schools" can carry
no one's details. The cost: an angle this table doesn't list still gets the
general briefing. Widening the table is the fix for that, not passing text
through.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Topic:
    key: str
    label: str                  # shown back to her: the reply header, the format question
    phrases: tuple[str, ...]    # whole-word matches in her message
    query: str                  # search terms used in place of the default price/yield terms
    metrics: tuple[str, ...] = ()  # numeric topic: the extraction METRICS that answer it
    nouns: tuple[str, ...] = ()    # place-type topic: words that put an untagged note on topic


# Deliberately missing from the phrases: singular "park", "beach", "mall",
# "tower", "golf", "road", "square". They start or end too many project and
# place names ("Park Views", "Beach Vista", "Bay Square", "Al Khail Road") —
# as triggers they would narrow a plain "tell me about Park Views" into an
# amenities answer. The plurals are unambiguous and kept.
TOPICS: tuple[Topic, ...] = (
    Topic("landmarks", "landmarks",
          ("landmark", "landmarks", "attraction", "attractions", "tourist spots",
           "things to do", "places to visit", "sightseeing"),
          "landmarks attractions nearby",
          nouns=("landmark", "attraction", "mall", "park", "garden", "museum", "beach",
                 "stadium", "autodrome", "circuit", "village", "souk", "lake", "canal",
                 "zoo", "golf", "burj", "frame", "arena", "opera", "waterfront", "island",
                 "mosque", "tower")),
    Topic("schools", "schools",
          ("school", "schools", "nursery", "nurseries", "education", "university",
           "universities", "college", "colleges"),
          "schools nurseries nearby",
          nouns=("school", "nursery", "academy", "college", "university", "campus")),
    Topic("transport", "transport & access",
          ("metro", "metro station", "tram", "transport", "public transport", "commute",
           "commuting", "connectivity", "access", "accessibility", "highway", "highways",
           "bus", "airport", "traffic", "how far", "distance"),
          "metro roads connectivity commute access",
          nouns=("metro", "tram", "station", "road", "highway", "interchange", "airport",
                 "bus", "route", "access")),
    Topic("amenities", "amenities",
          ("amenities", "amenity", "facilities", "malls", "shopping", "supermarket",
           "supermarkets", "grocery", "restaurants", "cafes", "gym", "gyms", "parks",
           "beaches", "lifestyle", "retail", "dining"),
          "amenities malls parks supermarkets",
          nouns=("mall", "supermarket", "retail", "restaurant", "cafe", "gym", "park",
                 "pool", "clubhouse", "community centre", "community center", "beach",
                 "dining", "shop")),
    Topic("healthcare", "healthcare",
          ("hospital", "hospitals", "clinic", "clinics", "healthcare", "medical",
           "pharmacy", "pharmacies"),
          "hospitals clinics nearby",
          nouns=("hospital", "clinic", "medical", "health", "pharmacy")),
    Topic("developer", "the developer",
          ("developer", "developers", "master developer", "who built", "who is building",
           "who's building", "builder", "track record"),
          "developer master developer track record",
          nouns=("developer", "developed", "master plan", "masterplan", "built by")),
    Topic("handover", "handover status",
          ("handover", "hand over", "handovers", "completion", "completion date",
           "construction status", "construction progress", "delivery date",
           "ready to move", "move-in ready"),
          "handover completion date construction status",
          nouns=("handover", "completion", "completed", "under construction", "off-plan",
                 "delivery", "phase")),
    Topic("prices", "prices",
          ("price", "prices", "pricing", "rate", "rates", "per sqft", "psf", "sqft",
           "cost", "costs", "valuation", "appreciation"),
          "price per sqft sale prices 2026",
          metrics=("price_per_sqft", "total_price", "yoy_change_pct")),
    Topic("yield", "rental yield",
          ("yield", "yields", "rental yield", "rental yields", "roi",
           "return on investment", "returns", "rental return", "rental returns"),
          "rental yield ROI 2026",
          metrics=("rental_yield_pct",)),
    Topic("rent", "rents",
          ("rent", "rents", "rental", "rentals", "rental price", "rental prices", "lease"),
          "average annual rent 2026",
          metrics=("annual_rent",)),
    Topic("service_charge", "service charges",
          ("service charge", "service charges", "maintenance fee", "maintenance fees"),
          "service charges per sqft",
          metrics=("service_charge",)),
    Topic("payment_plan", "payment plans",
          ("payment plan", "payment plans", "down payment", "downpayment", "installment",
           "installments", "instalment", "instalments", "post handover", "post-handover"),
          "payment plan down payment",
          metrics=("down_payment_pct",)),
    Topic("transactions", "transactions",
          ("transaction", "transactions", "deals", "sales volume", "units sold"),
          "transactions sales volume 2026",
          metrics=("transaction_count", "days_on_market")),
)

BY_KEY: dict[str, Topic] = {t.key: t for t in TOPICS}

# The place-type topics — the ones answered with named places rather than
# figures. Also the vocabulary the extractor tags each qualitative claim with.
PLACE_TOPICS: tuple[str, ...] = tuple(t.key for t in TOPICS if not t.metrics)

# "What's near JVC" asks for landmarks — but only when nothing more specific
# was asked: "schools nearby" is a schools question, not also a landmarks one.
_PROXIMITY = ("nearby", "near by", "close by", "what's near", "whats near", "what is near",
              "what's around", "whats around", "what is around", "surroundings")

# Longest phrase first, so "rental yield" is claimed as a yield before
# "rental" can read as a rent question.
_PHRASES: list[tuple[str, str]] = sorted(
    ((p, t.key) for t in TOPICS for p in t.phrases), key=lambda pk: -len(pk[0])
)


def _spans(text: str) -> list[tuple[int, int, str]]:
    """(start, end, topic key) for every topic phrase in `text`, longest
    first with matched spans consumed, in the order they appear."""
    lowered = text.lower()
    taken: list[tuple[int, int, str]] = []
    for phrase, key in _PHRASES:
        for m in re.finditer(rf"(?<!\w){re.escape(phrase)}(?!\w)", lowered):
            if any(m.start() < e and m.end() > s for s, e, _k in taken):
                continue
            taken.append((m.start(), m.end(), key))
    return sorted(taken)


def detect(text: str) -> tuple[str, ...]:
    """The topic keys in `text`, de-duplicated, in the order she wrote them."""
    keys: list[str] = []
    for _s, _e, key in _spans(text):
        if key not in keys:
            keys.append(key)
    if not any(k in PLACE_TOPICS for k in keys):
        lowered = text.lower()
        if any(re.search(rf"(?<!\w){re.escape(p)}(?!\w)", lowered) for p in _PROXIMITY):
            keys.insert(0, "landmarks")
    return tuple(keys)


def mask(text: str) -> str:
    """`text` with every topic phrase replaced by "§", and a conjunction
    between two topics folded away — so "landmarks and schools near JVC"
    reads as "§ near JVC". Used to stop an "and" joining two TOPICS from
    looking like an "and" joining two PLACES (see intents.wants_comparison)."""
    out, last = [], 0
    for s, e, _k in _spans(text):
        out.append(text[last:s])
        out.append("§")
        last = e
    out.append(text[last:])
    masked = "".join(out)
    prev = None
    while prev != masked:
        prev = masked
        masked = re.sub(r"§\s*(?:,|&|\band\b|\bor\b)\s*§", "§", masked, flags=re.IGNORECASE)
    return masked


def phrase_words() -> frozenset[str]:
    """Every single word any topic phrase is made of — for intents' edge
    trimming, which strips topic words off the ends of a candidate name."""
    return frozenset(w for _p, _k in _PHRASES for w in _p.split())


def label(focus: tuple[str, ...]) -> str:
    """"nearby landmarks", "schools & rental yield", "a, b & c"."""
    labels = [BY_KEY[k].label for k in focus if k in BY_KEY]
    if len(labels) <= 1:
        return "".join(labels)
    return ", ".join(labels[:-1]) + " & " + labels[-1]


def query_terms(focus: tuple[str, ...]) -> str:
    return " ".join(BY_KEY[k].query for k in focus if k in BY_KEY)


def metrics_for(focus: tuple[str, ...]) -> set[str]:
    return {m for k in focus if k in BY_KEY for m in BY_KEY[k].metrics}


def asks_about_places(focus: tuple[str, ...]) -> bool:
    return any(k in PLACE_TOPICS for k in focus)


def _on_topic(note_topic: str, note: str, focus: tuple[str, ...]) -> bool:
    if note_topic:
        return note_topic in focus
    # Untagged (the extractor left the tag off): fall back to the note's own
    # nouns. Tagged-but-other stays off topic — the extractor said so.
    lowered = note.lower()
    return any(n in lowered for k in focus if k in BY_KEY for n in BY_KEY[k].nouns)


def unanswered(focus: tuple[str, ...], ranges: list, qualitative: list) -> tuple[str, ...]:
    """The topics she asked about that nothing in (narrowed) `ranges` /
    `qualitative` answers — so a two-part question that only found one
    part says so, rather than quietly answering half of it."""
    shown = {r.metric for r in ranges}
    missing = []
    for k in focus:
        topic = BY_KEY.get(k)
        if topic is None:
            continue
        if topic.metrics:
            found = bool(shown & set(topic.metrics))
        else:
            found = any(_on_topic(q.topic, q.note, (k,)) for q in qualitative)
        if not found:
            missing.append(k)
    return tuple(missing)


def narrow(ranges: list, qualitative: list, focus: tuple[str, ...]) -> tuple[list, list, bool]:
    """Shape assembled facts to answer the question actually asked.

    Returns (ranges, qualitative, places_first). No focus: everything as it
    was, untouched.

    A place-type question (landmarks, schools, ...) is answered with the
    notes on that topic plus any figure she ALSO asked for — never padded
    out with a price briefing she didn't ask for, which is exactly the reply
    that made the original bug look like the question was ignored.

    A figures-only question ("rental yield in JVC") leads with the figures
    she asked for; the other figures follow as context, since for a numbers
    question the rest of the area's numbers are closely related.
    """
    if not focus:
        return ranges, qualitative, False
    wanted = metrics_for(focus)
    asked = [r for r in ranges if r.metric in wanted]
    if asks_about_places(focus):
        on_topic = [q for q in qualitative if _on_topic(q.topic, q.note, focus)]
        return asked, on_topic, True
    rest = [r for r in ranges if r.metric not in wanted]
    return asked + rest, qualitative, False
