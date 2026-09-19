"""Fixed Manim program; request data can never supply executable Python."""
import json
import os
from pathlib import Path
import re
import textwrap
import sys

import numpy as np
from manim import *

# Manim runs from an isolated temporary directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from logic.manim_tex import formula, set_tex_step


def label(text, size=24, width=12, color=WHITE):
    item = Text(str(text), font="Microsoft YaHei", font_size=size, color=color)
    if item.width > width: item.scale_to_fit_width(width)
    return item


def prose(text, size=18, width=12):
    """Typeset delimited math inside narration with the same safe TeX helper."""
    parts = re.split(r"(\$\$.*?\$\$|\$[^$]+\$|\\\(.*?\\\)|\\\[.*?\\\])", text, flags=re.S)
    lines, line = VGroup(), VGroup()
    for index, part in enumerate(parts):
        if not part: continue
        if index % 2:
            source = part[2:-2] if part.startswith(('$$', r'\(', r'\[')) else part[1:-1]
            pieces = [formula(source).scale(size/42)]
        else:
            pieces = [label(chunk, size, width) for chunk in textwrap.wrap(part, 14)]
        for piece in pieces:
            if len(line) and line.width + piece.width > width:
                lines.add(line); line = VGroup()
            line.add(piece); line.arrange(RIGHT, buff=.04)
    if len(line): lines.add(line)
    return lines.arrange(DOWN, buff=.12)


PALETTE = [TEAL_A, GOLD_A, BLUE_B, PURPLE_A, RED_A, GREEN_A]


def sequences(visual):
    if visual["kind"] == "plot":
        return [curve["points"] for curve in visual.get("curves", [])]
    points = visual.get("points", [])
    edges = visual.get("segments")
    edges = [[points[a], points[b]] for a, b in edges] if edges is not None else [points]
    return [curve["points"] for curve in visual.get("curves", [])] + edges


def number_line_graph(visual):
    rows = visual.get("rows", [])
    values = [i[k] for row in rows for i in row["intervals"] for k in ("lower", "upper") if i.get(k) is not None]
    low, high = min([0]+values), max([1]+values)
    pad = max((high-low)*.1, 1)
    low -= pad; high += pad
    def point(value, y): return np.array([-2.9+(value-low)/(high-low)*7.8, y, 0])
    result = VGroup()
    gap = min(.66, 3.1/max(len(rows)-1, 1))
    for index, row in enumerate(rows):
        y = 1-index*gap
        color = GOLD_A if index == len(rows)-1 else PALETTE[index % len(PALETTE)]
        result.add(label(row["label"], 16, width=2.7).move_to(np.array([-4.5,y,0])))
        result.add(Line(point(low,y), point(high,y), color=GREY_B, stroke_width=1))
        if not row["intervals"]:
            result.add(label("∅", 20).move_to(point((low+high)/2,y)))
        for interval in row["intervals"]:
            a, b = interval.get("lower"), interval.get("upper")
            start, end = point(low if a is None else a,y), point(high if b is None else b,y)
            if np.linalg.norm(end-start) > 1e-8:
                result.add(Line(start, end, color=color, stroke_width=5))
            for value, location, key, direction in [(a,start,"lower",LEFT), (b,end,"upper",RIGHT)]:
                if value is None:
                    result.add(Arrow(location-direction*.3,location,buff=0,color=color,stroke_width=2,max_tip_length_to_length_ratio=.5))
                else:
                    result.add(Dot(location,radius=.055,color=color) if interval.get(key+"_closed") else Circle(radius=.055,color=color,fill_color="#10182b",fill_opacity=1,stroke_width=2).move_to(location))
                    result.add(label(interval.get(key+"_label") or str(value), 12, width=1.5).next_to(location,DOWN,buff=.12))
    return result


def sequence_key(points):
    return tuple(tuple(point) for point in points)


def stable_axes(steps, kind):
    # Shared bounds prevent the same point from jumping when an auxiliary line,
    # root, or derivative is introduced later in the explanation.
    points = [point for step in steps if step["visual"]["kind"] == kind
              for seq in sequences(step["visual"]) + [step["visual"].get("points", [])] for point in seq]
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    xmin, xmax = min(xs+[0]), max(xs+[0])
    ymin, ymax = min(ys+[0]), max(ys+[0])
    dx, dy = max(xmax-xmin, 1), max(ymax-ymin, 1)
    if kind == "geometry":
        cx, cy = (xmin+xmax)/2, (ymin+ymax)/2
        unit = max(dx / 9, dy / 3.3)
        dx, dy = unit * 9, unit * 3.3
        xmin, ymin = cx-dx/2, cy-dy/2
    axes = Axes(x_range=[xmin-dx*.1, xmin+dx*1.1, dx/4],
                y_range=[ymin-dy*.1, ymin+dy*1.1, dy/4], x_length=9, y_length=3.3,
                tips=False, axis_config={"color": GREY_B, "include_ticks": False}).shift(DOWN*.35)
    marks = VGroup()
    if kind == "plot":
        for value in np.linspace(xmin, xmax, 5):
            marks.add(label(f"{value:.2g}", 12, width=1).next_to(axes.c2p(value, 0), DOWN, buff=.1))
        for value in np.linspace(ymin, ymax, 4):
            marks.add(label(f"{value:.2g}", 12, width=1).next_to(axes.c2p(0, value), LEFT, buff=.1))
    return axes, marks


class SolutionScene(Scene):
    def construct(self):
        self.camera.background_color = "#10182b"
        solution = json.loads(Path(os.environ["WISDOM_SOLUTION_JSON"]).read_text(encoding="utf-8"))
        steps = solution["steps"]
        previous_title = previous_equation = previous_description = None
        graph = VGroup()
        axes = None
        kind = None
        paths, dots, areas = {}, {}, {}
        matrix_shape = matrix_reference = None
        matrix_applied = False
        matrix_value = None
        tracker = None
        for index, step in enumerate(steps):
            set_tex_step(index)
            print(f"WISDOM_CHAPTER:{index}", flush=True)
            v = step["visual"]
            title = VGroup(label(f'{index+1:02d} / {len(steps):02d}', 24),
                           prose(step["title"], 28, width=10)).arrange(RIGHT, buff=.3).set_color(TEAL_A).to_edge(UP, buff=.32)
            equation = formula(step.get("formula", "")).move_to(UP*2.05)
            description = prose(step["explanation"][:240]).to_edge(DOWN, buff=.3)
            transitions = []
            if tracker is not None:
                transitions.append(FadeOut(tracker)); graph.remove(tracker); tracker = None
            if previous_title is None:
                transitions += [FadeIn(title), Write(equation), FadeIn(description)]
            else:
                transitions += [FadeTransform(previous_title, title), FadeTransform(previous_description, description)]
                if isinstance(previous_equation, MathTex) and isinstance(equation, MathTex):
                    # Match individual mathematical glyphs, including those inside
                    # fractions/radicals, without unsafe TeX string splitting.
                    transitions.append(TransformMatchingShapes(previous_equation, equation, path_arc=.12))
                else:
                    transitions.append(ReplacementTransform(previous_equation, equation))
            self.play(*transitions, run_time=1.2)
            previous_title, previous_equation, previous_description = title, equation, description

            animations = []
            if v["kind"] != kind and v["kind"] != "reasoning":
                if len(graph):
                    # Remove old family only when the mathematical space changes.
                    animations.append(FadeOut(graph))
                graph = VGroup()
                paths, dots, areas = {}, {}, {}
                kind = v["kind"]
                matrix_shape = None
                matrix_applied = False
                if kind in ("plot", "geometry"):
                    axes, marks = stable_axes(steps, kind)
                    graph.add(axes, marks)
                    animations.extend([Create(axes), FadeIn(marks)])

            if v["kind"] in ("plot", "geometry"):
                seqs = sequences(v)
                desired = {sequence_key(seq) for seq in seqs if len(seq) >= 2}
                for key in list(paths):
                    if key not in desired:
                        old = paths.pop(key); graph.remove(old); animations.append(FadeOut(old))
                additions = []
                for j, seq in enumerate(seqs):
                    if len(seq) < 2: continue
                    key = sequence_key(seq)
                    if key not in paths:
                        curve = VMobject(color=PALETTE[j % len(PALETTE)], stroke_width=3)
                        curve.set_points_as_corners([axes.c2p(*point) for point in seq])
                        paths[key] = curve; graph.add(curve)
                        additions.append(Create(curve))
                if additions:
                    animations.append(LaggedStart(*additions, lag_ratio=.22))
                desired_dots = {tuple(p) for p in v.get("points", [])}
                for key in list(dots):
                    if key not in desired_dots:
                        old = dots.pop(key); graph.remove(old); animations.append(FadeOut(old))
                for j, point in enumerate(v.get("points", [])):
                    key = tuple(point)
                    if key in dots: continue
                    text = (v.get("labels", []) + [""]*30)[j] if kind == "geometry" else f"({point[0]:.3g}, {point[1]:.3g})"
                    dot = VGroup(Dot(axes.c2p(*point), color=GOLD_A, radius=.055))
                    if text: dot.add(label(text, 15, width=2).next_to(axes.c2p(*point), UP, buff=.16))
                    dots[key] = dot; graph.add(dot); animations.append(FadeIn(dot))
                area_keys = {sequence_key(seq) for seq in seqs} if v.get("area") else set()
                for key in list(areas):
                    if key not in area_keys:
                        old = areas.pop(key); graph.remove(old); animations.append(FadeOut(old))
                if v.get("area"):
                    for seq in seqs:
                        key = sequence_key(seq)
                        if key in areas: continue
                        area = VMobject(fill_color=TEAL_A, fill_opacity=.25, stroke_width=0).set_z_index(-1)
                        graph.add(area); areas[key] = area
                        def accumulate(mob, alpha, seq=seq):
                            position = alpha*(len(seq)-1)
                            end = min(int(position), len(seq)-2)
                            cursor = np.array(seq[end]) + (position-end)*(np.array(seq[end+1])-seq[end])
                            values = [[seq[0][0], 0]] + seq[:end+1] + [cursor, [cursor[0], 0], [seq[0][0], 0]]
                            mob.set_points_as_corners([axes.c2p(*p) for p in values])
                        animations.append(UpdateFromAlphaFunc(area, accumulate, rate_func=linear))
                tangent_ok = v.get("tangent") and len(seqs) == 2 and len(seqs[0]) == len(seqs[1]) and np.allclose(np.array(seqs[0])[:,0], np.array(seqs[1])[:,0])
                if tangent_ok:
                    fn, derivative = np.array(seqs[0]), np.array(seqs[1])
                    tracker = VGroup(Dot(color=GOLD_A, radius=.07), Line(LEFT, RIGHT, color=GOLD_A))
                    def follow(mob, alpha):
                        x = fn[0,0]+alpha*(fn[-1,0]-fn[0,0])
                        y = np.interp(x, fn[:,0], fn[:,1]); slope = np.interp(x, derivative[:,0], derivative[:,1])
                        half = min((fn[-1,0]-fn[0,0])*.08, (axes.y_range[1]-axes.y_range[0])*.12/max(abs(slope),1))
                        mob[0].move_to(axes.c2p(x,y))
                        mob[1].put_start_and_end_on(axes.c2p(x-half,y-slope*half), axes.c2p(x+half,y+slope*half))
                    animations.append(UpdateFromAlphaFunc(tracker, follow, rate_func=linear))
                    graph.add(tracker)
                elif not additions and not animations and paths:
                    # A retained curve stays in place while attention moves to a
                    # computed root or a geometrical relation.
                    animations.append(Indicate(next(reversed(dots.values())) if dots else next(iter(paths.values())), color=GOLD_A, scale_factor=1.015))

            elif v["kind"] == "number_line":
                new_graph = number_line_graph(v)
                animations.append(ReplacementTransform(graph,new_graph) if len(graph) else FadeIn(new_graph))
                graph = new_graph
            elif v["kind"] == "matrix":
                m = np.array(v["matrix"], dtype=float)
                if matrix_shape is None:
                    vertices = [(0,0),(1,0),(1,1),(0,1)]
                    matrices = [np.array(s["visual"]["matrix"], dtype=float) for s in steps if s["visual"]["kind"] == "matrix"]
                    values = np.concatenate([np.array(vertices).T] + [a @ np.array(vertices).T for a in matrices], axis=1)
                    xmin, xmax = min(-.5, values[0].min()-.5), max(1.5, values[0].max()+.5)
                    ymin, ymax = min(-.5, values[1].min()-.5), max(1.5, values[1].max()+.5)
                    unit = min(8/(xmax-xmin), 3.1/(ymax-ymin))
                    axes = NumberPlane(x_range=[xmin,xmax,(xmax-xmin)/8], y_range=[ymin,ymax,(ymax-ymin)/6], x_length=(xmax-xmin)*unit, y_length=(ymax-ymin)*unit,
                                       background_line_style={"stroke_opacity":.22}).shift(DOWN*.4)
                    def basis_shape(a):
                        return VGroup(Polygon(*[axes.c2p(*(a@np.array(p))) for p in vertices], color=TEAL_A, fill_opacity=.25),
                                      Line(axes.c2p(0,0), axes.c2p(*(a@np.array([1,0]))), color=GOLD_A, stroke_width=5),
                                      Line(axes.c2p(0,0), axes.c2p(*(a@np.array([0,1]))), color=BLUE_B, stroke_width=5))
                    matrix_shape = basis_shape(np.eye(2))
                    matrix_reference = matrix_shape.copy().set_opacity(.2)
                    graph.add(axes, matrix_reference, matrix_shape)
                    animations.extend([Create(axes), Create(matrix_shape), FadeIn(matrix_reference)])
                elif not matrix_applied or not np.array_equal(matrix_value, m):
                    animations.append(Transform(matrix_shape, basis_shape(m), path_arc=0))
                    matrix_applied = True; matrix_value = m.copy()
                else:
                    animations.append(Indicate(matrix_shape, color=GOLD_A, scale_factor=1.02))
            else:
                # Algebra-only problems focus on the evolving equation itself.
                animations.append(Indicate(equation, color=TEAL_A, scale_factor=1.03))

            if animations: self.play(*animations, run_time=2.6)
            else: self.wait(2.6)
            self.wait(1.2)
