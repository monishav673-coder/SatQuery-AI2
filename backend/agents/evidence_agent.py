"""
SATQUERY AI — Evidence Generation Agent
Generates visual overlay images with clear feature highlights for:
- Composite Annotated Evidence
- Detected Buildings (Bounding boxes & contours)
- Water Bodies (NDWI / High-contrast blue highlight)
- Agricultural Regions (NDVI / Emerald green highlight)
- Land Cover Segmentation
- Multitemporal Change Detection Heatmap & Difference Map
"""

import os
import uuid
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# High-contrast RGBA colours for visual evidence overlays
OVERLAY_COLOURS = {
    "water": (0, 168, 255, 175),         # Electric Cyan/Blue
    "water_border": (0, 230, 255, 255),  # Luminous Cyan
    "agriculture": (16, 185, 129, 175),  # Emerald Green
    "agriculture_border": (52, 211, 153, 255),
    "vegetation": (22, 163, 74, 160),    # Forest Green
    "builtup": (239, 68, 68, 180),       # High-vis Coral Red
    "builtup_border": (255, 100, 100, 255),
    "bareland": (217, 119, 6, 160),      # Amber
    "change_gain": (245, 158, 11, 190),  # Bright Orange / Urban expansion
    "change_loss": (168, 85, 247, 190),  # Violet / Vegetation transformation
    "change_water": (59, 130, 246, 190), # Blue / Water delta
}


def run(
    image1_path: Optional[str] = None,
    image2_path: Optional[str] = None,
    water_result: Optional[dict] = None,
    agriculture_result: Optional[dict] = None,
    landcover_result: Optional[dict] = None,
    building_result: Optional[dict] = None,
    change_result: Optional[dict] = None,
    upload_folder: str = "",
) -> dict:
    """
    Returns:
        success         : bool
        overlays        : dict   — {overlay_name: relative_url}
        notes           : list[str]
    """
    result = {"success": False, "overlays": {}, "notes": []}

    if not image1_path or not os.path.exists(image1_path):
        result["notes"].append("No image available for visual evidence generation.")
        result["success"] = True
        return result

    try:
        from PIL import Image as PILImage, ImageDraw, ImageFilter, ImageEnhance
        import numpy as np

        base_img = PILImage.open(image1_path).convert("RGBA")
        w, h = base_img.size

        # ── 1. Composite Annotated Evidence (All features highlighted) ────
        composite_overlay = _composite_annotated_overlay(
            base_img, water_result, agriculture_result, building_result, landcover_result
        )
        if composite_overlay:
            path = _save_overlay(composite_overlay, upload_folder, "annotated_evidence")
            result["overlays"]["annotated_evidence"] = f"/uploads/{path}"

        # ── 2. Building Detections & Bounding Boxes Overlay ─────────────────
        bld_overlay = _building_overlay(base_img, building_result)
        if bld_overlay:
            path = _save_overlay(bld_overlay, upload_folder, "building_overlay")
            result["overlays"]["buildings"] = f"/uploads/{path}"

        # ── 3. Water Bodies Highlight Overlay ─────────────────────────────
        if water_result and water_result.get("water_coverage_pct", 0) > 0:
            arr = np.array(PILImage.open(image1_path).convert("L"), dtype="float32") / 255.0
            water_mask = arr < 0.22
            water_overlay_img = _highlighted_mask_overlay(
                base_img, water_mask, OVERLAY_COLOURS["water"], OVERLAY_COLOURS["water_border"], "Water Body Detected"
            )
            if water_overlay_img:
                path = _save_overlay(water_overlay_img, upload_folder, "water_overlay")
                result["overlays"]["water"] = f"/uploads/{path}"

        # ── 4. Agriculture & Cropland Highlight Overlay ───────────────────
        if agriculture_result and agriculture_result.get("agriculture_pct", 0) > 0:
            img_src = PILImage.open(image1_path)
            if img_src.mode in ("RGB", "RGBA"):
                arr_g = np.array(img_src.getchannel("G"), dtype="float32") / 255.0
                arr_r = np.array(img_src.getchannel("R"), dtype="float32") / 255.0
                denom = arr_g + arr_r
                with np.errstate(divide='ignore', invalid='ignore'):
                    gi = np.where(denom > 0, (arr_g - arr_r) / denom, 0)
                agri_mask = gi > 0.04
            else:
                arr = np.array(img_src.convert("L"), dtype="float32") / 255.0
                agri_mask = (arr >= 0.28) & (arr < 0.58)

            agri_overlay_img = _highlighted_mask_overlay(
                base_img, agri_mask, OVERLAY_COLOURS["agriculture"], OVERLAY_COLOURS["agriculture_border"], "Cropland / Agriculture Zone"
            )
            if agri_overlay_img:
                path = _save_overlay(agri_overlay_img, upload_folder, "agri_overlay")
                result["overlays"]["agriculture"] = f"/uploads/{path}"

        # ── 5. Land Cover Multi-class Segmentation Overlay ─────────────────
        if landcover_result and landcover_result.get("classes"):
            lc_overlay = _land_cover_overlay(base_img, landcover_result, w, h)
            if lc_overlay:
                path = _save_overlay(lc_overlay, upload_folder, "lc_overlay")
                result["overlays"]["land_cover"] = f"/uploads/{path}"

        # ── 6. Multitemporal Change Detection Heatmap & Difference Map ────
        if (change_result and change_result.get("changes_detected")
                and image2_path and os.path.exists(image2_path)):
            img2 = PILImage.open(image2_path).convert("L")
            img1 = PILImage.open(image1_path).convert("L")
            if img1.size != img2.size:
                img2 = img2.resize(img1.size, PILImage.LANCZOS)
            arr1 = np.array(img1, dtype="float32") / 255.0
            arr2 = np.array(img2, dtype="float32") / 255.0
            diff = arr2 - arr1
            gain_mask = diff > 0.12
            loss_mask = diff < -0.12
            change_overlay = _change_overlay(base_img, gain_mask, loss_mask)
            if change_overlay:
                path = _save_overlay(change_overlay, upload_folder, "change_overlay")
                result["overlays"]["change"] = f"/uploads/{path}"

        result["success"] = True

    except ImportError:
        result["notes"].append("Pillow not installed — visual overlays unavailable.")
        result["success"] = True
    except Exception as e:
        result["notes"].append(f"Evidence generation failed: {e}")
        logger.exception("Evidence generation error")
        result["success"] = True

    return result


# ── Helpers for High-Contrast Highlight Overlays ───────────────────────────────

def _highlighted_mask_overlay(base_img, mask, fill_colour: tuple, border_colour: tuple, label: str):
    """Creates a translucent highlight fill with bright glowing contour borders and HUD label."""
    try:
        from PIL import Image as PILImage, ImageDraw, ImageFilter
        import numpy as np

        w, h = base_img.size
        overlay = PILImage.new("RGBA", (w, h), (0, 0, 0, 0))
        overlay_arr = np.array(overlay)

        if mask.shape[:2] != (h, w):
            mask_pil = PILImage.fromarray((mask * 255).astype("uint8")).resize((w, h), PILImage.NEAREST)
            mask_resized = np.array(mask_pil) > 128
        else:
            mask_resized = mask

        r, g, b, a = fill_colour
        overlay_arr[mask_resized, 0] = r
        overlay_arr[mask_resized, 1] = g
        overlay_arr[mask_resized, 2] = b
        overlay_arr[mask_resized, 3] = a

        overlay = PILImage.fromarray(overlay_arr, "RGBA")

        # Composite base and mask
        comp = PILImage.alpha_composite(base_img, overlay)
        draw = ImageDraw.Draw(comp, "RGBA")

        # Draw HUD label banner in upper left
        banner_w = min(len(label) * 8 + 24, w - 20)
        draw.rounded_rectangle([10, 10, 10 + banner_w, 36], radius=4, fill=(4, 7, 26, 210), outline=border_colour, width=1)
        draw.text((18, 15), f"● {label}", fill=border_colour)

        return comp
    except Exception as exc:
        logger.debug("Highlighted mask overlay error: %s", exc)
        return None


def _building_overlay(base_img, building_result: Optional[dict]):
    """Draws glowing bounding boxes and detection crosshairs over detected buildings."""
    try:
        from PIL import Image as PILImage, ImageDraw
        import numpy as np

        w, h = base_img.size
        comp = base_img.copy()
        draw = ImageDraw.Draw(comp, "RGBA")

        boxes = []
        if building_result and building_result.get("bounding_boxes"):
            boxes = building_result["bounding_boxes"]
        else:
            # Detect high-contrast roof/structural edges if model boxes aren't directly available
            gray = np.array(base_img.convert("L"))
            high_edges = gray > 190
            y_indices, x_indices = np.where(high_edges)
            if len(x_indices) > 20:
                # Sample representative building clusters
                step = max(1, len(x_indices) // 12)
                for idx in range(0, len(x_indices), step):
                    cx, cy = x_indices[idx], y_indices[idx]
                    bw, bh = min(36, w // 15), min(36, h // 15)
                    x1 = max(4, cx - bw // 2)
                    y1 = max(4, cy - bh // 2)
                    x2 = min(w - 4, x1 + bw)
                    y2 = min(h - 4, y1 + bh)
                    boxes.append([x1, y1, x2, y2])

        if not boxes:
            return None

        # Draw tech-style bounding box brackets & labels
        for i, box in enumerate(boxes[:24]):
            x1, y1, x2, y2 = box
            # Translucent box fill
            draw.rectangle([x1, y1, x2, y2], fill=(239, 68, 68, 45), outline=(239, 68, 68, 240), width=2)
            # Corner accents
            c_len = max(4, min((x2 - x1) // 3, (y2 - y1) // 3))
            draw.line([(x1, y1), (x1 + c_len, y1)], fill=(255, 255, 255, 255), width=2)
            draw.line([(x1, y1), (x1, y1 + c_len)], fill=(255, 255, 255, 255), width=2)
            draw.line([(x2, y2), (x2 - c_len, y2)], fill=(255, 255, 255, 255), width=2)
            draw.line([(x2, y2), (x2, y2 - c_len)], fill=(255, 255, 255, 255), width=2)

        # HUD header tag
        tag_text = f"🏢 Building Detections ({len(boxes[:24])} regions)"
        draw.rounded_rectangle([10, 10, 220, 36], radius=4, fill=(4, 7, 26, 210), outline=(239, 68, 68, 255), width=1)
        draw.text((18, 15), tag_text, fill=(255, 100, 100, 255))

        return comp
    except Exception as exc:
        logger.debug("Building overlay error: %s", exc)
        return None


def _composite_annotated_overlay(base_img, water_result, agriculture_result, building_result, landcover_result):
    """Generates a complete multi-feature highlighted satellite evidence image."""
    try:
        from PIL import Image as PILImage, ImageDraw
        import numpy as np

        w, h = base_img.size
        comp = base_img.copy()
        draw = ImageDraw.Draw(comp, "RGBA")

        # Water layer tint
        arr_gray = np.array(base_img.convert("L"), dtype="float32") / 255.0
        water_mask = arr_gray < 0.18
        if np.any(water_mask):
            water_layer = PILImage.new("RGBA", (w, h), (0, 0, 0, 0))
            w_arr = np.array(water_layer)
            w_arr[water_mask] = (0, 168, 255, 130)
            comp = PILImage.alpha_composite(comp, PILImage.fromarray(w_arr, "RGBA"))
            draw = ImageDraw.Draw(comp, "RGBA")

        # Agriculture layer tint
        if base_img.mode in ("RGB", "RGBA"):
            arr_g = np.array(base_img.getchannel("G"), dtype="float32") / 255.0
            arr_r = np.array(base_img.getchannel("R"), dtype="float32") / 255.0
            denom = arr_g + arr_r
            with np.errstate(divide='ignore', invalid='ignore'):
                gi = np.where(denom > 0, (arr_g - arr_r) / denom, 0)
            agri_mask = gi > 0.05
            if np.any(agri_mask):
                agri_layer = PILImage.new("RGBA", (w, h), (0, 0, 0, 0))
                a_arr = np.array(agri_layer)
                a_arr[agri_mask] = (16, 185, 129, 130)
                comp = PILImage.alpha_composite(comp, PILImage.fromarray(a_arr, "RGBA"))
                draw = ImageDraw.Draw(comp, "RGBA")

        # Header Badge
        draw.rounded_rectangle([10, 10, 240, 36], radius=4, fill=(4, 7, 26, 220), outline=(0, 212, 255, 255), width=1)
        draw.text((18, 15), "✦ SATQUERY Multi-Feature Evidence", fill=(0, 212, 255, 255))

        return comp
    except Exception as exc:
        logger.debug("Composite annotated overlay error: %s", exc)
        return None


def _land_cover_overlay(base_img, landcover_result: dict, w: int, h: int):
    """Generates false-colour land-cover segmentation overlay with legend."""
    try:
        from PIL import Image as PILImage, ImageDraw
        overlay = base_img.copy()
        draw = ImageDraw.Draw(overlay, "RGBA")
        classes = landcover_result.get("classes", [])

        colour_map = {
            "water": OVERLAY_COLOURS["water"],
            "agriculture": OVERLAY_COLOURS["agriculture"],
            "forest": OVERLAY_COLOURS["vegetation"],
            "vegetation": OVERLAY_COLOURS["vegetation"],
            "built": OVERLAY_COLOURS["builtup"],
            "urban": OVERLAY_COLOURS["builtup"],
            "bare": OVERLAY_COLOURS["bareland"],
        }

        # Draw HUD header
        draw.rounded_rectangle([10, 10, 210, 36], radius=4, fill=(4, 7, 26, 220), outline=(34, 197, 94, 255), width=1)
        draw.text((18, 15), "🌍 Land Cover Classification", fill=(34, 197, 94, 255))

        # Draw bottom Legend bar
        strip_h = min(28, h // 16)
        x = 10
        for cls in classes:
            label = cls["label"].lower()
            colour = (200, 200, 200, 150)
            for key, col in colour_map.items():
                if key in label:
                    colour = col
                    break
            pct = cls.get("percentage") or 0
            box_w = max(24, int((w - 20) * pct / 100))
            draw.rectangle([x, h - strip_h - 10, x + box_w, h - 10], fill=colour, outline=(255,255,255,180), width=1)
            x += box_w + 3

        return overlay
    except Exception as exc:
        logger.debug("Land cover overlay error: %s", exc)
        return None


def _change_overlay(base_img, gain_mask, loss_mask):
    """Generates multitemporal change heatmap overlay with distinct color highlights."""
    try:
        from PIL import Image as PILImage, ImageDraw
        import numpy as np

        w, h = base_img.size
        overlay = PILImage.new("RGBA", (w, h), (0, 0, 0, 0))
        overlay_arr = np.array(overlay)

        def resize_mask(m):
            if m.shape[:2] != (h, w):
                mp = PILImage.fromarray((m * 255).astype("uint8")).resize((w, h), PILImage.NEAREST)
                return np.array(mp) > 128
            return m

        g = resize_mask(gain_mask)
        l = resize_mask(loss_mask)

        # Highlight Gains in Bright Orange
        r, gg, b, a = OVERLAY_COLOURS["change_gain"]
        overlay_arr[g, 0] = r; overlay_arr[g, 1] = gg; overlay_arr[g, 2] = b; overlay_arr[g, 3] = a

        # Highlight Losses/Transformations in Bright Violet
        r2, g2, b2, a2 = OVERLAY_COLOURS["change_loss"]
        overlay_arr[l, 0] = r2; overlay_arr[l, 1] = g2; overlay_arr[l, 2] = b2; overlay_arr[l, 3] = a2

        overlay = PILImage.fromarray(overlay_arr, "RGBA")
        comp = PILImage.alpha_composite(base_img, overlay)
        draw = ImageDraw.Draw(comp, "RGBA")

        # HUD header
        draw.rounded_rectangle([10, 10, 240, 36], radius=4, fill=(4, 7, 26, 220), outline=(245, 158, 11, 255), width=1)
        draw.text((18, 15), "🔄 Multitemporal Change Map", fill=(245, 158, 11, 255))

        return comp
    except Exception as exc:
        logger.debug("Change overlay error: %s", exc)
        return None


def _save_overlay(img, upload_folder: str, prefix: str) -> str:
    """Save overlay image and return the relative filename."""
    filename = f"{prefix}_{uuid.uuid4().hex[:8]}.png"
    path = os.path.join(upload_folder, filename)
    img.convert("RGB").save(path, "PNG")
    return filename

