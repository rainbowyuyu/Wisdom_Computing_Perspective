# Native visual planning runtime

This directory is self-contained within this project. It uses the exact npm
dependency `@deepseek-ai/dsh@0.2.0-rc.2`. Install root dependencies with `npm ci`.
Node 22.19+ or 24+ is required. Python dependencies belong to the project's venv.

`planner.capabilities()` returns configuration-only provider availability, without
network discovery. `planner.plan(prompt, provider, asset_path=None, duration=12,
previous=None, cancelled=None, on_event=None)` returns a raw Proposal mapping.
The caller must still validate it with `server.schema.Proposal`, authorize assets
and run the trusted builder. `asset_path` is a server-owned path, never model input.
Its filename stem must be the asset ID. `previous` may be a previous Proposal or
Scene mapping. `PlannerError.code` is stable; messages are safe for the local UI.
Long previous scenes are sent as explicitly marked context summaries: object
identity, initial state, controls, interactions and metadata are retained, while long paths and
keyframe lists are uniformly sampled. Full project rendering data is unchanged.
Sparse keyframe state is carried forward before sampling so an omitted keyframe
does not erase the meaning of later samples. The exact previous Proposal/Scene is
sent privately to the local bridge for merging, never included in model prompts.

Existing-project changes use a typed `{edit:{mode:"patch",base_id,...changes}}`
envelope. The selection tool supplies the exact base hash and edit guide. Patches
can update/add/remove custom objects by stable ID, explicitly replace interaction
or step lists, update metadata, or partially update trusted recipe parameters.
Everything omitted retains the exact original data, including full paths and
keyframes. The host rescales retained custom frame/step times if duration changes;
new tracks use the new duration. Title/summary/assumption edits reach the custom
scene unless explicitly overridden in `scene_updates`. Existing exploration values
remain context rather than being baked a second time into unchanged geometry.

Ordinary edits inherit their engine, category and recipe. Intentional reconstruction
uses `edit_strategy=rebuild` and `{edit:{mode:"rebuild",base_id,reason,proposal}}`;
an unmarked whole-scene replacement is rejected. Clarifications remain possible.
The merger validates the expanded Proposal before the existing short confirmation
step, then returns a full Proposal to Python. No extra model step is introduced.
Host input/output remain bounded at 8 MB; generated submissions are capped at
600 KB and merged candidates at 7.5 MB. Oversized exact bases fail explicitly.

The bridge explicitly composes the official Cordis Context, LLM, Session, Session
Projection, Agent, SystemPrompt, Tools, pi-ai adapter and native AgentLoop. The
only registered tools are `select_visual_tool` and `check_proposal`. It has no
profile loader, shell, filesystem tools, arbitrary execution, MCP, plugin loading,
title generation, compaction model, automatic provider switching or retries.

The first model step calls `select_visual_tool` with its semantic classification
of the actual goal, subject and explicit dimension preference. This tool returns
the capability catalog and a binding `selection` (engine, category and reason).
Mechanical/spatial goals default to Three.js 3D; formulas recommend Manim 2D;
numerical tasks use trusted computed recipes; relationships and image annotation
use Canvas 2D. Explicit user 2D/3D preference takes precedence and must cite the
current request. There is no keyword trigger that replaces arbitrary equipment
with a sample. The trusted `fan` recipe is only for an axial fan; other devices
use an appropriate custom solid model (or the electric-motor recipe when exact).
The numerical catalog also includes fixed `y=x²` Riemann sums, Snell-law
refraction/total internal reflection, and a deterministic single-server D/D/1
queue. Their small parameter sets and scientific assumptions come from trusted
builders; adding these recipes does not enable arbitrary generated simulation.

The second step checks the proposal against the accepted route. A successful check
stores an immutable snapshot and returns its SHA-256 `proposal_id` plus a short
`final_response`. The third step returns that exact `{"accept_proposal":"..."}`
acknowledgement, avoiding a second long scene serialization. The host resolves the
reference only after a normally completed turn and validates the snapshot again.
An invalid check clears the saved reference. Full final Proposal JSON remains
supported for repairs and compatibility, and is always validated. Timeout,
cancellation, partial JSON and an unknown/stale ID cannot adopt a saved candidate.
The route cannot be changed after selection. Proposal and custom
scene must copy the returned selection. Three.js custom scenes require actual
volumetric primitives; a mechanical scene also needs multiple solid parts and
part/group motion from keyframes or effective transform interactions. Flat cards,
labels or camera motion alone cannot satisfy it.

Custom scenes may define content-specific `interactions` (at most 8, normally
1–4), separate from trusted recipe `controls`. Each slider or toggle adds bounded
offsets to named object properties; a coupled gear angle, a limited joint or an
assembly-axis separation can be explored without another model call. Optional
dragging targets an explicitly bound object or a group with rendered descendants.
The selection tool returns this capability guide, and the same proposal check
validates IDs, dimensionality, toggle ranges, drag ownership, effective clipped
ranges and duplicate bindings. Geometry, arbitrary expressions, executable code
and formula strings cannot be bound. Computed scenes retain trusted controls only.
Custom `controls` stay empty, and older scenes default to no interactions. Static
formula/image content need not invent freedoms. See
[`docs/interaction-contract.md`](../docs/interaction-contract.md) for the shared
renderer, persistence and export semantics.

Each invocation has at most 3 model calls, 8192 output tokens per call, 8 tool
executions and a 120-second total child-process deadline. The third model step
must produce the final acknowledgement or repaired proposal. A native request-boundary guard prevents the
fourth network call; provider retry policy is zero. Reasoning is locally capped
at low (preserving off/minimal) to fit the interactive deadline. This never writes
to the user's model preferences. Cancellation terminates the owned process tree.
Server task admission and longer-term budgets remain the caller's responsibility.

Provider selection is fresh per invocation:

- ChatGPT: CC Switch's current Codex provider ID from its settings, falling back
  only to one `is_current` row. Credentials and endpoint stay paired. The current
  Codex model/effort is used only when its endpoint matches the selected snapshot.
- Claude: current `.claude/settings.json`; an explicit `ANTHROPIC_AUTH_TOKEN`
  takes precedence over `ANTHROPIC_API_KEY`, including a blank token failing closed.
- Qwen on Windows: current `.codex/tools/qwen/config.json` metadata and the global
  `Load-Qwen.ps1`. Each Qwen client starts through `runtime/qwen-launch.ps1` in a
  fresh, profile-free PowerShell invocation, dot-sources that loader, and launches
  Node in the same process. The loader decrypts the current-user DPAPI file afresh.
  Python never receives the plaintext key, and inherited Qwen/auth/proxy/Node-hook
  variables are discarded. Loader output is suppressed; failures return a fixed
  safe code. No global preferences or credentials are changed.
- Qwen on Linux: reads the existing server-owned `DASHSCOPE_API_KEY`,
  `QWEN_API_KEY` or legacy `ALIYUN_KEY` (in that order). The key is passed only
  through the private Node child's environment, never command arguments, browser
  responses or audit records. No Windows files need to be copied to the server.
  Both paths share the same official-endpoint, redirect and bounded-step guards.
- Explicit project `.env`/process overrides: `VISUALIZATION_CHATGPT_MODEL`,
  `VISUALIZATION_CHATGPT_BASE_URL`, `VISUALIZATION_CHATGPT_API_KEY` (all required
  together), optional `_API` (`openai-responses` or `openai-completions`) and
  `_EFFORT`. Claude uses the same names with `CLAUDE`, defaults to
  `anthropic-messages`, and `_AUTH=bearer` or `api-key`. Environment values override
  `.env.local`, `.env`, then deployment defaults in `.env.deploy`; interpolation
  is disabled. Never commit a populated `.env` or `.env.local`.

Qwen defaults to `qwen-plus` for text/formulas and `qwen3-vl-plus` whenever an
authorized image is present, including inherited project image context. This is
image understanding and declarative visualization planning, not a Qwen-Image
raster-generation endpoint. Both defaults support native function calling.
`VISUALIZATION_QWEN_MODEL` and `VISUALIZATION_QWEN_VISION_MODEL` can pin an
appropriate official Qwen model/snapshot; operators must choose a model supporting
function calling and, for the latter, image input. These overrides are syntax
checked locally; no discovery or paid capability probe runs. Optional
`VISUALIZATION_QWEN_BASE_URL` accepts only the standard HTTPS
`/compatible-mode/v1` endpoint on `dashscope.aliyuncs.com`,
`dashscope-intl.aliyuncs.com`, or `dashscope-us.aliyuncs.com`. The account region
must match the chosen endpoint. The unsupported `VISUALIZATION_QWEN_API_KEY`, alternate `_API`/`_AUTH`,
third-party gateways, arbitrary paths and loopback endpoints are rejected for
Qwen. The private Node process restricts network requests to that exact official
Chat Completions endpoint and disables redirects.

Qwen uses the native pi-ai Chat Completions adapter with `max_tokens`,
`enable_thinking:false`, streaming usage, and the `system` role. It omits OpenAI
`store`, strict-tool-schema flags, `reasoning_effort` and `tool_stream`.
Tool choice stays at the documented `auto` default and parallel calls at the
documented `false` default; the existing required-tool and step guards still apply.
`required` is not a supported reliable Qwen tool-choice strategy. No model/provider
fallback or extra request is added. The same exact-scene edit merger, short
confirmation, budget, image limits, cancellation tree and sanitized audit apply.

Qwen's configuration status checks only local configuration and DSH runtime
(plus loader, encrypted-file presence/size and PowerShell on Windows). It does not decrypt a Windows key, test
remote authentication, verify account region or confirm model access. The public
message explicitly says remote authentication/model permissions are unverified.
Do not label this state “connected” or “verified”.

Official documentation checked for the adapter contract:
[text models](https://help.aliyun.com/zh/model-studio/text-generation-model),
[vision models](https://help.aliyun.com/zh/model-studio/vision-model),
[function calling](https://help.aliyun.com/zh/model-studio/qwen-function-calling),
[Chat Completions parameters](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions),
[image content](https://help.aliyun.com/zh/model-studio/vision),
[thinking controls](https://help.aliyun.com/zh/model-studio/deep-thinking), and
[regional base URLs](https://help.aliyun.com/zh/model-studio/base-url).

The child receives only an OS environment allowlist and the selected provider
configuration. Credentials never appear in argv, stdin, browser responses or raw
provider diagnostics. Remote endpoints require HTTPS; loopback HTTP supports local
ChatGPT/Claude gateways and tests. Qwen retains its stricter official-host restriction.
CC Switch and global provider configuration are read-only.

`DSH_HOME` is `data/dsh-home`. Native `session/event` records are copied into
`audit/<session-id>.jsonl` with image binary data, credentials and provider error
details removed. The audit identifies itself as a sanitized copy with
`automaticReplay:false`. It is not a restorable DSH session or a second execution
authority. An abrupt hard cancellation can leave an incomplete audit; the server's
job state records cancellation. Uploaded image attachments may be normalized by
the official attachment component into local files, never full base64 audit data.

Validation is offline:

```powershell
.venv/Scripts/python.exe -m pytest tests/test_planner.py tests/test_qwen.py -q
npm run test:runtime
```

Tests run the real pinned Harness against local synthetic OpenAI Responses,
OpenAI Chat and Anthropic SSE servers. They cover tool call/result lifecycle,
schema repair, image admission, previous context, three-call bounds, cancellation,
deadline, provider error redaction and absence of automatic retries. They do not
contact real model endpoints.
Qwen tests run the actual PowerShell wrapper against a synthetic loader and a
test-only localhost fetch interceptor; they never read/decrypt the real key or
connect to DashScope. They also cover fragmented tool arguments, final empty
`choices` usage chunks, automatic vision selection, exact incremental edits,
official-route restrictions, safe loader failure and PowerShell/Node cancellation.
