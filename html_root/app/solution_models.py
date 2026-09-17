"""Shared, bounded data contract for the tutor, browser and trusted Manim scene."""
from typing import List, Literal, Optional, Tuple
import re

from pydantic import BaseModel, Field, confloat, conint, conlist, constr, field_validator, model_validator

Number = confloat(ge=-1e6, le=1e6, allow_inf_nan=False)
ShortText = constr(max_length=240)


class Curve(BaseModel):
    label: ShortText = ""
    points: conlist(Tuple[Number, Number], min_length=2, max_length=401)


class FunctionPlot(BaseModel):
    expression: constr(min_length=1, max_length=180)
    label: ShortText = "f(x)"
    domain: Tuple[Number, Number] = (-5, 5)

    @model_validator(mode="after")
    def valid_domain(self):
        if not 0 < self.domain[1] - self.domain[0] <= 2000:
            raise ValueError("函数采样区间必须递增，跨度不超过 2000")
        return self


class Visual(BaseModel):
    kind: Literal["plot", "matrix", "geometry", "reasoning"] = "reasoning"
    caption: constr(max_length=800) = ""
    curves: conlist(Curve, max_length=6) = Field(default_factory=list)
    functions: conlist(FunctionPlot, max_length=2) = Field(default_factory=list)
    points: conlist(Tuple[Number, Number], max_length=30) = Field(default_factory=list)
    labels: conlist(ShortText, max_length=30) = Field(default_factory=list)
    segments: Optional[conlist(Tuple[conint(strict=True, ge=0), conint(strict=True, ge=0)], max_length=60)] = None
    tangent: bool = False
    area: bool = False
    matrix: Optional[conlist(conlist(Number, min_length=2, max_length=2), min_length=2, max_length=2)] = None

    @model_validator(mode="after")
    def usable_visual(self):
        values = self.model_dump()
        if values.get("kind") == "matrix" and values.get("matrix") is None:
            raise ValueError("matrix visual requires a 2×2 matrix")
        if values.get("kind") == "plot" and not values.get("curves") and not values.get("functions"):
            raise ValueError("plot visual requires sampled curves")
        if values.get("kind") == "geometry" and len(values.get("points", [])) < 2:
            raise ValueError("geometry visual requires at least two vertices")
        if self.segments is not None:
            if self.kind != "geometry" or any(a == b or max(a, b) >= len(self.points) for a, b in self.segments):
                raise ValueError("geometry segments must reference two distinct existing point indices")
        return self


class SolutionStep(BaseModel):
    title: ShortText
    explanation: constr(min_length=1, max_length=2400)
    formula: constr(max_length=1600) = ""
    hint: constr(max_length=600) = ""
    visual: Visual = Field(default_factory=Visual)

    @field_validator("formula")
    @classmethod
    def normalize_formula(cls, value):
        value = value.strip()
        for left, right in [('$$', '$$'), (r'\[', r'\]'), (r'\(', r'\)'), ('$', '$')]:
            if value.startswith(left) and value.endswith(right) and len(value) >= len(left) + len(right):
                value = value[len(left):-len(right)].strip()
                break
        # Some model responses escape commands twice after JSON decoding.
        # Only normalize that pattern outside environments, preserving matrix rows.
        if r"\begin" not in value:
            value = re.sub(r"\\{2}(?=[A-Za-z])", lambda _: "\\", value)
        # Compatibility for equations saved by the former factorization joiner.
        # Only repair its exact separator; arbitrary unknown commands still fail.
        value = value.replace(r"\quad\mathrm{or}\quadx", r"\quad\mathrm{or}\quad x")
        return value


class Solution(BaseModel):
    title: ShortText
    summary: constr(max_length=2400)
    steps: conlist(SolutionStep, min_length=2, max_length=12)
    source: Literal["sympy", "ai"] = "ai"
    verification: constr(max_length=1000) = "AI 推导，请结合题目条件核对。"


class SolveRequest(BaseModel):
    problem: constr(strip_whitespace=True, min_length=1, max_length=6000)
    context: constr(max_length=4000) = ""


class RenderRequest(BaseModel):
    solution: Solution

    @model_validator(mode="after")
    def resolved_visuals(self):
        if any(step.visual.functions for step in self.solution.steps):
            raise ValueError("渲染需要使用解题接口返回的已采样 solution")
        return self
