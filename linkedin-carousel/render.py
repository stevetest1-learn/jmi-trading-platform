"""Renders slides.html to the LinkedIn carousel PDF (plus one PNG per slide).

    python render.py

Reads images/ (from capture.py) and data/trade-excerpt.csv (one real trade
from the demo run's audit CSV). Needs `pip install playwright` and Chrome.
"""

import csv
import html
from decimal import Decimal
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
OUT_PDF = HERE / "JMI-Trading-Platform-Carousel.pdf"
SLIDES_DIR = HERE / "slides-png"
SLIDES_DIR.mkdir(exist_ok=True)


def num(value: str) -> str:
    d = Decimal(value)
    text = f"{d:,.4f}".rstrip("0").rstrip(".")
    return text if text not in ("-0", "") else "0"


def csv_rows_html() -> str:
    cells = []
    with open(HERE / "data" / "trade-excerpt.csv", newline="") as f:
        for row in csv.DictReader(f):
            side = row["side"].lower()
            pnl = Decimal(row["realized_pnl_this_fill"])
            pnl_text = ("+" if pnl > 0 else "") + num(row["realized_pnl_this_fill"])
            cells += [
                f"<div>{html.escape(row['trade_id'])}</div>",
                f"<div>{html.escape(row['account'])}</div>",
                f"<div class='{side}'>{html.escape(row['side'])}</div>",
                f"<div>{num(row['order_price'])}</div>",
                f"<div>{num(row['fill_price'])}</div>",
                f"<div>{num(row['fill_qty'])}</div>",
                f"<div class='{'pos' if pnl > 0 else ''}'>{pnl_text}</div>",
            ]
    return "\n      ".join(cells)


def main() -> None:
    source = (HERE / "slides.html").read_text()
    rendered = HERE / "_rendered.html"
    rendered.write_text(source.replace("<!--CSV_ROWS-->", csv_rows_html()))

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1080, "height": 1350}, device_scale_factor=1)
        page.goto(rendered.as_uri(), wait_until="networkidle")
        page.evaluate("document.fonts.ready")
        page.wait_for_timeout(500)

        # Fail loudly if a slide overflows its 1350px frame.
        overflow = page.evaluate(
            """() => [...document.querySelectorAll('.slide')].map((s, i) => ({
                 slide: i + 1, content: s.scrollHeight, frame: s.clientHeight
               })).filter(s => s.content > s.frame)"""
        )
        if overflow:
            print("OVERFLOW:", overflow)

        for i, slide in enumerate(page.locator(".slide").all(), start=1):
            slide.screenshot(path=SLIDES_DIR / f"slide-{i}.png")

        page.pdf(path=str(OUT_PDF), width="1080px", height="1350px", print_background=True, prefer_css_page_size=True)
        browser.close()

    rendered.unlink()
    print("wrote", OUT_PDF.name, f"({OUT_PDF.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
