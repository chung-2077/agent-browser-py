from __future__ import annotations


def to_ai_friendly_error(error: Exception, selector: str) -> Exception:
    """
    将 Playwright 的错误转换为对 AI 友好的提示。
    """
    message = str(error)

    if "strict mode violation" in message:
        return Exception(
            f'选择器 "{selector}" 匹配到多个元素，请使用更精确的选择器或先执行 snapshot。'
        )

    if "intercepts pointer events" in message:
        return Exception(
            f'元素 "{selector}" 被遮挡，可能存在弹窗/遮罩，请先处理遮挡元素。'
        )

    if "not visible" in message and "Timeout" not in message:
        return Exception(f'元素 "{selector}" 不可见，请检查是否被隐藏或滚动到可见区域。')

    if "waiting for" in message and ("to be visible" in message or "Timeout" in message):
        return Exception(f'元素 "{selector}" 未找到或不可见，请先执行 snapshot 获取最新元素。')

    return error
