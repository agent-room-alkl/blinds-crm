"""Playwright test for portal at 390px and 1440px"""
import os
import sys
import hashlib
from pathlib import Path

# Add backend to path
sys.path.insert(0, "/workspace/backend")

from playwright.sync_api import sync_playwright, expect

# Setup paths
ARTIFACTS = Path("/opt/cursor/artifacts")
SCREENSHOTS = ARTIFACTS / "screenshots"
SCREENSHOTS.mkdir(parents=True, exist_ok=True)

DB_PATH = Path("/workspace/backend/.demo/vera-portal-test.db")
if not DB_PATH.exists():
    raise FileNotFoundError(f"Demo database not found: {DB_PATH}")

os.environ["VERA_DB"] = str(DB_PATH)
os.environ["VERA_DB_BACKEND"] = "sqlite"
os.environ["VERA_STORAGE_BACKEND"] = "local"
os.environ["VERA_DEMO_PASSWORD"] = "vera-demo"
os.environ["SMTP_HOST"] = ""

# Start server in background
import subprocess
import time
import urllib.request

server_proc = subprocess.Popen(
    ["python3", "-m", "uvicorn", "service:app", "--host", "0.0.0.0", "--port", "8000"],
    cwd="/workspace/backend",
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    env={**os.environ, "PYTHONPATH": "/workspace/backend"},
)

# Wait for server to start (up to 15 seconds)
print("Waiting for server to start...")
for i in range(30):
    try:
        with urllib.request.urlopen("http://localhost:8000/api/health", timeout=1) as response:
            if response.status == 200:
                print(f"✓ Server ready after {i+1} attempts")
                break
    except:
        pass
    time.sleep(0.5)
else:
    raise RuntimeError("Server failed to start")

try:
    with sync_playwright() as p:
        for width in [390, 1440]:
            browser = p.chromium.launch()
            context = browser.new_context(viewport={"width": width, "height": 2400})
            page = context.new_page()
            
            # Login
            page.goto("http://localhost:8000/portal")
            page.fill('input[autocomplete="username"]', "demo-trade")
            page.fill('input[type="password"]', "local-demo-only")
            page.click("button[type=submit]")
            page.wait_for_url("**/portal/orders", timeout=5000)
            
            screenshots = {}
            
            # 1. Orders list
            page.goto("http://localhost:8000/portal/orders")
            page.wait_for_load_state("networkidle")
            path = SCREENSHOTS / f"01-orders-list-{width}px.png"
            page.screenshot(path=str(path), full_page=True)
            screenshots[f"orders-list-{width}"] = path
            
            # 2. New order wizard - step 1 (series)
            page.goto("http://localhost:8000/portal/order/new")
            page.wait_for_load_state("networkidle")
            path = SCREENSHOTS / f"02-wizard-step1-series-{width}px.png"
            page.screenshot(path=str(path), full_page=True)
            screenshots[f"wizard-step1-{width}"] = path
            
            # Select a series and go to step 2
            series_cards = page.locator(".series-card").all()
            if series_cards:
                series_cards[0].click()
                page.wait_for_timeout(500)
                page.click("button:has-text('Next')")
                page.wait_for_timeout(500)
                
                # 3. Wizard step 2 (windows)
                path = SCREENSHOTS / f"03-wizard-step2-windows-{width}px.png"
                page.screenshot(path=str(path), full_page=True)
                screenshots[f"wizard-step2-{width}"] = path
            
            # 4. Invoices
            page.goto("http://localhost:8000/portal/invoices")
            page.wait_for_load_state("networkidle")
            path = SCREENSHOTS / f"04-invoices-{width}px.png"
            page.screenshot(path=str(path), full_page=True)
            screenshots[f"invoices-{width}"] = path
            
            # 5. Company
            page.goto("http://localhost:8000/portal/company")
            page.wait_for_load_state("networkidle")
            path = SCREENSHOTS / f"05-company-{width}px.png"
            page.screenshot(path=str(path), full_page=True)
            screenshots[f"company-{width}"] = path
            
            # 6. Help
            page.goto("http://localhost:8000/portal/help")
            page.wait_for_load_state("networkidle")
            path = SCREENSHOTS / f"06-help-{width}px.png"
            page.screenshot(path=str(path), full_page=True)
            screenshots[f"help-{width}"] = path
            
            browser.close()
            
            # Check md5s to verify screenshots are different
            md5s = {}
            for name, path in screenshots.items():
                with open(path, "rb") as f:
                    md5s[name] = hashlib.md5(f.read()).hexdigest()
            
            unique_md5s = len(set(md5s.values()))
            print(f"\n{width}px screenshots: {len(screenshots)} files, {unique_md5s} unique md5s")
            
            if unique_md5s < len(screenshots):
                print(f"  WARNING: Some screenshots are identical (possible login screen)")
                for name, md5 in md5s.items():
                    print(f"    {name}: {md5}")
            
            # Measure scrollWidth vs innerWidth
            page = context.new_page()
            page.set_viewport_size({"width": width, "height": 1200})
            
            measurements = {}
            for route, name in [
                ("/portal/orders", "orders"),
                ("/portal/order/new", "wizard"),
                ("/portal/invoices", "invoices"),
                ("/portal/company", "company"),
                ("/portal/help", "help"),
            ]:
                page.goto(f"http://localhost:8000{route}")
                page.wait_for_load_state("networkidle")
                
                scroll_width = page.evaluate("document.documentElement.scrollWidth")
                inner_width = page.evaluate("window.innerWidth")
                overflow = scroll_width > inner_width
                
                # Find smallest tap target
                min_tap = page.evaluate("""
                    () => {
                        const clickable = document.querySelectorAll('button, a, input, select, [role="button"]');
                        let min = Infinity;
                        clickable.forEach(el => {
                            const rect = el.getBoundingClientRect();
                            const size = Math.min(rect.width, rect.height);
                            if (size > 0 && size < min) min = size;
                        });
                        return min === Infinity ? null : min;
                    }
                """)
                
                measurements[name] = {
                    "scrollWidth": scroll_width,
                    "innerWidth": inner_width,
                    "overflow": overflow,
                    "minTapTarget": min_tap,
                }
            
            print(f"\n{width}px measurements:")
            print(f"  {'Page':<15} {'ScrollW':<10} {'InnerW':<10} {'Overflow':<10} {'MinTap':<10}")
            print(f"  {'-'*15} {'-'*10} {'-'*10} {'-'*10} {'-'*10}")
            for name, m in measurements.items():
                overflow_str = "YES ❌" if m["overflow"] else "NO ✓"
                tap_str = f"{m['minTapTarget']:.0f}px" if m["minTapTarget"] else "N/A"
                tap_status = "❌" if m["minTapTarget"] and m["minTapTarget"] < 44 else "✓"
                print(f"  {name:<15} {m['scrollWidth']:<10} {m['innerWidth']:<10} {overflow_str:<10} {tap_str} {tap_status}")
    
    print(f"\n✓ All screenshots saved to {SCREENSHOTS}")
    print(f"  Verify they show logged-in portal pages, not login screens")

finally:
    server_proc.terminate()
    server_proc.wait(timeout=5)
