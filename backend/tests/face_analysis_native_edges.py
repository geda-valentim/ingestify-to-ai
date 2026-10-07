"""Qualify pinned CPU adapters with a licensed fixture, blank image, EXIF and face limits.

Usage: FACE_ANALYSIS_ENABLED=true python tests/face_analysis_native_edges.py /path/to/astronaut.png
The fixture is supplied externally; no personal images or weights are checked in.
"""
import io
import json
import resource
import sys
import time
from PIL import Image, ImageOps
from shared.face_analysis import FaceRequestOptions
from workers.vision.faces import FacePipeline, capabilities


def check(image, maximum=2):
    options = FaceRequestOptions(max_faces=maximum).effective()
    pipeline = FacePipeline(options, capabilities()['models'])
    started = time.monotonic()
    try:
        result = pipeline.detection(image)
        for face in result['faces']:
            width, height = image.size
            x1, y1, x2, y2 = face['bbox']
            assert 0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height
            assert len(face['keypoints']) == 6
            movements = pipeline.movements(image, face)
            expression = pipeline.expression(image, face)
            assert len(movements['landmarks']) == 478 and len(movements['blendshapes']) == 52
            assert len(expression['scores']) == 8
            assert abs(sum(item['score'] for item in expression['scores'])-1) < 1e-6
        print(json.dumps({'size':image.size,'detected':result['detected_count'],'selected':result['selected_count'],
            'omitted':result['omitted_count'],'seconds':round(time.monotonic()-started,3),
            'process_peak_rss_mb':round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,1)}),flush=True)
        return result
    finally:pipeline.close()


if __name__ == '__main__':
    original = Image.open(sys.argv[1]).convert('RGB')
    base = check(original)
    assert base['detected_count'] == 1
    blank = Image.new('RGB', (512,512), 'white')
    assert check(blank)['detected_count'] == 0
    rotated = original.transpose(Image.Transpose.ROTATE_90)
    exif = Image.Exif(); exif[274] = 6
    encoded = io.BytesIO(); rotated.save(encoded,'JPEG',quality=95,exif=exif)
    with Image.open(io.BytesIO(encoded.getvalue())) as stored:
        canonical = ImageOps.exif_transpose(stored).convert('RGB')
    assert canonical.size == original.size
    oriented = check(canonical)
    assert oriented['detected_count'] == 1
    assert max(abs(a-b) for a,b in zip(base['faces'][0]['bbox'],oriented['faces'][0]['bbox'])) <= 3
    portrait = original.crop((150,50,310,210))
    group = Image.new('RGB',(540,360),'white')
    for row in range(2):
        for column in range(3):group.paste(portrait,(column*180,row*180))
    selected = check(group)
    assert selected['detected_count'] > 2 and selected['selected_count'] == 2
    assert selected['selection_limited'] and selected['omitted_count'] == selected['detected_count']-2
    print('PASS: native CPU, blank image, EXIF canonical coordinates, independent faces and visible selection limit',flush=True)
