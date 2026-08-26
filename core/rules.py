"""
Rule-based compliance engine.

Loads mandatory-declaration definitions from data/rules.json and checks
a block of OCR-extracted text against each one. Deliberately simple and
regex-based — transparent and easy for a judge (or your team) to
explain, and easy to extend as you learn more about the actual rules.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

RULES_PATH = Path(__file__).resolve().parent.parent / "data" / "rules.json"


@dataclass
class FieldResult:
    id: str
    label: str
    description: str
    required: bool
    found: bool
    matched_text: str | None = None


@dataclass
class ComplianceResult:
    fields: list[FieldResult] = field(default_factory=list)

    @property
    def total_required(self) -> int:
        return sum(1 for f in self.fields if f.required)

    @property
    def passed_required(self) -> int:
        return sum(1 for f in self.fields if f.required and f.found)

    @property
    def is_compliant(self) -> bool:
        return self.passed_required == self.total_required

    @property
    def score_pct(self) -> float:
        if self.total_required == 0:
            return 100.0
        return round(100 * self.passed_required / self.total_required, 1)

    @property
    def missing_required(self) -> list[FieldResult]:
        return [f for f in self.fields if f.required and not f.found]


def load_rules() -> list[dict]:
    with open(RULES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["rules"]


def check_compliance(extracted_text: str) -> ComplianceResult:
    """
    Run every rule from rules.json against the extracted text.

    Matching is case-insensitive. A field is "found" if ANY of its
    listed patterns matches somewhere in the text.
    """
    text = extracted_text.upper()
    rules = load_rules()
    result = ComplianceResult()

    for rule in rules:
        matched_text = None
        for pattern in rule["patterns"]:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                matched_text = m.group(0)
                break

        result.fields.append(
            FieldResult(
                id=rule["id"],
                label=rule["label"],
                description=rule["description"],
                required=rule["required"],
                found=matched_text is not None,
                matched_text=matched_text,
            )
        )

    return result
