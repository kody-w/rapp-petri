#!/usr/bin/env python3
"""rapp-petri — culture RAPP agents in a sterile, headless vbrainstem.

Boots the browser vBrainstem from a URL in headless Chromium, then drops agents
into a synthetic vbrainstem file. No install, no brainstem service, no
credentials. Same dispatch surface the live page uses.

    petri.py                              boot only -- is the dish alive?
    petri.py --dir ./agents               discover every *_agent.py in ONE boot
    petri.py --agent ship_agent.py        discover one agent
    petri.py --routes                     map the brainstem's HTTP surface
    petri.py --self-test-dead             prove a blank page is rejected

Boot costs once; every agent after that is fast, which is what makes --dir
usable as a test suite rather than a demo.

Exit code is 0 only if the dish boots and every supplied agent is discovered.
Non-zero is a usable CI gate.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import http.server
import re
import sys
import time
import threading
from pathlib import Path

VBRAINSTEM = "https://kody-w.github.io/vbrainstem/"

async def open_dish(page, timeout_s: int) -> dict | None:
    await page.goto(VBRAINSTEM, wait_until="domcontentloaded", timeout=90_000)
    try:
        await page.wait_for_function(
            "() => !!(window.vbrainstem && window.vbrainstem.dispatch)",
            timeout=min(max(timeout_s, 5) * 1000, 120_000),
        )
    except Exception:
        return None
    return await page.evaluate(
        """async (tries) => {
             for (let i = 0; i < tries; i++) {
               try {
                 const r = await window.vbrainstem.dispatch('GET', '/health');
                 if (r && r.status === 200 && r.json &&
                     (r.json.status === 'ok' || r.json.status === 'unauthenticated')) {
                   return r.json;
                 }
               } catch (e) {}
               await new Promise(r => setTimeout(r, 2000));
             }
             return null;
           }""",
        max(1, timeout_s // 2),
    )


def specimens(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    found = sorted(p for p in target.rglob("*_agent.py") if "__pycache__" not in p.parts)
    return found


def agent_name(source: str) -> str:
    for match in re.finditer(r"self\.name\s*=\s*(['\"])([^'\"\n{}]+)\1", source):
        return match.group(2)
    return ""


def fence(source: str) -> str:
    ticks = max((len(m.group(0)) for m in re.finditer(r"`+", source)), default=2) + 1
    mark = "`" * max(3, ticks)
    return f"{mark}python\n{source.rstrip()}\n{mark}"


def person_file(files: list[Path]) -> tuple[str, list[dict]]:
    entries = []
    blocks = []
    for path in files:
        source = path.read_text(encoding="utf-8")
        name = agent_name(source)
        if not name:
            entries.append({"agent": path.name, "discovered": False, "output": "no plain self.name assignment"})
            continue
        entries.append({"agent": path.name, "expected": name, "discovered": False})
        blocks.append(f"### agents/{path.name}\n\n{fence(source)}\n")
    today = time.strftime("%Y-%m-%d")
    text = "\n".join([
        "---",
        'name: "petri"',
        'description: "Synthetic petri dish file."',
        'license: "MIT"',
        'compatibility: "vbrainstem"',
        "metadata:",
        '  id: "vb-petri"',
        '  owner: "rapp-petri"',
        f'  created: "{today}"',
        f'  updated: "{today}"',
        "---",
        "",
        "# Petri",
        "",
        "## Who I am",
        "",
        "A sterile CI file for testing vbrainstem tool discovery.",
        "",
        "## My tools",
        "",
        "- (none)",
        "",
        "## Memory",
        "",
        "- (nothing yet)",
        "",
        "## Memory (older)",
        "",
        "- (nothing yet)",
        "",
        "## Storage",
        "",
        *blocks,
    ])
    return text, entries


async def culture_files(page, files: list[Path]) -> list[dict]:
    text, report = person_file(files)
    await page.evaluate(
        """async (text) => {
             localStorage.clear();
             localStorage.setItem('vbrainstem.file', text);
           }""",
        text,
    )
    health = await page.evaluate(
        """async () => (await window.vbrainstem.dispatch('GET', '/health')).json"""
    )
    agents = set(health.get("agents") or [])
    for item in report:
        expected = item.get("expected")
        if expected:
            item["discovered"] = expected in agents
            item["output"] = "listed in /health" if item["discovered"] else "not listed in /health"
    return report


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def blank_server() -> tuple[http.server.ThreadingHTTPServer, str]:
    class Handler(QuietHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<!doctype html><title>blank</title><p>no dish</p>")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_port}/"


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
    ap.add_argument("--self-test-dead", action="store_true",
                    help="prove a page without vbrainstem dispatch fails the boot check")
    ap.add_argument("--url", default=VBRAINSTEM)
    ap.add_argument("--boot-timeout", type=int, default=300)
    ap.add_argument("--json", action="store_true", help="emit machine-readable results")
    opts = ap.parse_args()

    if opts.skill and not opts.toaster:
        print("--skill needs --toaster (github.com/kody-w/rapp-toaster)", file=sys.stderr)
        return 2
    if opts.self_test_dead:
        server, url = blank_server()
        try:
            opts.url = url
            opts.boot_timeout = min(opts.boot_timeout, 5)
        finally:
            pass

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
                if opts.self_test_dead:
                    print("SELF-TEST OK: a blank page was rejected as dead")
                    return 0
                print("DEAD: the dish never came up")
                return 1
            print(f"  alive in {time.time() - t0:.0f}s — vbrainstem {health.get('version')}, "
                  f"status={health.get('status')}, agents={len(health.get('agents') or [])}\n")

            if opts.self_test_dead:
                print("SELF-TEST FAILED: a blank page was accepted as a dish", file=sys.stderr)
                return 1

            if opts.routes:
                results = await page.evaluate(
                    """async () => {
                         const gets = ['/health','/version','/agents','/models','/diagnostics'];
                         const out = [];
                         for (const path of gets) {
                           try { const r = await window.vbrainstem.dispatch('GET', path);
                                 out.push({path, status:r.status, body:JSON.stringify(r.json).slice(0,150)}); }
                           catch (e) { out.push({path, status:'ERR', body:String(e).slice(0,120)}); }
                         }
                         try {
                           const r = await window.vbrainstem.dispatch('POST', '/chat', {user_input:'ping', conversation_history:[]});
                           out.push({path:'/chat', status:r.status, body:JSON.stringify(r.json).slice(0,150)});
                         } catch (e) { out.push({path:'/chat', status:'ERR', body:String(e).slice(0,120)}); }
                         return out;
                       }"""
                )
                for r in results:
                    print(f"  {r['path']:<14} {str(r['status']):<4} {r['body']}")
                return 0

            if opts.skill:
                print("--skill conversion belonged to the retired Pyodide dish; current vbrainstem exposes file/tool discovery and canonical chat dispatch.", file=sys.stderr)
                return 2

            if not (opts.dir or opts.agent):
                return 0

            target = Path(opts.dir or opts.agent).expanduser()
            files = specimens(target)
            if not files:
                print(f"no *_agent.py under {target}", file=sys.stderr)
                return 1

            print(f"culturing {len(files)} agent(s)\n")
            started = time.time()
            report = await culture_files(page, files)
            failed = len([item for item in report if not item.get("discovered")])
            took = time.time() - started
            if not opts.json:
                for item in report:
                    mark = "ok  " if item.get("discovered") else "FAIL"
                    print(f"  {mark} {item['agent']:<38} {took:5.1f}s  "
                          f"{item.get('expected') or ''}")
                    if not item.get("discovered"):
                        print("         " + item.get("output", "not discovered"))

            if opts.json:
                print(json.dumps({"url": opts.url, "agents": report,
                                  "failed": failed}, indent=2))
            else:
                print(f"\n{len(files) - failed}/{len(files)} discovered "
                      f"in one boot, total {time.time() - t0:.0f}s")
            return 1 if failed else 0
        finally:
            if opts.self_test_dead:
                server.shutdown()
            await browser.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
