import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

from rrh.dictation import segment_dictation
from rrh.editor import edit_field, negated_entities
from rrh.impression import condense
from rrh.pipeline import Config, ReportGenerator, infer_laterality
from rrh.routing import RoutingModel, normalize_level
from rrh.splitting import candidate_splits
from rrh.template import parse_template, render_report, resolve_placeholders
from rrh.textutil import split_sentences, tidy_sentence
from rrh.validate import validate

CHEST_TEMPLATE = """FINDINGS:
SUPPORT DEVICES: None.
CARDIOMEDIASTINAL SILHOUETTE: Within normal size limits.
LUNGS: No focal airspace opacity or pulmonary edema.
PLEURA: No pleural effusion or pneumothorax.
OSSEOUS STRUCTURES: No acute osseous abnormality identified on these views.

IMPRESSION:
No acute cardiopulmonary abnormality."""

CFG = Config()


def make_generator():
    return ReportGenerator(RoutingModel(), CFG)


# ------------------------------------------------------------------ text


def test_sentence_split_keeps_decimals_and_levels():
    out = split_sentences("Lesion measures 2.3 cm. C5-C6 shows a disc bulge.")
    assert out == ["Lesion measures 2.3 cm.", "C5-C6 shows a disc bulge."]


def test_sentence_split_recovers_missing_full_stop():
    out = split_sentences("Mild soft tissue edema is seen The medial meniscus is torn.")
    assert len(out) == 2 and out[1].startswith("The medial meniscus")


def test_tidy_sentence():
    assert tidy_sentence("  mild effusion is seen ") == "Mild effusion is seen."


# -------------------------------------------------------------- template


def test_template_roundtrip_preserves_labels_and_order():
    tmpl = parse_template(CHEST_TEMPLATE)
    assert [f.label for f in tmpl.fields] == [
        "SUPPORT DEVICES", "CARDIOMEDIASTINAL SILHOUETTE", "LUNGS", "PLEURA",
        "OSSEOUS STRUCTURES",
    ]
    out = render_report([(f.label, f.text) for f in tmpl.fields], tmpl.impression)
    assert "FINDINGS:" in out and out.rstrip().endswith("No acute cardiopulmonary abnormality.")


def test_labels_are_uppercased():
    tmpl = parse_template("FINDINGS:\nMedial meniscus: Intact.\n\nIMPRESSION:\nNormal.")
    assert tmpl.fields[0].label == "MEDIAL MENISCUS"


def test_placeholders_resolved():
    assert resolve_placeholders("Normal [left/right] shoulder.", "right", "shoulder") == (
        "Normal right shoulder."
    )


# ------------------------------------------------------------- splitting


def test_negation_split_does_not_propagate_qualifier():
    assert candidate_splits("No acute fracture or dislocation is identified.")[0] == [
        "No acute fracture is identified.",
        "No dislocation is identified.",
    ]


def test_subject_list_split():
    parts = candidate_splits(
        "The anterior cruciate ligament, posterior cruciate ligament, and medial "
        "collateral ligament are intact."
    )[0]
    assert parts == [
        "The anterior cruciate ligament is intact.",
        "The posterior cruciate ligament is intact.",
        "The medial collateral ligament is intact.",
    ]


def test_negated_entities():
    assert negated_entities("No pleural effusion or pneumothorax.") == [
        "pleural effusion",
        "pneumothorax",
    ]


def test_level_normalisation():
    assert normalize_level("C5-6") == normalize_level("C5-C6") == "c5-6"


# ---------------------------------------------------------------- editor


def test_contradicted_entity_is_removed_from_negative_list():
    body = edit_field("No pleural effusion or pneumothorax.", ["Small right pleural effusion."], CFG)
    assert "No pneumothorax." in body
    assert "No pleural effusion" not in body


def test_untouched_field_is_byte_identical():
    assert edit_field("The soft tissues are unremarkable.", [], CFG) == (
        "The soft tissues are unremarkable."
    )


# ------------------------------------------------------------ dictation


def test_boilerplate_is_not_reported():
    doc = segment_dictation(
        "Three radiographic views of the left hand obtained. Mild soft tissue swelling."
    )
    assert len(doc.findings) == 1
    assert doc.findings[0].text.startswith("Mild soft tissue swelling")


def test_normal_dictation_detected():
    assert segment_dictation("norml").is_normal


def test_shorthand_expanded():
    doc = segment_dictation("degen chnges of the rt hip")
    assert "degenerative changes" in doc.findings[0].text
    assert "right hip" in doc.findings[0].text


# ------------------------------------------------------------- pipeline


def worked_example_row():
    return {
        "case_id": "x",
        "modality": "XRAY",
        "body_part": "Chest",
        "study_description": "XR CXR 2V",
        "patient_age_band": "45-49",
        "patient_sex": "female",
        "template_content": CHEST_TEMPLATE,
        "dictation": "mild right basilar opacity, small right pleural effusion",
    }


def test_worked_example_routes_and_edits_correctly():
    report, trace = make_generator().generate(worked_example_row())
    assert "LUNGS: Mild right basilar opacity." in report
    assert "PLEURA: Small right pleural effusion. No pneumothorax." in report
    # untouched fields stay exactly as the template had them
    assert "SUPPORT DEVICES: None." in report
    assert "CARDIOMEDIASTINAL SILHOUETTE: Within normal size limits." in report
    assert "OSSEOUS STRUCTURES: No acute osseous abnormality identified on these views." in report
    # the normal impression must not survive alongside abnormal findings
    assert report.split("IMPRESSION:")[1].strip().startswith("1. ")


def test_normal_dictation_reproduces_template():
    row = dict(worked_example_row(), dictation="normal")
    report, _ = make_generator().generate(row)
    tmpl = parse_template(CHEST_TEMPLATE)
    expected = render_report([(f.label, f.text) for f in tmpl.fields], tmpl.impression)
    assert report.strip() == expected.strip()


def test_other_findings_left_empty():
    tmpl = CHEST_TEMPLATE.replace("IMPRESSION:", "OTHER FINDINGS:\n\nIMPRESSION:")
    row = dict(worked_example_row(), template_content=tmpl)
    report, _ = make_generator().generate(row)
    assert "OTHER FINDINGS:\n" in report + "\n"
    assert "OTHER FINDINGS: " not in report


def test_laterality_preserved():
    row = dict(worked_example_row(), dictation="small left pleural effusion")
    report, _ = make_generator().generate(row)
    assert "left pleural effusion" in report.lower()
    assert "right pleural effusion" not in report.lower()


def test_measurement_preserved():
    row = dict(worked_example_row(), dictation="right pleural effusion measuring 2.3 cm")
    report, _ = make_generator().generate(row)
    assert "2.3 cm" in report


def test_negation_not_flipped():
    row = dict(worked_example_row(), dictation="no pleural effusion, no pneumothorax")
    report, trace = make_generator().generate(row)
    pleura = [ln for ln in report.split("\n") if ln.startswith("PLEURA:")][0].lower()
    assert "no pleural effusion" in pleura and "no pneumothorax" in pleura
    assert not [i for i in validate(row, report, trace).issues if i.kind == "negation"]


def test_validator_flags_invented_content():
    row = worked_example_row()
    report, trace = make_generator().generate(row)
    bad = report.replace("No pneumothorax.", "No pneumothorax. Findings suggest sarcoidosis.")
    kinds = {i.kind for i in validate(row, bad, trace).issues}
    assert "unsupported_term" in kinds


def test_infer_laterality():
    assert infer_laterality({"study_description": "XR RT HIP 2V", "dictation": ""}) == "right"


def test_condense_strips_copula_and_detail():
    assert condense("Degenerative changes are present.") == "Degenerative changes."
    assert condense(
        "Mild osteoarthrosis of the left hip with joint space narrowing and sclerosis.",
        trim_detail=True,
    ) == "Mild osteoarthrosis of the left hip."


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
