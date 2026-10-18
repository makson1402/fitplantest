"""Report export to CSV and PDF (B-25; FR-R6). Both files are built from the stored report, so they show exactly the
figures that `GET /reports/{id}` returns."""
from __future__ import annotations

import csv
import io

from fpdf import FPDF

from app.schemas.reports import Report

# (key, label shown in the PDF); the CSV uses the keys. Null values stay empty in the CSV and read "n/a" in the PDF.
SUMMARY_FIELDS = [
    ("report_type", "Report type"), ("period_start", "From"), ("period_end", "To"),
    ("weight_difference_kg", "Weight change (kg)"), ("training_volume_kg", "Training volume (kg)"),
    ("training_sessions_completed", "Workouts completed"), ("training_sessions_planned", "Workouts planned"),
    ("workout_compliance_pct", "Workout compliance (%)"), ("diet_compliance_pct", "Diet compliance (%)"),
    ("avg_daily_calories", "Average daily calories (kcal)"),
    ("estimated_goal_completion_date", "Estimated goal date"), ("irregular_data", "Irregular data"),
    ("is_auto", "Generated automatically"), ("generated_at", "Generated at"),
]
SERIES = [("weight", "Weight (kg)"), ("tonnage", "Tonnage per day (kg)"), ("calories", "Calories per day (kcal)"),
          ("workouts_per_week", "Workouts per week")]

CSV_COLUMNS = ["section", "key", "value"]


def _text(value) -> str:
    """The value as the API shows it: ISO dates, true/false, no exponent."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if hasattr(value, "isoformat"):
        return value.isoformat().replace("+00:00", "Z")  # the same spelling as the JSON answer
    return str(value)


def _fields(report: Report) -> list[tuple[str, str, object]]:
    return [(key, label, getattr(report, key)) for key, label in SUMMARY_FIELDS]


def to_csv(report: Report) -> bytes:
    """Rows `section,key,value`: `summary` rows hold the figures of the report; one section per chart series (key =
    date) and `key_lift_first_e1rm_kg` / `key_lift_best_e1rm_kg` (key = exercise name)."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(CSV_COLUMNS)
    for key, _, value in _fields(report):
        writer.writerow(["summary", key, _text(value)])
    charts = report.details.get("charts", {})
    for name, _ in SERIES:
        for point in charts.get(name, []):
            writer.writerow([name, point["date"], _text(point["value"])])
    for lift in report.details.get("key_lifts", []):
        writer.writerow(["key_lift_first_e1rm_kg", lift["exercise_name"], _text(lift["first_e1rm_kg"])])
        writer.writerow(["key_lift_best_e1rm_kg", lift["exercise_name"], _text(lift["best_e1rm_kg"])])
    prediction = report.details.get("goal_prediction") or {}
    for key in ("status", "slope_kg_per_week", "r2", "target_weight_kg"):
        writer.writerow(["goal_prediction", key, _text(prediction.get(key))])
    writer.writerow(["goal_prediction", "warnings", ";".join(prediction.get("warnings", []))])
    return ("﻿" + out.getvalue()).encode("utf-8")  # BOM: Excel opens it as UTF-8


def _latin1(text: str) -> str:
    """The built-in PDF fonts cover Latin-1 only; other characters become '?' instead of failing the export."""
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _line(pdf: FPDF, text: str, height: float = 6) -> None:
    pdf.cell(0, height, _latin1(text), new_x="LMARGIN", new_y="NEXT")


def _heading(pdf: FPDF, text: str) -> None:
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 12)
    _line(pdf, text, 8)
    pdf.set_font("Helvetica", "", 10)


def to_pdf(report: Report) -> bytes:
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    _line(pdf, "FitPlan Pro - progress report", 12)
    pdf.set_font("Helvetica", "", 11)
    _line(pdf, f"{report.period_start.isoformat()} to {report.period_end.isoformat()} ({report.report_type})", 7)
    pdf.ln(3)
    for _, label, value in _fields(report):
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(80, 6, _latin1(label))
        pdf.set_font("Helvetica", "", 10)
        _line(pdf, _text(value) or "n/a")

    lifts = report.details.get("key_lifts", [])
    if lifts:
        _heading(pdf, "Strength in key exercises (estimated 1RM, kg)")
        for lift in lifts:
            _line(pdf, f"{lift['exercise_name']}: first {_text(lift['first_e1rm_kg'])}, "
                       f"best {_text(lift['best_e1rm_kg'])}")

    charts = report.details.get("charts", {})
    for name, title in SERIES:
        points = charts.get(name, [])
        if points:
            _heading(pdf, title)
            for point in points:
                _line(pdf, f"{point['date']}: {_text(point['value'])}", 5)

    prediction = report.details.get("goal_prediction") or {}
    if prediction:
        _heading(pdf, "Goal prediction")
        warnings = ", ".join(prediction.get("warnings", [])) or "none"
        _line(pdf, f"Status: {prediction.get('status')}; warnings: {warnings}")
    return bytes(pdf.output())
