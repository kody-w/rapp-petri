# rapp-petri

Culture RAPP agents in a sterile, headless brainstem.

`petri.py` boots the Pyodide [vBrainstem](https://kody-w.github.io/vbrainstem/)
in headless Chromium and drops your agents into it. No install. No brainstem
service. No credentials. No local Python for the agents themselves — the same
runtime that answers on a real machine, running in a browser you never see.

```console
$ petri.py --dir ./agents
petri: https://kody-w.github.io/vbrainstem/
  alive in 4s — CPython 3.12.1, registry RAR, signed_in=False

culturing 4 agent(s)

  ok   knowledge_companion_agent.py             0.0s  KnowledgeCompanionAgent
  ok   knowledge_ingest_agent.py                0.0s  KnowledgeIngestAgent
  ok   program_corpus_agent.py                  0.1s  ProgramCorpusAgent
  ok   sharepoint_loader_agent.py               0.0s  SharePointLoaderAgent

4/4 executed in one boot, total 4s
```

Boot is paid once. Every agent after it costs milliseconds — which is the
difference between a demo and a test suite. Twenty-three agents also complete
in about four seconds.

## Why this exists

A RAPP agent is a single `*_agent.py` with a typed contract and a `perform()`.
Testing one has meant installing a brainstem, which means the test depends on
the machine it runs on — and "works on mine" is not a result.

The vBrainstem already solves the runtime half: it is the real brainstem
compiled to WebAssembly, served as a static page. `rapp-petri` is the other
half — the harness that drives it with no human in front of it, so a folder of
agents can be executed and asserted from CI, a laptop with pip blocked, or a
host that has no shell at all.

The agent never touches disk. Its source travels as a string into
`brainstem_web.rapp_run()`, the same entry the brainstem uses after it resolves
a registry slug.

## Install

```bash
pip install playwright && playwright install chromium
curl -O https://raw.githubusercontent.com/kody-w/rapp-petri/main/petri.py
```

One file, one dependency.

## Use

```bash
petri.py                                  # boot only — is the dish alive?
petri.py --dir ./agents                   # run every *_agent.py in ONE boot
petri.py --agent ship_agent.py --args '{"repo":"demo"}'
petri.py --skill ship/SKILL.md --toaster toaster.py
petri.py --routes                         # map the brainstem HTTP surface
petri.py --dir ./agents --json            # machine-readable, for CI
```

Exit code is `0` only when every agent executed, so it gates a build directly.

### SKILL.md in, agent out, in the browser

[`rapp-toaster`](https://github.com/kody-w/rapp-toaster) is stdlib-only, so the
whole conversion runs client-side too — a raw `SKILL.md` becomes an agent and
executes without either file ever existing on disk:

```console
$ petri.py --skill ship/SKILL.md --toaster toaster.py --args '{"repo":"demo-site"}'
  capability_id: ddd317502185
  params: ['marker', 'repo', 'sensible_kebab_name', 'url']
  steps: 9
  agent_bytes: 13100
  executed: True
  ran_class: ShipAgent
```

That `capability_id` is the value the toaster reports for the same skill
locally. The browser-built agent is not similar to the local one — it is the
same capability.

## What answers without a credential

`--routes` maps it. Measured against the live dish:

| route | | |
|---|---|---|
| `GET /health` | 200 | version, model, soul path, agents, quarantine list |
| `GET /version` | 200 | `{"version":"0.6.16"}` |
| `GET /agents` | 200 | the loaded agent files |
| `GET /models` | 200 | gpt-4.1, gpt-4o, gpt-4o-mini, claude-sonnet-4, … |
| `GET /diagnostics` | 200 | the real event log, timestamped |
| `POST /chat` | **500** | `Not authenticated. Visit /login to sign in with GitHub.` |

So the split is clean, and worth stating plainly rather than glossing:

- **Agent execution and the entire read side of the brainstem need nothing.**
  That is the part CI can run on every push, with no secret.
- **`/chat` — the model loop, routing, memory — needs a sign-in.** The route is
  live; it wants a token. `/login` and `/login/poll` are a device-code flow, so
  it is scriptable, but it is not free.

Known gap: `POST /surgeon/complete` returns an nginx `405`, not a brainstem
JSON error — the request escapes the in-page interceptor and hits the static
host. That route is in the brainstem's table but is not currently served
in-browser.

## CI

```yaml
- run: pip install playwright && playwright install --with-deps chromium
- run: python petri.py --dir ./agents
```

No service to stand up, no secret to mount, no runtime to match. The dish is a
URL.

## How it works

```
petri.py ──▶ headless Chromium ──▶ kody-w.github.io/vbrainstem
                                      └─ Web Worker
                                          └─ Pyodide ── CPython 3.12
                                              └─ brainstem_web.rapp_run(source, …)
```

The worker takes the agent source as a string, scans it for pip dependencies,
installs them, `exec`s it, finds the `BasicAgent` subclass and calls `perform`.
Scratch files land outside `agents/`, so a cultured agent never leaks into a
later conversation.

Agent source is UTF-8 encoded before base64 on the way in — `btoa` is latin-1
only, and agents are full of em dashes.

## Related

- [vbrainstem](https://github.com/kody-w/vbrainstem) — the brainstem in Pyodide
- [rapp-toaster](https://github.com/kody-w/rapp-toaster) — SKILL.md ⇄ agent.py
- [rapp-skills](https://github.com/kody-w/rapp-skills) — portable skills, each
  shipping the agent it converts to

## License

MIT
