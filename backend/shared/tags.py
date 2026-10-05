"""
Job tags: parsing and normalisation.

Tags arrive as a comma-separated form field (multipart endpoints) or a JSON
list. Both go through `parse_tags`, so every tag in the database has the same
shape: trimmed, inner whitespace collapsed, lower-cased, no leading '#'.
Lower-casing makes "Cliente" and "cliente" one tag, which is what a filter
needs.
"""

import re
from typing import Iterable, List, Optional, Union

MAX_TAGS_PER_JOB = 20
MAX_TAG_LENGTH = 50

_WHITESPACE = re.compile(r"\s+")


class InvalidTagsError(ValueError):
    """The tags cannot be accepted; the message is safe to show the caller."""


def normalize_tag(raw: str) -> str:
    return _WHITESPACE.sub(" ", raw.strip().lstrip("#").strip()).lower()


def parse_tags(raw: Union[None, str, Iterable[str]]) -> List[str]:
    """
    Normalised, de-duplicated tags in the order given.

    Raises:
        InvalidTagsError: a tag is too long, or there are too many.
    """
    if raw is None:
        return []
    items = raw.split(",") if isinstance(raw, str) else [p for item in raw for p in str(item).split(",")]

    tags: List[str] = []
    for item in items:
        tag = normalize_tag(item)
        if not tag or tag in tags:
            continue
        if len(tag) > MAX_TAG_LENGTH:
            raise InvalidTagsError(f"Tag muito longa (máximo {MAX_TAG_LENGTH} caracteres): {tag[:60]}")
        tags.append(tag)

    if len(tags) > MAX_TAGS_PER_JOB:
        raise InvalidTagsError(f"Máximo de {MAX_TAGS_PER_JOB} tags por job ({len(tags)} enviadas)")
    return tags


def set_job_tags(job, tags: List[str]) -> None:
    """Replace the job's tags. The caller commits."""
    from shared.models import JobTag

    wanted = list(dict.fromkeys(tags))
    if len(wanted) > MAX_TAGS_PER_JOB:
        raise InvalidTagsError(f"Máximo de {MAX_TAGS_PER_JOB} tags por job ({len(wanted)} no total)")
    job.tag_rows = [row for row in job.tag_rows if row.tag in wanted] + [
        JobTag(tag=tag) for tag in wanted if tag not in job.tags
    ]


def add_job_tags(job, tags: Optional[List[str]]) -> None:
    """Add tags to the job, keeping the ones it has. The caller commits."""
    if tags:
        set_job_tags(job, job.tags + [t for t in tags if t not in job.tags])
