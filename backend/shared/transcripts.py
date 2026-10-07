"""
Transcript output formats (audio/video transcription jobs)

The worker stores each format in the private audio bucket so it outlives the
Redis result TTL; the API serves them via GET /jobs/{job_id}/result?format=...
"""

TRANSCRIPT_FORMATS = ["vtt", "srt", "txt", "json"]

TRANSCRIPT_CONTENT_TYPES = {
    "vtt": "text/vtt; charset=utf-8",
    "srt": "application/x-subrip; charset=utf-8",
    "txt": "text/plain; charset=utf-8",
    "json": "application/json",
}


def transcript_object_name(job_id: str, fmt: str, generation: int = None) -> str:
    """MinIO object name of a transcript format for a job"""
    prefix = f"transcripts/{job_id}/live/{generation}" if generation is not None else f"transcripts/{job_id}"
    return f"{prefix}/transcript.{fmt}"


def transcript_result_object_name(job_id: str, generation: int = None) -> str:
    """Full display result, metadata and formats; independent of caches/indexes."""
    return transcript_object_name(job_id, "json", generation).rsplit("/", 1)[0] + "/result.json"
