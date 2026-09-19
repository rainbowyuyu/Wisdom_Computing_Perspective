"""Bounded task plans: backward dependencies form a DAG, never executable code."""
from pydantic import BaseModel, Field, model_validator, StrictInt
from typing import Literal


class MathJobRequest(BaseModel):
    problem: str = Field(min_length=1, max_length=6000)
    context: str = Field(default='', max_length=4000)
    auto_render: bool = True
    force_decompose: bool = False
    request_key: str = Field(pattern=r'^[a-zA-Z0-9_-]{8,80}$')


class MathSubtask(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    goal: str = Field(min_length=1, max_length=600)
    depends_on: list[StrictInt] = Field(default_factory=list, max_length=5)


class MathTaskPlan(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    status: Literal['ready','needs_information'] = 'ready'
    message: str = Field(default='', max_length=600)
    tasks: list[MathSubtask] = Field(default_factory=list, max_length=6)

    @model_validator(mode='after')
    def valid_dependencies(self):
        if self.status == 'ready' and not self.tasks:
            raise ValueError('拆解计划至少需要一个子目标')
        for index, task in enumerate(self.tasks):
            if len(set(task.depends_on)) != len(task.depends_on) or any(type(i) is not int or i < 0 or i >= index for i in task.depends_on):
                raise ValueError('依赖只能引用当前子任务之前的任务序号，不能重复或形成循环')
        return self
