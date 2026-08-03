#!/usr/bin/env python3
"""rapp-petri — culture RAPP agents in a sterile, headless brainstem.

Boots the Pyodide vBrainstem from a URL in headless Chromium, then drops agents
into it. No install, no local Python for the agents, no brainstem service, no
credentials. Same runtime that answers on a real machine.

    petri.py                              boot only -- is the dish alive?
    petri.py --dir ./agents               run every *_agent.py in ONE boot
    petri.py --agent ship_agent.py        run one, with --args '{...}'
    petri.py --skill ship/SKILL.md \
             --toaster toaster.py         SKILL.md -> agent.py -> run, in-browser
    petri.py --routes                     map the brainstem's HTTP surface

Boot costs ~20-40s once; every agent after that is fast, which is what makes
--dir usable as a test suite rather than a demo.

Exit code is 0 only if every agent executed. Non-zero is a usable CI gate.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path

VBRAINSTEM = "https://kody-w.github.io/vbrainstem/"

GENERATED_BLOCK = re.compile(
    r"\n?^<!-- toaster:generated:begin -->$.*?^<!-- toaster:generated:end -->$\n?",
    re.S | re.M,
)
CAPSULE = re.compile(r"\n?^<!-- rci-capsule:v1:[^>]*-->$\n?", re.S | re.M)

# ---- Python that runs INSIDE the dish ------------------------------------
# rapp.eval sends multi-line code through exec(), which discards a trailing
# expression, so every result is printed rather than returned.

RUN_AGENT = """
import base64, json, brainstem_web
_src = base64.b64decode(AGENT_B64).decode("utf-8")
_out = brainstem_web.rapp_run(_src, AGENT_NAME, REQUEST, ARGS_OBJ)
print(json.dumps({
    "executed": _out.get("executed"),
    "ran_class": _out.get("ran_class"),
    "output": (_out.get("output") or _out.get("error") or "")[:4000],
    "trace": (_out.get("trace") or "")[:600],
}))
"""

BUILD_AND_RUN = """
import base64, importlib.util, json, os, sys, brainstem_web
os.makedirs("/tmp/tk", exist_ok=True)
open("/tmp/tk/toaster.py", "w").write(base64.b64decode(TOASTER_B64).decode())
open("/tmp/tk/SKILL.md", "w").write(base64.b64decode(SKILL_B64).decode())
spec = importlib.util.spec_from_file_location("toaster", "/tmp/tk/toaster.py")
tk = importlib.util.module_from_spec(spec); spec.loader.exec_module(tk)
rci = tk.load("/tmp/tk/SKILL.md", "skill")
# Drop the vaulted raw copy or render() restores the bytes we are replacing and
# the toast silently no-ops -- the rule `toaster.py toast` follows.
rci.setdefault("preserved", {}).pop("skill", None)
tk.toast_rci(rci)
agent_src = tk.render(rci, "agent").decode()
_out = brainstem_web.rapp_run(agent_src, rci["name"], REQUEST, ARGS_OBJ)
print(json.dumps({
    "capability_id": tk.capability_id(rci)[:12],
    "params": sorted((rci.get("parameters") or {}).get("properties", {})),
    "steps": len((rci.get("impl") or {}).get("steps") or []),
    "agent_bytes": len(agent_src),
    "executed": _out.get("executed"),
    "ran_class": _out.get("ran_class"),
    "output": (_out.get("output") or _out.get("error") or "")[:4000],
}))
"""

# btoa is latin-1 only, so source is UTF-8 encoded before base64 -- otherwise a
# single em dash breaks the round trip, and agents are full of them.
EVAL_JS = """
async ({code, consts}) => {
  const enc = (s) => btoa(String.fromCharCode(...new TextEncoder().encode(s)));
  let head = '';
  for (const [k, v] of Object.entries(consts)) {
    head += (typeof v === 'string' && k.endsWith('_B64'))
      ? `${k} = "${enc(v)}"\\n`
      : `${k} = json.loads(${JSON.stringify(JSON.stringify(v))})\\n`;
  }
  return await window.rapp.eval('import json\\n' + head + code);
}
"""


async def open_dish(page, timeout_s: int) -> dict | None:
    await page.goto(VBRAINSTEM, wait_until="domcontentloaded", timeout=90_000)
    await page.wait_for_function("() => !!window.rapp", timeout=120_000)
    return await page.evaluate(
        """async (tries) => {
             for (let i = 0; i < tries; i++) {
               try { const h = await window.rapp.health();
                     if (h && h.status === 'ok') return h; } catch (e) {}
               await new Promise(r => setTimeout(r, 2000));
             }
             return null;
           }""",
        max(1, timeout_s // 2),
    )


async def culture(page, code: str, consts: dict) -> dict:
    """Run one specimen in the dish and parse what it printed."""
    raw = await page.evaluate(EVAL_JS, {"code": code, "consts": consts})
    out = (raw or {}).get("output", "").strip()
    if not out:
        return {"executed": False, "output": "runtime returned nothing"}
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {"executed": False, "output": out[:1000]}


def specimens(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    found = sorted(p for p in target.rglob("*_agent.py") if "__pycache__" not in p.parts)
    return found


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", help="folder of *_agent.py to run in one boot")
    ap.add_argument("--agent", help="a single *_agent.py")
    ap.add_argument("--skill", help="a SKILL.md to convert in-browser then run")
    ap.add_argument("--toaster", help="toaster.py, required with --skill")
    ap.add_argument("--args", default="{}", help="JSON args passed to perform()")
    ap.add_argument("--request", default="run it")
    ap.add_argument("--name", default="Agent", help="display name for --agent")
    ap.add_argument("--routes", action="store_true",
                    help="map which brainstem HTTP routes answer unauthenticated")
    ap.add_argument("--url", default=VBRAINSTEM)
    ap.add_argument("--boot-timeout", type=int, default=300)
    ap.add_argument("--json", action="store_true", help="emit machine-readable results")
    opts = ap.parse_args()

    if opts.skill and not opts.toaster:
        print("--skill needs --toaster (github.com/kody-w/rapp-toaster)", file=sys.stderr)
        return 2

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("playwright missing:\n  pip install playwright && playwright install chromium",
              file=sys.stderr)
        return 2

    args_obj = json.loads(opts.args)
    globals()["VBRAINSTEM"] = opts.url

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            t0 = time.time()
            print(f"petri: {opts.url}")
            health = await open_dish(page, opts.boot_timeout)
            if not health:
                print("DEAD: the dish never came up")
                return 1
            print(f"  alive in {time.time() - t0:.0f}s — CPython "
                  f"{health['runtime'].split()[-1]}, registry {health['registry']}, "
                  f"signed_in={health['signed_in']}\n")

            if opts.routes:
                results = await page.evaluate(
                    """async () => {
                         const gets = ['/health','/version','/agents','/models','/diagnostics'];
                         const out = [];
                         for (const path of gets) {
                           try { const r = await fetch(path);
                                 out.push({path, status:r.status, body:(await r.text()).slice(0,150)}); }
                           catch (e) { out.push({path, status:'ERR', body:String(e).slice(0,120)}); }
                         }
                         try {
                           const r = await fetch('/chat', {method:'POST',
                             headers:{'Content-Type':'application/json'},
                             body: JSON.stringify({user_input:'ping', conversation_history:[]})});
                           out.push({path:'/chat', status:r.status, body:(await r.text()).slice(0,150)});
                         } catch (e) { out.push({path:'/chat', status:'ERR', body:String(e).slice(0,120)}); }
                         return out;
                       }"""
                )
                for r in results:
                    print(f"  {r['path']:<14} {str(r['status']):<4} {r['body']}")
                return 0

            if opts.skill:
                text = Path(opts.skill).read_text(encoding="utf-8")
                res = await culture(page, BUILD_AND_RUN, {
                    "TOASTER_B64": Path(opts.toaster).read_text(encoding="utf-8"),
                    "SKILL_B64": CAPSULE.sub("", GENERATED_BLOCK.sub("", text)),
                    "REQUEST": opts.request, "ARGS_OBJ": args_obj,
                })
                if opts.json:
                    print(json.dumps(res, indent=2))
                else:
                    for k in ("capability_id", "params", "steps", "agent_bytes",
                              "executed", "ran_class"):
                        if k in res:
                            print(f"  {k}: {res[k]}")
                    print("  output:")
                    for line in str(res.get("output", "")).splitlines()[:25]:
                        print("    " + line)
                return 0 if res.get("executed") else 1

            target = Path(opts.dir or opts.agent or ".").expanduser()
            files = specimens(target)
            if not files:
                print(f"no *_agent.py under {target}", file=sys.stderr)
                return 1

            print(f"culturing {len(files)} agent(s)\n")
            report, failed = [], 0
            for path in files:
                started = time.time()
                res = await culture(page, RUN_AGENT, {
                    "AGENT_B64": path.read_text(encoding="utf-8"),
                    "AGENT_NAME": opts.name if opts.agent else path.stem,
                    "REQUEST": opts.request,
                    "ARGS_OBJ": args_obj,
                })
                took = time.time() - started
                ok = bool(res.get("executed"))
                failed += 0 if ok else 1
                report.append({"agent": path.name, "executed": ok,
                               "ran_class": res.get("ran_class"),
                               "seconds": round(took, 1),
                               "output": res.get("output", "")[:2000]})
                if not opts.json:
                    mark = "ok  " if ok else "FAIL"
                    print(f"  {mark} {path.name:<38} {took:5.1f}s  "
                          f"{res.get('ran_class') or ''}")
                    if not ok:
                        for line in str(res.get("output", "")).splitlines()[:6]:
                            print("         " + line)

            if opts.json:
                print(json.dumps({"url": opts.url, "agents": report,
                                  "failed": failed}, indent=2))
            else:
                print(f"\n{len(files) - failed}/{len(files)} executed "
                      f"in one boot, total {time.time() - t0:.0f}s")
            return 1 if failed else 0
        finally:
            await browser.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
