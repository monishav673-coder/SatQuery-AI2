"""
SATQUERY AI — PDF Report Generation Service
Generates a professional analysis report using ReportLab.
Falls back to a plain-text report if ReportLab is unavailable.
"""

import os
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

APP_NAME = "SATQUERY AI"
APP_SUBTITLE = "Satellite Intelligence Analysis Report"


def generate_pdf_report(analysis, result: dict, reports_folder: str) -> str:
    """
    Generate a PDF report for the given analysis.
    Returns the filename (relative to reports_folder).
    """
    os.makedirs(reports_folder, exist_ok=True)
    filename = f"SATQUERY_Report_{analysis.id[:8]}_{_timestamp()}.pdf"
    output_path = os.path.join(reports_folder, filename)

    try:
        _generate_with_reportlab(analysis, result, output_path)
    except ImportError:
        logger.warning("ReportLab not installed. Generating plain-text report.")
        txt_filename = filename.replace(".pdf", ".txt")
        output_path = os.path.join(reports_folder, txt_filename)
        _generate_plain_text(analysis, result, output_path)
        filename = txt_filename

    return filename


# ── ReportLab PDF ─────────────────────────────────────────────────────────────

def _generate_with_reportlab(analysis, result: dict, output_path: str):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, KeepTogether,
    )
    from reportlab.platypus import Image as RLImage

    W, H = A4
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2.5 * cm, bottomMargin=2 * cm,
        title=f"{APP_NAME} Analysis Report",
        author=APP_NAME,
    )

    styles = getSampleStyleSheet()
    # Custom styles
    DARK = colors.HexColor("#0a0e27")
    ACCENT = colors.HexColor("#00d4ff")
    LIGHT = colors.HexColor("#e0e8ff")

    title_style = ParagraphStyle(
        "SQTitle", parent=styles["Title"],
        fontSize=22, textColor=DARK, spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "SQSubtitle", parent=styles["Normal"],
        fontSize=11, textColor=colors.HexColor("#555577"), spaceAfter=12,
    )
    section_style = ParagraphStyle(
        "SQSection", parent=styles["Heading2"],
        fontSize=13, textColor=DARK, spaceBefore=16, spaceAfter=6,
        borderPad=4,
    )
    body_style = ParagraphStyle(
        "SQBody", parent=styles["Normal"],
        fontSize=10, leading=15, textColor=colors.HexColor("#222244"),
    )
    caption_style = ParagraphStyle(
        "SQCaption", parent=styles["Normal"],
        fontSize=8, textColor=colors.grey, spaceAfter=8,
    )

    story = []

    # ── Cover ──────────────────────────────────────────────────────────────
    story.append(Spacer(1, 1 * cm))
    story.append(Paragraph(APP_NAME, title_style))
    story.append(Paragraph(APP_SUBTITLE, subtitle_style))
    story.append(HRFlowable(width="100%", thickness=2, color=ACCENT))
    story.append(Spacer(1, 0.4 * cm))

    # ── 1. Analysis Summary ────────────────────────────────────────────────
    story.append(Paragraph("1. Analysis Summary", section_style))
    mode_label = {
        "single": "Single Image Analysis",
        "optical_sar": "Optical + SAR Analysis",
        "multitemporal": "Multitemporal Change Detection",
    }.get(analysis.mode, analysis.mode)

    summary_data = [
        ["Analysis ID", analysis.id],
        ["Mode", mode_label],
        ["Status", analysis.status.capitalize()],
        ["Overall AI Confidence", f"{result.get('overall_confidence', 'N/A')}/100"],
        ["Generated", datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")],
    ]
    story.append(_make_table(summary_data, styles))

    # ── 2. Input Information ───────────────────────────────────────────────
    story.append(Paragraph("2. Input Information", section_style))
    input_type = result.get("input_type", analysis.input_type)
    input_data = [["Input Type", input_type.replace("_", " ").title()]]

    loc = result.get("location", {})
    if loc.get("latitude") is not None:
        input_data.append(["Latitude", f"{loc['latitude']:.6f}"])
        input_data.append(["Longitude", f"{loc['longitude']:.6f}"])
    if loc.get("place_name"):
        input_data.append(["Location", loc["place_name"]])

    dates = result.get("dates", {})
    if dates.get("before"):
        input_data.append(["Before Date", dates["before"]])
    if dates.get("after"):
        input_data.append(["After Date", dates["after"]])
    if dates.get("observation"):
        input_data.append(["Observation Date", dates["observation"]])

    story.append(_make_table(input_data, styles))

    # ── 3. Data Source ─────────────────────────────────────────────────────
    story.append(Paragraph("3. Data Source & Model", section_style))
    ds = result.get("data_source", {})
    model = result.get("model_info", {})
    ds_data = [
        ["Data Provider", ds.get("provider", "User-uploaded image")],
        ["Satellite", ds.get("satellite", "Unknown")],
        ["Dataset", model.get("dataset", "BigEarthNet (reference)")],
        ["Model Note", model.get("note", "See documentation for model configuration.")],
    ]
    story.append(_make_table(ds_data, styles))

    # ── 4. Confidence ──────────────────────────────────────────────────────
    story.append(Paragraph("4. AI Confidence", section_style))
    conf = result.get("confidence", {})
    per_cat = conf.get("per_category", {})
    conf_data = [["Category", "Confidence"]]
    conf_data.append(["Overall", f"{result.get('overall_confidence', 'N/A')}/100"])
    for cat, val in per_cat.items():
        conf_data.append([cat, f"{val:.0f}/100"])
    story.append(_make_table(conf_data, styles, header=True))
    if conf.get("explanation"):
        story.append(Paragraph(conf["explanation"], body_style))

    # ── 5. Land Cover ──────────────────────────────────────────────────────
    lc = result.get("landcover", {})
    if lc:
        story.append(Paragraph("5. Land Cover Analysis", section_style))
        story.append(Paragraph(
            f"Method: {lc.get('method', 'N/A').replace('_', ' ').title()}  |  "
            f"Confidence: {lc.get('confidence', 'N/A'):.0f}/100",
            body_style,
        ))
        lc_classes = lc.get("classes", [])
        if lc_classes:
            lc_data = [["Class", "Coverage (%)", "Area (km²)", "Confidence", "Direction"]]
            for cls in lc_classes:
                lc_data.append([
                    cls.get("label", ""),
                    f"{cls.get('percentage', 'N/A')}",
                    f"{cls.get('area_km2', 'N/A')}",
                    f"{cls.get('confidence', 'N/A'):.0f}/100",
                    cls.get("direction", "N/A"),
                ])
            story.append(_make_table(lc_data, styles, header=True))
        for note in lc.get("notes", []):
            story.append(Paragraph(f"⚠ {note}", caption_style))

    # ── 6. Buildings ───────────────────────────────────────────────────────
    bld = result.get("buildings", {})
    if bld:
        story.append(Paragraph("6. Building Detection", section_style))
        if bld.get("limitation"):
            story.append(Paragraph(f"⚠ {bld['limitation']}", body_style))
        else:
            story.append(Paragraph(
                f"Detected buildings: {bld.get('building_count', 'N/A')}  |  "
                f"Confidence: {bld.get('confidence', 0):.0f}/100",
                body_style,
            ))

    # ── 7. Water Bodies ────────────────────────────────────────────────────
    water = result.get("water", {})
    if water:
        story.append(Paragraph("7. Water Body Analysis", section_style))
        w_data = [
            ["Water Bodies Detected", str(water.get("water_body_count", "N/A"))],
            ["Coverage", f"{water.get('water_coverage_pct', 'N/A')}%"],
            ["Area", f"{water.get('water_area_km2', 'N/A')} km²"],
            ["Locations", ", ".join(water.get("locations", [])) or "N/A"],
            ["Confidence", f"{water.get('confidence', 0):.0f}/100"],
        ]
        story.append(_make_table(w_data, styles))
        story.append(Paragraph(water.get("water_level_note", ""), caption_style))

    # ── 8. Agriculture ─────────────────────────────────────────────────────
    agri = result.get("agriculture", {})
    if agri:
        story.append(Paragraph("8. Agricultural Area", section_style))
        a_data = [
            ["Coverage", f"{agri.get('agriculture_pct', 'N/A')}%"],
            ["Area", f"{agri.get('agriculture_area_km2', 'N/A')} km²"],
            ["Confidence", f"{agri.get('confidence', 0):.0f}/100"],
        ]
        story.append(_make_table(a_data, styles))

    # ── 9. Change Detection ────────────────────────────────────────────────
    chg = result.get("change_detection")
    if chg:
        story.append(Paragraph("9. Change Detection", section_style))
        if chg.get("changes_detected"):
            story.append(Paragraph(
                f"Changes detected in {chg.get('overall_change_pct', 'N/A')}% of area.  "
                f"Confidence: {chg.get('confidence', 0):.0f}/100",
                body_style,
            ))
            chg_data = [["Change Type", "Area (km²)", "Direction", "Confidence"]]
            for c in chg.get("change_summary", []):
                chg_data.append([
                    c.get("type", ""),
                    str(c.get("area_km2", "N/A")),
                    c.get("direction", "N/A"),
                    f"{c.get('confidence', 0):.0f}/100",
                ])
            if len(chg_data) > 1:
                story.append(_make_table(chg_data, styles, header=True))
        else:
            story.append(Paragraph("No significant change reliably detected.", body_style))
        for note in chg.get("notes", []):
            story.append(Paragraph(f"⚠ {note}", caption_style))

    # ── 10. Natural Language Q&A ───────────────────────────────────────────
    if analysis.nl_query:
        story.append(Paragraph("10. Natural Language Query & Answer", section_style))
        story.append(Paragraph(f"<b>Question:</b> {analysis.nl_query}", body_style))
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph(
            f"<b>Answer:</b> {analysis.nl_answer or 'No answer generated.'}",
            body_style,
        ))

    # ── 11. Visual Evidence Overlays ───────────────────────────────────────
    evidence = result.get("evidence", {})
    overlays = evidence.get("overlays", {})
    if overlays:
        story.append(Paragraph("11. Visual Evidence & Overlays", section_style))
        story.append(Paragraph("Satellite feature overlays generated during pipeline processing:", caption_style))
        story.append(Spacer(1, 0.2 * cm))

        # Check for uploads folder to find local image paths
        try:
            from flask import current_app
            upload_dir = current_app.config.get("UPLOAD_FOLDER", "")
        except RuntimeError:
            upload_dir = os.path.join(os.path.dirname(__file__), "..", "uploads")

        for key, url in overlays.items():
            fname = os.path.basename(url)
            img_disk_path = os.path.join(upload_dir, fname)
            if os.path.exists(img_disk_path):
                try:
                    rl_img = RLImage(img_disk_path, width=7 * cm, height=5 * cm)
                    lbl_text = key.replace("_", " ").title() + " Overlay"
                    story.append(Paragraph(f"<b>{lbl_text}</b>", body_style))
                    story.append(Spacer(1, 0.1 * cm))
                    story.append(rl_img)
                    story.append(Spacer(1, 0.3 * cm))
                except Exception as img_err:
                    logger.debug("PDF image embed skipped for %s: %s", key, img_err)

    # ── 12. Limitations ────────────────────────────────────────────────────
    limitations = result.get("limitations", [])
    if limitations:
        story.append(Paragraph("12. Limitations & Disclaimers", section_style))
        for lim in limitations:
            story.append(Paragraph(f"• {lim}", body_style))

    # ── Footer note ────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.5 * cm))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey))
    story.append(Paragraph(
        "This report was generated automatically by SATQUERY AI. "
        "Results are based on the analysis methods described above. "
        "All confidence values are model-derived, not manually assigned. "
        "Consult domain experts for operational decisions.",
        caption_style,
    ))

    doc.build(story)


def _make_table(data: list, styles, header: bool = False):
    from reportlab.platypus import Table, TableStyle
    from reportlab.lib import colors

    DARK = colors.HexColor("#0a0e27")
    ACCENT = colors.HexColor("#00d4ff")
    STRIPE = colors.HexColor("#f0f4ff")

    col_widths = None
    if len(data[0]) == 2:
        col_widths = [5.5 * 28.35, 9 * 28.35]  # approx cm in points

    t = Table(data, colWidths=col_widths, repeatRows=1 if header else 0)
    ts = [
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, STRIPE]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (0, -1), DARK),
    ]
    if header:
        ts += [
            ("BACKGROUND", (0, 0), (-1, 0), DARK),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ]
    t.setStyle(TableStyle(ts))
    return t


# ── Plain text fallback ───────────────────────────────────────────────────────

def _generate_plain_text(analysis, result: dict, output_path: str):
    lines = [
        "=" * 70,
        f"  {APP_NAME}  —  {APP_SUBTITLE}",
        "=" * 70,
        "",
        f"Analysis ID   : {analysis.id}",
        f"Mode          : {analysis.mode}",
        f"Status        : {analysis.status}",
        f"Confidence    : {result.get('overall_confidence', 'N/A')}/100",
        f"Generated     : {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        "",
    ]

    loc = result.get("location", {})
    if loc.get("place_name"):
        lines.append(f"Location      : {loc['place_name']}")
    if loc.get("latitude") is not None:
        lines.append(f"Coordinates   : {loc['latitude']:.6f}, {loc['longitude']:.6f}")
    lines.append("")

    lc = result.get("landcover", {})
    if lc.get("classes"):
        lines.append("LAND COVER")
        lines.append("-" * 40)
        for c in lc["classes"]:
            lines.append(
                f"  {c['label']:<30} {c.get('percentage', 'N/A')}%  "
                f"Area: {c.get('area_km2', 'N/A')} km²  "
                f"Conf: {c.get('confidence', 'N/A')}"
            )
        lines.append("")

    water = result.get("water", {})
    if water.get("water_coverage_pct") is not None:
        lines.append("WATER BODIES")
        lines.append("-" * 40)
        lines.append(f"  Coverage: {water['water_coverage_pct']}%")
        lines.append(f"  Area: {water.get('water_area_km2', 'N/A')} km²")
        lines.append(f"  Locations: {', '.join(water.get('locations', []))}")
        lines.append("")

    agri = result.get("agriculture", {})
    if agri.get("agriculture_pct") is not None:
        lines.append("AGRICULTURE")
        lines.append("-" * 40)
        lines.append(f"  Coverage: {agri['agriculture_pct']}%")
        lines.append(f"  Area: {agri.get('agriculture_area_km2', 'N/A')} km²")
        lines.append("")

    chg = result.get("change_detection")
    if chg:
        lines.append("CHANGE DETECTION")
        lines.append("-" * 40)
        if chg.get("changes_detected"):
            lines.append(f"  Changes detected in {chg.get('overall_change_pct', 'N/A')}% of area.")
            for c in chg.get("change_summary", []):
                lines.append(f"  • {c['type']} — {c.get('area_km2', 'N/A')} km² — {c.get('direction', '')}")
        else:
            lines.append("  No significant change detected.")
        lines.append("")

    if analysis.nl_query:
        lines.append("NATURAL LANGUAGE Q&A")
        lines.append("-" * 40)
        lines.append(f"  Q: {analysis.nl_query}")
        lines.append(f"  A: {analysis.nl_answer or 'No answer generated.'}")
        lines.append("")

    limitations = result.get("limitations", [])
    if limitations:
        lines.append("LIMITATIONS")
        lines.append("-" * 40)
        for lim in limitations:
            lines.append(f"  • {lim}")
        lines.append("")

    lines += [
        "=" * 70,
        "Report generated by SATQUERY AI.",
        "Confidence values are model-derived, not manually assigned.",
        "=" * 70,
    ]

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _timestamp() -> str:
    return datetime.utcnow().strftime("%Y%m%d_%H%M%S")
