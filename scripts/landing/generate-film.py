#!/usr/bin/env python3
"""Resumable Higgsfield production. Credentials and paid job state stay outside git."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from decimal import Decimal
import requests

ROOT = Path(__file__).resolve().parents[2]
STATE = Path('/data/tmp/ingestify/film-production')
MANIFEST = ROOT / 'docs/landing/film-manifest.json'
BASE = 'https://api.higgsfield.ai'

def save(path, data):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2) + '\n')
    tmp.replace(path)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['estimate', 'submit', 'poll'])
    parser.add_argument('--clip')
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text())
    STATE.mkdir(parents=True, exist_ok=True)
    key = os.environ.get('HIGGSFIELD_API_KEY') or Path('/data/tmp/ingestify/.higgsfield-key').read_text().strip()
    headers = {'Authorization': 'Key ' + key}
    records = []
    for clip in manifest['clips']:
        body = {k: manifest[k] for k in ('aspect_ratio', 'sound', 'multi_shots')}
        body.update({k: clip[k] for k in ('mode', 'prompt', 'duration')})
        prefix = 'https://raw.githubusercontent.com/geda-valentim/ingestify-to-ai/' + manifest['source_commit'] + '/'
        body.update(first_frame_url=prefix + clip['first'], last_frame_url=prefix + clip['last'])
        identity = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        path = STATE / (clip['id'] + '.json')
        record = json.loads(path.read_text()) if path.exists() else {'id': clip['id'], 'identity': identity, 'body': body}
        if record['identity'] != identity:
            raise RuntimeError('Changed generation intent: review state explicitly before continuing: ' + clip['id'])
        records.append((path, record))
    if args.action == 'estimate':
        total = Decimal('0')
        for path, record in records:
            response = requests.post(BASE + '/estimate/' + manifest['model'], headers=headers, json=record['body'], timeout=60)
            response.raise_for_status()
            record['estimate'] = response.json()
            amount = Decimal(record['estimate']['usd'])
            if amount > Decimal('0.30'):
                raise RuntimeError('Per-clip quote guard exceeded')
            total += amount
            save(path, record)
        if total > Decimal('4.50'):
            raise RuntimeError('Total quote guard exceeded')
        print('Quote total USD:', total, flush=True)
        return
    if args.action == 'submit' and manifest['approval'] != 'approved_storyboard_review':
        raise RuntimeError('Storyboard review must approve manifest before submission')
    quoted_total = sum(Decimal(r.get('estimate', {}).get('usd', '999')) for _, r in records)
    if args.action == 'submit' and quoted_total > Decimal('4.50'):
        raise RuntimeError('Estimate all clips first; total quote guard exceeded')
    for path, record in records:
        if args.clip and record['id'] != args.clip:
            continue
        if args.action == 'submit' and 'receipt' not in record:
            quote = requests.post(BASE + '/estimate/' + manifest['model'], headers=headers, json=record['body'], timeout=60)
            quote.raise_for_status()
            current = quote.json()
            if Decimal(current['usd']) > Decimal('0.30') or quoted_total - Decimal(record['estimate']['usd']) + Decimal(current['usd']) > Decimal('4.50'):
                raise RuntimeError('Quote changed beyond guard')
            quoted_total += Decimal(current['usd']) - Decimal(record['estimate']['usd'])
            record['estimate'] = current
            # Durable identity is written BEFORE the paid request. Never retry with a new key.
            save(path, record)
            response = requests.post(BASE + '/' + manifest['model'], headers={**headers, 'Idempotency-Key': 'ingestify-home-' + record['identity']}, json=record['body'], timeout=120)
            response.raise_for_status()
            record['receipt'] = response.json()
            save(path, record)
        if 'receipt' not in record:
            print(record['id'], 'not submitted', flush=True)
            continue
        status_url = record['receipt']['status_url']
        if not status_url.startswith(BASE + '/'):
            raise RuntimeError('Unexpected polling origin')
        response = requests.get(status_url, headers=headers, timeout=60)
        response.raise_for_status()
        record['result'] = response.json()
        save(path, record)
        status = record['result']['status']
        print(record['id'], status, flush=True)
        output = STATE / (record['id'] + '.mp4')
        if status == 'completed' and not output.exists():
            download = requests.get(record['result']['video']['url'], timeout=120)
            download.raise_for_status()
            tmp = output.with_suffix('.part')
            tmp.write_bytes(download.content)
            tmp.replace(output)

if __name__ == '__main__':
    main()
