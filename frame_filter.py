"""
Perceptual-hash frame filter for the watcher pre-check.

Cheap pHash diff drops near-identical frames before the (expensive) Claude vision
trigger check. A pHash distance of ≤4 over 64-bit hash is "essentially the same
scene"; we use ≤5 as the dedup threshold to be slightly more aggressive.
"""

import base64
import io

import imagehash
from PIL import Image

PHASH_SAME_THRESHOLD = 5  # Hamming distance ≤ this → treat as duplicate frame


def phash_from_b64(jpeg_b64: str) -> imagehash.ImageHash:
    raw = base64.b64decode(jpeg_b64)
    img = Image.open(io.BytesIO(raw))
    return imagehash.phash(img)


def distance(a: imagehash.ImageHash, b: imagehash.ImageHash) -> int:
    return a - b


def is_duplicate(prev: imagehash.ImageHash | None, current: imagehash.ImageHash) -> bool:
    if prev is None:
        return False
    return distance(prev, current) <= PHASH_SAME_THRESHOLD
