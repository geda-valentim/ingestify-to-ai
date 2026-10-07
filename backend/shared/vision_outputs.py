"""Normalize Florence geometry without discarding the original model output."""
import math


def coordinates(values, *, size=None, polygon=False):
    if not isinstance(values, (list, tuple)):
        return None
    try:
        result = [float(value) for value in values]
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in result):
        return None
    if size is not None and len(result) != size:
        return None
    if polygon and (len(result) < 6 or len(result) % 2):
        return None
    return result


def normalize_output(output):
    if isinstance(output, str):
        return output.strip().removeprefix("</s>").strip(), [], []
    if not isinstance(output, dict):
        return "", [], []
    regions, lines = [], []
    labels = output.get("labels") or []
    def label_at(labels, index):
        return str(labels[index]).strip().removeprefix("</s>").strip() if index < len(labels) else ""
    for index, raw in enumerate(output.get("bboxes") or []):
        bbox = coordinates(raw, size=4)
        if bbox is not None:
            region = {"label": label_at(output.get("bboxes_labels") or labels, index), "bbox": bbox, "polygons": []}
            scores = output.get("scores") or []
            if index < len(scores):
                try:
                    score = float(scores[index])
                    if math.isfinite(score):
                        region["score"] = score
                except (TypeError, ValueError):
                    pass
            regions.append(region)
    for index, raw in enumerate(output.get("quad_boxes") or []):
        quad = coordinates(raw, size=8)
        if quad is not None:
            bbox = [min(quad[::2]), min(quad[1::2]), max(quad[::2]), max(quad[1::2])]
            label = label_at(labels, index)
            regions.append({"label": label, "bbox": bbox, "quad_box": quad, "polygons": []})
            lines.append({"text": label, "bbox": bbox, "quad_box": quad})
    for index, group in enumerate(output.get("polygons") or []):
        if not isinstance(group, (list, tuple)):
            continue
        if group and isinstance(group[0], (int, float)):
            group = [group]
        polygons = [valid for polygon in group if (valid := coordinates(polygon, polygon=True)) is not None]
        if polygons:
            regions.append({"label": label_at(output.get("polygons_labels") or labels, index), "polygons": polygons})
    text = "\n".join(line["text"] for line in lines) if lines else "\n".join(r["label"] for r in regions if r["label"])
    return text, regions, lines
