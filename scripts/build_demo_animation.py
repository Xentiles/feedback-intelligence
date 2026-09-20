#!/usr/bin/env python3
"""Assemble a 24-second still-frame walkthrough from verified screenshots.

Requires Pillow 12.3.0. This is a screenshot sequence, not a live screen recording.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ASSETS = Path(__file__).resolve().parents[1] / "docs/assets"
SCENES = (
    (
        "dashboard.jpg",
        "1 / 4  OVERVIEW",
        "480 synthetic records. Select SemIf to follow the recorded local-model decisions.",
    ),
    (
        "signal-explorer.jpg",
        "2 / 4  SIGNAL EXPLORER",
        "Inspect the monthly rate and denominator, then follow the contributing evidence.",
    ),
    (
        "evidence-trace.jpg",
        "3 / 4  EVIDENCE TRACE",
        "Read the synthetic source record and its typed model answers.",
    ),
    (
        "evaluation.jpg",
        "4 / 4  COMPARE METHODS",
        "AI-reference agreement, not human gold. GPT-5.4 Mini remains a partial run.",
    ),
)


def main():
    frames = []
    for name, title, caption in SCENES:
        with Image.open(ASSETS / name) as source:
            screenshot = source.convert("RGB")
            screenshot.thumbnail((960, 667), Image.Resampling.LANCZOS)
        frame = Image.new("RGB", (960, 757), "#202020")
        frame.paste(screenshot, (0, 42))
        draw = ImageDraw.Draw(frame)
        draw.text((16, 10), title, font=ImageFont.load_default(size=18), fill="#e9e9e9")
        draw.text(
            (16, 717), caption, font=ImageFont.load_default(size=13), fill="#e9e9e9"
        )
        draw.text(
            (720, 12),
            "Synthetic demo / still frames",
            font=ImageFont.load_default(size=13),
            fill="#e9e9e9",
        )
        frames.append(frame.quantize(colors=128))
    frames[0].save(
        ASSETS / "demo.gif",
        save_all=True,
        append_images=frames[1:],
        duration=6000,
        loop=0,
        disposal=2,
        optimize=False,
    )
    with Image.open(ASSETS / "demo.gif") as result:
        assert result.n_frames == 4
        assert result.size == (960, 757)
    print("Built four-frame, 24-second synthetic demo walkthrough.")


if __name__ == "__main__":
    main()
