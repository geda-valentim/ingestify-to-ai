"""The job result contract shared by vision workers and authenticated reads."""

def vision_result(payload: dict, *, operation=None, image_bytes=None, mime=None, filename=None,
                  embed_image=True) -> dict:
    """`embed_image=False` (the job asked for purge_source): the result keeps the
    image's metadata but never carries the image itself."""
    if payload.get("image") and "markdown" in payload:
        return payload
    operation = operation or ("describe" if "description" in payload else "ocr")
    text = payload.get("description" if operation == "describe" else "text") or ""
    image = {
        "operation": operation,
        "task": payload.get("task") or ("<OCR_WITH_REGION>" if operation == "ocr" else "<MORE_DETAILED_CAPTION>"),
        "width": payload.get("width", 0), "height": payload.get("height", 0),
        "model": payload.get("model"), "duration_ms": payload.get("duration_ms", 0),
        "description": payload.get("description"), "text": payload.get("text"),
        "lines": payload.get("lines", []),
        "output": payload.get("output"), "regions": payload.get("regions", []),
        "request": payload.get("request"),
    }
    from shared.vision_capabilities import VISION_TASKS
    if image["task"] in VISION_TASKS:
        image["task_label"] = VISION_TASKS[image["task"]][0]
    if image_bytes is not None and embed_image:
        import base64
        image.update(image_base64=base64.b64encode(image_bytes).decode("ascii"), image_mime_type=mime)
    elif image_bytes is not None:
        image.update(image_base64=None, image_mime_type=mime)
    return {
        **payload, "markdown": text,
        "metadata": {"format": (mime or "image").split("/")[-1],
                     "size_bytes": len(image_bytes or b""), "words": len(text.split()),
                     "title": filename, "device": (payload.get("model") or {}).get("device")},
        "image": image,
    }
