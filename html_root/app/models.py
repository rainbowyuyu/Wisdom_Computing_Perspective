# API 请求/响应数据模型
from typing import Optional
from pydantic import BaseModel, Field


class AuthModel(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=72)
    captcha: str = Field(default="", max_length=12)
    captcha_id: str = Field(default="", max_length=64)
    email: Optional[str] = Field(default=None, max_length=254)
    email_code: Optional[str] = Field(default=None, max_length=12)


class EmailCodeRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    purpose: str = Field(pattern=r'^(register|verify|reset|change_email)$')
    captcha: Optional[str] = Field(default=None, max_length=12)
    captcha_id: Optional[str] = Field(default=None, max_length=64)


class EmailVerifyModel(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    code: str = Field(min_length=4, max_length=12)


class PasswordResetModel(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    code: str = Field(min_length=4, max_length=12)
    new_password: str = Field(min_length=6, max_length=72)


class CalcModel(BaseModel):
    matrixA: str = Field(max_length=6000)
    matrixB: str = Field(max_length=6000)
    operation: str = Field(max_length=40)
    # 可选：来自识别页的视觉描述 Prompt，用于给 Manim 生成代码时补充几何/结构信息
    vision_prompt: Optional[str] = Field(default=None, max_length=4000)


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
    code: str = Field(max_length=40000)


class ManimKeyframeModel(BaseModel):
    code: str = Field(max_length=40000)
    breakpoint_line: Optional[int] = None  # 1-based, 渲染到该行为止


class ManimCodeEditModel(BaseModel):
    code: str = Field(default="", max_length=40000)
    instruction: str = Field(min_length=1, max_length=3000)
    render_log: Optional[str] = Field(default=None, max_length=12000)  # 渲染日志，纠错意图时传入供模型参考


class AgentRequest(BaseModel):
    prompt: str = Field(max_length=6000)
    image_base64: Optional[str] = Field(default=None, max_length=8000000)
    last_user_message: Optional[str] = Field(default=None, max_length=6000)
    last_assistant_message: Optional[str] = Field(default=None, max_length=6000)


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
