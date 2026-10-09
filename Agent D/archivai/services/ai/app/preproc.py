"""Image preprocessing for aged archival scans (pure PIL, no numpy).

Tuned for the target corpus: 1920s–40s typewriter pages on yellowed paper with
red hand corrections, pencil marks and blue stamps. Every step is measurable via
scripts/ocr_eval.py — change defaults only with the eval numbers in hand.
"""
from PIL import Image, ImageChops, ImageFilter, ImageOps


def suppress_color_ink(im: Image.Image, threshold: int = 28) -> Image.Image:
    """Whiten red ink (hand corrections) and blue ink (stamps) so they stop
    corrupting typewriter-text OCR. Black/gray text is untouched: it has no
    dominant channel. Only meaningful for color scans."""
    if im.mode != "RGB":
        return im
    r, g, b = im.split()
    red_excess = ImageChops.subtract(r, ImageChops.lighter(g, b))
    blue_excess = ImageChops.subtract(b, ImageChops.lighter(r, g))
    mask = ImageChops.lighter(
        red_excess.point(lambda v: 255 if v > threshold else 0),
        blue_excess.point(lambda v: 255 if v > threshold else 0),
    ).filter(ImageFilter.MaxFilter(3))  # dilate to catch anti-aliased edges
    out = im.copy()
    out.paste(Image.new("RGB", im.size, (255, 255, 255)), mask=mask)
    return out


def binarize_otsu(im: Image.Image) -> Image.Image:
    """Global Otsu threshold — separates faded type from yellowed paper far
    better than a fixed cutoff. Input must be grayscale ('L')."""
    hist = im.histogram()[:256]
    total = sum(hist)
    if total == 0:
        return im
    ssum = sum(i * h for i, h in enumerate(hist))
    sum_b = 0.0
    w_b = 0
    best_t, best_var = 127, -1.0
    for t in range(256):
        w_b += hist[t]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += t * hist[t]
        m_b = sum_b / w_b
        m_f = (ssum - sum_b) / w_f
        var = w_b * w_f * (m_b - m_f) ** 2
        if var > best_var:
            best_var, best_t = var, t
    return im.point(lambda v, t=best_t: 255 if v > t else 0)


def _row_variance(im: Image.Image) -> float:
    """Variance of row means — sharp text lines maximize it when horizontal."""
    col = im.resize((1, im.height), Image.Resampling.BOX)
    vals = list(col.getdata())
    if not vals:
        return 0.0
    m = sum(vals) / len(vals)
    return sum((v - m) ** 2 for v in vals) / len(vals)


def estimate_skew(im_gray: Image.Image, max_angle: float = 3.0,
                  step: float = 0.25) -> float:
    """Projection-profile skew estimate on a small binarized copy."""
    w = 400
    h = max(1, round(im_gray.height * w / max(im_gray.width, 1)))
    small = binarize_otsu(im_gray.resize((w, h), Image.Resampling.BILINEAR))
    best_a, best_v = 0.0, -1.0
    a = -max_angle
    while a <= max_angle + 1e-9:
        rot = small.rotate(a, resample=Image.Resampling.BILINEAR,
                           expand=False, fillcolor=255)
        v = _row_variance(rot)
        if v > best_v:
            best_v, best_a = v, a
        a += step
    return best_a


def deskew(im: Image.Image) -> Image.Image:
    """Tesseract degrades sharply from ~1° of skew; typewriter pages are often
    fed crooked. Rotate by the estimated angle when it matters."""
    gray = im if im.mode == "L" else im.convert("L")
    angle = estimate_skew(gray)
    if abs(angle) >= 0.25:
        return im.rotate(angle, resample=Image.Resampling.BICUBIC,
                         expand=True, fillcolor=255 if im.mode == "L" else (255, 255, 255))
    return im


def preprocess_for_ocr(im: Image.Image, filter_ink: bool = True,
                       do_deskew: bool = True, binarize: bool = True) -> Image.Image:
    """Full pipeline for tesseract: ink suppression → grayscale → upscale →
    contrast → deskew → despeckle → binarize."""
    if filter_ink:
        im = suppress_color_ink(im)
    im = im.convert("L")
    if max(im.size) < 2200:
        im = im.resize((im.width * 2, im.height * 2), Image.Resampling.LANCZOS)
    im = ImageOps.autocontrast(im, cutoff=1)
    if do_deskew:
        im = deskew(im)
    im = im.filter(ImageFilter.MedianFilter(3))
    if binarize:
        im = binarize_otsu(im)
    return im
