"""UAE emirate/area reference tables.

Moved out of app.services.launch_matcher.parser (which still imports and
re-exports these three names unchanged, so nothing that already does
`from app.services.launch_matcher.parser import EMIRATES` — including
app.services.launch_matcher.contact_signals — needs to change) so that a
second UAE-geography consumer (the broker_intel vertical) can depend on this
table directly instead of reaching into a specific vertical's parser module
for data that has nothing to do with parsing launch broadcasts.

Contents and values are unchanged from their original home in parser.py —
this is a move, not a rewrite. See app.services.launch_matcher.parser's own
history/comments for why each entry is here (e.g. why short emirate codes
like "auh" are safe in EMIRATES but a bare 2-letter code is not).
"""

from __future__ import annotations

EMIRATES = {
    "dubai": "Dubai",
    "abu dhabi": "Abu Dhabi",
    "abudhabi": "Abu Dhabi",
    "auh": "Abu Dhabi",
    "ras al khaimah": "RAK",
    "rak": "RAK",
    "sharjah": "Sharjah",
    "ajman": "Ajman",
    "fujairah": "Fujairah",
    "umm al quwain": "UAQ",
    "uaq": "UAQ",
}

# Areas we can recognise, mapped to their emirate. Used both to pull the area
# out of the text and to infer the emirate when the broadcast doesn't say it
# outright — which is common, because everyone in the group already knows.
AREA_TO_EMIRATE = {
    # ── Dubai ──
    "sobha hartland": "Dubai", "hartland": "Dubai", "meydan": "Dubai",
    "mbr city": "Dubai", "mohammed bin rashid city": "Dubai",
    "downtown": "Dubai", "downtown dubai": "Dubai", "business bay": "Dubai",
    "dubai marina": "Dubai", "marina": "Dubai", "jbr": "Dubai",
    "palm jumeirah": "Dubai", "bluewaters": "Dubai", "city walk": "Dubai",
    "jvc": "Dubai", "jumeirah village circle": "Dubai",
    "jvt": "Dubai", "jumeirah village triangle": "Dubai",
    "dubai hills": "Dubai", "dubai hills estate": "Dubai",
    "creek harbour": "Dubai", "dubai creek harbour": "Dubai",
    "damac hills": "Dubai", "damac lagoons": "Dubai",
    "arjan": "Dubai", "al furjan": "Dubai", "dubai south": "Dubai",
    "emaar beachfront": "Dubai", "dubai islands": "Dubai",
    "expo city": "Dubai", "the valley": "Dubai", "emaar south": "Dubai",
    "town square": "Dubai", "dubailand": "Dubai", "silicon oasis": "Dubai",
    "sports city": "Dubai", "motor city": "Dubai", "discovery gardens": "Dubai",
    "international city": "Dubai", "al barsha": "Dubai", "tilal al ghaf": "Dubai",
    "rashid yachts": "Dubai", "mina rashid": "Dubai", "za'abeel": "Dubai",
    "zabeel": "Dubai", "jumeirah garden city": "Dubai", "barsha heights": "Dubai",
    # ── Abu Dhabi ──
    "yas island": "Abu Dhabi", "saadiyat": "Abu Dhabi",
    "saadiyat island": "Abu Dhabi", "al reem": "Abu Dhabi",
    "reem island": "Abu Dhabi", "al maryah": "Abu Dhabi",
    "maryah island": "Abu Dhabi", "al raha": "Abu Dhabi",
    "masdar city": "Abu Dhabi", "khalifa city": "Abu Dhabi",
    "al ghadeer": "Abu Dhabi", "zayed city": "Abu Dhabi",
    # ── Ras Al Khaimah ──
    "al marjan": "RAK", "al marjan island": "RAK", "mina al arab": "RAK",
    "hayat island": "RAK", "al hamra": "RAK",
    # ── Sharjah ──
    "aljada": "Sharjah", "al jada": "Sharjah", "maryam island": "Sharjah",
    "sharjah waterfront": "Sharjah",
}

# Areas whose display form isn't just .title() — acronyms and stylised names.
AREA_DISPLAY = {
    "jvc": "JVC", "jvt": "JVT", "jbr": "JBR",
    "mbr city": "MBR City", "damac hills": "DAMAC Hills",
    "damac lagoons": "DAMAC Lagoons", "za'abeel": "Za'abeel",
    "al maryah": "Al Maryah", "aljada": "Aljada",
}
