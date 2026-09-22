"""
SATQUERY AI — Confidence Estimation Agent
Aggregates confidence scores from all agents into an overall confidence value.
Confidence is data-driven, not random.
"""

from typing import Optional


def run(
    pre_result: Optional[dict] = None,
    landcover_result: Optional[dict] = None,
    building_result: Optional[dict] = None,
    water_result: Optional[dict] = None,
    agriculture_result: Optional[dict] = None,
    change_result: Optional[dict] = None,
    mode: str = "single",
    input_type: str = "image",
) -> dict:
    """
    Returns:
        overall_confidence  : float  — 0-100
        per_category        : dict   — confidence per analysis category
        factors             : list[str]  — factors influencing confidence
        explanation         : str
    """

    factors = []
    weights = {}
    scores = {}

    # ── Image quality ─────────────────────────────────────────────────────
    quality_score = 50.0
    if pre_result:
        quality_score = pre_result.get("quality_score", 50.0)
        if quality_score < 30:
            factors.append("Low image quality reduces overall confidence.")
        elif quality_score > 75:
            factors.append("Good image quality supports higher confidence.")

        if pre_result.get("has_georeference"):
            quality_score = min(100, quality_score + 10)
            factors.append("Georeferenced image enables accurate area calculations.")
        else:
            quality_score = max(0, quality_score - 10)
            factors.append("Image lacks georeferencing; area calculations unavailable.")

        cloud_cov = pre_result.get("cloud_coverage")
        if cloud_cov is not None:
            if cloud_cov > 50:
                quality_score *= 0.7
                factors.append(f"High cloud coverage ({cloud_cov:.0f}%) significantly reduces confidence.")
            elif cloud_cov > 20:
                quality_score *= 0.9
                factors.append(f"Moderate cloud coverage ({cloud_cov:.0f}%) slightly reduces confidence.")

    # ── Coordinate-only ───────────────────────────────────────────────────
    if input_type == "coordinates":
        quality_score = min(quality_score, 40.0)
        factors.append("Coordinate-based analysis without a connected imagery API limits confidence.")

    # ── Per-agent scores ──────────────────────────────────────────────────
    scores["Image Quality"] = quality_score

    if landcover_result:
        lc_conf = landcover_result.get("confidence", 0.0)
        scores["Land Cover"] = lc_conf
        weights["Land Cover"] = 3
        if landcover_result.get("method") == "spectral_heuristic":
            factors.append("Land cover uses spectral heuristics — accuracy limited without trained model.")
        elif landcover_result.get("method") == "model":
            factors.append("Land cover classification from trained model.")

    if building_result:
        b_conf = building_result.get("confidence", 0.0)
        scores["Buildings"] = b_conf
        weights["Buildings"] = 2
        if building_result.get("limitation"):
            factors.append(f"Buildings: {building_result['limitation']}")

    if water_result:
        w_conf = water_result.get("confidence", 0.0)
        scores["Water Bodies"] = w_conf
        weights["Water Bodies"] = 2
        if water_result.get("method") == "brightness_heuristic":
            factors.append("Water detection uses brightness heuristics — NIR band improves accuracy.")

    if agriculture_result:
        a_conf = agriculture_result.get("confidence", 0.0)
        scores["Agriculture"] = a_conf
        weights["Agriculture"] = 2

    if change_result and mode == "multitemporal":
        c_conf = change_result.get("confidence", 0.0)
        scores["Change Detection"] = c_conf
        weights["Change Detection"] = 3
        if change_result.get("method") == "image_differencing":
            factors.append("Change detection uses image differencing — semantic model improves results.")

    # ── Weighted average ──────────────────────────────────────────────────
    base_weight = 1
    total_weight = base_weight
    weighted_sum = quality_score * base_weight

    for category, conf in scores.items():
        if category == "Image Quality":
            continue
        w = weights.get(category, 1)
        weighted_sum += conf * w
        total_weight += w

    overall = round(weighted_sum / total_weight, 1) if total_weight > 0 else 0.0
    overall = max(0.0, min(100.0, overall))

    explanation = _build_explanation(overall, factors, mode, input_type)

    return {
        "overall_confidence": overall,
        "per_category": scores,
        "factors": factors,
        "explanation": explanation,
    }


def _build_explanation(score: float, factors: list, mode: str, input_type: str) -> str:
    if score >= 80:
        level = "high"
    elif score >= 60:
        level = "moderate"
    elif score >= 40:
        level = "low"
    else:
        level = "very low"

    lines = [
        f"Overall AI confidence is {score:.0f}/100 ({level}).",
        f"Analysis mode: {mode.replace('_', ' ').title()}.",
        f"Input type: {input_type}.",
    ]
    if factors:
        lines.append("Key factors:")
        for f in factors[:5]:
            lines.append(f"  • {f}")
    if score < 60:
        lines.append(
            "Confidence can be improved by: supplying a georeferenced multispectral image, "
            "configuring a trained analysis model, or connecting a satellite imagery API."
        )
    return " ".join(lines)
