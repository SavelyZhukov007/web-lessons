"""Rebuild the Golos UI subset: pip install fonttools brotli.

Use the already optimized Latin/Cyrillic source WOFF2, not the larger upstream TTF.
One shared variable subset is smaller than two files with duplicated variation tables.
"""
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1] / "frontend/fonts"


def main():
    font = TTFont(ROOT / "GolosText-Variable.woff2")
    options = subset.Options()
    options.hinting = False
    worker = subset.Subsetter(options)
    worker.populate(unicodes=[*range(0x20, 0x530), *range(0x2000, 0x2300)])
    worker.subset(font)
    font.flavor = "woff2"
    dest = ROOT / "GolosText-ui.woff2"
    font.save(dest)
    print(dest.name, dest.stat().st_size)


if __name__ == "__main__":
    main()
