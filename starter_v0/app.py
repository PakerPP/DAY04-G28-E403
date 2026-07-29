"""Streamlit UI for the Research Agent.

Reuses `run_model_tool_loop` from chat.py so the UI, the CLI (`chat.py`), and
the eval harness (`run_eval.py`) all drive the exact same agent loop and the
same `artifacts/system_prompt.md` / `artifacts/tools.yaml` declarations.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

try:
    # chat.py's run_model_tool_loop prints tool names with an emoji; on Windows
    # the default console codepage (cp1252) can't encode it and crashes the run.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from chat import ROOT, ARTIFACTS_DIR, run_model_tool_loop, write_transcript, trim_history, now_iso, safe_slug
from providers import make_provider
from tools import load_tool_declarations, to_openai_tools
from versioning import artifact_version_dict, build_artifact_version

RUNS_DIR = ROOT / "runs"
TRANSCRIPTS_DIR = ROOT / "transcripts"

TOKEN_PATTERN = re.compile(r"\b\d{6,10}:[A-Za-z0-9_-]{30,}\b")
BEARER_PATTERN = re.compile(r"(Bearer|Authorization[:=]\s*Bearer)\s+[A-Za-z0-9._-]+", re.IGNORECASE)

PROVIDER_LABELS = {
    "openrouter": "🟣 OpenRouter",
    "openai": "🟢 OpenAI",
    "anthropic": "🟠 Anthropic",
    "gemini": "🔵 Gemini",
}
TOOL_ICONS = {
    "clarify": "❓",
    "get_twitter": "🐦",
    "timeline": "🐦",
    "social_search": "🔎",
    "lookup": "🌐",
    "fetch": "📄",
    "format": "📝",
    "send": "📨",
    "policy": "📚",
    "papers": "📑",
    "paper_text": "📖",
}
QUICK_START = [
    ("🔎 Research bình thường", "Tin tức AI hôm nay có gì nổi bật?"),
    ("❓ Thiếu thông tin", "Tóm tắt 5 tweet mới nhất giúp mình"),
    ("📤 Hành động nhạy cảm", "Đẩy bản tin AI hôm nay lên Telegram giúp mình"),
]


def tool_icon(name: str) -> str:
    return TOOL_ICONS.get(name, "🔧")


def redact(value: Any) -> Any:
    if isinstance(value, str):
        value = TOKEN_PATTERN.sub("[REDACTED_TOKEN]", value)
        value = BEARER_PATTERN.sub("[REDACTED_AUTH]", value)
        return value
    if isinstance(value, dict):
        return {key: redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def format_args(args: dict[str, Any] | None) -> str:
    args = args or {}
    return ", ".join(f"{key}={value!r}" for key, value in args.items())


def render_rounds(rounds: list[dict[str, Any]]) -> None:
    for round_record in rounds:
        calls = round_record.get("tool_calls") or []
        results = round_record.get("tool_results") or []
        if not calls:
            continue
        for call, event in zip(calls, results):
            result = redact(event.get("result", {}))
            args = redact(event.get("args", call.get("args", {})))
            is_error = isinstance(result, dict) and bool(result.get("error"))
            is_wait = isinstance(result, dict) and bool(result.get("awaiting_user"))
            label = f"{tool_icon(call['name'])} {call['name']}({format_args(call.get('args'))})"
            with st.status(label, state="error" if is_error else "complete", expanded=is_error):
                meta_cols = st.columns([1, 3])
                meta_cols[0].caption(f"Round {round_record['round']}")
                if is_wait:
                    meta_cols[1].badge("đang chờ người dùng", icon="⏸️", color="orange")
                elif is_error:
                    meta_cols[1].badge("lỗi", icon="❌", color="red")
                else:
                    meta_cols[1].badge("thành công", icon="✅", color="green")
                col1, col2 = st.columns(2)
                with col1:
                    st.caption("Args")
                    st.json(args)
                with col2:
                    st.caption("Result")
                    st.json(result)


def queue_prompt(text: str) -> None:
    st.session_state["pending_prompt"] = text


st.set_page_config(page_title="Research Agent Console", page_icon="🔎", layout="wide")

with st.sidebar:
    st.markdown("### ⚙️ Cấu hình")
    provider_name = st.selectbox(
        "Provider", list(PROVIDER_LABELS), format_func=lambda key: PROVIDER_LABELS[key],
    )
    model_override = st.text_input("Model (tuỳ chọn)", value="", placeholder="để trống = dùng mặc định")
    version_label = st.text_input(
        "Version label", value="v_ui",
        help="Nhãn version để ghi vào transcript, ví dụ v0/v1/v2/v3",
    )
    with st.expander("🔧 Nâng cao"):
        max_tool_rounds = st.slider("Max tool rounds", 1, 10, 4)
        history_window = st.slider("History window", 0, 20, 5, help="Số cặp lượt user/assistant giữ lại làm ngữ cảnh")
    st.divider()
    reset_clicked = st.button("🔄 Bắt đầu phiên mới", type="primary", use_container_width=True)
    st.caption("🔒 Token/API key nhạy cảm được tự động ẩn trước khi hiển thị hoặc lưu transcript.")

system_prompt_path = ARTIFACTS_DIR / "system_prompt.md"
tools_path = ARTIFACTS_DIR / "tools.yaml"
system_prompt_text = system_prompt_path.read_text(encoding="utf-8")
tool_declarations = load_tool_declarations(tools_path)
openai_tools = to_openai_tools(tool_declarations)
artifact_version = build_artifact_version(version_label or "manual", system_prompt_path, tools_path)

try:
    provider = make_provider(provider_name)
except Exception as exc:
    st.error(f"Không khởi tạo được provider `{provider_name}`: {exc}")
    st.stop()

selected_model = model_override.strip() or getattr(provider, "default_model", None)

st.session_state.setdefault("turns", [])
st.session_state.setdefault("history", [])
st.session_state.setdefault("transcript", None)
st.session_state.setdefault("transcript_path", None)


def start_new_session() -> None:
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
    transcript_id = "_".join([safe_slug(version_label or "manual"), safe_slug(provider_name), timestamp])
    path = TRANSCRIPTS_DIR / f"{transcript_id}.transcript.json"
    st.session_state.transcript_path = path
    st.session_state.transcript = {
        "transcript_id": transcript_id,
        **artifact_version_dict(artifact_version),
        "provider": provider_name,
        "model": selected_model,
        "system_prompt": str(system_prompt_path),
        "tools": str(tools_path),
        "history_window": int(history_window),
        "max_tool_rounds": int(max_tool_rounds),
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "ui": "streamlit",
        "turns": [],
    }
    st.session_state.turns = []
    st.session_state.history = []


if reset_clicked or st.session_state.transcript is None:
    start_new_session()

head_col, badge_col = st.columns([5, 1])
with head_col:
    st.markdown("## 🔎 Research Agent Console")
    st.caption(
        "Trợ lý nghiên cứu: tra tin theo từ khóa/tài khoản, đọc URL, tổng hợp digest — "
        "luôn hỏi lại khi thiếu thông tin và xác nhận trước khi gửi ra ngoài."
    )
with badge_col:
    st.badge("Sẵn sàng", icon="🟢", color="green")

with st.expander("🧰 Tool đang bật cho agent"):
    for item in tool_declarations:
        st.markdown(f"**{tool_icon(item['name'])} `{item['name']}`** — {item.get('description', '')}")

with st.container(border=True):
    top_cols = st.columns(4)
    top_cols[0].metric("🔌 Provider", PROVIDER_LABELS[provider_name].split(" ", 1)[1])
    top_cols[1].metric("🧠 Model", selected_model or "-")
    top_cols[2].metric("🧬 Artifact version", artifact_version.artifact_version)
    top_cols[3].metric("📝 Transcript", st.session_state.transcript_path.name if st.session_state.transcript_path else "-")

tab_chat, tab_compare = st.tabs(["💬 Live Chat", "📊 So sánh version"])

with tab_chat:
    if not st.session_state.turns:
        st.markdown("#### 👋 Bắt đầu nhanh")
        st.caption("Bấm một gợi ý bên dưới, hoặc gõ câu hỏi của riêng bạn ở khung chat cuối trang.")
        sugg_cols = st.columns(3)
        for col, (label, example) in zip(sugg_cols, QUICK_START):
            col.button(label, use_container_width=True, help=example, on_click=queue_prompt, args=(example,))

    for turn in st.session_state.turns:
        with st.chat_message("user", avatar="🧑"):
            st.write(turn["user"])
        with st.chat_message("assistant", avatar="🤖"):
            st.write(turn.get("assistant_text") or "_(không có phản hồi văn bản)_")
            status = turn.get("status")
            if status == "waiting_for_user":
                st.info("⏸ Agent đang chờ bạn bổ sung thông tin trước khi tiếp tục.")
            elif status == "provider_error":
                st.error(turn.get("error", "Lỗi provider không xác định."))
            elif status == "max_tool_rounds":
                st.warning("Đã dừng vì chạm giới hạn số round tool cho phép.")
            if turn.get("rounds"):
                render_rounds(turn["rounds"])

with tab_compare:
    st.caption("Chọn 2 file (run JSON của run_eval.py hoặc transcript JSON của chat/UI) để so sánh cùng một scenario qua các version khác nhau.")
    candidates: list[tuple[str, Path]] = []
    if RUNS_DIR.exists():
        candidates += [("RUN", p) for p in sorted(RUNS_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)]
    if TRANSCRIPTS_DIR.exists():
        candidates += [("TRANSCRIPT", p) for p in sorted(TRANSCRIPTS_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)]

    if not candidates:
        st.info("Chưa có run/transcript nào được lưu trong `runs/` hoặc `transcripts/`.")
    else:
        labels = [f"[{kind}] {path.name}" for kind, path in candidates]

        def render_candidate(index: int) -> None:
            kind, path = candidates[index]
            data = json.loads(path.read_text(encoding="utf-8"))
            with st.container(border=True):
                st.markdown(f"**{path.name}**")
                st.badge(data.get("artifact_version", "?"), icon="🧬", color="violet")
                if kind == "RUN":
                    summary = data.get("summary", {})
                    metric_keys = [
                        "case_accuracy", "tool_routing_accuracy", "argument_accuracy",
                        "multiturn_accuracy", "provider_error_cases", "measured_cases", "total_cases",
                    ]
                    st.json({key: summary.get(key) for key in metric_keys})
                    with st.expander("Chi tiết từng case"):
                        st.json(redact(data.get("results", [])))
                else:
                    for turn in data.get("turns", []):
                        st.markdown(f"— **User:** {turn.get('user')}")
                        st.markdown(f"  **Agent:** {turn.get('assistant_text')}")
                        if turn.get("rounds"):
                            render_rounds(turn["rounds"])

        col_a, col_b = st.columns(2)
        with col_a:
            idx_a = st.selectbox("File A", range(len(labels)), format_func=lambda i: labels[i], key="cmp_a")
        with col_b:
            default_b = 1 if len(labels) > 1 else 0
            idx_b = st.selectbox("File B", range(len(labels)), index=default_b, format_func=lambda i: labels[i], key="cmp_b")

        c1, c2 = st.columns(2)
        with c1:
            render_candidate(idx_a)
        with c2:
            render_candidate(idx_b)

prompt = st.chat_input("Nhập yêu cầu nghiên cứu... (vd: 'Tweet mới nhất của Sam Altman là gì?')")
if not prompt:
    prompt = st.session_state.pop("pending_prompt", None)

if prompt:
    turn_record: dict[str, Any] = {
        "turn_index": len(st.session_state.turns) + 1,
        "started_at": now_iso(),
        "user": prompt,
        "status": "started",
        "assistant_text": None,
        "rounds": [],
        "tool_events": [],
    }
    messages = [
        {"role": "system", "content": system_prompt_text},
        *trim_history(st.session_state.history, int(history_window)),
        {"role": "user", "content": prompt},
    ]
    with st.spinner("Agent đang xử lý..."):
        try:
            result = run_model_tool_loop(
                provider=provider,
                messages=messages,
                tools=openai_tools,
                model=model_override.strip() or None,
                max_tool_rounds=int(max_tool_rounds),
            )
            turn_record.update(result)
            st.session_state.history.append({"role": "user", "content": prompt})
            st.session_state.history.append({"role": "assistant", "content": result.get("assistant_text", "")})
        except Exception as exc:
            turn_record.update({
                "status": "provider_error",
                "assistant_text": None,
                "error": f"{type(exc).__name__}: {exc}",
            })
    turn_record["ended_at"] = now_iso()
    st.session_state.turns.append(turn_record)
    st.session_state.transcript["turns"].append(redact(turn_record))
    write_transcript(st.session_state.transcript_path, st.session_state.transcript)
    st.rerun()
