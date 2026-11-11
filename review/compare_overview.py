"""Compare Local and Online Overview geometry with the same synthetic site."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import expect, sync_playwright

p=argparse.ArgumentParser()
p.add_argument("--local",type=int,required=True)
p.add_argument("--online",type=int,required=True)
p.add_argument("--out",type=Path,required=True)
p.add_argument("--compact",action="store_true")
args=p.parse_args()
args.out.mkdir(parents=True,exist_ok=True)
results={}
errors=[]
with sync_playwright() as pw:
    browser=pw.chromium.launch()
    for channel,port in (("local",args.local),("online",args.online)):
        base=f"http://127.0.0.1:{port}"
        context=browser.new_context(viewport={"width":1440,"height":900})
        page=context.new_page()
        page.on("pageerror",lambda error: errors.append(str(error)))
        page.goto(base+f"/login/{channel}.html")
        page.locator("#login-identifier").fill("uengliangseng")
        page.locator("#login-password").fill("uengliangseng")
        page.locator("#login-form button[type=submit]").click()
        page.wait_for_url(base+"/")
        expect(page.locator("#connection-label.live-tag")).to_be_visible()
        expect(page.locator(".monitor-card")).to_have_count(6)
        expect(page.locator(".monitor-card [data-action='machine-settings']")).to_have_count(6 if channel=="local" else 0)
        expect(page.locator(".monitor-card[data-level='alarm']")).to_have_count(1)
        for width,height in ((360,800),(768,900),(1280,720),(1440,900),(1920,1080),(1920,1440),(2560,1440)):
            page.set_viewport_size({"width":width,"height":height})
            page.evaluate("""async () => {
                await document.fonts.ready;
                await new Promise(resolve => requestAnimationFrame(resolve));
                await Promise.all(document.querySelector('.workspace').getAnimations().map(animation => animation.finished));
            }""")
            value=page.evaluate("""() => {
                const cards=[...document.querySelectorAll('.monitor-card')];
                const bounds=cards.map(card=>card.getBoundingClientRect());
                const grid=document.querySelector('.monitor-grid').getBoundingClientRect();
                return {width:Math.round(bounds[0].width),height:Math.round(bounds[0].height),
                  gridWidth:Math.round(grid.width),columns:bounds.filter(r=>Math.abs(r.top-bounds[0].top)<1).length,
                  overflow:document.documentElement.scrollWidth>innerWidth+1,
                  clipped:cards.some(card=>card.scrollHeight>card.clientHeight+1)};
            }""")
            results[f"{channel}-{width}x{height}"]=value
            if args.compact:
                assert not value["overflow"] and not value["clipped"], (channel,width,height,value)
                assert value["columns"] == (1 if width<=500 else 2 if width<=999 else 3)
            if (width,height) in ((1920,1440),(360,800)):
                page.screenshot(path=str(args.out/f"{channel}-{width}x{height}.png"))
        if args.compact:
            assert results[f"{channel}-1920x1080"]["height"]==results[f"{channel}-1920x1440"]["height"]
            page.set_viewport_size({"width":360,"height":800})
            page.locator("[data-action=language]").click()
            expect(page.locator("html")).to_have_attribute("lang","en")
            page.locator("[data-action=theme]").click()
            expect(page.locator("html")).to_have_attribute("data-theme","dark")
            offline=page.locator("[data-action=filter][data-value=offline]")
            offline.focus()
            offline.press("Enter")
            expect(offline).to_have_attribute("aria-pressed","true")
            expect(page.locator(".monitor-card[data-level=offline]")).to_be_visible()
            assert page.locator(".monitor-card").count() < 6
            page.locator("[data-action=filter][data-value=all]").click()
            expect(page.locator(".monitor-card")).to_have_count(6)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.locator(".monitor-card footer [data-action=detail]").first.click()
            expect(page.locator("body")).to_have_attribute("data-page","detail")
            context.close()
            context=browser.new_context(viewport={"width":1920,"height":1080})
            page=context.new_page()
            page.on("pageerror",lambda error: errors.append(str(error)))
            page.goto(base+f"/login/{channel}.html")
            page.locator("#login-identifier").fill("pumpkintec")
            page.locator("#login-password").fill("pumpkintec")
            page.locator("#login-form button[type=submit]").click()
            page.wait_for_url(base+"/")
            expect(page.locator("#connection-label.live-tag")).to_be_visible()
            expect(page.locator(".monitor-card")).to_have_count(1)
            assert page.locator(".monitor-card").bounding_box()["width"] <= 620
        context.close()
    browser.close()
assert not errors,errors
if args.compact:
    for key,value in results.items():
        if key.startswith("local-"):
            other=results[key.replace("local-","online-",1)]
            assert value["width"]==other["width"] and value["columns"]==other["columns"]
(args.out/"geometry.json").write_text(json.dumps(results,indent=2),encoding="utf-8")
print(json.dumps(results))
