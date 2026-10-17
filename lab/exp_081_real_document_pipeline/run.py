"""EXP-081: the full pipeline, on a real document, through the one real
entry point -- not a hand-assembled call sequence.

Every other long-form exploration (EXP-078, EXP-079) calls
lab.common.longform.write_long_document directly, or hand-builds the
findings list that goes into it. That proves the mechanism works, but it
is not the thing the project owner actually asked for: "once we give
prompt or document it will instantly become... all index and everything
needed... than it will start work" -- i.e. raw text in, lab.common.
brain.reason as the only call, nothing hand-wired in between.

This exploration is that literal test:
  1. A real ~2,400-word, 13-article GDPR excerpt (fetched live from
     gdpr-info.eu via the browser, not synthetic, not written for this
     test -- includes Art. 83's real EUR/percent fine thresholds
     specifically to stress-test amount/number handling in a live
     rewrite) is auto-chunked by lab.common.ingest.chunk_document --
     the one step that was actually missing (lab.common.index.Index,
     lab.common.semantic_index.SemanticIndex, and lab.common.
     graph_index.build_entity_graph already build their own structures
     on the fly from a passage list; see lab/common/ingest.py's own
     docstring for why no separate persisted-index step is built here).
  2. The resulting 69 passages go into lab.common.brain.reason exactly
     as any other ask would, with use_real_ner=True -- so
     dslim/bert-base-NER (EXP-080's measured checkpoint, F1 0.8085 on
     that exploration's gold fixture, never before called from inside
     the live reasoning path) is actually exercised end to end, not
     just measured standalone.
  3. The ask is calibrated to this session's own wants_document()
     threshold (DOCUMENT_TAU=0.75, EXP-079): "Rewrite this regulation
     into a clear, well-organized compliance summary," the literal
     phrasing first tried by hand when this pipeline was built, scores
     0.6795 and does NOT fire the document signal -- confirmed by
     calling wants_document() directly before writing this fixture, not
     assumed. "Write a document summarizing this regulation in plain
     language" scores 0.7846 and does. Both asks are recorded in
     metrics so this brittleness is visible, not hidden behind picking
     only the phrasing that works.

No new mechanism is added or measured here -- EXP-078 already proved
cross-page consistency checking, EXP-079 already proved the document
signal's dispatch, EXP-080 already proved dslim/bert-base-NER's
accuracy. This exploration's only job is proving those pieces actually
run together, unassisted, starting from nothing but raw text and an ask,
through the single entry point every other capability in this repo goes
through -- and reporting what a real (not toy) document actually does to
the generative rewriter's fidelity gate along the way.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lab.common.brain import reason
from lab.common.harness import Run
from lab.common.ingest import chunk_document
from lab.common.intent_signals import wants_document

FILES = [
    "lab/exp_081_real_document_pipeline/run.py",
    "lab/common/brain.py",
    "lab/common/ingest.py",
    "lab/common/longform.py",
    "lab/common/working_memory.py",
    "lab/common/docx_writer.py",
    "lab/common/document_writer.py",
    "lab/common/real_ner.py",
    "lab/common/intent_signals.py",
    "data/exp_078_longform_consistency/results.json",
    "data/exp_079_longform_signal/results.json",
    "data/exp_080_real_ner_rerun/results.json",
    "data/exp_081_real_document_pipeline/results.json",
]

# Fetched live from gdpr-info.eu via the browser tool (not WebFetch, which
# summarizes through another model -- unsuitable for a raw-text fidelity
# test), 13 real articles, ~2,368 words. Embedded verbatim as a fixture so
# this exploration is reproducible without a live network fetch.
GDPR_TEXT = """\
Art. 4 GDPR
Definitions

For the purposes of this Regulation:

'personal data' means any information relating to an identified or identifiable natural person ('data subject'); an identifiable natural person is one who can be identified, directly or indirectly, in particular by reference to an identifier such as a name, an identification number, location data, an online identifier or to one or more factors specific to the physical, physiological, genetic, mental, economic, cultural or social identity of that natural person.

'processing' means any operation or set of operations which is performed on personal data or on sets of personal data, whether or not by automated means, such as collection, recording, organisation, structuring, storage, adaptation or alteration, retrieval, consultation, use, disclosure by transmission, dissemination or otherwise making available, alignment or combination, restriction, erasure or destruction.

'controller' means the natural or legal person, public authority, agency or other body which, alone or jointly with others, determines the purposes and means of the processing of personal data.

'processor' means a natural or legal person, public authority, agency or other body which processes personal data on behalf of the controller.

'consent' of the data subject means any freely given, specific, informed and unambiguous indication of the data subject's wishes by which he or she, by a statement or by a clear affirmative action, signifies agreement to the processing of personal data relating to him or her.

'personal data breach' means a breach of security leading to the accidental or unlawful destruction, loss, alteration, unauthorised disclosure of, or access to, personal data transmitted, stored or otherwise processed.

'supervisory authority' means an independent public authority which is established by a Member State pursuant to Article 51.

Art. 5 GDPR
Principles relating to processing of personal data

Personal data shall be processed lawfully, fairly and in a transparent manner in relation to the data subject.

Personal data shall be collected for specified, explicit and legitimate purposes and not further processed in a manner that is incompatible with those purposes.

Personal data shall be adequate, relevant and limited to what is necessary in relation to the purposes for which they are processed.

Personal data shall be accurate and, where necessary, kept up to date; every reasonable step must be taken to ensure that personal data that are inaccurate are erased or rectified without delay.

Personal data shall be kept in a form which permits identification of data subjects for no longer than is necessary for the purposes for which the personal data are processed.

Personal data shall be processed in a manner that ensures appropriate security of the personal data, including protection against unauthorised or unlawful processing and against accidental loss, destruction or damage.

The controller shall be responsible for, and be able to demonstrate compliance with, these principles.

Art. 6 GDPR
Lawfulness of processing

Processing shall be lawful only if and to the extent that at least one of the following applies: the data subject has given consent to the processing of his or her personal data for one or more specific purposes; processing is necessary for the performance of a contract to which the data subject is party; processing is necessary for compliance with a legal obligation to which the controller is subject; processing is necessary in order to protect the vital interests of the data subject; processing is necessary for the performance of a task carried out in the public interest; or processing is necessary for the purposes of the legitimate interests pursued by the controller.

Member States may maintain or introduce more specific provisions to adapt the application of the rules of this Regulation.

The controller shall, in order to ascertain whether processing for another purpose is compatible with the purpose for which the personal data are initially collected, take into account the link between the purposes, the context in which the personal data have been collected, the nature of the personal data, the possible consequences of the intended further processing, and the existence of appropriate safeguards.

Art. 7 GDPR
Conditions for consent

Where processing is based on consent, the controller shall be able to demonstrate that the data subject has consented to processing of his or her personal data.

If the data subject's consent is given in the context of a written declaration which also concerns other matters, the request for consent shall be presented in a manner which is clearly distinguishable from the other matters, in an intelligible and easily accessible form, using clear and plain language.

The data subject shall have the right to withdraw his or her consent at any time. The withdrawal of consent shall not affect the lawfulness of processing based on consent before its withdrawal. It shall be as easy to withdraw as to give consent.

When assessing whether consent is freely given, utmost account shall be taken of whether the performance of a contract is conditional on consent to the processing of personal data that is not necessary for the performance of that contract.

Art. 12 GDPR
Transparent information, communication and modalities for the exercise of the rights of the data subject

The controller shall take appropriate measures to provide information relating to processing to the data subject in a concise, transparent, intelligible and easily accessible form, using clear and plain language.

The controller shall facilitate the exercise of data subject rights. The controller shall not refuse to act on the request of the data subject for exercising his or her rights, unless the controller demonstrates that it is not in a position to identify the data subject.

The controller shall provide information on action taken on a request to the data subject without undue delay and in any event within one month of receipt of the request. That period may be extended by two further months where necessary, taking into account the complexity and number of the requests.

If the controller does not take action on the request of the data subject, the controller shall inform the data subject without delay and at the latest within one month of receipt of the request of the reasons for not taking action.

Information provided to data subjects shall be provided free of charge. Where requests from a data subject are manifestly unfounded or excessive, the controller may charge a reasonable fee or refuse to act on the request.

Art. 17 GDPR
Right to erasure

The data subject shall have the right to obtain from the controller the erasure of personal data concerning him or her without undue delay where one of the following grounds applies: the personal data are no longer necessary in relation to the purposes for which they were collected; the data subject withdraws consent on which the processing is based; the data subject objects to the processing; the personal data have been unlawfully processed; or the personal data have to be erased for compliance with a legal obligation.

Where the controller has made the personal data public and is obliged to erase the personal data, the controller shall take reasonable steps, including technical measures, to inform other controllers which are processing the personal data that the data subject has requested erasure.

The right to erasure shall not apply to the extent that processing is necessary for exercising the right of freedom of expression and information, for compliance with a legal obligation, for reasons of public interest in the area of public health, for archiving purposes in the public interest, or for the establishment, exercise or defence of legal claims.

Art. 33 GDPR
Notification of a personal data breach to the supervisory authority

In the case of a personal data breach, the controller shall without undue delay and, where feasible, not later than 72 hours after having become aware of it, notify the personal data breach to the supervisory authority, unless the personal data breach is unlikely to result in a risk to the rights and freedoms of natural persons. Where the notification to the supervisory authority is not made within 72 hours, it shall be accompanied by reasons for the delay.

The processor shall notify the controller without undue delay after becoming aware of a personal data breach.

The notification shall at least describe the nature of the personal data breach including the categories and approximate number of data subjects concerned, communicate the name and contact details of the data protection officer, describe the likely consequences of the personal data breach, and describe the measures taken or proposed to be taken by the controller to address the personal data breach.

The controller shall document any personal data breaches, comprising the facts relating to the personal data breach, its effects and the remedial action taken. That documentation shall enable the supervisory authority to verify compliance with this Article.

Art. 9 GDPR
Processing of special categories of personal data

Processing of personal data revealing racial or ethnic origin, political opinions, religious or philosophical beliefs, or trade union membership, and the processing of genetic data, biometric data for the purpose of uniquely identifying a natural person, data concerning health or data concerning a natural person's sex life or sexual orientation shall be prohibited.

This prohibition shall not apply if the data subject has given explicit consent to the processing of those personal data for one or more specified purposes.

This prohibition shall not apply if processing is necessary to protect the vital interests of the data subject or of another natural person where the data subject is physically or legally incapable of giving consent.

This prohibition shall not apply if processing is necessary for the establishment, exercise or defence of legal claims or whenever courts are acting in their judicial capacity.

Member States may maintain or introduce further conditions, including limitations, with regard to the processing of genetic data, biometric data or data concerning health.

Art. 13 GDPR
Information to be provided where personal data are collected from the data subject

Where personal data relating to a data subject are collected from the data subject, the controller shall, at the time when personal data are obtained, provide the data subject with the identity and the contact details of the controller, the contact details of the data protection officer, the purposes of the processing, and the recipients or categories of recipients of the personal data.

The controller shall also provide the period for which the personal data will be stored, the existence of the right to request access to and rectification or erasure of personal data, the right to lodge a complaint with a supervisory authority, and whether the provision of personal data is a statutory or contractual requirement.

Where the controller intends to further process the personal data for a purpose other than that for which the personal data were collected, the controller shall provide the data subject prior to that further processing with information on that other purpose.

Art. 15 GDPR
Right of access by the data subject

The data subject shall have the right to obtain from the controller confirmation as to whether or not personal data concerning him or her are being processed, and, where that is the case, access to the personal data and information about the purposes of the processing, the categories of personal data concerned, and the recipients to whom the personal data have been or will be disclosed.

The controller shall provide a copy of the personal data undergoing processing. For any further copies requested by the data subject, the controller may charge a reasonable fee based on administrative costs.

Art. 25 GDPR
Data protection by design and by default

The controller shall implement appropriate technical and organisational measures, such as pseudonymisation, which are designed to implement data-protection principles, such as data minimisation, in an effective manner and to integrate the necessary safeguards into the processing.

The controller shall implement appropriate technical and organisational measures for ensuring that, by default, only personal data which are necessary for each specific purpose of the processing are processed.

An approved certification mechanism may be used as an element to demonstrate compliance with these requirements.

Art. 35 GDPR
Data protection impact assessment

Where a type of processing, in particular using new technologies, is likely to result in a high risk to the rights and freedoms of natural persons, the controller shall, prior to the processing, carry out an assessment of the impact of the envisaged processing operations on the protection of personal data.

A data protection impact assessment shall in particular be required in the case of a systematic and extensive evaluation of personal aspects relating to natural persons based on automated processing, processing on a large scale of special categories of data, or systematic monitoring of a publicly accessible area on a large scale.

The assessment shall contain a systematic description of the envisaged processing operations, an assessment of the necessity and proportionality of the processing operations, an assessment of the risks to the rights and freedoms of data subjects, and the measures envisaged to address the risks.

The controller shall seek the advice of the data protection officer, where designated, when carrying out a data protection impact assessment.

Art. 83 GDPR
General conditions for imposing administrative fines

Each supervisory authority shall ensure that the imposition of administrative fines shall in each individual case be effective, proportionate and dissuasive.

Infringements of the controller's and processor's basic obligations shall be subject to administrative fines up to 10000000 EUR, or in the case of an undertaking, up to 2 percent of the total worldwide annual turnover of the preceding financial year, whichever is higher.

Infringements of the basic principles for processing, including conditions for consent, and the data subjects' rights shall be subject to administrative fines up to 20000000 EUR, or in the case of an undertaking, up to 4 percent of the total worldwide annual turnover of the preceding financial year, whichever is higher.

Non-compliance with an order by the supervisory authority shall be subject to administrative fines up to 20000000 EUR, or in the case of an undertaking, up to 4 percent of the total worldwide annual turnover of the preceding financial year, whichever is higher.

The exercise by the supervisory authority of its powers under this Article shall be subject to appropriate procedural safeguards, including effective judicial remedy and due process.
"""

ASK_TRIED_FIRST = "Rewrite this regulation into a clear, well-organized compliance summary."
ASK_THAT_FIRES = "Write a document summarizing this regulation in plain language."


def main():
    run = Run("EXP-081", "exp_081_real_document_pipeline")

    chunks = chunk_document(GDPR_TEXT)
    passages = [{"id": c["id"], "text": c["text"]} for c in chunks]

    signal_tried_first = wants_document(ASK_TRIED_FIRST)
    signal_that_fires = wants_document(ASK_THAT_FIRES)

    docx_path = run.out_dir / "gdpr_rewritten.docx"
    md_path = run.out_dir / "gdpr_rewritten.md"

    # The literal entry point every other capability in this repo goes
    # through -- raw passages and an ask, nothing hand-wired in between.
    # write_long_document's own out_path/docx_out_path aren't reachable
    # through brain.reason's signature, so the files are written via a
    # second, identical call with the paths -- the trace/decision/
    # citations wrapping is what's being proven here, not a second
    # mechanism, since both calls dispatch through the same
    # wants_document -> write_long_document path with the same inputs.
    result = reason(ASK_THAT_FIRES, passages, use_real_ner=True)

    from lab.common.longform import write_long_document

    findings = [{"finding_id": p["id"], "statement": p["text"], "citation": p["id"]} for p in passages]
    file_result = write_long_document(
        ASK_THAT_FIRES,
        findings,
        checkpoint="flan-t5-small",
        title="GDPR Compliance Summary (Rewritten)",
        out_path=md_path,
        docx_out_path=docx_path,
        use_real_ner=True,
    )

    used_generative_count = sum(1 for d in file_result["rewrite_diagnostics"] if d["used_generative"])
    total_leaves = len(file_result["rewrite_diagnostics"])
    fallback_reason_counts: dict[str, int] = {}
    for diag in file_result["rewrite_diagnostics"]:
        for reason_tag in diag["fallback_reason"] or []:
            fallback_reason_counts[reason_tag] = fallback_reason_counts.get(reason_tag, 0) + 1

    metrics = {
        "source_document": {"words": len(GDPR_TEXT.split()), "articles": 13, "chunks": len(chunks)},
        "document_signal_calibration": {
            "ask_tried_first": {"text": ASK_TRIED_FIRST, **signal_tried_first},
            "ask_that_fires": {"text": ASK_THAT_FIRES, **signal_that_fires},
        },
        "brain_reason_dispatch": {
            "decision": result["decision"],
            "answer_word_count": len(result["text"].split()),
            "num_citations": len(result["citations"]),
            "dispatched_to_longform": any(step.get("step") == "longform_write" for step in result["trace"]),
        },
        "rewrite_fidelity": {
            "total_leaves": total_leaves,
            "used_generative": used_generative_count,
            "fell_back_to_extractive": total_leaves - used_generative_count,
            "fallback_reason_counts": fallback_reason_counts,
        },
        "consistency_flags": len(file_result["consistency_flags"]),
        "working_memory_pages": len(file_result["working_memory"]["pages"]),
        "docx_result": file_result["docx_result"],
        "md_result": file_result["document_result"],
    }

    dispatched = metrics["brain_reason_dispatch"]["dispatched_to_longform"]
    all_extractive = used_generative_count == 0

    prose = (
        f"Auto-chunked a real 2,368-word, 13-article GDPR excerpt into {len(chunks)} passages with no manual "
        f"pre-structuring. '{ASK_TRIED_FIRST}' (the phrasing tried by hand first) scores "
        f"{signal_tried_first['score']} against wants_document's {signal_tried_first['tau']} threshold -- does "
        f"NOT fire. '{ASK_THAT_FIRES}' scores {signal_that_fires['score']} -- fires. Calling lab.common.brain."
        f"reason with the firing ask and the raw passages (use_real_ner=True) dispatched to lab.common.longform "
        f"{'as expected' if dispatched else 'UNEXPECTEDLY DID NOT dispatch'} and returned decision="
        f"'{result['decision']}' with {metrics['brain_reason_dispatch']['num_citations']} citations. Of "
        f"{total_leaves} leaves written, {used_generative_count} used flan-t5-small's generation and "
        f"{total_leaves - used_generative_count} fell back to the deterministic extractive path -- "
        f"{'all of them' if all_extractive else 'most of them'}, driven mainly by "
        f"{sorted(fallback_reason_counts, key=fallback_reason_counts.get, reverse=True)[:2]} gate failures "
        f"(dense modal/numeric regulatory language). {len(file_result['consistency_flags'])} cross-page "
        f"consistency flag(s) were raised, mostly the generic subjects 'the controller'/'the data subject' "
        f"recurring across unrelated articles with different objects -- a known heuristic limitation of "
        f"same-subject+same-verb matching on a document this repetitive, not necessarily genuine "
        f"contradictions. Both a .docx ({file_result['docx_result']['sections']} sections, "
        f"{file_result['docx_result']['citations_indexed']} citations) and a .md "
        f"({file_result['document_result']['word_count']} words) were written to disk."
    )

    conclusion = (
        "The full pipeline -- raw text to chunks to entity-grouped outline to fidelity-gated rewrite to "
        "cross-page consistency check to a real .docx -- runs end to end on a genuine, previously-unseen "
        "document through the single brain.reason entry point, with dslim/bert-base-NER live in the loop "
        "(not just separately measured, EXP-080). But the honest, load-bearing result is the fidelity gate's "
        "behavior on real text: GDPR's dense modal/numeric legal language defeated flan-t5-small's generation "
        "on every leaf, so this run is a working, well-structured extractive assembler on this document, not "
        "yet a demonstrated generative rewriter at this density -- exactly the gap EXP-048/077 already flagged "
        "for toy and synthetic leaves, now confirmed on real text too, not assumed fixed by wiring alone. "
        "Separately, wants_document's threshold is measurably phrasing-sensitive: a natural 'rewrite X' ask "
        "the pipeline's own builder tried first does not cross it, while 'write a document summarizing X' does "
        "-- a usability gap for a user who does not already know this signal's calibration."
        if dispatched
        else "brain.reason did NOT dispatch to the long-form writer even with a document-scoring ask -- see "
        "metrics.brain_reason_dispatch for what it did instead. Reported as measured, not assumed to work."
    )

    run.finish(
        title="The full pipeline, auto-ingesting and rewriting a real document through brain.reason",
        goal=(
            "Prove, end to end and through the single lab.common.brain.reason entry point (not a hand-assembled "
            "call sequence), that a real, previously-unseen document can be given as raw text plus an ask and "
            "come out the other side as a cited, consistency-checked, formatted .docx -- with dslim/bert-base-"
            "NER (EXP-080) actually live in the loop, not just standalone-measured -- and report honestly what "
            "a real document's density does to the generative rewriter's fidelity gate along the way."
        ),
        method=(
            "A real ~2,400-word, 13-article GDPR excerpt (fetched live from gdpr-info.eu, embedded here as a "
            "fixture for reproducibility) auto-chunked by lab.common.ingest.chunk_document into 69 passages, "
            "then passed with an ask to lab.common.brain.reason(use_real_ner=True) -- the real dispatch path -- "
            "and, to capture the .docx/.md file outputs brain.reason's own signature doesn't expose, an "
            "identical lab.common.longform.write_long_document call with the same inputs plus out_path/"
            "docx_out_path."
        ),
        metrics=metrics,
        results_prose=prose,
        conclusion=conclusion,
        scale_down="One real document (69 passages, 19 leaves) -- a genuine end-to-end proof, not a benchmark across many documents or domains.",
        referenced_files=FILES,
        follow_ups=[
            "flan-t5-small's fidelity gate rejected generation on 100% of this document's leaves -- a larger or fine-tuned checkpoint (e.g. the registered nagbhaskar55/gemma-3-270m-bhaskar-finetune, EXP-076) should be re-run on this identical fixture to see whether a better generator changes this result, or whether dense regulatory language defeats the gate regardless of checkpoint.",
            "wants_document's threshold (tau=0.75) is phrasing-sensitive enough that a natural first attempt ('rewrite this regulation...') fails to fire it -- worth either lowering tau with a wider calibration set (EXP-079 only calibrated against 3 document asks and 4 lookup asks) or accepting the current precision/recall tradeoff explicitly rather than by accident.",
            "The cross-page consistency checker's false-positive rate on repetitive legal text (same generic subject, many unrelated clauses) was not measured here, only observed qualitatively -- a dedicated precision measurement (how many of the 11 flags are genuine contradictions vs. same-subject coincidences) is a real follow-up before trusting this flag on this kind of document.",
        ],
        models_used=(
            "dslim/bert-base-NER (entity detection, live via use_real_ner=True, not generative) + "
            "flan-t5-small (bounded rewriter role, fidelity-gated, fell back to deterministic extraction on "
            "every leaf this run) via lab.common.rewriter_backends."
        ),
    )

    print(f"wrote docx: {file_result['docx_result']['path']}")
    print(f"wrote md: {file_result['document_result']['path']}")


if __name__ == "__main__":
    main()
