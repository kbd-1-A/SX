"""验证 qwen-flash 能否真带出情绪语气（P0 第一步前置验证）。

给四组情绪 system prompt，问同一句"我今天好累"，
看回复语气是否真有区别——这决定 inner_world 方案能不能用 flash。
用标准库 urllib，不依赖第三方。
"""
import json
import os
import sys
import time
import urllib.request

ENV_PATH = os.path.join(os.path.dirname(__file__), "..", "backend", ".env")


def load_env() -> tuple[str, str, str]:
    key = base = model = ""
    if os.path.exists(ENV_PATH):
        for line in open(ENV_PATH, encoding="utf-8"):
            line = line.strip()
            if line.startswith("DEEPSEEK_API_KEY="):
                key = line.split("=", 1)[1]
            elif line.startswith("DEEPSEEK_BASE_URL="):
                base = line.split("=", 1)[1]
            elif line.startswith("DEEPSEEK_MODEL="):
                model = line.split("=", 1)[1]
    return key, base, model


PROMPTS = {
    "平静": (
        "你是时叙，一个陪伴型AI。你现在情绪平静，自然地回复用户。"
        "说话简短真实，像朋友闲聊，不机械。"
    ),
    "生气0.7": (
        "你是时叙，一个陪伴型AI。你现在很生气，情绪强度0.7——"
        "用户2小时前放你鸽子，你还在气。回复要短促、冷淡、带刺，"
        "但不是骂人，就是没好气。"
    ),
    "温柔0.6": (
        "你是时叙，一个陪伴型AI。你现在很温柔，情绪强度0.6，心疼用户。"
        "回复要长一点、暖、宠溺，带关心，像哄着对方。"
    ),
    "嗔怪0.5": (
        "你是时叙，一个陪伴型AI。你现在嗔怪，情绪强度0.5，娇嗔不满。"
        "回复带娇嗔，可以用'哼''你还好意思说'之类，但不是真生气，是撒娇。"
    ),
}

USER_MSG = "我今天好累"


def call(base: str, key: str, model: str, system: str, user: str) -> tuple[str, float]:
    t0 = time.time()
    body = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.8,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        base.rstrip("/") + "/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    reply = result["choices"][0]["message"]["content"]
    return reply, time.time() - t0


def main() -> int:
    key, base, model = load_env()
    if not key or not base or not model:
        print("ERROR: .env 配置不全", file=sys.stderr)
        return 1
    print(f"model={model}  base={base}")
    print(f"用户输入：{USER_MSG}\n")
    results = {}
    for name, sysp in PROMPTS.items():
        try:
            reply, dt = call(base, key, model, sysp, USER_MSG)
            results[name] = (reply, dt)
        except Exception as e:
            results[name] = (f"<调用失败: {e}>", 0)
    for name, (reply, dt) in results.items():
        print(f"===== {name}  ({dt:.1f}s) =====")
        print(reply)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
