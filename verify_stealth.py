import asyncio
from agent_browser import AgentBrowser

async def verify():
    print("Starting stealth verification (Headless Mode)...")
    browser = AgentBrowser(headless=True)
    
    try:
        # 1. Sannysoft
        url = "https://bot.sannysoft.com/"
        print(f"Visiting {url}...")
        page_id = await browser.open(url)
        # Wait for potential tests to run
        await asyncio.sleep(8)
        
        print("--- Sannysoft Results ---")
        # Print captured console logs
        state = browser._get_state(page_id)
        entries = state.console.get_entries()
        print(f"Console Logs ({len(entries)}):")
        for log in entries:
            print(f"  [{log.type}] {log.text}")

        try:
            # Use evaluate to extract data robustly
            # Access internal _pages
            page = browser._pages[page_id].page
            
            data = await page.evaluate("""
                () => {
                    const getText = (label) => {
                        const els = Array.from(document.querySelectorAll('td'));
                        for (let i = 0; i < els.length; i++) {
                            if (els[i].innerText.includes(label)) {
                                const next = els[i].nextElementSibling;
                                if (next) return next.innerText;
                            }
                        }
                        return 'N/A';
                    };
                    return {
                        webdriver: getText('WebDriver'),
                        webgl_vendor: getText('WebGL Vendor'),
                        webgl_renderer: getText('WebGL Renderer'),
                        plugins_len: getText('Plugins Length'),
                        ua: getText('User Agent'),
                        failed_count: document.querySelectorAll('.failed').length,
                        failed_items: Array.from(document.querySelectorAll('.failed')).map(e => e.innerText.substring(0, 50)),
                        stealth_debug: window.__stealth_debug || ['Not found']
                    };
                }
            """)
            
            print(f"Stealth Debug: {data['stealth_debug']}")
            print(f"WebDriver: {data['webdriver']}")
            print(f"WebGL Vendor: {data['webgl_vendor']}")
            print(f"WebGL Renderer: {data['webgl_renderer']}")
            print(f"Plugins Length: {data['plugins_len']}")
            print(f"User Agent: {data['ua']}")
            print(f"Failed Items Count: {data['failed_count']}")
            if data['failed_count'] > 0:
                print(f"Failed Items Samples: {data['failed_items']}")
            
        except Exception as e:
            print(f"Error extracting Sannysoft data: {e}")
            import traceback
            traceback.print_exc()
            
        try:
            await browser.screenshot(page_id, path="verify_sannysoft.png", full_page=False)
        except Exception as e:
            print(f"Screenshot failed: {e}")

        # 2. Antoine Vastel
        url = "https://arh.antoinevastel.com/bots/"
        print(f"\nVisiting {url}...")
        page_id = await browser.open(url)
        await asyncio.sleep(5)
        
        print("--- Antoine Vastel Results ---")
        try:
            content = await browser.inner_html(page_id, "body")
            if "You are a bot" in content:
                print("Verdict: BOT DETECTED")
            elif "You are not a bot" in content:
                print("Verdict: HUMAN (PASSED)")
            else:
                # Try to extract table content if it exists
                page = browser._pages[page_id].page
                table_text = await page.evaluate("document.body.innerText")
                print("Verdict: UNKNOWN")
                print(f"Page Text Sample: {table_text[:500]}...")
        except Exception as e:
            print(f"Error checking Antoine: {e}")
            
        try:
            await browser.screenshot(page_id, path="verify_antoine.png", full_page=False)
        except Exception as e:
             print(f"Screenshot failed: {e}")
        
    finally:
        await browser.close()
        print("\nVerification finished.")

if __name__ == "__main__":
    asyncio.run(verify())
