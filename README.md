# rapp-petri

Culture RAPP agents in a sterile, headless brainstem.

`petri.py` boots the browser [vBrainstem](https://kody-w.github.io/vbrainstem/)
in headless Chromium and drops your agents into a synthetic vbrainstem file. No
install. No brainstem service. No credentials. The same browser dispatch surface
that answers on the live page, running in a browser you never see.

```console
$ petri.py --dir ./agents
petri: https://kody-w.github.io/vbrainstem/
  alive in 1s — vbrainstem 1.0.0, status=unauthenticated, agents=0

culturing 4 agent(s)

  ok   knowledge_companion_agent.py             0.1s  KnowledgeCompanionAgent
  ok   knowledge_ingest_agent.py                0.1s  KnowledgeIngestAgent
  ok   program_corpus_agent.py                  0.1s  ProgramCorpusAgent
  ok   sharepoint_loader_agent.py               0.1s  SharePointLoaderAgent

4/4 discovered in one boot, total 1s
```

Boot is paid once. Every agent after it costs milliseconds — which is the
difference between a demo and a test suite. Twenty-three agents also complete
in about four seconds.

## Why this exists

A RAPP agent is a single `*_agent.py` with a typed contract and a `perform()`.
Testing one has meant installing a brainstem, which means the test depends on
the machine it runs on — and "works on mine" is not a result.

The vBrainstem already solves the browser half: it is a static page with the
same dispatch boundary the browser uses for `/health`, `/agents`, `/models`,
and `/chat`. `rapp-petri` is the other half — the harness that drives it with no
human in front of it, so a folder of agents can be asserted from CI, a laptop
with pip blocked, or a host that has no shell at all.

The agent never touches disk. Its source is embedded into a synthetic
vbrainstem file under `## Storage`, the same place browser vBrainstem discovers
tools a person's file carries. The gate fails if the dish does not boot or if an
agent is not discovered by `/health`.

## Install

```bash
pip install playwright && playwright install chromium
curl -O https://raw.githubusercontent.com/kody-w/rapp-petri/main/petri.py
```

One file, one dependency.

## Use

```bash
petri.py                                  # boot only — is the dish alive?
petri.py --dir ./agents                   # discover every *_agent.py in ONE boot
petri.py --agent ship_agent.py
petri.py --routes                         # map the brainstem HTTP surface
petri.py --dir ./agents --json            # machine-readable, for CI
petri.py --self-test-dead                 # prove a blank page is rejected
```

Exit code is `0` only when the dish boots and every supplied agent is discovered,
so it gates a build directly. The retired Pyodide dish executed `perform()`
inside the browser; current vBrainstem is a browser file/tool surface plus
canonical chat dispatch, so unauthenticated CI checks discovery, not model
execution.

## What answers without a credential

`--routes` maps it. Measured against the live dish:

| route | | |
|---|---|---|
| `GET /health` | 200 | version, model, soul state, agents, quarantine list |
| `GET /agents` | 200 | the loaded factory and file-carried agents |
| `GET /models` | 200 | gpt-4.1, gpt-4o, gpt-4o-mini, claude-sonnet-4, … |
| `POST /chat` | 400/401 | asks for a file or sign-in before model chat |

So the split is clean, and worth stating plainly rather than glossing:

- **Boot, read-side dispatch, and file-carried agent discovery need nothing.**
  That is the part CI can run on every push, with no secret.
- **`/chat` — the model loop, routing, memory — needs a file and usually a
  sign-in.** The route is live; it wants the same context the page needs.

## CI

```yaml
- run: pip install playwright && playwright install --with-deps chromium
- run: python petri.py --self-test-dead
- run: python petri.py --dir ./agents
```

No service to stand up, no secret to mount, no runtime to match. The dish is a
URL.

## How it works

```
petri.py ──▶ headless Chromium ──▶ kody-w.github.io/vbrainstem
                                      └─ window.vbrainstem.dispatch
                                          ├─ GET /health
                                          ├─ GET /agents
                                          └─ synthetic file Storage agent discovery
```

`petri.py` builds a temporary vbrainstem file in browser storage, places each
agent source under `## Storage`, and asks the page's own `/health` dispatch what
agents it can see. A cultured agent never writes to the repository or to a real
Brainstem folder.

## Related

- [vbrainstem](https://github.com/kody-w/vbrainstem) — the browser Brainstem file surface
- [rapp-skills](https://github.com/kody-w/rapp-skills) — portable skills, each
  shipping the agent it converts to

## License

MIT
