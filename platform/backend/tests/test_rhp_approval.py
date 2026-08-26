import pytest

from app.services.rhp.approval import automatic_review_resolutions, validate_review_resolutions


def test_review_requires_one_resolution_for_every_warning():
    issues = [{"code": "MODEL_WARNING"}, {"code": "VALUE_NOT_IN_EVIDENCE"}]
    with pytest.raises(ValueError, match="Every validation issue"):
        validate_review_resolutions(
            issues,
            [
                {
                    "issue_code": "MODEL_WARNING",
                    "disposition": "ACCEPTED",
                    "note": "Expected bounded-list truncation.",
                }
            ],
        )


def test_review_resolutions_preserve_issue_order_and_audit_notes():
    issues = [{"code": "MODEL_WARNING"}, {"code": "UNEXPECTED_NEGATIVE"}]
    resolutions = [
        {
            "issue_code": "MODEL_WARNING",
            "disposition": "ACCEPTED",
            "note": "The omitted list entries are non-canonical descriptive data.",
        },
        {
            "issue_code": "UNEXPECTED_NEGATIVE",
            "disposition": "ACCEPTED",
            "note": "The RHP prints the peer P/E in parentheses.",
        },
    ]
    assert validate_review_resolutions(issues, resolutions) == resolutions


@pytest.mark.parametrize("disposition", ["", "IGNORED", "APPROVED"])
def test_review_rejects_unknown_dispositions(disposition):
    with pytest.raises(ValueError, match="Unsupported review disposition"):
        validate_review_resolutions(
            [{"code": "MODEL_WARNING"}],
            [
                {
                    "issue_code": "MODEL_WARNING",
                    "disposition": disposition,
                    "note": "Checked manually.",
                }
            ],
        )


def test_review_requires_a_nonempty_note():
    with pytest.raises(ValueError, match="requires a note"):
        validate_review_resolutions(
            [{"code": "MODEL_WARNING"}],
            [
                {
                    "issue_code": "MODEL_WARNING",
                    "disposition": "ACCEPTED",
                    "note": "",
                }
            ],
        )


def test_automatic_review_accepts_every_issue_with_an_audit_note():
    issues = [{"code": "VALUE_NOT_IN_EVIDENCE"}, {"code": "MODEL_WARNING"}]
    assert automatic_review_resolutions(issues) == [
        {
            "issue_code": "VALUE_NOT_IN_EVIDENCE",
            "disposition": "ACCEPTED",
            "note": "Automatically accepted by the configured RHP publication policy.",
        },
        {
            "issue_code": "MODEL_WARNING",
            "disposition": "ACCEPTED",
            "note": "Automatically accepted by the configured RHP publication policy.",
        },
    ]
