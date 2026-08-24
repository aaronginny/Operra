"""Launch Matcher — WhatsApp-native, criteria-only investor matching.

The advisor forwards a project launch broadcast to our number; we parse it,
match it against their own stored investor criteria, and reply with the
matching labels and why each one matched. The advisor then forwards to those
investors themselves — the loop stays human-initiated on purpose, which is
what keeps this outside bulk-messaging territory. Nothing here ever sends to an
investor.

The pipeline has four deliberately separate seams so each can be replaced
without touching the others:

    source  ->  parser  ->  matcher  ->  formatter  ->  provider
    (text,      (text ->    (launch +    (result ->     (send via
     OCR        launch)     criteria     reply text)     WhatsApp)
     later)                 -> matches)

  * `sources`   turns an inbound payload into plain text. Only text messages
                today; an OCR source for launch flyers slots in here later
                without anything downstream changing.
  * `parser`    text -> ParsedLaunch. Provider-agnostic and OCR-agnostic.
  * `matcher`   ParsedLaunch + criteria -> matches, emirate filtered first.
  * `formatter` matches -> the WhatsApp reply body.
  * `providers` the only module that knows WhatsApp exists.

PII: nothing in this package writes a name, phone number, or email anywhere.
Investors are labels. Forwarded launch text is parsed in memory and never
persisted, so a broker's details embedded in a forwarded broadcast cannot leak
into storage.
"""
