#!/usr/bin/env python3
"""Normalize Kling outputs to 3 seconds each; assemble a silent seekable home film."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path('/data/tmp/ingestify/film-production')
DEST = ROOT / 'frontend/public/landing/film'
manifest = json.loads((ROOT / 'docs/landing/film-manifest.json').read_text())
DEST.mkdir(parents=True, exist_ok=True)
normalized = SOURCE / 'normalized'
normalized.mkdir(exist_ok=True)
provenance = []
for clip in manifest['clips']:
    source = SOURCE / (clip['id'] + '.mp4')
    target = normalized / source.name
    probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', str(source)]))
    duration = float(probe['format']['duration'])
    # The provider can return 73 frames (3.041667 s). Retiming prevents drift
    # against the exact 45-second HTML timeline while retaining the endpoint.
    subprocess.run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-i', str(source),
        '-vf', f'setpts=(PTS-STARTPTS)*3/{duration},scale=1440:-2,fps=24',
        '-t', '3', '-an', '-c:v', 'libx264', '-preset', 'slow', '-threads', '4', '-crf', '20',
        '-g', '6', '-keyint_min', '6', '-sc_threshold', '0', '-pix_fmt', 'yuv420p',
        '-movflags', '+faststart', str(target)], check=True)
    record = json.loads((SOURCE / (clip['id'] + '.json')).read_text())
    provenance.append({'id': clip['id'], 'request_id': record['receipt']['request_id'],
        'source_duration': duration, 'duration': 3, 'quote_usd': record['estimate']['usd'],
        'sha256': hashlib.sha256(source.read_bytes()).hexdigest()})
concat = normalized / 'concat.txt'
concat.write_text(''.join("file '" + str(normalized / (c['id'] + '.mp4')) + "'\n" for c in manifest['clips']))
output = DEST / 'ingestify-scroll.mp4'
subprocess.run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-f', 'concat', '-safe', '0',
    '-i', str(concat), '-c', 'copy', '-movflags', '+faststart', str(output)], check=True)
mobile = DEST / 'ingestify-scroll-mobile.mp4'
subprocess.run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-i', str(output),
    '-vf', 'scale=768:-2', '-an', '-c:v', 'libx264', '-preset', 'slow', '-threads', '4', '-crf', '22',
    '-g', '6', '-keyint_min', '6', '-sc_threshold', '0', '-pix_fmt', 'yuv420p',
    '-movflags', '+faststart', str(mobile)], check=True)
(ROOT / 'docs/landing/film-provenance.json').write_text(json.dumps({'model':manifest['model'],
    'duration':45, 'fps':24, 'keyframe_interval':6, 'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
    'bytes':output.stat().st_size, 'mobile_bytes':mobile.stat().st_size,
    'mobile_sha256':hashlib.sha256(mobile.read_bytes()).hexdigest(), 'clips':provenance}, indent=2) + '\n')
print('Film assembled:', output, output.stat().st_size, 'bytes')
