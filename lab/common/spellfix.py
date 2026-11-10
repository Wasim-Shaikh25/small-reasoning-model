"""Spelling correction, resolved WITHOUT a generative model.

Final design, `fix_sentence_joint` + `_pick_by_context_embedding`: find
every typo via vocabulary + edit distance (safe, closed, never invents a
word), then resolve any ambiguity by bge-embedding similarity between
each candidate word and its sentence context -- the same non-generative
signal `intent_signals._best_similarity` already uses elsewhere in this
project. Verified live (2026-11-09) at 4/4 on the genuinely ambiguous
cases this file's history records every generative attempt failing:
"herd"->heard, "realy"->really, "lonly"->lonely, "peopel"->people.

This is the project's own "closed output space" principle taken one step
further: not just constraining WHICH words a model may answer with
(every earlier attempt already did that), but removing the generative
model from the decision entirely, because the actual judgment needed --
does this candidate's meaning fit the context -- turned out to be a
semantic-similarity question, which embeddings answer reliably, not a
multi-step reasoning question, which is what was being asked of a 270M-
500M generative model every time, unnecessarily.

`resolve()` and `fix_sentence()` below are kept as the superseded,
less-reliable generative alternatives (closed-candidate-set-then-ask-the-
model, and whole-sentence-free-rewrite-then-validate, respectively) --
not deleted, since this project's practice is to keep a tested, failed
design visible with its evidence rather than erase the trail. Both
scored at or below 50% on these same cases across five independent
prompt/architecture/checkpoint combinations; see AUDIT.md, "the fix:
embedding-based disambiguation, zero generative model calls" (2026-11-09).

Three bugs fixed along the way, all found by actually running this
against real text rather than assuming it would work:
1. Plain vocabulary-nearest-match with no context picks a real but
   wrong word ("peopel"->"propel", "cos"->"cost") -- fixed by separating
   candidate generation (context-free, safe) from disambiguation
   (context-aware).
2. The vocabulary extraction itself misses real compound words that
   tokenize into >1 piece ("overhear" was never a single token, so it
   got wrongly flagged as a typo and "corrected" to "overhead") -- fixed
   by `_splits_into_known_compound`, checked to find zero false matches
   on the real typos in this file's own test set.
3. Ordinary verb/noun inflection has the same root cause, far more
   common (HANDOFF.md, 2026-11-10): `candidates_for("commissioned")`
   returned only `["commissioner"]`, silently swapping a correctly-
   spelled past participle for a different, wrong-part-of-speech word,
   because "commission" is a single token but "commissioned" isn't --
   fixed by `_lemma_known` (lemmatize via `lab.common.rules._parser`,
   already a project dependency, before the vocabulary check), checked
   directly against both regular ("walked", "studies") and irregular
   ("ran", "children") inflections, with the real typos in this file's
   own test set (herd/realy/lonly/peopel) confirmed still caught.
"""

from __future__ import annotations

import json

_KEEP_ORIGINAL = "KEEP_ORIGINAL"
_vocab: set[str] | None = None


def _load_vocab() -> set[str]:
    global _vocab
    if _vocab is None:
        from transformers import AutoTokenizer

        tok = AutoTokenizer.from_pretrained("google/flan-t5-small")
        words = set()
        for piece in tok.get_vocab():
            if piece.startswith("▁"):
                w = piece[1:]
                if w.isalpha() and w.islower() and len(w) > 1:
                    words.add(w)
        _vocab = words
    return _vocab


def _damerau_levenshtein(a: str, b: str) -> int:
    d = {}
    la, lb = len(a), len(b)
    for i in range(-1, la + 1):
        d[(i, -1)] = i + 1
    for j in range(-1, lb + 1):
        d[(-1, j)] = j + 1
    for i in range(la):
        for j in range(lb):
            cost = 0 if a[i] == b[j] else 1
            d[(i, j)] = min(d[(i - 1, j)] + 1, d[(i, j - 1)] + 1, d[(i - 1, j - 1)] + cost)
            if i > 0 and j > 0 and a[i] == b[j - 1] and a[i - 1] == b[j]:
                d[(i, j)] = min(d[(i, j)], d[(i - 2, j - 2)] + cost)
    return d[(la - 1, lb - 1)]


def _splits_into_known_compound(word: str, vocab: set[str], min_piece: int = 3) -> bool:
    """A correctly-spelled compound word ("overhear") is often NOT a
    single whole-word token in flan-t5-small's vocabulary -- found live
    (2026-11-09) wrongly flagging "overhear" as a typo and "correcting"
    it to "overhead", actively damaging correct text, not just failing
    to fix broken text. Checked directly: this split-check finds zero
    false matches on 7 real typos (peopel/wrk/herd/lonly/realy/cos/thats)
    and correctly rescues overhear/overhead/cannot/without/however.
    """
    for i in range(min_piece, len(word) - min_piece + 1):
        if word[:i] in vocab and word[i:] in vocab:
            return True
    return False


def _lemma_known(word: str, vocab: set[str]) -> bool:
    """True if `word`'s own LEMMA (spaCy's dependency parser pipeline,
    already a project dependency -- `lab.common.rules._parser`) is a real
    vocabulary word, even when the inflected surface form itself isn't a
    single flan-t5-small token. Found live: `candidates_for("commissioned")`
    returned only `["commissioner"]` (one true edit away: "...oned" vs
    "...oner"), silently "correcting" a correctly-spelled past participle
    to a different, wrong-part-of-speech word, because "commission" IS a
    single token but "commissioned" is not -- the same subword-splitting
    root cause already named for "overhear"/compound words, just for
    ordinary verb inflection instead, and far more frequent in real prose.
    Checked directly, not assumed: this correctly resolves both regular
    inflections ("walked"->"walk", "studies"->"study") and irregular ones
    ("ran"->"run", "children"->"child") the same way, while leaving real
    typos ("herd", "realy", "peopel") untouched -- spaCy's lemmatizer
    returns an unrecognized token's own surface form unchanged when it
    isn't a known inflection, so a genuine typo's "lemma" is just itself,
    still correctly absent from `vocab`.
    """
    from lab.common.rules import _parser

    doc = _parser()(word)
    if not len(doc):
        return False
    lemma = doc[0].lemma_.lower()
    return lemma in vocab or _splits_into_known_compound(lemma, vocab)


def candidates_for(word: str, max_distance: int = 1) -> list[str]:
    """Every vocabulary word within `max_distance` true edits of `word`,
    sorted for determinism. Already a real word (no fix needed) returns [].

    Words of length <=2 ("i", "a", "is", "to", ...) are always treated as
    already valid, never flagged -- found live (2026-11-09) that the
    vocabulary extraction itself excludes 1-letter words, which otherwise
    makes a correct bare "i" look like a misspelling and get "fixed" into
    "im". The risk of a genuine 1-2 letter typo is low and the risk of
    wrongly rewriting a correct short word is high, so this errs toward
    leaving short words alone entirely.
    """
    lower = word.lower()
    if len(lower) <= 2:
        return []
    vocab = _load_vocab()
    if lower in vocab or _splits_into_known_compound(lower, vocab) or _lemma_known(lower, vocab):
        return []
    out = []
    for v in vocab:
        if abs(len(v) - len(lower)) > max_distance:
            continue
        if _damerau_levenshtein(lower, v) <= max_distance:
            out.append(v)
    return sorted(out)


def fix_sentence(sentence: str, checkpoint: str = "gemma3:270m", max_drift: int = 2) -> dict:
    """Whole-sentence rewrite, word-level validated.

    `resolve()` above isolates one word and asks the model to pick among
    pre-vetted candidates -- tested live and found genuinely unreliable
    (gemma3:270m and Qwen2.5-0.5B-Instruct both scored under 50% on the
    hard, multi-candidate cases across two prompt framings each; see
    AUDIT.md, 2026-11-09). The isolated word has no sentence context left
    once pulled out, and that turns out to matter more than expected.

    This instead lets the model read and rewrite the WHOLE sentence (the
    framing that already correctly fixed "peopel"->"people" earlier this
    session, because it had the rest of the sentence to work with), then
    validates the result WORD BY WORD: a changed word is only accepted if
    it is a real vocabulary word AND within `max_drift` true edits of what
    was actually typed. A word-count mismatch (something dropped or
    added, not just misspelled) rejects the whole rewrite outright. This
    is the same shape as this project's other generate-then-gate designs
    (`real_rewriter.fidelity_gate`) -- the model proposes with context,
    a cheap deterministic check decides whether to trust each specific
    change, so it can't silently swap in something unrelated even when it
    tries to.
    """
    from lab.common.real_rewriter_ollama import generate

    prompt = (
        "Fix only the spelling and grammar of this sentence. Do not add, "
        "remove, or change any fact, name, number, or claim. Output only "
        "the corrected sentence, nothing else.\n\n"
        f"Sentence: {sentence}\nCorrected:"
    )
    generated = generate(prompt, max_tokens=120).strip()
    orig_words, new_words = sentence.split(), generated.split()
    if len(orig_words) != len(new_words):
        return {"text": sentence, "accepted": False, "reason": "word_count_changed", "changes": []}

    vocab = _load_vocab()
    final, changes = [], []
    for orig, new in zip(orig_words, new_words):
        orig_clean = orig.strip(".,!?\"'").lower()
        new_clean = new.strip(".,!?\"'").lower()
        if orig_clean == new_clean:
            final.append(orig)
            continue
        if new_clean in vocab and _damerau_levenshtein(orig_clean, new_clean) <= max_drift:
            final.append(new)
            changes.append({"from": orig, "to": new, "accepted": True})
        else:
            final.append(orig)
            changes.append({"from": orig, "to": new, "accepted": False, "reason": "not_real_word_or_too_different"})
    return {"text": " ".join(final), "accepted": True, "changes": changes}


def _cosine(a, b) -> float:
    import numpy as np

    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def _pick_by_context_embedding(word: str, sentence: str, candidates: list[str]) -> tuple[str, float]:
    """No generative model at all. Embed the sentence with the ambiguous
    word removed (the context), and each candidate word alone, then pick
    whichever candidate's own meaning is most similar to that context --
    the same bge-embedding signal `intent_signals._best_similarity`
    already uses for ask-vs-capability-exemplar matching, applied here to
    word-vs-context instead.

    Found live (2026-11-09) to beat every generative approach tried on
    this task, decisively: gemma3:270m and Qwen2.5-0.5B-Instruct, across
    five different prompt/architecture combinations (isolated-word pick,
    joint-sentence pick, whole-sentence free rewrite, two prompt
    rewordings, and a worked few-shot example with the literal answer
    shown immediately before the real question -- which still didn't
    change the model's wrong answer), scored at or below 50% on the
    genuinely ambiguous cases. Pure embedding similarity scored 4/4 on
    the same cases ("herd"->heard, "realy"->really, "lonly"->lonely,
    "peopel"->people), because word-sense-fits-context is a semantic
    relatedness judgment, the same kind of judgment this project already
    established bge embeddings are reliable for (ask-vs-capability-
    exemplar matching) -- as opposed to ask-vs-passage-content similarity
    for guessing fact presence, which this project separately measured
    and found UNRELIABLE (gapfill.py, same day). Different use case,
    different reliability; tested, not assumed, either way.
    """
    from lab.common.real_encoders import bge_embed

    context = sentence.replace(word, "", 1)
    context_vec = bge_embed([context])[0]
    cand_vecs = bge_embed(candidates)
    scored = sorted(
        ((c, _cosine(context_vec, cand_vecs[i])) for i, c in enumerate(candidates)),
        key=lambda x: -x[1],
    )
    return scored[0]


def fix_sentence_joint(sentence: str, max_distance: int = 1) -> dict:
    """Find every typo in the sentence (vocabulary + edit distance, see
    `candidates_for`) and resolve each one by context-embedding similarity
    (see `_pick_by_context_embedding`) -- no generative model call
    anywhere in this path. A typo with only one candidate is applied
    directly (no ambiguity to resolve); a typo with several candidates is
    resolved by whichever one's own meaning best fits the rest of the
    sentence.

    Informal-register words ("cos", "gonna", ...) are normalized first
    (`informal_register.normalize_informal`) -- they are not typos (no
    candidate within edit distance means what they mean) and were
    confirmed live to be misdiagnosed as one otherwise ("cos"->"cons").

    A capitalized word is never flagged -- found live (2026-11-09, a real
    Bombay HC sample-petition test): with no such skip, "Sagar" (a proper
    noun, correctly spelled, not in the lowercase-only vocabulary) was
    "corrected" to "sugar", "Mehta" to "meta", and the abbreviation "Pvt"
    to "pot" -- all real, close English words, all wrong, all actively
    corrupting correctly-spelled input. Same risk-asymmetry reasoning
    `candidates_for`'s own length<=2 exemption already uses: proper nouns
    and abbreviations are overwhelmingly capitalized in running English
    text, so this is a cheap, reliable signal, and the cost of wrongly
    "fixing" a correct capitalized word (an active corruption) is worse
    than the cost of missing a rare genuine typo in one (a silent
    non-fix) -- same direction as leaving short words alone, not a new
    principle.

    First-fixed version of this skip only excluded `i > 0` (mid-sentence)
    capitalized words, reasoning position 0 is capitalized by English
    convention regardless of word identity. Caught live by direct
    adversarial testing before trusting it: that left a sentence-initial
    proper noun ("Sagar Mehta of Oceanic Pvt Ltd filed...") still
    corrupted to "sugar Mehta...", since "Sagar" at position 0 was never
    checked at all. The trade-off this module already accepts (missing a
    rare sentence-initial typo is cheaper than corrupting a real name)
    applies identically regardless of position, so the skip is now
    unconditional on position -- a genuine capability loss for typos that
    happen to start a sentence, accepted on purpose, not an oversight.
    """
    from lab.common.informal_register import normalize_informal

    sentence = normalize_informal(sentence)["text"]
    words = sentence.split()
    ambiguous: dict[int, list[str]] = {}
    for i, w in enumerate(words):
        if w[:1].isupper():
            continue
        clean = w.strip(".,!?\"'").lower()
        cands = candidates_for(clean, max_distance=max_distance)
        if cands:
            ambiguous[i] = cands

    final_words = list(words)
    picks = {}
    for i, cands in ambiguous.items():
        if len(cands) == 1:
            final_words[i] = cands[0]
            continue
        choice, score = _pick_by_context_embedding(words[i].strip(".,!?\"'").lower(), sentence, cands)
        final_words[i] = choice
        picks[f"w{i}"] = {"choice": choice, "score": round(score, 4)}
    return {"text": " ".join(final_words), "picks": picks, "ambiguous": ambiguous}


def resolve(word: str, sentence: str, candidates: list[str], checkpoint: str = "gemma3:270m") -> dict:
    """Returns {"word", "changed", "reason", "candidates"}.

    `reason` is one of: "already_valid" (not reached here, candidates==[]
    means no fix needed, handled by the caller), "no_candidates" (not a
    recognized typo shape, left alone), "unambiguous" (exactly one real
    word that close, no model call made), "model_chose", "model_declined",
    "model_unparseable" (constrained output didn't parse -- fails closed,
    original word kept, same discipline as every other fallback in this
    project).
    """
    if not candidates:
        return {"word": word, "changed": False, "reason": "no_candidates", "candidates": []}
    if len(candidates) == 1:
        return {"word": candidates[0], "changed": True, "reason": "unambiguous", "candidates": candidates}

    from lab.common.real_rewriter_ollama import _post_with_retry

    schema = {
        "type": "object",
        "properties": {"choice": {"type": "string", "enum": candidates + [_KEEP_ORIGINAL]}},
        "required": ["choice"],
    }
    blanked = sentence.replace(word, "____", 1)
    prompt = (
        f"Fill in the blank with the ONE word from the list that makes the "
        f"most sense. If none of them make sense, answer {_KEEP_ORIGINAL}.\n\n"
        f"Sentence: {blanked}\n"
        f"Word list: {', '.join(candidates)}\n"
        f"Which word fills the blank?"
    )
    resp = _post_with_retry({
        "model": checkpoint, "prompt": prompt, "stream": False, "format": schema,
        "options": {"num_predict": 40, "temperature": 0, "seed": 0},
    })
    resp.raise_for_status()
    try:
        choice = json.loads(resp.json()["response"])["choice"]
    except (json.JSONDecodeError, KeyError):
        return {"word": word, "changed": False, "reason": "model_unparseable", "candidates": candidates}
    if choice == _KEEP_ORIGINAL or choice not in candidates:
        return {"word": word, "changed": False, "reason": "model_declined", "candidates": candidates}
    return {"word": choice, "changed": True, "reason": "model_chose", "candidates": candidates}
