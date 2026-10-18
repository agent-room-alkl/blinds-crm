#!/usr/bin/env python3
"""
Playwright screenshot and measurement script for portal redesign verification.
Captures screenshots at 1440px and 390px for all wizard steps and nav pages.
Measures horizontal overflow and minimum tap target sizes.
"""
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, Page

BACKEND_URL = "http://localhost:8002"
FRONTEND_URL = "http://localhost:5173"
SCREENSHOTS_DIR = Path("/opt/cursor/artifacts/screenshots")
RESULTS_FILE = Path("/opt/cursor/artifacts/portal_verification.json")

# Viewports
DESKTOP = {"width": 1440, "height": 900}
MOBILE = {"width": 390, "height": 844}

def md5_file(path: Path) -> str:
    """Compute MD5 hash of a file."""
    if not path.exists():
        return ""
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()

def wait_for_services():
    """Wait for backend and frontend to be ready."""
    print("Waiting for services...")
    for _ in range(30):
        try:
            subprocess.check_output(["curl", "-sf", f"{BACKEND_URL}/api/health"], timeout=2)
            subprocess.check_output(["curl", "-sf", FRONTEND_URL], timeout=2)
            print("Services ready")
            return True
        except:
            time.sleep(1)
    raise RuntimeError("Services did not start in time")

def measure_overflow_and_targets(page: Page) -> dict:
    """Measure horizontal overflow and minimum tap target size."""
    result = page.evaluate("""() => {
        const scrollWidth = document.documentElement.scrollWidth;
        const innerWidth = window.innerWidth;
        const overflow = scrollWidth > innerWidth;
        
        // Find all interactive elements
        const selectors = 'button, a, input, select, textarea, [role="button"], [role="link"]';
        const elements = Array.from(document.querySelectorAll(selectors));
        
        let minWidth = Infinity;
        let minHeight = Infinity;
        let minElement = null;
        
        elements.forEach(el => {
            const rect = el.getBoundingClientRect();
            if (rect.width > 0 && rect.height > 0) {
                if (rect.width < minWidth) {
                    minWidth = rect.width;
                    minElement = el.tagName;
                }
                if (rect.height < minHeight) {
                    minHeight = rect.height;
                }
            }
        });
        
        return {
            scrollWidth,
            innerWidth,
            overflow,
            minWidth: minWidth === Infinity ? null : minWidth,
            minHeight: minHeight === Infinity ? null : minHeight,
            minElement,
            minTarget: Math.min(minWidth === Infinity ? Infinity : minWidth, 
                               minHeight === Infinity ? Infinity : minHeight)
        };
    }""")
    return result

def capture_screenshots(page: Page, name: str, viewport: dict, measurements: dict):
    """Capture screenshot and measurements for current page."""
    viewport_label = f"{viewport['width']}x{viewport['height']}"
    screenshot_path = SCREENSHOTS_DIR / f"{name}_{viewport_label}.png"
    
    # Wait for any pending requests and animations
    page.wait_for_load_state("networkidle", timeout=5000)
    page.wait_for_timeout(500)
    
    # Take screenshot
    page.screenshot(path=screenshot_path, full_page=True)
    
    # Measure
    metrics = measure_overflow_and_targets(page)
    md5 = md5_file(screenshot_path)
    
    measurements[f"{name}_{viewport_label}"] = {
        "path": str(screenshot_path),
        "md5": md5,
        "viewport": viewport,
        "metrics": metrics
    }
    
    print(f"  ✓ {name} @ {viewport_label}: scroll={metrics['scrollWidth']} inner={metrics['innerWidth']} "
          f"overflow={metrics['overflow']} minTarget={metrics.get('minTarget', 'N/A')}")

def main():
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    wait_for_services()
    
    measurements = {}
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        for viewport_name, viewport in [("desktop", DESKTOP), ("mobile", MOBILE)]:
            print(f"\n=== Testing {viewport_name} ({viewport['width']}x{viewport['height']}) ===")
            
            context = browser.new_context(
                viewport=viewport,
                device_scale_factor=1,
                locale="en-NZ",
                storage_state=None  # Fresh session
            )
            page = context.new_page()
            
            # Navigate and login
            print("Logging in...")
            page.goto(f"{FRONTEND_URL}/portal")
            page.wait_for_selector('input[autocomplete="username"]', timeout=10000)
            page.fill('input[autocomplete="username"]', "demo-trade")
            page.fill('input[type="password"]', "local-demo-only")
            
            # Submit and wait for API response
            with page.expect_response(lambda r: "/api/portal/login" in r.url) as response_info:
                page.click('button[type="submit"]')
            
            response = response_info.value
            if response.status == 200:
                print("  ✓ Login API successful")
            else:
                print(f"  ❌ Login API failed: {response.status}")
                page.screenshot(path=SCREENSHOTS_DIR / f"login_api_failed_{viewport_name}.png")
            
            # Wait for page to update
            page.wait_for_timeout(2000)
            
            # Check if we see logged-in content
            url_after = page.url
            html_snippet = page.inner_text('body')[:200]
            print(f"  URL after login: {url_after}")
            print(f"  Body text: {html_snippet[:80]}...")
            
            # Verify we're logged in by checking for nav or user-specific content
            has_nav = page.locator('nav').count() > 0
            has_signout = page.locator('text=登出').count() > 0 or page.locator('text=Sign out').count() > 0
            if has_nav or has_signout:
                print("  ✓ Logged in successfully")
            else:
                print("  ⚠ Login may have failed - proceeding anyway")
                page.screenshot(path=SCREENSHOTS_DIR / f"login_failed_{viewport_name}.png")
            
            # Step 1: Series selection
            print("Capturing wizard steps...")
            page.goto(f"{FRONTEND_URL}/portal/order/new")
            page.wait_for_timeout(2000)
            capture_screenshots(page, "01_wizard_series", viewport, measurements)
            
            # Click first series to proceed (if exists)
            try:
                page.click('button:has-text("选系列")', timeout=2000)
            except:
                pass
            page.wait_for_timeout(500)
            
            # Step 2: Window list (may be empty initially)
            try:
                page.goto(f"{FRONTEND_URL}/portal/order/new?step=2")
                page.wait_for_timeout(1000)
            except:
                pass
            capture_screenshots(page, "02_wizard_windows", viewport, measurements)
            
            # Add a window if button exists
            try:
                page.click('button:has-text("添加")', timeout=2000)
                page.wait_for_timeout(500)
            except:
                pass
            
            # Step 3: Window config
            page.goto(f"{FRONTEND_URL}/portal/order/new?step=3")
            page.wait_for_timeout(1000)
            capture_screenshots(page, "03_wizard_config", viewport, measurements)
            
            # Step 4: Review
            page.goto(f"{FRONTEND_URL}/portal/order/new?step=4")
            page.wait_for_timeout(1000)
            capture_screenshots(page, "04_wizard_review", viewport, measurements)
            
            # Navigation pages
            print("Capturing navigation pages...")
            
            page.goto(f"{FRONTEND_URL}/portal/orders")
            page.wait_for_timeout(1000)
            capture_screenshots(page, "05_orders_list", viewport, measurements)
            
            # Try to navigate to first order detail
            try:
                page.click('tr:has(td)', timeout=2000)
                page.wait_for_timeout(1000)
                capture_screenshots(page, "06_order_detail", viewport, measurements)
            except:
                print("  ⚠ No orders found, skipping detail view")
                # Take a placeholder screenshot anyway
                page.goto(f"{FRONTEND_URL}/portal/orders")
                page.wait_for_timeout(500)
            
            page.goto(f"{FRONTEND_URL}/portal/invoices")
            page.wait_for_timeout(1000)
            capture_screenshots(page, "07_invoices", viewport, measurements)
            
            page.goto(f"{FRONTEND_URL}/portal/company")
            page.wait_for_timeout(1000)
            capture_screenshots(page, "08_company", viewport, measurements)
            
            page.goto(f"{FRONTEND_URL}/portal/help")
            page.wait_for_timeout(1000)
            capture_screenshots(page, "09_help", viewport, measurements)
            
            context.close()
        
        browser.close()
    
    # Check for duplicates (login screens)
    print("\n=== MD5 Verification ===")
    md5_counts = {}
    for name, data in measurements.items():
        md5 = data["md5"]
        md5_counts[md5] = md5_counts.get(md5, []) + [name]
    
    duplicates = {md5: names for md5, names in md5_counts.items() if len(names) > 1}
    if duplicates:
        print("⚠ WARNING: Duplicate MD5s found (possible login screens):")
        for md5, names in duplicates.items():
            print(f"  {md5}: {', '.join(names)}")
    else:
        print("✓ All screenshots have distinct MD5s")
    
    # Summary table
    print("\n=== Measurement Summary ===")
    print(f"{'Page':<30} {'Viewport':<10} {'Overflow':<10} {'Min Target (px)':<15}")
    print("-" * 70)
    for name, data in sorted(measurements.items()):
        metrics = data["metrics"]
        overflow = "YES ❌" if metrics["overflow"] else "NO ✓"
        min_target = metrics.get("minTarget")
        target_str = f"{min_target:.1f}" if min_target and min_target != float('inf') else "N/A"
        if min_target and min_target < 44:
            target_str += " ❌"
        else:
            target_str += " ✓"
        
        viewport_str = f"{data['viewport']['width']}px"
        print(f"{name:<30} {viewport_str:<10} {overflow:<10} {target_str:<15}")
    
    # Save results
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_FILE, "w") as f:
        json.dump(measurements, f, indent=2)
    
    print(f"\n✓ Results saved to {RESULTS_FILE}")
    print(f"✓ Screenshots saved to {SCREENSHOTS_DIR}")

if __name__ == "__main__":
    main()
