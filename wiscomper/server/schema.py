"""Versioned data contract shared by planners, trusted builders and renderers."""
from typing import Literal, Annotated
from pydantic import BaseModel, ConfigDict, Field, model_validator

N = Annotated[float, Field(ge=-10000, le=10000, allow_inf_nan=False)]
Color = Annotated[str, Field(pattern=r'^#[0-9a-fA-F]{6}$')]
Ident = Annotated[str, Field(pattern=r'^[a-zA-Z0-9_-]{1,64}$')]
Assumption = Annotated[str, Field(max_length=200)]
Point = Annotated[list[N], Field(min_length=2, max_length=3)]

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Frame(Strict):
    t: float = Field(ge=0, le=60, allow_inf_nan=False)
    x: N | None = None
    y: N | None = None
    z: N | None = None
    rotation: N | None = None
    rotation_x: N | None = None
    rotation_y: N | None = None
    scale: float | None = Field(default=None, ge=.01, le=20, allow_inf_nan=False)
    opacity: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    draw: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)

class VisualObject(Strict):
    id: Ident
    kind: Literal['circle','rect','line','arrow','path','text','formula','image','box','sphere','cylinder','group','torus','cone','prism']
    parent_id: Ident | None = None
    label: str = Field(default='', max_length=80)
    x: N = 0
    y: N = 0
    z: N = 0
    width: float = Field(default=1, gt=0, le=100, allow_inf_nan=False)
    height: float = Field(default=1, gt=0, le=100, allow_inf_nan=False)
    depth: float = Field(default=1, gt=0, le=100, allow_inf_nan=False)
    radius: float = Field(default=.25, gt=0, le=50, allow_inf_nan=False)
    tube_radius: float = Field(default=.1, gt=0, le=10, allow_inf_nan=False)
    color: Color = '#69e3c0'
    stroke: Color = '#69e3c0'
    filled: bool = True
    line_width: float = Field(default=.035, ge=.005, le=.5, allow_inf_nan=False)
    text: str = Field(default='', max_length=240)
    latex: str = Field(default='', max_length=400)
    latex_next: str = Field(default='', max_length=400)
    asset_id: Ident | None = None
    font_size: float = Field(default=.34, ge=.12, le=1.5, allow_inf_nan=False)
    points: list[Point] = Field(default_factory=list, max_length=600)
    rotation: N = 0
    rotation_x: N = 0
    rotation_y: N = 0
    scale: float = Field(default=1, ge=.01, le=20, allow_inf_nan=False)
    opacity: float = Field(default=1, ge=0, le=1, allow_inf_nan=False)
    draw: float = Field(default=1, ge=0, le=1, allow_inf_nan=False)
    frames: list[Frame] = Field(default_factory=list, max_length=901)

    @model_validator(mode='after')
    def geometry(self):
        if any(len(p) not in (2,3) for p in self.points):
            raise ValueError('坐标点必须包含x、y，可选z。')
        if self.kind in {'line','arrow','path'} and len(self.points)<2:
            raise ValueError('路径至少需要两个点。')
        if self.kind=='image' and not self.asset_id:
            raise ValueError('图片图层必须引用本次上传素材。')
        if self.kind=='torus' and self.tube_radius>=self.radius:
            raise ValueError('环形构件的管半径应小于主半径。')
        if self.kind=='prism':
            if not 3<=len(self.points)<=64 or any(len(p)!=2 for p in self.points):
                raise ValueError('挤出体需要3至64个二维轮廓点。')
            area=sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(self.points,self.points[1:]+self.points[:1]))
            if abs(area)<1e-8:raise ValueError('挤出轮廓需要非零面积。')
        times=[f.t for f in self.frames]
        if times!=sorted(set(times)):
            raise ValueError('关键帧时间必须严格递增。')
        return self

class Step(Strict):
    title: str = Field(max_length=80)
    explanation: str = Field(default='', max_length=600)
    start: float = Field(ge=0, le=60, allow_inf_nan=False)
    end: float = Field(gt=0, le=60, allow_inf_nan=False)
    focus: list[Ident] = Field(default_factory=list, max_length=20)

class Control(Strict):
    id: Ident
    label: str = Field(max_length=40)
    value: N
    min: N
    max: N
    step: float = Field(gt=0, le=1000, allow_inf_nan=False)
    unit: str = Field(default='', max_length=16)

    @model_validator(mode='after')
    def valid_range(self):
        if not self.min<self.max or not self.min<=self.value<=self.max:
            raise ValueError('参数上下限与当前值不一致。')
        if self.step>self.max-self.min:
            raise ValueError('参数步长不能大于可调整范围。')
        return self

class Camera(Strict):
    azimuth: N = .55
    elevation: float = Field(default=.35, ge=-1.56, le=1.56, allow_inf_nan=False)
    distance: float = Field(default=14, ge=3, le=60, allow_inf_nan=False)
    orbit: float = Field(default=.3, ge=-3.14, le=3.14, allow_inf_nan=False)

class InteractionBinding(Strict):
    target_id: Ident
    property: Literal['x','y','z','rotation','rotation_x','rotation_y','scale','opacity','draw']
    multiplier: float = Field(ge=-100,le=100,allow_inf_nan=False)

    @model_validator(mode='after')
    def nonzero(self):
        if self.multiplier==0:raise ValueError('交互绑定必须产生实际变化。')
        return self

class DragBinding(Strict):
    target_id: Ident
    axis: Literal['horizontal','vertical']
    sensitivity: float = Field(ge=.001,le=10,allow_inf_nan=False)

class Interaction(Control):
    kind: Literal['slider','toggle'] = 'slider'
    description: str = Field(default='',max_length=160)
    bindings: list[InteractionBinding] = Field(min_length=1,max_length=24)
    drag: DragBinding | None = None

    @model_validator(mode='after')
    def valid_toggle(self):
        if self.kind=='toggle' and (self.min!=0 or self.max!=1 or self.step!=1 or self.value not in (0,1)):
            raise ValueError('开关只允许0和1两个状态。')
        if self.kind=='toggle' and self.drag:raise ValueError('开关请通过按钮操作，不能绑定连续拖动。')
        return self

class ToolSelection(Strict):
    engine: Literal['threejs','canvas2d','manim']
    reason: str = Field(min_length=1,max_length=240)
    category: Literal['mechanism','spatial','formula','numerical','process','image_annotation']

class Scene(Strict):
    version: Literal[1] = 1
    title: str = Field(min_length=1, max_length=100)
    summary: str = Field(default='', max_length=1000)
    duration: float = Field(default=12, ge=6, le=45, allow_inf_nan=False)
    mode: Literal['2d','3d'] = '2d'
    background: Color = '#0c1420'
    objects: list[VisualObject] = Field(min_length=1, max_length=180)
    steps: list[Step] = Field(default_factory=list, max_length=12)
    controls: list[Control] = Field(default_factory=list, max_length=12)
    interactions: list[Interaction] = Field(default_factory=list,max_length=8)
    camera: Camera = Field(default_factory=Camera)
    assumptions: list[Assumption] = Field(default_factory=list, max_length=12)
    evidence: Literal['schematic','computed','image_annotation'] = 'schematic'
    selection: ToolSelection | None = None

    @model_validator(mode='after')
    def consistency(self):
        ids=[o.id for o in self.objects]
        if len(set(ids))!=len(ids): raise ValueError('图层ID不能重复。')
        nodes={o.id:o for o in self.objects}
        for obj in self.objects:
            if obj.parent_id and (obj.parent_id not in nodes or nodes[obj.parent_id].kind!='group'):
                raise ValueError('父级必须引用当前场景中的构件组。')
        for obj in self.objects:
            visited={obj.id};parent=obj.parent_id
            while parent:
                if parent in visited:raise ValueError('构件层级不能循环引用。')
                if len(visited)>8:raise ValueError('构件嵌套最多8层。')
                visited.add(parent);parent=nodes[parent].parent_id
            if self.mode=='2d' and (obj.parent_id or obj.kind in {'group','torus','cone','prism'} or obj.rotation_x or obj.rotation_y or any((f.rotation_x or f.rotation_y) for f in obj.frames)):
                raise ValueError('空间构件与三轴旋转需要三维场景。')
        if self.selection and (self.selection.engine=='threejs')!=(self.mode=='3d'):
            raise ValueError('选择的工具与场景维度不一致。')
        if sum(len(o.frames) for o in self.objects)>60000:raise ValueError('场景关键帧总量超过限制。')
        control_ids=[c.id for c in self.controls]
        if len(set(control_ids))!=len(control_ids):raise ValueError('参数ID不能重复。')
        interaction_ids=[c.id for c in self.interactions]
        if len(set(interaction_ids))!=len(interaction_ids):raise ValueError('交互ID不能重复。')
        if self.evidence=='computed' and self.interactions:raise ValueError('数值场景请通过可信参数重算，不能任意更改计算结果。')
        drag_targets=set()
        for interaction in self.interactions:
            keys=[(b.target_id,b.property) for b in interaction.bindings]
            if len(keys)!=len(set(keys)):raise ValueError('同一交互不能重复绑定同一对象的属性。')
            for binding in interaction.bindings:
                if binding.target_id not in nodes:raise ValueError('交互引用不存在的图层。')
                if self.mode=='2d' and binding.property in {'z','rotation_x','rotation_y'}:raise ValueError('二维交互不能使用空间自由度。')
                target=nodes[binding.target_id];prop=binding.property
                bounds=(.01,20) if prop=='scale' else (0,1) if prop in {'opacity','draw'} else (-10000,10000)
                values=[getattr(target,prop)]+[getattr(f,prop) for f in target.frames if getattr(f,prop) is not None]
                clip=lambda v:max(bounds[0],min(bounds[1],v))
                if not any(abs(clip(v+(interaction.min-interaction.value)*binding.multiplier)-clip(v+(interaction.max-interaction.value)*binding.multiplier))>1e-9 for v in values):
                    raise ValueError('每个交互绑定在范围内必须能实际改变场景。')
            if interaction.drag:
                ident=interaction.drag.target_id
                if ident not in {b.target_id for b in interaction.bindings}:raise ValueError('拖动对象必须属于当前交互的绑定目标。')
                if ident in drag_targets:raise ValueError('同一对象只能绑定一个拖动自由度。')
                drag_targets.add(ident)
                def renderable(obj):
                    if obj.kind in {'group','text','formula'}:return False
                    parent=obj.id
                    while parent:
                        if parent==ident:return True
                        parent=nodes[parent].parent_id
                    return False
                if not any(renderable(o) for o in self.objects):raise ValueError('拖动目标必须包含可见图形，不能仅是文字或公式。')
        for obj in self.objects:
            if obj.frames and obj.frames[-1].t>self.duration: raise ValueError('关键帧超出动画时长。')
        for step in self.steps:
            if step.end<=step.start or step.end>self.duration: raise ValueError('步骤时间范围不正确。')
            if not set(step.focus)<=set(ids): raise ValueError('步骤引用不存在的图层。')
        return self

Recipe = Literal['diagram','function','projectile','pendulum','wave','field','formula','image','model3d','fan','custom','riemann','refraction','queue']

class ModelVisualObject(VisualObject):
    """Model output stays smaller than trusted locally computed motion tracks."""
    frames: list[Frame] = Field(default_factory=list, max_length=180)

class ModelScene(Scene):
    objects: list[ModelVisualObject] = Field(min_length=1, max_length=180)
    # Custom controls need a trusted recompute implementation to be meaningful.
    controls: list[Control] = Field(default_factory=list, max_length=0)

class Proposal(Strict):
    title: str = Field(min_length=1, max_length=100)
    summary: str = Field(default='', max_length=1000)
    recipe: Recipe
    duration: float = Field(default=12, ge=6, le=45, allow_inf_nan=False)
    expression: str = Field(default='', max_length=300)
    formula: str = Field(default='', max_length=400)
    formula_next: str = Field(default='', max_length=400)
    labels: list[Annotated[str, Field(max_length=64)]] = Field(default_factory=list, max_length=8)
    parameters: dict[Ident,N] = Field(default_factory=dict, max_length=12)
    assumptions: list[Assumption] = Field(default_factory=list, max_length=12)
    needs_clarification: bool = False
    question: str = Field(default='', max_length=600)
    scene: ModelScene | None = None
    selection: ToolSelection | None = None

class CreateRequest(Strict):
    prompt: str = Field(default='', max_length=6000)
    provider: Literal['chatgpt','claude','qwen'] = 'qwen'
    asset_id: Ident | None = None
    duration: Literal[12,20,30] = 12
    sample: str | None = Field(default=None, max_length=64)
    request_key: str = Field(min_length=8, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')
    parent_id: Ident | None = None
    expected_revision: int | None = Field(default=None,ge=1)

    @model_validator(mode='after')
    def valid_iteration(self):
        if self.sample and self.parent_id:raise ValueError('本地示例请新建项目，不能覆盖已有项目。')
        if self.expected_revision is not None and not self.parent_id:raise ValueError('版本校验需要指定正在修改的项目。')
        return self

class UploadRequest(Strict):
    data_url: str = Field(max_length=7000000)

class RecomputeRequest(Strict):
    parameters: dict[Ident,N] = Field(max_length=12)
    expected_revision: int | None = Field(default=None,ge=1)

class RestoreRequest(Strict):
    revision: int = Field(ge=1)
    expected_revision: int = Field(ge=1)

class ExportRequest(Strict):
    engine: Literal['browser','manim'] = 'browser'
    fps: Literal[15,24] = 24

class InteractionStateRequest(Strict):
    values: dict[Ident,N] = Field(default_factory=dict,max_length=8)
    camera: Camera | None = None
    expected_revision: int | None = Field(default=None,ge=1)
