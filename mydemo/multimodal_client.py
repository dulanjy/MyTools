import os, re, sys, json, hashlib
from typing import Optional, List, Tuple
from zai import ZhipuAiClient

# 优先级：环境变量 > keyring 凭据 (service='zhipu', username='api_key')
try:
    import keyring  # type: ignore
except ImportError:  # 允许未安装 keyring 时继续运行（但只支持环境变量）
    keyring = None  # noqa: A001

COORD_PATTERN = re.compile(r"\[\[(\d+),(\d+),(\d+),(\d+)\]\]")
BOX_TAG_PATTERN = re.compile(r"<\|begin_of_box\|>|<\|end_of_box\|>")


def sanitize_api_key(key: str) -> str:
    """去除首尾空白与包裹引号。"""
    k = key.strip()
    if (k.startswith("\"") and k.endswith("\"")) or (k.startswith("'") and k.endswith("'")):
        k = k[1:-1]
    return k


def debug_key_info(key: str):
    if not os.getenv("API_KEY_SOURCE_DEBUG"):
        return
    h = hashlib.sha256(key.encode()).hexdigest()[:8]
    print(f"[DEBUG] key_len={len(key)} sha256_8={h}")

def extract_box(text: str) -> Optional[List[int]]:
    m = COORD_PATTERN.search(text.replace(" ", ""))
    if m:
        return list(map(int, m.groups()))
    return None

def resolve_api_key(env_name: str = "ZHIPU_API_KEY",
                    service: str = "zhipu",
                    username: str = "api_key") -> str:
    """返回 API Key。

    优先顺序：
    1. 环境变量 ZHIPU_API_KEY (或传入的 env_name)
    2. keyring（如果已安装并存储）

    用户首次使用可运行:  python -m mydemo.setup_keyring_api_key  (见单独脚本)
    """
    val = os.getenv(env_name)
    if val:
        val = sanitize_api_key(val)
        if os.getenv("API_KEY_SOURCE_DEBUG"):
            print(f"[DEBUG] 使用来源: 环境变量 {env_name}")
            debug_key_info(val)
        return val
    if keyring is not None:
        try:
            stored = keyring.get_password(service, username)
            if stored:
                stored = sanitize_api_key(stored)
                if os.getenv("API_KEY_SOURCE_DEBUG"):
                    print("[DEBUG] 使用来源: keyring 凭据 (service='zhipu')")
                    debug_key_info(stored)
                return stored
        except Exception as e:  # pragma: no cover - keyring 运行期异常
            print(f"[WARN] 读取 keyring 失败: {e}", file=sys.stderr)
    raise RuntimeError(
        "未找到 API Key。可选方式:\n"
        f"1) 设置环境变量 {env_name}\n"
        f"2) 安装 keyring 并执行 python mydemo/setup_keyring_api_key.py 录入密钥\n"
        "3) 临时：运行前使用 `$env:ZHIPU_API_KEY='xxx'` (PowerShell)\n"
    )


def clean_answer(text: str) -> str:
    """移除模型添加的 box 标签并 strip。"""
    return BOX_TAG_PATTERN.sub("", text).strip()


def call_model(image_url: str,
               question: str,
               model: str = "glm-4.5v",
               stream: bool = True,
               show_reasoning: bool = True,
               api_key_env: str = "ZHIPU_API_KEY") -> dict:
    api_key = resolve_api_key(api_key_env)

    client = ZhipuAiClient(api_key=api_key)

    messages = [{
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": image_url}},
            {"type": "text", "text": question}
        ]
    }]

    # thinking enabled 仅在需要可解释时
    kwargs = {
        "model": model,
        "messages": messages,
        "thinking": {"type": "enabled"} if show_reasoning else {"type": "disabled"},
        "stream": stream
    }

    final_text_parts: List[str] = []
    reasoning_parts: List[str] = []
    printed_reasoning_header = False

    try:
        if stream:
            resp = client.chat.completions.create(**kwargs)
            for chunk in resp:
                delta = chunk.choices[0].delta
                if show_reasoning and getattr(delta, "reasoning_content", None):
                    part = delta.reasoning_content
                    reasoning_parts.append(part)
                    if not printed_reasoning_header:
                        print("[Reasoning] ", end="", flush=True)
                        printed_reasoning_header = True
                    print(part, end="", flush=True)
                if getattr(delta, "content", None):
                    part = delta.content
                    final_text_parts.append(part)
                    print(part, end="", flush=True)
            print()
            full_answer = "".join(final_text_parts)
        else:
            resp = client.chat.completions.create(**kwargs)
            message = resp.choices[0].message
            # SDK 结构假设：message.content 是最终文本
            full_answer = getattr(message, "content", str(message))
            print(full_answer)
    except Exception as e:
        err_str = str(e)
        print("调用失败：", err_str, file=sys.stderr)
        hints = None
        if "401" in err_str:
            hints = (
                "检测到 401：请确认密钥是否最新、未过期；检查是否粘贴多余空白；确认该账户已开通模型权限；"
                "可先用基础模型 glm-4 测试；必要时重新生成密钥并更新 keyring。"
            )
        return {"error": err_str, "hints": hints, "error_code": 401 if "401" in err_str else None}

    cleaned = clean_answer(full_answer)
    box = extract_box(cleaned)
    return {
        "answer_raw": full_answer,
        "answer_clean": cleaned,
        "box": box,
        "reasoning": "".join(reasoning_parts) if show_reasoning else None
    }

if __name__ == "__main__":
    try:
        result = call_model(
            image_url="https://cloudcovert-1305175928.cos.ap-guangzhou.myqcloud.com/%E5%9B%BE%E7%89%87grounding.PNG",
            question="Where is the second bottle of beer from the right on the table? Provide coordinates in [[xmin,ymin,xmax,ymax]] format",
            stream=True,
            show_reasoning=True
        )
    except RuntimeError as e:  # 来自 resolve_api_key 或其他显式抛出的运行期错误
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:  # 兜底未知异常
        print(f"[ERROR] 未预期的异常: {e}", file=sys.stderr)
        sys.exit(2)
    else:
        print("\nParsed JSON:", json.dumps(result, ensure_ascii=False, indent=2))