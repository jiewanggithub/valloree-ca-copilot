"""Streamlit demo:  streamlit run app.py"""
import json

import streamlit as st

from ca_copilot.data import load_cases, load_clients, load_products
from ca_copilot.pipeline import Generator
from ca_copilot.schema import SCENARIO_LABELS, Request, Scenario, Turn

st.set_page_config(page_title="Vallorée CA Copilot", layout="wide")
st.title("瓦洛蕾 Vallorée · CA 话术助手")
st.caption("Fictional brand · generates three WeChat message options for a Client Advisor")

clients, products, cases = load_clients(), load_products(), load_cases()
case_map = {f"{r.case_id} · {m['focus'][:30]}": r for r, m in cases}

qp = st.query_params  # e.g. ?case=G04&run=1 preloads a test case and generates immediately
keys = ["(custom)"] + list(case_map)
qi = next((i for i, k in enumerate(keys) if k.split(" · ")[0] == qp.get("case")), 0)
with st.sidebar:
    preset = st.selectbox("从测试用例载入 / Load a test case", keys, index=qi)
    base = case_map.get(preset)

col1, col2 = st.columns([1, 1])
with col1:
    scen = st.selectbox("场景 Scenario", list(Scenario), format_func=lambda s: SCENARIO_LABELS[s],
                        index=list(Scenario).index(base.scenario) if base else 0)
    cid = st.selectbox("客户 Client", list(clients), format_func=lambda c: f"{c} {clients[c].surname}{'女士' if clients[c].gender=='F' else '先生'} · {clients[c].tier}",
                       index=list(clients).index(base.client.client_id) if base else 0)
    today = st.text_input("今天 Today", base.today if base else "2026-11-07")
    skus = st.multiselect("产品 Products", list(products), default=[p.sku for p in base.products] if base else [],
                          format_func=lambda s: products[s].name)
    context = st.text_area("场景背景 Context / CA intent", base.context if base and base.context else "", height=120)
with col2:
    hist_default = "\n".join(f"{t.speaker}|{t.time}|{t.text}" for t in base.history) if base else ""
    hist_txt = st.text_area("对话历史 (speaker|time|text 每行一条, speaker=CA/client)", hist_default, height=220)
    with st.expander("客户档案 Client profile"):
        st.json(clients[cid].model_dump(exclude_none=True))

clicked = st.button("生成三条话术 Generate", type="primary")
if clicked or (qp.get("run") == "1" and "auto_done" not in st.session_state):
    st.session_state["auto_done"] = True
    history = []
    for line in hist_txt.strip().splitlines():
        parts = line.split("|", 2)
        if len(parts) == 3:
            history.append(Turn(speaker=parts[0].strip(), time=parts[1].strip(), text=parts[2].strip()))
    req = Request(scenario=scen, today=today, client=clients[cid], history=history,
                  products=[products[s] for s in skus], context=context or None)
    with st.spinner("Generating…"):
        res = Generator().generate(req)
    a = res.analysis
    if a.get("timing_ok") is False:
        st.warning("⏰ 发送时机可能不合适：" + "；".join(a.get("risks", [])))
    with st.expander("分析 Analysis", expanded=False):
        st.json(a)
    cols = st.columns(3)
    for c, cand in zip(cols, res.candidates):
        with c:
            st.subheader(cand.angle)
            st.text_area("message", cand.message, height=320, label_visibility="collapsed")
            st.caption(cand.rationale)
            for i in cand.issues:
                (st.error if i.startswith("[HARD") else st.info)(i)
            if cand.repaired:
                st.caption("🔧 edited by fact-check critic / guardrail repair")
    st.caption(f"{res.model} · {res.latency_s}s · {res.version}")
