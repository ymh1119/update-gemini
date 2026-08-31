import streamlit as st
from datetime import datetime, timezone, timedelta
from db_core import load_user_history, rename_session_in_db

def init_expert_sessions():
    """初始化专家的多线程记忆字典（终极修复：跨会话/断线重连记忆恢复）"""
    
    # 1. 尝试获取当前用户。如果连 current_user 都没了，说明是被彻底踢下线了，不用恢复
    current_user = st.session_state.get("current_user")
    
    if current_user:
        # 2. 核心逻辑：如果当前没有 loaded_user 标记，说明是“长时间断线后刷新”或“新登录”
        # 或者是切换了账号登录。此时必须强行查库！
        if "loaded_user" not in st.session_state or st.session_state["loaded_user"] != current_user:
            # 💡 从 SQLite 数据库中硬捞该用户的所有历史数据
            st.session_state.chat_sessions = load_user_history(current_user)
            # 烙上标记，防止系统每次点击都去查库（拖慢速度）
            st.session_state["loaded_user"] = current_user

    # 3. 保底初始化：极其罕见的情况下，查库返回了空，或者刚注册的新号，给它一套空壳字典
    if "chat_sessions" not in st.session_state:
        st.session_state.chat_sessions = {
            "🔍 深度答疑专家 (讲解/解惑)": {"默认对话": []},
            "📝 测验与解析专家 (出题/批改)": {"默认对话": []},
            "📊 仿真绘图专家 (波形/频谱)": {"默认对话": []}
        }
        
    # 4. 确保当前所在的对话框有名字
    if "current_session_id" not in st.session_state:
        st.session_state.current_session_id = "默认对话"

def render_sidebar_history(expert_mode):
    if expert_mode not in st.session_state.chat_sessions:
        st.session_state.chat_sessions[expert_mode] = {"默认对话": []}
    
    if st.session_state.current_session_id not in st.session_state.chat_sessions[expert_mode]:
        st.session_state.current_session_id = list(st.session_state.chat_sessions[expert_mode].keys())[0]

    st.markdown("---")
    st.header("📚 历史对话")
    
    if st.button("➕ 新建对话", use_container_width=True):
        bj_tz = timezone(timedelta(hours=8))
        new_id = f"新对话 {datetime.now(bj_tz).strftime('%Y年%m月%d日 %H:%M:%S')}"
        st.session_state.chat_sessions[expert_mode][new_id] = []
        st.session_state.current_session_id = new_id
        st.rerun()

    st.caption("往期记录")
    session_ids = list(st.session_state.chat_sessions[expert_mode].keys())
    
    for sid in reversed(session_ids):
        btn_label = f"💬 {sid}" if sid != st.session_state.current_session_id else f"👉 {sid}"
        if st.button(btn_label, use_container_width=True, key=f"btn_{expert_mode}_{sid}"):
            st.session_state.current_session_id = sid
            st.rerun()
            
    return st.session_state.chat_sessions[expert_mode][st.session_state.current_session_id]

def auto_rename_session(expert_mode, prompt, current_expert_messages):
    if len(current_expert_messages) == 2 and st.session_state.current_session_id.startswith("新对话 "):
        new_title = prompt[:12] + "..." if len(prompt) > 12 else prompt
        old_title = st.session_state.current_session_id
        
        st.session_state.chat_sessions[expert_mode][new_title] = st.session_state.chat_sessions[expert_mode].pop(old_title)
        st.session_state.current_session_id = new_title
        
        rename_session_in_db(st.session_state.current_user, expert_mode, old_title, new_title)
        st.rerun()
