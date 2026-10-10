"""
knowledge_base.py - KNOWLEDGE REPRESENTATION + FACT MANAGEMENT
================================================================
This module answers the KRR question: "How do we store what we know?"

* A Fact is a predicate such as  marks(Artificial Intelligence, 40).
* A Subject is the student's input. It is converted into Facts.
* The KnowledgeBase holds the configurable thresholds (e.g. "low marks = below 50"),
  the study-time weights and the advice texts. Rules read these thresholds, so you
  can change the behaviour of the system without touching any rule code.
* Input validation lives here too, so bad data never reaches the reasoner.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any, NamedTuple, Optional

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------
PRIORITY_LEVELS = ("low", "medium", "high")           # ordered from weakest to strongest
PRIORITY_RANK = {"low": 1, "medium": 2, "high": 3}    # used to compare levels
DIFFICULTY_LEVELS = ("low", "medium", "high")

MAX_SUBJECTS = 20
MAX_DAYS_LEFT = 365
MAX_NAME_LENGTH = 60
MIN_DAILY_HOURS = 0.5
MAX_DAILY_HOURS = 16.0

# Thresholds used by the rules. Rules refer to them as "@name".
DEFAULT_THRESHOLDS: dict[str, Any] = {
    "low_marks": 50,          # below this = weak performance
    "medium_marks": 65,       # below this (but >= low_marks) = moderate performance
    "good_marks": 80,         # at or above this = strong performance
    "critical_days": 1,       # exam today or tomorrow
    "urgent_days": 3,         # exam within 3 days
    "soon_days": 7,           # exam within a week
    "low_confidence": 2,      # self-rated confidence (1-5) at or below this = shaky
    "default_priority": "medium",  # used by the default rule R7
}

THRESHOLD_DESCRIPTIONS = {
    "low_marks": "Marks below this value count as low performance",
    "medium_marks": "Marks below this value (but not low) count as moderate performance",
    "good_marks": "Marks at or above this value count as strong performance",
    "critical_days": "Exam this many days away or fewer is CRITICAL",
    "urgent_days": "Exam this many days away or fewer is URGENT",
    "soon_days": "Exam this many days away or fewer is SOON",
    "low_confidence": "Self-assessed confidence at or below this is shaky (scale 1-5)",
    "default_priority": "Priority given by the default rule R7 when nothing else applies",
}

# Weights used to share study time (higher priority = bigger share).
DEFAULT_WEIGHTS = {"high": 3.0, "medium": 2.0, "low": 1.0}

# Advice texts: this is "knowledge" too, stored as data and not buried in UI code.
DIFFICULTY_STRATEGIES = {
    "high": "Split the subject into small topics and learn one concept at a time. "
            "Use several short sessions instead of one long cram, and test yourself on practice problems.",
    "medium": "Alternate between reading your notes and solving past questions. "
              "Write a one-page summary for every chapter.",
    "low": "Use quick active recall (flashcards or short self-quizzes) to keep the material fresh. "
           "Avoid over-studying this subject.",
}
PERFORMANCE_ADVICE = {
    "weak": "Your marks show gaps in understanding. Go back to the basics and fix the weakest topics first.",
    "moderate": "You know the basics. Practise exam-style questions to turn average marks into good marks.",
    "good": "You are doing well. Revise regularly and practise a few harder questions.",
    "strong": "Your marks are strong. A light weekly revision is enough to keep them there.",
}
URGENCY_ADVICE = {
    "critical": "Do not start new topics. Revise key formulas, definitions and past-paper answers only.",
    "urgent": "Focus on the highest-value topics and solve past papers under timed conditions.",
    "soon": "Build a topic checklist and finish a first full revision before the final days.",
    "comfortable": "You have time. Learn steadily and leave the last week for revision.",
}
URGENCY_WARNINGS = {
    "critical": "CRITICAL: the exam is {when}. Use all available time on this subject.",
    "urgent": "URGENT: the exam is in {days} days. Start intensive revision now.",
    "soon": "Heads up: the exam is in {days} days. Begin structured revision this week.",
    "comfortable": "",
}


# --------------------------------------------------------------------------
# Facts
# --------------------------------------------------------------------------
class Fact(NamedTuple):
    """One piece of knowledge written as predicate(subject, value)."""
    predicate: str
    subject: str
    value: Any

    def __str__(self) -> str:
        return f"{self.predicate}({self.subject}, {self.value})"


@dataclass(frozen=True)
class Subject:
    """A validated subject entered by the student."""
    name: str
    marks: float
    days_left: int
    difficulty: str
    confidence: Optional[int] = None


def _clean_number(value: float):
    """Show 40.0 as 40 so facts read nicely: marks(AI, 40)."""
    return int(value) if float(value).is_integer() else float(value)


# --------------------------------------------------------------------------
# Validation helpers
# --------------------------------------------------------------------------
def _is_blank(value: Any) -> bool:
    """True for None, empty text, NaN and pandas NA."""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    try:
        return bool(value != value)      # NaN is not equal to itself
    except TypeError:                    # pandas.NA cannot be turned into bool
        return True


def _to_number(value: Any) -> float:
    """Convert to a finite float or raise ValueError."""
    if isinstance(value, bool):
        raise ValueError("not a number")
    if isinstance(value, str):
        value = value.strip().rstrip("%").strip()
    number = float(value)
    if math.isnan(number) or math.isinf(number):
        raise ValueError("not a finite number")
    return number


def normalise_name(name: Any) -> str:
    """Trim and collapse repeated spaces."""
    return re.sub(r"\s+", " ", str(name)).strip()


def parse_subject(name, marks, days_left, difficulty, confidence=None, label: str = "Subject"):
    """Validate one subject. Returns (Subject or None, list_of_error_messages)."""
    errors: list[str] = []

    # --- name
    clean_name = "" if _is_blank(name) else normalise_name(name)
    if not clean_name:
        errors.append(f"{label}: the subject name is required.")
    elif len(clean_name) > MAX_NAME_LENGTH:
        errors.append(f"{label}: the name is longer than {MAX_NAME_LENGTH} characters.")
    elif not re.fullmatch(r"\w[\w .,&()'/+:\-]*", clean_name):
        errors.append(f"{label}: '{clean_name}' contains characters that are not allowed.")

    # --- marks
    marks_value = None
    if _is_blank(marks):
        errors.append(f"{label}: marks are required.")
    else:
        try:
            marks_value = _to_number(marks)
            if not 0 <= marks_value <= 100:
                errors.append(f"{label}: marks must be between 0 and 100 (got {marks_value:g}).")
                marks_value = None
        except (ValueError, TypeError):
            errors.append(f"{label}: marks must be a number between 0 and 100.")

    # --- days left
    days_value = None
    if _is_blank(days_left):
        errors.append(f"{label}: days left until the exam is required.")
    else:
        try:
            number = _to_number(days_left)
            if not number.is_integer():
                errors.append(f"{label}: days left must be a whole number.")
            elif number < 0:
                errors.append(f"{label}: days left cannot be negative.")
            elif number > MAX_DAYS_LEFT:
                errors.append(f"{label}: days left cannot be more than {MAX_DAYS_LEFT}.")
            else:
                days_value = int(number)
        except (ValueError, TypeError):
            errors.append(f"{label}: days left must be a whole number.")

    # --- difficulty
    difficulty_value = None if _is_blank(difficulty) else str(difficulty).strip().lower()
    if difficulty_value not in DIFFICULTY_LEVELS:
        errors.append(f"{label}: difficulty must be Low, Medium or High.")
        difficulty_value = None

    # --- optional confidence (1-5)
    confidence_value = None
    if not _is_blank(confidence):
        try:
            number = _to_number(confidence)
            if number.is_integer() and 1 <= number <= 5:
                confidence_value = int(number)
            else:
                errors.append(f"{label}: confidence must be a whole number from 1 to 5.")
        except (ValueError, TypeError):
            errors.append(f"{label}: confidence must be a whole number from 1 to 5.")

    if errors:
        return None, errors
    return Subject(clean_name, _clean_number(marks_value), days_value,
                   difficulty_value, confidence_value), []


def validate_subject_list(rows: list[dict]):
    """Validate a list of row dicts (keys: name, marks, days_left, difficulty, confidence).

    Completely blank rows are ignored. Returns (subjects, errors).
    """
    subjects: list[Subject] = []
    errors: list[str] = []
    seen: dict[str, int] = {}
    for index, row in enumerate(rows, start=1):
        if all(_is_blank(row.get(k)) for k in ("name", "marks", "days_left")):
            continue                                   # empty row added by accident
        subject, row_errors = parse_subject(
            row.get("name"), row.get("marks"), row.get("days_left"),
            row.get("difficulty"), row.get("confidence"), label=f"Row {index}")
        if row_errors:
            errors.extend(row_errors)
            continue
        key = subject.name.casefold()
        if key in seen:
            errors.append(f"Row {index}: duplicate subject name '{subject.name}' (same as row {seen[key]}).")
            continue
        seen[key] = index
        subjects.append(subject)
    if len(subjects) > MAX_SUBJECTS:
        errors.append(f"Please enter at most {MAX_SUBJECTS} subjects.")
    return subjects, errors


def validate_daily_hours(value):
    """Validate daily study hours. Returns (float or None, list_of_error_messages)."""
    if _is_blank(value):
        return None, ["Daily study hours are required."]
    try:
        hours = _to_number(value)
    except (ValueError, TypeError):
        return None, ["Daily study hours must be a number."]
    if hours < MIN_DAILY_HOURS or hours > MAX_DAILY_HOURS:
        return None, [f"Daily study hours must be between {MIN_DAILY_HOURS:g} and {MAX_DAILY_HOURS:g}."]
    return hours, []


# --------------------------------------------------------------------------
# The knowledge base
# --------------------------------------------------------------------------
class KnowledgeBase:
    """Stores thresholds and weights, and turns subjects into facts."""

    def __init__(self, thresholds: Optional[dict] = None, weights: Optional[dict] = None):
        self.thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
        self.weights = {**DEFAULT_WEIGHTS, **(weights or {})}
        errors = self.validate()
        if errors:
            raise ValueError(" ".join(errors))

    def validate(self) -> list[str]:
        """Check that thresholds make sense together."""
        t, errors = self.thresholds, []
        for key in DEFAULT_THRESHOLDS:
            if key not in t:
                errors.append(f"Missing threshold '{key}'.")
        if errors:
            return errors
        try:
            if not 0 <= t["low_marks"] < t["medium_marks"] <= t["good_marks"] <= 100:
                errors.append("Marks thresholds must satisfy 0 <= low < medium <= good <= 100.")
            if not 0 <= t["critical_days"] <= t["urgent_days"] <= t["soon_days"]:
                errors.append("Day thresholds must satisfy 0 <= critical <= urgent <= soon.")
            if not 1 <= t["low_confidence"] <= 5:
                errors.append("The low-confidence threshold must be between 1 and 5.")
        except TypeError:
            errors.append("Thresholds must be numbers.")
        if t["default_priority"] not in PRIORITY_LEVELS:
            errors.append("The default priority must be low, medium or high.")
        for level in PRIORITY_LEVELS:
            weight = self.weights.get(level)
            if not isinstance(weight, (int, float)) or weight < 0:
                errors.append(f"The weight for '{level}' priority must be a number >= 0.")
        return errors

    def resolve(self, value: Any) -> Any:
        """Turn '@low_marks' into its number. Other values are returned unchanged."""
        if isinstance(value, str) and value.startswith("@"):
            key = value[1:]
            if key not in self.thresholds:
                raise ValueError(f"Unknown threshold '{key}'.")
            return self.thresholds[key]
        return value

    def facts_for(self, subject: Subject) -> list[Fact]:
        """Convert a subject into facts: marks(S, v), days_left(S, v), ..."""
        facts = [
            Fact("marks", subject.name, subject.marks),
            Fact("days_left", subject.name, subject.days_left),
            Fact("difficulty", subject.name, subject.difficulty),
        ]
        if subject.confidence is not None:
            facts.append(Fact("confidence", subject.name, subject.confidence))
        return facts

    def performance_band(self, marks: float) -> str:
        """weak / moderate / good / strong, based on thresholds."""
        t = self.thresholds
        if marks < t["low_marks"]:
            return "weak"
        if marks < t["medium_marks"]:
            return "moderate"
        if marks < t["good_marks"]:
            return "good"
        return "strong"

    def to_dict(self) -> dict:
        return {"thresholds": dict(self.thresholds), "weights": dict(self.weights)}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, text: str) -> "KnowledgeBase":
        data = json.loads(text)
        return cls(data.get("thresholds"), data.get("weights"))


# --------------------------------------------------------------------------
# Sample data (clearly labelled as demonstration data in the UI)
# --------------------------------------------------------------------------
SAMPLE_SUBJECTS = [
    {"name": "Artificial Intelligence", "marks": 40, "days_left": 2, "difficulty": "high", "confidence": 2},
    {"name": "Database Systems", "marks": 72, "days_left": 10, "difficulty": "medium", "confidence": 3},
    {"name": "Statistics", "marks": 55, "days_left": 6, "difficulty": "medium", "confidence": 3},
    {"name": "Operating Systems", "marks": 62, "days_left": 4, "difficulty": "high", "confidence": 4},
    {"name": "English Communication", "marks": 88, "days_left": 14, "difficulty": "low", "confidence": 5},
]
