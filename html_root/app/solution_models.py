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


class CirclePlot(BaseModel):
    center: Tuple[Number, Number]
    radius: confloat(gt=0, le=1e4, allow_inf_nan=False)
    label: ShortText = ""


class NumberInterval(BaseModel):
    lower: Optional[Number] = None
    upper: Optional[Number] = None
    lower_closed: bool = False
    upper_closed: bool = False
    lower_label: ShortText = ""
    upper_label: ShortText = ""

    @model_validator(mode="after")
    def ordered(self):
        if self.lower is not None and self.upper is not None and self.lower > self.upper:
            raise ValueError("区间下界不得大于上界")
        return self


class NumberLineRow(BaseModel):
    label: ShortText
    intervals: conlist(NumberInterval, max_length=8) = Field(default_factory=list)


class Visual(BaseModel):
    kind: Literal["plot", "matrix", "geometry", "number_line", "reasoning"] = "reasoning"
    caption: constr(max_length=800) = ""
    curves: conlist(Curve, max_length=6) = Field(default_factory=list)
    functions: conlist(FunctionPlot, max_length=2) = Field(default_factory=list)
    points: conlist(Tuple[Number, Number], max_length=30) = Field(default_factory=list)
    labels: conlist(ShortText, max_length=30) = Field(default_factory=list)
    segments: Optional[conlist(Tuple[conint(strict=True, ge=0), conint(strict=True, ge=0)], max_length=60)] = None
    tangent: bool = False
    area: bool = False
    matrix: Optional[conlist(conlist(Number, min_length=2, max_length=2), min_length=2, max_length=2)] = None
    circles: conlist(CirclePlot, max_length=4) = Field(default_factory=list)
    rows: conlist(NumberLineRow, max_length=10) = Field(default_factory=list)

    @model_validator(mode="after")
    def usable_visual(self):
        values = self.model_dump()
        if values.get("kind") == "matrix" and values.get("matrix") is None:
            raise ValueError("matrix visual requires a 2×2 matrix")
        if values.get("kind") == "plot" and not values.get("curves") and not values.get("functions"):
            raise ValueError("plot visual requires sampled curves")
        if values.get("kind") == "geometry" and len(values.get("points", [])) < 2 and not self.circles and not self.curves:
            raise ValueError("geometry visual requires at least two vertices")
        if self.kind == "number_line" and not self.rows:
            raise ValueError("数轴需要至少一行区间")
        if self.circles and (self.kind != "geometry" or len(self.circles) + len(self.curves) > 6):
            raise ValueError("圆应放入 geometry，圆与曲线合计不超过六条")
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


class ParameterConstraint(BaseModel):
    label: ShortText
    left: constr(min_length=1, max_length=180)
    relation: Literal["<", "<=", ">", ">=", "=", "!="]
    right: constr(min_length=1, max_length=180)


class ExactInterval(BaseModel):
    lower: Optional[constr(min_length=1, max_length=80)] = None
    upper: Optional[constr(min_length=1, max_length=80)] = None
    lower_closed: bool = False
    upper_closed: bool = False


class ParameterAnalysis(BaseModel):
    variable: constr(pattern=r"^[a-zA-Z]$")
    constraints: conlist(ParameterConstraint, min_length=1, max_length=8)
    answer: conlist(ExactInterval, max_length=8)


class Solution(BaseModel):
    title: ShortText
    summary: constr(max_length=2400)
    steps: conlist(SolutionStep, min_length=2, max_length=12)
    source: Literal["sympy", "ai", "curriculum"] = "ai"
    verification: constr(max_length=1000) = "AI 推导，请结合题目条件核对。"
    parameter_analysis: Optional[ParameterAnalysis] = None
    completion: Literal['solved', 'partial', 'needs_information'] = 'solved'
    next_tasks: conlist(constr(min_length=1, max_length=240), max_length=4) = Field(default_factory=list)
    task_goal: constr(max_length=600) = ''


class SolveRequest(BaseModel):
    problem: constr(strip_whitespace=True, min_length=1, max_length=6000)
    context: constr(max_length=4000) = ""


class RenderRequest(BaseModel):
    solution: Solution

    @model_validator(mode="after")
    def resolved_visuals(self):
        if any(step.visual.functions or step.visual.circles for step in self.solution.steps):
            raise ValueError("渲染需要使用解题接口返回的已采样 solution")
        return self
