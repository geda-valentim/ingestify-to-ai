#!/usr/bin/env python3
"""Download the administrator-controlled facial manifest, verifying every SHA."""
import argparse
import hashlib
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from shared.face_analysis import manifest


def download(destination):
    destination.mkdir(parents=True, exist_ok=True)
    for model in manifest()['models']:
        target = destination / model['filename']
        if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == model['sha256']:
            print(f"Verified: {model['model_id']}")
            continue
        fd, temporary = tempfile.mkstemp(dir=destination, prefix='.download-')
        try:
            digest = hashlib.sha256()
            with os.fdopen(fd, 'wb') as output, urllib.request.urlopen(model['source_url'], timeout=60) as response:
                while chunk := response.read(1024*1024):
                    digest.update(chunk)
                    output.write(chunk)
            if digest.hexdigest() != model['sha256']:
                raise ValueError(f"Checksum mismatch: {model['model_id']}")
            os.chmod(temporary, 0o644)
            os.replace(temporary, target)
            print(f"Downloaded and verified: {model['model_id']}")
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, default=Path('/models/faces'))
    download(parser.parse_args().destination)
