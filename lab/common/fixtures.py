"""Shared real-document fixtures used by multiple experiments.

GDPR_TEXT was originally embedded in lab/exp_081_real_document_pipeline/
run.py (fetched live from gdpr-info.eu via the browser tool, 13 real
articles, ~2,368 words -- not synthetic, not written for any one test).
When EXP-081 itself was deleted (2026-11-11, its own pipeline run already
RETIRED and non-runnable once the generative rewriter checkpoints it
compared were removed), GDPR_TEXT was moved here because six other live
experiments (on-disk indexing, neighbor coherence, exception scoping,
deontic classification, connective detection, connective coverage) import
it as their shared real-document fixture, independent of EXP-081's own
retired pipeline measurement. Recover EXP-081 itself with
`git show <commit before its deletion>:lab/exp_081_real_document_pipeline/run.py`
if that specific measurement is ever needed again.
"""

from __future__ import annotations

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
