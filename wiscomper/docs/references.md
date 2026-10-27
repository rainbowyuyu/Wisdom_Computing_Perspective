# Design principles and implementation boundaries

Wiscomper is a standalone visualization workbench with its own runtime, dependencies, data store, and task lifecycle. It can connect to a compatible legacy account database, but it does not import or execute the legacy website. The scene format is defined in the [scene contract](contract.md); model integration is documented in [Runtime](../runtime/README.md).

## Design principles

- **Keep one scene throughout an explanation.** Objects, labels, paths, and camera state share a timeline. Replaying a timestamp should reproduce the same state.
- **Choose the representation for the content.** Spatial structures use Three.js; mathematical transformations can use Manim; diagrams and image annotations use Canvas 2D. Explicit user preferences are considered during tool selection.
- **Keep object identity through revisions.** A local edit can preserve unrelated objects, tracks, interactions, and explanations. Rebuilding a scene is an explicit operation.
- **Separate exploration from calculation.** Bounded controls let users inspect a model. Numerical examples recompute through fixed Python builders rather than treating arbitrary dragging as a physical solution.
- **Explain the assumptions.** Display scale, teaching simplifications, computed quantities, and illustrative motion should be distinguishable.
- **Keep execution bounded.** Model output is validated scene data. The application does not execute model-authored Python, JavaScript, HTML, shaders, or shell commands.

## Rendering and interaction

The browser renderer interprets validated scene objects, samples keyframes from absolute time, draws 2D geometry on Canvas, typesets formulas with local KaTeX, and renders supported 3D geometry with local Three.js. Images are referenced by private, same-origin asset IDs. Formula previews can show the starting and next expression; symbol-matching transformations are provided by the Manim export path.

Objects have stable identifiers, parent relationships, and constrained interaction bindings. Views can rotate, zoom, and inspect supported parts. Interaction state is saved with the project. The [interaction contract](interaction-contract.md) describes the available controls and validation rules.

Preview and browser MP4 export use the same ScenePlayer. Export seeks exact frame times in an isolated browser context, captures the canvas and formula overlays at 1280 × 720, and encodes 15 or 24 fps H.264/yuv420p MP4 with FFmpeg faststart. It supports cancellation and has a deadline. Manim is optional and uses the project's fixed renderer; its availability depends on installed Manim, LaTeX, dvisvgm, and FFmpeg components.

## Numerical examples

The trusted builders implement stated teaching models: sampled functions, projectile motion, a damped nonlinear pendulum, a travelling wave, a rotational velocity field, a Riemann-sum example, single-interface refraction, and a deterministic queue. Their assumptions and parameter bounds belong to the scene output.

Motion builders sample waves, pendulums, and rotational fields at 20 Hz, with up to 901 samples for a 45-second scene and a total limit of 60,000 keyframes. Model-authored tracks are limited to 180 keys per object. Tests cover the undamped pendulum period against an independent elliptic-integral calculation, intermediate rod/bob consistency, high-frequency wave interpolation, and agreement between a projectile path endpoint and its moving object. See the [testing guide](verification.md) for reproducible commands.

## Dependencies and assets

Runtime dependencies are declared in [package.json](../package.json), [requirements.txt](../requirements.txt), and [requirements-manim.txt](../requirements-manim.txt). Model providers are configured separately; credentials and user content are not included in the source distribution.

The Wiscomper logo is a local copy of the original site's brand asset, with provenance recorded in the [asset notes](../web/assets/README.md). Scenes use procedural geometry and user-supplied images. Commercial graphics libraries, source-project media, third-party music, and generated narration are not bundled by these design references.

## Scope

Generic structures, airflow, and mechanical motion are explanatory illustrations unless a scene identifies a specific computed model. They must not be described as measured telemetry, real building monitoring, or safety certification. The built-in examples do not establish arbitrary CAD/BIM ingestion, collision physics, CFD, or structural FEM support.

A single image cannot reliably recover real dimensions or a complete 3D model. Formula display does not prove an arbitrary identity. Additional renderers and engineering data formats require their own contracts, validation, and documented limitations.
