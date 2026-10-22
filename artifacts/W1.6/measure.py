import json
import re
import sys
from pathlib import Path

import textstat
from selenium import webdriver


def open_page(path, width=1440):
    o = webdriver.ChromeOptions()
    for f in ("--headless=new", "--no-sandbox", "--proxy-server=http://127.0.0.1:9"):
        o.add_argument(f)
    d = webdriver.Chrome(options=o)
    d.execute_cdp_cmd(
        "Emulation.setDeviceMetricsOverride",
        {"width": width, "height": 900, "deviceScaleFactor": 1, "mobile": False},
    )
    d.get(path.resolve().as_uri())
    d.implicitly_wait(5)
    return d


out = Path(sys.argv[1])
text = (out / "report.html").read_text()
d = open_page(out / "report.html", 390)
res = {}
try:
    body = d.execute_script("""
      const w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let s=[];
      while(w.nextNode()){const n=w.currentNode,p=n.parentElement;
        if(!p||['SCRIPT','STYLE','NOSCRIPT'].includes(p.tagName))continue;
        if(p.closest('details:not([open])')&&!p.closest('summary'))continue;
        if(p.offsetParent===null&&getComputedStyle(p).position!=='fixed')continue;
        s.push(n.textContent)}
      return s.join(' ')""")
    words = re.findall(r"[A-Za-z0-9'-]+", body)
    res["words_at_load"] = len(words)
    res["fk"] = textstat.flesch_kincaid_grade(body)
    m = re.search(r'"model_km":\{"aaa":([\d.]+)\}', text)
    res["model_km_raw"] = m.group(1) if m else None
    tiles = []
    for b in d.find_elements("css selector", "[data-stage]"):
        b.click()
        __import__("time").sleep(1.2)
        tiles.append(d.find_element("id", "t-km").text)
    res["tile_km_by_stage"] = tiles
    d.execute_cdp_cmd(
        "Emulation.setDeviceMetricsOverride",
        {"width": 360, "height": 800, "deviceScaleFactor": 1, "mobile": True},
    )
    res["scroll_w_360"] = d.execute_script(
        "return [document.documentElement.scrollWidth, innerWidth]"
    )
    from pathlib import Path as P

    banned = [
        line[2:].strip()
        for line in P("VOICE.md")
        .read_text()
        .split("## Banned words")[1]
        .split("##")[0]
        .splitlines()
        if line.startswith("- ")
    ]
    res["banned_found"] = [
        b
        for b in banned
        if re.search(re.escape(b) if b == "!" else r"\b" + re.escape(b) + r"\b", body, re.I)
    ]
    d.execute_cdp_cmd(
        "Emulation.setDeviceMetricsOverride",
        {"width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": True},
    )
    d.execute_script("window.scrollTo(0,0)")
    res["first_screen_390"] = (
        d.execute_script("""const r=e=>e?Math.round(e.getBoundingClientRect().bottom):null;
      return {hero:r(document.querySelector('h1')),
      map:r(document.querySelector('#map,svg,.map')),
      tiles:r(document.querySelector('.tiles')),vh:innerHeight}""")
    )
finally:
    d.quit()
print(json.dumps(res, indent=1))
