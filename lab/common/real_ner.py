"""The real NER checkpoint (dslim/bert-base-NER, CoNLL-2003), wired into
the shape lab.common.entities.detect_primary already returns -- closing
EXP-034's long-open gap: the checkpoint has been loaded in
lab.common.real_encoders since EXP-033, but nothing in this repo actually
called it for the entity-detection role it was loaded for.

Non-generative by construction (a token classifier, never asked to
generate text) -- this is not the generative-model extraction FORBIDDEN.md
forbids. It supplements the regex tagger for person/organization only:
dslim/bert-base-NER's CoNLL-2003 label set (PER/ORG/LOC/MISC) has no
address/date/amount category at all, so the regex tagger still owns those
entirely; this module never claims to replace it, only to give person/org
detection a real second opinion beyond lab.common.entities' own second
regex tagger (which EXP-009's own docstring already noted is "a second
opinion only in that limited sense").
"""

from __future__ import annotations

from lab.common.real_encoders import real_entities

_LABEL_MAP = {"PER": "person", "ORG": "organization"}


def detect_real(text: str) -> list[dict]:
    """dslim/bert-base-NER's PER/ORG spans, reshaped to detect_primary's
    exact mention shape -- LOC/MISC are dropped, not mapped to "address":
    CoNLL's LOC is place names generally (cities, countries), not postal
    addresses with house numbers, so mapping it to this project's
    "address" label would claim a correspondence the checkpoint was never
    trained to make.
    """
    mentions = []
    for ent in real_entities(text):
        label = _LABEL_MAP.get(ent["label"])
        if label is None:
            continue
        mentions.append(
            {
                "start": ent["start"],
                "end": ent["end"],
                "text": ent["text"],
                "label": label,
                "conf": ent["score"],
                "tagger": "dslim_bert_base_ner",
            }
        )
    return mentions
