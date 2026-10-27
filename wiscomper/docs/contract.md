# Shared contract

Python `server/schema.py` is authoritative. World coordinates: visible width16 (-8..8), height9 (-4.5..4.5), y upward; angles radians. All animation state is sampled from absolute seconds, linear interpolation between frames (fields unspecified retain last value); before first frame use base. `draw` is path fraction. 3D uses same units and object fields. Image routes `/api/assets/{asset_id}` only, never external URLs. Formula: latex + optional latex_next (transition at duration/2). UI treats text as text, no HTML.

Scene {version,title,summary,duration,mode,background,objects,steps,controls,camera,assumptions,evidence,selection?}. Proposal {title,summary,recipe,duration,expression,formula,formula_next,labels,parameters,assumptions,needs_clarification,question,scene?,selection?}. `custom` uses a validated generic Scene. Other recipes are computed by trusted Python builders (root). `controls` values submitted to recompute, not client eval.

`selection` contains `engine` (`threejs`, `canvas2d`, `manim`), a short user-facing `reason`, and semantic `category`. Three.js requires mode `3d`; the other engines require `2d`. New model tasks must first call `select_visual_tool`; its result is locked for validation and final output. Explicit dimension preferences require a matching quote from the user's current prompt. Old stored projects may omit selection; the UI identifies their existing renderer without claiming a new model decision.

3D objects support `parent_id` referencing a `group`, with at most eight parent levels and no cycles. Positions and rotations are local to the parent. `rotation_x`, `rotation_y`, and the existing Z `rotation` use Euler XYZ; they are also keyframe fields. Group visibility and opacity propagate to descendants. `torus` lies in XY with major `radius` and smaller `tube_radius`; `cone` uses Y as its axis; `prism` extrudes 3–64 XY polygon vertices across centered Z depth. These new types, parent references and XY rotations are rejected in 2D scenes. Labels project their world position but remain screen-horizontal. All new geometry is created by fixed renderer code, never model-provided JavaScript.

The trusted `fan` recipe builds an axial-fan teaching model with separate stationary and rotating assemblies, pitched solid blades, guards, shaft, and qualitative axial flow. Its controls are `speed` (0.1–1 displayed revolutions/second), `pitch` (0–40 degrees), and `explode` (0–2.5 scene units). Airflow illustrates direction, not computed pressure or volume; no CAD or CFD accuracy is claimed. Other mechanical subjects must use their appropriate custom geometry, not silently substitute this fan.

Trusted `Scene` tracks allow at most 901 keyframes per object and 60,000 across a scene. This supports up to 45 seconds of 20 Hz locally computed wave, pendulum and field motion. Model-authored `Proposal.scene` uses the stricter `ModelScene` / `ModelVisualObject` schema: at most 180 keyframes per object, and no recompute `controls`. Only trusted recipes expose physical recomputation; generic scenes may define up to eight bounded `interactions` as described in [interaction-contract.md](interaction-contract.md). Custom scene duration must equal proposal duration. All schema variants forbid unknown fields, nonfinite values and duplicate object/control IDs; controls require `min < max`, a value within the interval, and `0 < step <= max-min`. Assumptions are limited to 12 entries of 200 characters, and parameter IDs follow the same 64-character identifier rule as object IDs.

Numerical tracks retain physical assumptions: projectile path length reveal and ball position share the same physical-time sampling; the pendulum uses nonlinear RK4 with a step no larger than 1/240 second; wave and rotational field display tracks sample at least 20 Hz. Linear visual interpolation is still an approximation between samples. Physical time and explanatory playback duration are identified in scene assumptions. Dense trusted tracks are summarized, not transmitted in full, when a model continues an existing project; the stored original is preserved.

## HTTP (3088, same-origin local session)
- GET /api/bootstrap -> {csrf,providers:[{id,name,available,message}],samples:[{id,title,description,category,prompt}],renderers:{browser:bool,manim:bool},limits}
- POST /api/assets {data_url} -> {asset_id,url,width,height}
- POST /api/jobs CreateRequest -> {job}
- GET /api/jobs -> {jobs}; GET /api/jobs/{id} -> {job}
- POST /api/jobs/{id}/cancel -> {job}
- GET /api/projects -> {projects}; GET /api/projects/{id} -> {project}
- POST /api/projects/{id}/recompute {parameters} -> {project} (new revision)
- POST /api/projects/{id}/interaction-state {values,camera} -> {project} (local exploration, no model cost)
- POST /api/projects/{id}/export {engine:'browser'|'manim',fps:15|24} -> {job}
- GET /api/projects/{id}/scene -> Scene JSON download
- GET /api/projects/{id}/scene?bundle=true -> {format:'visualize-project',version:1,scene,exploration} JSON download
- GET /api/media/{job_id} -> MP4 private range/attachment on ?download=true
- GET /healthz -> {status:'ok',app:'visualize-dsh'}
All mutations require X-CSRF-Token from bootstrap; fetch same-origin credentials. cookie HttpOnly. No public service binding.

job {id,kind:'create'|'export',status:'queued'|'planning'|'validating'|'building'|'rendering'|'completed'|'failed'|'cancelled'|'needs_input',stage,message,progress:null|0..100,events:[{time,stage,message}],created,updated,project_id?,video_url?,error?}. project {id,title,prompt,asset_id,provider,created,updated,revision,proposal,scene}. Poll only while active; histories private local session (session identity persists across restart).

## Engine API (web/engine.js)
export class ScenePlayer { constructor(host); async load(scene); seek(seconds); play(); pause(); setSpeed(n); setVisible(id,bool); select(id); resize(); dispose(); get time(); get playing(); }.
Dispatch CustomEvent 'scene-time' on host {time,duration,playing}; 'scene-select' {id}. Engine owns canvas/WebGL/LaTeX overlay inside host; host has sized relative layout. Export page web/render.html exposes window.renderReady + window.renderFrame(t), receives scene fetched from same-origin private /api/export-scene/{jobId}, created by server export controller; do not expose arbitrary filesystem paths.

## Model adapter (runtime/planner.py)
capabilities() -> list providers. plan(prompt,provider,asset_path=None,duration=12,previous=None,cancelled=threading.Event(),on_event=callable) -> Proposal dict. on_event({stage,message}). Call through real pinned DSH; bounded tool loop; no arbitrary execution tools. Root validates with Proposal and builds scene. Callback and exception messages must not leak credentials/raw upstream data.
