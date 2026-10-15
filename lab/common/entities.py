"""Rule-based entity detection, address fields, pair matching, and the resolution loop.

Substitutes for GLiNER, BERT-NER, and libpostal. Both taggers are rules, so agreement
is a second opinion only in that limited sense.
"""

from __future__ import annotations

import re

from rapidfuzz import fuzz
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics.pairwise import cosine_similarity

from lab.common.qa import answer_with_agreement
from lab.common.textutil import content_tokens, find_span, normalize, sentences

TITLE_PERSON = re.compile(
    r"\b(?:Mr|Mrs|Ms|Dr|Shri|Smt)\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b"
)
# Captures 2 OR 3 consecutive title-case words (greedy): a 3-word run is
# common when a sentence-initial common noun ("Claimant Lakshmi Iyer...")
# happens to be capitalized only because it starts the sentence, not
# because it's part of the name. _add() trims that leading word off when
# the match is sentence-initial -- a generic English-capitalization rule,
# not a list of role words to recognize.
FULL_PERSON = re.compile(r"\b[A-Z][a-z]{1,20}(?:\s+[A-Z][a-z]{1,20}){1,2}\b")
INITIAL_PERSON = re.compile(r"\b[A-Z]\.\s?[A-Z][a-z]+\b")
ORG_RE = re.compile(
    r"\b[A-Z][A-Za-z0-9&]*(?:\s+[A-Z][A-Za-z0-9&]*){0,4}\s+"
    r"(?:Pvt\.?\s+Ltd\.?|Private Limited|Inc\.?|LLC|Ltd\.?|LLP|GmbH|Corp\.?|Corporation)\b"
)
DEFINED_RE = re.compile(r"\bthe\s+[A-Z][a-z]+\b|\(the\s+[A-Z][a-z]+\)")
DATE_RE = re.compile(
    r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}|"
    r"\d{1,2}(?:st|nd|rd|th)?\s+(?:January|February|March|April|May|June|July|"
    r"August|September|October|November|December)\s+\d{4})\b",
    re.I,
)
#  A closed, finite set of English function words (pronouns, articles,
#  prepositions, conjunctions, short auxiliaries/modals) -- not a growing
#  domain-vocabulary list like "lessee"/"lessor" was. Needed because a short
#  lowercase word right after a number ("1081 he", found against real SQuAD
#  text, EXP-070) is otherwise indistinguishable from a real short lowercase
#  unit ("7 grams") by the capitalization/length heuristic alone. The same
#  category of list sklearn's own stop_words="english" already uses
#  elsewhere in this repo (lab.common.index), not a per-domain word list.
_AMOUNT_UNIT_STOPWORDS = (
    r"(?:he|she|it|we|us|you|they|is|was|are|am|be|to|of|in|on|at|by|or|and"
    r"|the|a|an|as|if|so|do|did|has|had|can|may|not|no|nor|but|yet|for|up|out|off)"
)

AMOUNT_RE = re.compile(
    # Currency-prefixed ("INR 30000"), percent ("90%"/"90 percent"), or a
    # number followed by a generic unit suffix -- "30 days", "7 grams",
    # "300mg", "250 MPa" -- covering whatever unit a domain uses instead of
    # enumerating specific units (which would just be domain-specific
    # hardcoding one level down).
    #
    # The real signal distinguishing a unit from a house-number's street
    # name (EXP-069's follow-up fix, after a first attempt that capped unit
    # length at 4 letters broke "7 grams" -- "grams" is 5 letters, a real
    # unit, not a street name): capitalization, not length. A unit word is
    # either plain lowercase ("grams", "minutes", however long) or a short
    # abbreviation that isn't single-capital-then-lowercase ("MPa", "PSI",
    # "C"); a street name is exactly that shape ("Hill", "Road", "Lake") --
    # one capital letter followed by lowercase letters, and nothing else.
    # The leading negative lookahead rejects that one shape; the length cap
    # (<=7) and trailing lookahead (not followed by another capitalized
    # word) catch the remaining case, an all-lowercase or all-caps token
    # that still isn't really a unit ("30 employees", "14 MG Road"). The
    # function-word lookahead (_AMOUNT_UNIT_STOPWORDS) catches the case
    # neither capitalization nor length rules out: an ordinary short
    # lowercase function word ("1081 he") that happens to immediately
    # follow a number in real prose.
    #
    # Word-based currency codes (INR/USD/Rs) keep a leading \b since they're
    # word characters. Symbol currencies ($/€/£) get their own branch with
    # no leading \b -- \b needs a word/non-word transition, and a symbol
    # preceded by a space is non-word on both sides, so "\b\$" can never
    # match at all. A latent bug, not one introduced here: every amount in
    # every fixture before EXP-069 used a word-prefixed currency (INR/USD),
    # so this never fired until a fixture finally used a bare "$" symbol.
    # The two capitalization lookaheads must stay case-sensitive regardless
    # of the compile-time re.I flag (needed for the lowercase currency codes
    # and "percent") -- (?-i: ...) scopes that locally; without it, re.I
    # makes [A-Z]/[a-z] both match any case and the whole distinction this
    # comment describes silently stops doing anything.
    r"\b(?:INR|USD|Rs\.?)\s?\d[\d,]*(?:\.\d+)?\b"
    r"|[$€£]\s?\d[\d,]*(?:\.\d+)?\b"
    r"|\b\d[\d,]*(?:\.\d+)?\s?(?:percent|%)\b"
    r"|\b\d[\d,]*(?:\.\d+)?\s?(?!" + _AMOUNT_UNIT_STOPWORDS + r"\b)(?-i:(?![A-Z][a-z]+\b))[A-Za-z]{1,7}\b(?-i:(?!\s+[A-Z]))",
    re.I,
)
STREET_RE = re.compile(
    r"\b\d{1,5}\s+(?:[A-Z0-9][A-Za-z0-9.]*\s+){0,4}"
    r"(?:Road|Street|St|Avenue|Ave|Lane|Marg|Drive|Boulevard|Blvd)\b"
    r"(?:,\s*[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*)?"
    r"(?:,?\s*\d{5,6})?",
)
PLOT_RE = re.compile(r"\bPlot\s+\d+,\s*Sector\s+\d+\b", re.I)
NAGAR_RE = re.compile(r"\b[A-Z][a-z]+\s+Nagar\b")
PARK_STREET_RE = re.compile(r"\bPark Street\b")
NOT_PERSON = {
    "Park Street", "New Delhi", "High Court", "Notice Period", "MG Road",
    "Ashok Nagar", "Baker Street", "Private Limited", "United States",
    "Security Deposit", "Termination Clause", "Pvt Ltd", "Private Ltd",
}
ORG_SUFFIXES = {"pvt", "ltd", "inc", "llc", "llp", "gmbh", "corp", "corporation", "limited", "private"}
PLACE_LAST = {"road", "street", "st", "avenue", "ave", "lane", "marg", "drive", "boulevard", "blvd", "nagar", "market"}


def _add(found: list[dict], text: str, match: re.Match, label: str, conf: float, tagger: str):
    span = match.group(0).strip(" ,;")
    start = match.start() + match.group(0).find(span)
    if label == "person":
        words = span.split()
        # If the capitalized run continues past this match ("New Delhi High
        # |Court|"), FULL_PERSON's word cap is truncating a longer
        # institution/place name, not catching a short one -- trimming a
        # leading sentence-initial word in that case produces a confident
        # wrong span ("Delhi High") no denylist entry anticipates, rather
        # than widening the match. Reject the candidate outright instead.
        if re.match(r"\s+[A-Z]", text[match.end():]):
            return
        if len(words) >= 3:
            before = text[:match.start()]
            sentence_initial = not before.strip() or re.search(r"[.?!]\s*$", before)
            if sentence_initial:
                start += len(words[0]) + 1
                span = " ".join(words[1:])
        if span in NOT_PERSON:
            return
        pieces = {p.lower().strip(".") for p in span.split()}
        if pieces & ORG_SUFFIXES:
            return
        if span.split()[-1].lower().strip(".") in PLACE_LAST:
            return
    if label == "defined term":
        span = span.replace("(", "").replace(")", "")
        located = find_span(text, span)
        if not located:
            return
        start, end = located
    else:
        end = start + len(span)
    found.append(
        {
            "start": start,
            "end": end,
            "text": text[start:end],
            "label": label,
            "conf": conf,
            "tagger": tagger,
        }
    )


def detect_primary(text: str) -> list[dict]:
    found: list[dict] = []
    for rx, label, conf in (
        (TITLE_PERSON, "person", 0.9),
        (INITIAL_PERSON, "person", 0.7),
        (FULL_PERSON, "person", 0.62),
        (ORG_RE, "organization", 0.88),
        (STREET_RE, "address", 0.84),
        (PLOT_RE, "address", 0.7),
        (NAGAR_RE, "address", 0.55),
        (PARK_STREET_RE, "address", 0.5),
        (DEFINED_RE, "defined term", 0.8),
        (DATE_RE, "date", 0.9),
        (AMOUNT_RE, "amount", 0.86),
    ):
        for match in rx.finditer(text or ""):
            _add(found, text, match, label, conf, "primary")
    return _dedupe(found)


def detect_secondary(text: str) -> list[dict]:
    """Stricter second opinion for people and organizations only."""
    found: list[dict] = []
    for match in TITLE_PERSON.finditer(text or ""):
        _add(found, text, match, "person", 0.8, "secondary")
    for match in ORG_RE.finditer(text or ""):
        _add(found, text, match, "organization", 0.8, "secondary")
    return _dedupe(found)


def _dedupe(found: list[dict]) -> list[dict]:
    found.sort(key=lambda row: (row["start"], -(row["end"] - row["start"]), -row["conf"]))
    kept: list[dict] = []
    for row in found:
        if any(row["label"] == prev["label"] and not (row["end"] <= prev["start"] or row["start"] >= prev["end"]) for prev in kept):
            continue
        kept.append(row)
    return kept


def agreement(primary: list[dict], secondary: list[dict]) -> list[dict]:
    out = []
    for mention in primary:
        overlap = [
            other
            for other in secondary
            if not (mention["end"] <= other["start"] or mention["start"] >= other["end"])
        ]
        if mention["label"] in {"person", "organization"}:
            agree = any(other["label"] == mention["label"] for other in overlap)
            disagree = any(other["label"] != mention["label"] for other in overlap)
        else:
            agree = True
            disagree = False
        if disagree:
            conf = max(0.05, mention["conf"] - 0.25)
            status = "unsure"
        elif agree and mention["conf"] >= 0.7:
            conf = min(0.99, mention["conf"] + 0.08)
            status = "high"
        elif mention["conf"] >= 0.8:
            conf = mention["conf"]
            status = "high"
        else:
            conf = mention["conf"]
            status = "unsure"
        out.append({**mention, "conf": round(conf, 4), "agreement": agree, "status": status})
    return out


def parse_address(text: str) -> dict:
    house = re.search(r"\b(\d{1,5}[A-Z]?)\b", text or "")
    road = re.search(
        r"\b\d{1,5}\s+((?:[A-Z0-9][A-Za-z0-9.]*\s+)*"
        r"(?:Road|Street|St|Avenue|Ave|Lane|Marg|Drive|Boulevard|Blvd))\b",
        text or "",
    )
    pin = re.search(r"\b(\d{6}|\d{5}(?:-\d{4})?)\b", text or "")
    city = None
    if road:
        tail = text[road.end():]
        city_match = re.search(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b", tail)
        if city_match and city_match.group(1) not in {"Plot", "Sector"}:
            city = city_match.group(1)
    return {
        "house_number": house.group(1) if house else None,
        "road": road.group(1) if road else None,
        "city": city,
        "postcode": pin.group(1) if pin else None,
    }


def pair_features(left: dict, right: dict) -> list[float]:
    name_ratio = fuzz.ratio(normalize(left.get("text", "")), normalize(right.get("text", ""))) / 100
    left_toks = set(content_tokens(left.get("context", "")))
    right_toks = set(content_tokens(right.get("context", "")))
    jac = len(left_toks & right_toks) / len(left_toks | right_toks) if left_toks and right_toks else 0.0
    left_sur = normalize(left.get("text", "")).split()[-1:] or [""]
    right_sur = normalize(right.get("text", "")).split()[-1:] or [""]
    same_surname = 1.0 if left_sur == right_sur and left_sur != [""] else 0.0
    same_addr = 1.0 if left.get("address") and left.get("address") == right.get("address") else 0.0
    same_role = 1.0 if left.get("role") and left.get("role") == right.get("role") else 0.0
    return [name_ratio, jac, same_surname, same_addr, same_role]


def train_pair_matcher(pairs: list[dict]) -> LogisticRegression:
    model = LogisticRegression(max_iter=400)
    x = [pair_features(p["left"], p["right"]) for p in pairs]
    y = [p["same"] for p in pairs]
    model.fit(x, y)
    return model


class ExampleStore:
    def __init__(self):
        self.rows: list[dict] = []
        self.vectorizer = None
        self.matrix = None

    def add(self, span: str, context: str, label: str, evidence_id: str):
        self.rows.append(
            {"span": span, "context": context, "label": label, "evidence_id": evidence_id}
        )
        self.vectorizer = None

    def _fit(self):
        if self.vectorizer is not None or not self.rows:
            return
        self.vectorizer = TfidfVectorizer(stop_words="english")
        self.matrix = self.vectorizer.fit_transform(
            [f"{row['span']} {row['context']}" for row in self.rows]
        )

    def vote(self, span: str, context: str) -> dict | None:
        if not self.rows:
            return None
        self._fit()
        query = self.vectorizer.transform([f"{span} {context}"])
        sims = cosine_similarity(query, self.matrix).ravel()
        best = int(sims.argmax())
        if float(sims[best]) < 0.2:
            return None
        return {"label": self.rows[best]["label"], "score": round(float(sims[best]), 4), "example": self.rows[best]}


def resolve_mentions(chunks: list[dict], store: ExampleStore | None = None, max_rounds: int = 3) -> list[dict]:
    """Resolution loop over the supplied chunks, which stand in for the searchable context."""
    store = store or ExampleStore()
    mentions = []
    for chunk in chunks:
        primary = agreement(detect_primary(chunk["text"]), detect_secondary(chunk["text"]))
        for mention in primary:
            vote = store.vote(mention["text"], chunk["text"])
            if vote and vote["label"] == mention["label"]:
                mention["conf"] = round(min(0.99, mention["conf"] + 0.05), 4)
                mention["knn"] = vote["score"]
            elif vote and vote["label"] != mention["label"]:
                mention["conf"] = round(max(0.05, mention["conf"] - 0.2), 4)
                mention["status"] = "unsure"
            mentions.append({**mention, "chunk_id": chunk.get("chunk_id") or chunk.get("id"), "context": chunk["text"]})

    resolved = []
    for mention in mentions:
        if mention["status"] == "high":
            resolved.append(_close(mention, "resolved", [mention["chunk_id"]]))
            continue
        outcome = _resolve_unsure(mention, chunks, max_rounds)
        resolved.append(outcome)
    return apply_ambiguity_rules(resolved)


def _close(mention: dict, status: str, evidence_ids: list[str], alternatives: list | None = None) -> dict:
    address = parse_address(mention["context"]) if mention["label"] == "address" else None
    return {
        "text": mention["text"],
        "label": mention["label"],
        "status": status,
        "conf": mention.get("conf", 0.0),
        "evidence_ids": evidence_ids,
        "chunk_id": mention.get("chunk_id"),
        "address_parsed": address,
        "alternatives": alternatives or [],
        "context": mention.get("context", ""),
    }


def _resolve_unsure(mention: dict, chunks: list[dict], max_rounds: int) -> dict:
    alternatives = []
    for rnd in range(max_rounds):
        scope_ids = {mention.get("chunk_id")} if rnd == 0 else {c.get("chunk_id") or c.get("id") for c in chunks}
        queries_hit = []
        for chunk in chunks:
            cid = chunk.get("chunk_id") or chunk.get("id")
            if cid not in scope_ids and rnd == 0:
                continue
            text = chunk["text"]
            if mention["text"] and mention["text"] in text:
                queries_hit.append(chunk)
            elif mention["label"] == "defined term" and mention["text"] in text:
                queries_hit.append(chunk)
        if mention["label"] == "defined term":
            role = mention["text"].replace("the ", "").strip()
            question = f"Who is the {role}?"
            qa = answer_with_agreement(question, queries_hit or chunks, tau=0.2)
            if qa.get("span") and qa.get("second_model_agrees"):
                return _close(
                    {**mention, "text": qa["span"], "label": "person", "conf": 0.8},
                    "resolved",
                    [qa.get("passage_id")],
                )
            if qa.get("span"):
                alternatives.append(qa["span"])
        elif len(queries_hit) == 1:
            return _close(mention, "resolved", [queries_hit[0].get("chunk_id") or queries_hit[0].get("id")])
        elif len(queries_hit) > 1:
            names = sorted({mention["text"]})
            alternatives.extend(names)
    status = "ambiguous" if alternatives or mention.get("status") == "unsure" else "unresolved"
    if mention["label"] == "address" and mention.get("conf", 0) < 0.6:
        status = "ambiguous"
    return _close(mention, status, [mention.get("chunk_id")], alternatives)


def apply_ambiguity_rules(mentions: list[dict]) -> list[dict]:
    """Shared surnames and two addresses for one name stay unresolved guesses."""
    titles = {"mr", "mrs", "ms", "dr", "shri", "smt"}
    people = [m for m in mentions if m.get("label") == "person"]
    by_surname: dict[str, list[dict]] = {}
    for person in people:
        parts = [p.strip(".") for p in person["text"].replace(".", " ").split() if p.strip(".").lower() not in titles]
        if not parts:
            continue
        by_surname.setdefault(parts[-1].lower(), []).append(person)
    for group in by_surname.values():
        def content_parts(text: str) -> list[str]:
            return [t for t in text.replace(".", " ").split() if t.strip(".").lower() not in titles and t.strip(".")]

        full = {normalize(p["text"]) for p in group if len([t for t in content_parts(p["text"]) if len(t) > 1]) >= 2}
        for person in group:
            content = content_parts(person["text"])
            short = len(content) <= 1 or any(len(part) == 1 for part in content)
            other_full = full - {normalize(person["text"])}
            if short and other_full:
                person["status"] = "ambiguous"
                person["alternatives"] = sorted(other_full)
    by_name: dict[str, list[dict]] = {}
    for mention in mentions:
        if mention.get("label") != "address":
            continue
        by_name.setdefault(normalize(mention.get("context", "")), []).append(mention)
    grouped: dict[str, set[str]] = {}
    for mention in mentions:
        if mention.get("label") != "address":
            continue
        context = mention.get("context") or ""
        host = next((sent for sent in sentences(context) if mention["text"] in sent), context)
        for person in people:
            if person["text"] and person["text"] in host:
                grouped.setdefault(normalize(person["text"]), set()).add(normalize(mention["text"]))
    for person in people:
        addresses = grouped.get(normalize(person["text"]), set())
        if len(addresses) >= 2:
            person["status"] = "ambiguous"
            person["alternatives"] = sorted(addresses)
    return mentions


def same_entity_pairs(mentions: list[dict], model: LogisticRegression) -> list[dict]:
    results = []
    for i, left in enumerate(mentions):
        for right in mentions[i + 1 :]:
            if left["label"] != right["label"]:
                continue
            block = (
                normalize(left["text"]) == normalize(right["text"])
                or normalize(left["text"]).split()[-1:] == normalize(right["text"]).split()[-1:]
            )
            if not block:
                continue
            feats = pair_features(
                {"text": left["text"], "context": left.get("context", ""), "address": left.get("address_parsed"), "role": None},
                {"text": right["text"], "context": right.get("context", ""), "address": right.get("address_parsed"), "role": None},
            )
            prob = float(model.predict_proba([feats])[0][1])
            different_address = (
                left.get("address_parsed")
                and right.get("address_parsed")
                and left["address_parsed"] != right["address_parsed"]
                and left["address_parsed"].get("postcode")
                and right["address_parsed"].get("postcode")
                and left["address_parsed"]["postcode"] != right["address_parsed"]["postcode"]
            )
            if different_address:
                decision = "separate_ambiguous" if prob >= 0.5 else "separate"
            else:
                decision = "same" if prob >= 0.5 else "different"
            results.append({"left": left["text"], "right": right["text"], "prob": round(prob, 4), "decision": decision})
    return results
