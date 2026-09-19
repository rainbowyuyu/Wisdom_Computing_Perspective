"""User-facing provider failures, without leaking raw service responses."""
from openai import APIConnectionError, APITimeoutError
from .usage_guard import UsageDenied

def recoverable_error(error):
    """Never retry missing permissions, exhausted budgets or invalid requests."""
    if isinstance(error,UsageDenied) or getattr(error,'retryable',True) is False:return False
    status=getattr(error,'status_code',None)
    if status is not None and 400<=status<500 and status!=408:return False
    body=getattr(error,'body',{}) or {}
    detail=body.get('error',body) if isinstance(body,dict) else {}
    return not isinstance(detail,dict) or detail.get('code')!='Arrearage'

def llm_error_message(error):
    if isinstance(error, UsageDenied):
        return str(error)
    if isinstance(error, (TimeoutError, APITimeoutError)):
        return "AI 服务响应超时，请重试。题目和已完成的步骤会保留。"
    if isinstance(error, APIConnectionError):
        return "暂时无法连接 AI 服务，请稍后重试。题目和已完成的步骤会保留。"
    body = getattr(error, "body", {}) or {}
    detail = body.get("error", body) if isinstance(body, dict) else {}
    code = detail.get("code", detail.get("type", "")) if isinstance(detail, dict) else ""
    if code == "Arrearage":
        return "阿里云 AI 服务因账户欠费暂不可用，请恢复服务后重试。方程、求导、积分和矩阵等本地计算仍可使用。"
    status = getattr(error, "status_code", None)
    if status in (401, 403):
        return "AI 服务鉴权失败，请检查服务端 ALIYUN_KEY 与模型访问权限。"
    if status == 429:
        return "AI 服务请求过于频繁，请稍后重试。已完成的步骤会保留。"
    if status is not None and status >= 500:
        return "AI 服务暂时繁忙，请稍后重试。题目和已完成的步骤会保留。"
    return "本次 AI 推导未完成，请重试或补充题目条件。已显示的步骤会保留。"
