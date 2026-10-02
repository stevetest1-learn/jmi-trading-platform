"""Captures carousel screenshots from the throwaway demo frontend (default
http://localhost:5180, backed by the demo backend that scenario.py populated).

Needs `pip install playwright` and a local Google Chrome (no browser download).
Usage: python capture.py [http://localhost:5180]
"""

import sys
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5180"
OUT = Path(__file__).parent / "images"
OUT.mkdir(exist_ok=True)


def login(page: Page, user: str) -> None:
    page.goto(BASE)
    page.get_by_placeholder("Username").fill(user)
    page.get_by_placeholder("Password").fill("demo1234")
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_selector(".app-header .app-header__account", timeout=15000)


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)

        # ---- Alice: trading engine view -------------------------------------
        ctx = browser.new_context(viewport={"width": 1280, "height": 900}, device_scale_factor=2)
        page = ctx.new_page()
        login(page, "alice")
        page.wait_for_selector(".depth-panel__row--bid")
        page.wait_for_selector(".blotter__table tbody tr")
        page.wait_for_selector(".panel__table tbody tr")
        page.wait_for_timeout(800)

        # Everything from the symbol tabs down through the open-orders/positions column.
        # .app-main stretches below its panels, so clip to the lowest panel edge instead.
        box = page.evaluate(
            """() => {
              const top = document.querySelector('.symbol-selector').getBoundingClientRect().top;
              const bottom = Math.max(...[...document.querySelectorAll(
                '.depth-panel, .order-ticket, .app-main__side > .panel')].map(e => e.getBoundingClientRect().bottom));
              return { x: 0, y: top + scrollY, w: innerWidth, h: bottom - top + 12 };
            }"""
        )
        page.screenshot(path=OUT / "book.png", clip={"x": box["x"], "y": box["y"], "width": box["w"], "height": box["h"]}, full_page=True)
        ctx.close()

        # Narrow viewport so the 8-column table is naturally larger once scaled
        # to a slide (the table's own minimum width is 760px).
        ctx = browser.new_context(viewport={"width": 820, "height": 900}, device_scale_factor=3)
        page = ctx.new_page()
        login(page, "alice")
        page.wait_for_selector(".blotter__table tbody tr")
        page.wait_for_timeout(500)
        page.locator(".blotter").screenshot(path=OUT / "blotter.png")
        ctx.close()

        # ---- Market maker: risk cockpit -------------------------------------
        ctx = browser.new_context(viewport={"width": 1100, "height": 900}, device_scale_factor=2)
        page = ctx.new_page()
        login(page, "market_maker")
        page.get_by_role("button", name="Risk & Exposure").click()
        page.wait_for_selector(".risk-kpis")
        page.wait_for_selector(".risk-alert")
        page.wait_for_timeout(800)

        page.locator(".risk").screenshot(path=OUT / "cockpit.png")
        panels = page.locator(".risk-split > .panel")
        panels.nth(0).screenshot(path=OUT / "exposure.png")
        panels.nth(1).screenshot(path=OUT / "alerts.png")
        ctx.close()
        browser.close()

    for f in sorted(OUT.glob("*.png")):
        print(f.name)


if __name__ == "__main__":
    main()
