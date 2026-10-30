"""AAOP — Minimal Streamlit UI."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

st.set_page_config(page_title="Cortex Intelligence", layout="wide", initial_sidebar_state="expanded")


def _load_secrets() -> None:
    try:
        for key in ("GROQ_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "STREAMLIT_CLOUD"):
            if key in st.secrets and key not in os.environ:
                os.environ[key] = str(st.secrets[key])
    except Exception:
        pass


_load_secrets()


@st.cache_resource(show_spinner="Loading agent runner...")
def _get_runner():
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
    from core.orchestration.agent_runner import AgentRunner

    return AgentRunner(base_dir=str(BASE_DIR))


@st.cache_data(ttl=30, show_spinner=False)
def _agents_for_env(env: str) -> list[tuple[str, str]]:
    registry_path = BASE_DIR / "configs/registry.yaml"
    if not registry_path.exists():
        return []
    registry = yaml.safe_load(registry_path.read_text()).get("agents", {})
    result = []
    for name, cfg in registry.items():
        version = cfg.get(env)
        if not version and env == "uat":
            version = cfg.get("dev")
        if version and (BASE_DIR / "agents" / name / version).exists():
            result.append((name, version))
    return sorted(result)


def _ask_direct(question: str, agent: str, version: str) -> dict:
    from tools.mock_snowflake import build_agent_context

    doc = ""
    agent_cfg_path = BASE_DIR / "agents" / agent / version / "agent.yaml"
    if agent_cfg_path.exists():
        cfg = yaml.safe_load(agent_cfg_path.read_text())
        ds = cfg.get("data_source", {})
        if ds.get("type") == "snowflake_semantic_view":
            doc = build_agent_context(ds["view"], question)

    result = asyncio.run(_get_runner().run(agent_name=agent, version=version, query=question, document_content=doc))
    answer = result.output or "(no answer)"
    if result.output_parsed and isinstance(result.output_parsed, dict):
        answer = result.output_parsed.get("answer") or result.output
    return {
        "answer": answer,
        "tokens": result.total_tokens,
        "cost_usd": result.total_cost,
        "duration_seconds": result.duration_seconds,
        "status": result.status,
    }


# --- session state ---
for key, default in [("messages", []), ("interaction_log", []), ("session_cost", 0.0), ("_agent_key", "")]:
    if key not in st.session_state:
        st.session_state[key] = default

# --- sidebar ---
with st.sidebar:
    st.title("AAOP")
    env_label = st.radio("Environment", ["DEV", "UAT", "PROD"], horizontal=True)
    env = env_label.lower()

    agents = _agents_for_env(env)
    if not agents:
        st.warning(f"No agents in {env_label}.")
        selected_agent = selected_version = ""
    else:
        labels = [f"{a} ({v})" for a, v in agents]
        idx = st.selectbox("Agent", range(len(labels)), format_func=lambda i: labels[i])
        selected_agent, selected_version = agents[idx]

        if env == "uat":
            registry = yaml.safe_load((BASE_DIR / "configs/registry.yaml").read_text()).get("agents", {})
            if not registry.get(selected_agent, {}).get("uat"):
                st.caption("⚠ UAT not pinned — using DEV version")

    st.caption(f"Session cost: ${st.session_state.session_cost:.6f}")

    if st.button("New Chat", use_container_width=True):
        st.session_state.messages = []

# clear history on agent/env switch
agent_key = f"{env_label}:{selected_agent}:{selected_version}"
if st.session_state._agent_key != agent_key:
    st.session_state.messages = []
    st.session_state._agent_key = agent_key

# --- header ---
st.title("Snowflake Cortex Intelligence")
st.caption(
    "Ask natural-language questions against your Snowflake semantic views. "
    "Each agent is backed by a versioned Snowflake Cortex model — answers are grounded in your data, "
    "not generic LLM knowledge. Select an agent from the sidebar and start asking."
)
st.divider()

# --- tabs ---
log = st.session_state.interaction_log
tab_chat, tab_usage, tab_feedback = st.tabs(["Chat", "Usage", "Feedback"])

with tab_chat:
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if selected_agent and (prompt := st.chat_input("Ask a business question")):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    data = _ask_direct(prompt.strip(), selected_agent, selected_version)
                    st.markdown(data["answer"])
                    st.caption(
                        f"{data['status']} · {data['tokens']} tokens · "
                        f"${data['cost_usd']:.6f} · {data['duration_seconds']:.2f}s"
                    )
                    st.session_state.messages.append({"role": "assistant", "content": data["answer"]})
                    st.session_state.session_cost += data["cost_usd"]
                    st.session_state.interaction_log.append({
                        "id": len(log),
                        "agent": selected_agent,
                        "question": prompt.strip(),
                        "answer": data["answer"],
                        "tokens": data["tokens"],
                        "cost_usd": data["cost_usd"],
                        "duration": data["duration_seconds"],
                        "status": data["status"],
                        "feedback": None,
                    })
                except Exception as exc:
                    st.error(f"Error: {exc}")

with tab_usage:
    if not log:
        st.caption("No interactions yet.")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Runs", len(log))
        c2.metric("Total Tokens", sum(r["tokens"] for r in log))
        c3.metric("Total Cost", f"${sum(r['cost_usd'] for r in log):.6f}")
        df = pd.DataFrame([{
            "agent": r["agent"],
            "question": r["question"][:60] + ("…" if len(r["question"]) > 60 else ""),
            "tokens": r["tokens"],
            "cost_usd": r["cost_usd"],
            "duration": round(r["duration"], 2),
            "status": r["status"],
        } for r in log])
        st.dataframe(df, use_container_width=True)

with tab_feedback:
    if not log:
        st.caption("No interactions yet.")
    else:
        for row in log:
            rated = row["feedback"]
            st.markdown(f"**Q:** {row['question']}")
            st.caption(f"**A:** {row['answer'][:200]}{'…' if len(row['answer']) > 200 else ''}")
            if rated is not None:
                st.caption("✓ Helpful" if rated == 1 else "✓ Not helpful")
            else:
                b1, b2, _ = st.columns([1, 1, 6])
                if b1.button("Helpful", key=f"h_{row['id']}"):
                    row["feedback"] = 1
                    st.rerun()
                if b2.button("Not helpful", key=f"nh_{row['id']}"):
                    row["feedback"] = -1
                    st.rerun()
            st.divider()
