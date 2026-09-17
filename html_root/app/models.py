# API 请求/响应数据模型
from typing import Optional
from pydantic import BaseModel, Field


class AuthModel(BaseModel):
    username: str
    password: str
    captcha: str
    captcha_id: str


class CalcModel(BaseModel):
    matrixA: str
    matrixB: str
    operation: str
    # 可选：来自识别页的视觉描述 Prompt，用于给 Manim 生成代码时补充几何/结构信息
    vision_prompt: Optional[str] = None


class FormulaModel(BaseModel):
    username: str
    latex: str
    note: str = ""


class FormulaUpdateModel(BaseModel):
    id: int
    username: str
    latex: str
    note: str


class AnimationScriptModel(BaseModel):
    username: str
    note: str = ""
    code: str


class AnimationScriptUpdateModel(BaseModel):
    id: int
    username: str
    note: str = ""
    code: str


class UserSettingsModel(BaseModel):
    settings: dict


class UserProfileModel(BaseModel):
    avatar_url: Optional[str] = None
    nickname: Optional[str] = None


class ChangeUsernameModel(BaseModel):
    new_username: str
    password: str


class ChangePasswordModel(BaseModel):
    current_password: str
    new_password: str


class ManimCodeModel(BaseModel):
    code: str


class ManimKeyframeModel(BaseModel):
    code: str
    breakpoint_line: Optional[int] = None  # 1-based, 渲染到该行为止


class ManimCodeEditModel(BaseModel):
    code: str = Field(default="", max_length=40000)
    instruction: str = Field(min_length=1, max_length=3000)
    render_log: Optional[str] = Field(default=None, max_length=12000)  # 渲染日志，纠错意图时传入供模型参考


class AgentRequest(BaseModel):
    prompt: str
    image_base64: Optional[str] = None
    last_user_message: Optional[str] = None
    last_assistant_message: Optional[str] = None


class ExampleVideo(BaseModel):
    filename: str
    title: str
    description: str
    url: str
    poster: str = ""


class AgentTemplateCreate(BaseModel):
    username: str
    name: str = "未命名"
    prompt: str
    steps: list = []
