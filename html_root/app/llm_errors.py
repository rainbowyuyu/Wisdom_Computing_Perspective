"""User-facing provider failures, without leaking raw service responses."""
def llm_error_message(error):
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
    return "本次 AI 推导未完成，请重试或补充题目条件。已显示的步骤会保留。"
