import streamlit as st
import datetime
from datetime import timezone, timedelta
import db_core
import rag_core
import plot_core

# 1. 页面与全局设置
st.set_page_config(page_title="信号与系统 AI 助教", page_icon="📡", layout="wide")

st.markdown("""
    <style>
    .block-container {
        max-width: 900px !important; 
        padding-top: 2rem;
        padding-left: 2rem;
        padding-right: 2rem;
    }
    </style>
""", unsafe_allow_html=True)

def render_markdown_with_latex(text):
    if not isinstance(text, str):
        return
    text = text.replace('\\[', '$$').replace('\\]', '$$')
    text = text.replace('\\(', '$').replace('\\)', '$')
    st.markdown(text)

# 2. 登录认证
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = ""

st.sidebar.title("🔐 用户登录")
if not st.session_state.logged_in:
    username_input = st.sidebar.text_input("👤 用户名")
    password_input = st.sidebar.text_input("🔑 密码", type="password")
    
    if st.sidebar.button("登录"):
        if username_input.strip() and password_input.strip():
            st.session_state.logged_in = True
            st.session_state.username = username_input.strip()
            st.rerun()
        else:
            st.sidebar.error("用户名和密码不能为空！")
    st.stop()
else:
    st.sidebar.success(f"欢迎回来：{st.session_state.username}")
    if st.sidebar.button("退出登录"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.rerun()

# 3. 专家选择与 PDF 路径
st.sidebar.markdown("---")
expert_modes = [
    "🔍 深度答疑专家 (讲解/解惑)", 
    "📝 测验与解析专家 (出题/批改)", 
    "📊 仿真绘图专家 (波形/频谱)"
]
selected_expert = st.sidebar.radio("请选择你的专属 AI 助教", expert_modes)

# 指向你的课本文件名
PDF_FILE_PATH = "textbook.pdf" 

# 4. 历史记录模块
st.sidebar.markdown("---")
st.sidebar.markdown("### 📚 历史对话记录")

with st.spinner("🔄 同步历史记忆..."):
    full_history = db_core.load_user_history(st.session_state.username)

available_sessions = list(full_history.get(selected_expert, {}).keys())
if not available_sessions:
    available_sessions = ["默认对话"]

if st.sidebar.button("➕ 新建对话"):
    new_session = datetime.datetime.now().strftime("对话_%m%d_%H%M")
    st.session_state.current_session = new_session
    st.rerun()

if "current_session" not in st.session_state or st.session_state.current_session not in available_sessions:
    if "current_session" in st.session_state and st.session_state.current_session.startswith("对话_"):
        available_sessions.insert(0, st.session_state.current_session)
    else:
        st.session_state.current_session = available_sessions[-1] if available_sessions else "默认对话"

current_session = st.sidebar.selectbox(
    "选择或切换聊天记录",
    options=available_sessions,
    index=available_sessions.index(st.session_state.current_session) if st.session_state.current_session in available_sessions else 0
)
st.session_state.current_session = current_session

messages = full_history.get(selected_expert, {}).get(current_session, [])

# 5. 主界面渲染
st.title(selected_expert.split()[1])

for i, msg in enumerate(messages):
    with st.chat_message(msg["role"]):
        if "time" in msg and msg["time"]:
            st.caption(f"🕒 {msg['time']}")
            
        render_markdown_with_latex(msg["content"])
        
        if msg["role"] == "assistant":
            with st.expander("📋 点击展开以一键复制全文"):
                st.code(msg["content"], language="markdown")
        
        if "📊" in selected_expert and msg["role"] == "assistant":
            plot_core.render_interactive_plot(msg["content"], msg_index=f"history_{i}")

# 6. 问题接收与对话响应
if prompt := st.chat_input("输入你的问题（系统会自动检索课本页码）..."):
    
    history_for_chain = []
    for msg in messages:
        role = "assistant" if msg["role"] == "assistant" else "user"
        history_for_chain.append((role, msg["content"]))
    
    was_renamed = False
    if st.session_state.current_session.startswith("对话_"):
        old_session_name = st.session_state.current_session
        new_session_name = prompt[:12] + ("..." if len(prompt) > 12 else "")
        st.session_state.current_session = new_session_name
        was_renamed = True
        
        db_core.rename_session_in_db(
            st.session_state.username, 
            selected_expert, 
            old_session_name, 
            new_session_name
        )

    bj_tz = timezone(timedelta(hours=8))
    current_time = datetime.datetime.now(bj_tz).strftime("%Y年%m月%d日 %H:%M:%S")

    with st.chat_message("user"):
        st.caption(f"🕒 {current_time}")
        render_markdown_with_latex(prompt)
        
    with st.chat_message("assistant"):
        with st.spinner("🔍 正在检索《信号与系统》课本并生成精准解答..."):
            try:
                api_key = st.secrets["API_KEY"]
                
                qa_chain = rag_core.init_rag_system(
                    api_key=api_key, 
                    expert_mode=selected_expert, 
                    pdf_name=PDF_FILE_PATH
                )
                
                response = qa_chain.invoke({
                    "query": prompt,
                    "chat_history": history_for_chain
                })
                
                ai_reply = str(response)
                
                st.caption(f"🕒 {current_time}")
                render_markdown_with_latex(ai_reply)
                
                with st.expander("📋 点击展开以一键复制全文"):
                    st.code(ai_reply, language="markdown")
                
                if "📊" in selected_expert:
                    plot_core.render_interactive_plot(ai_reply, msg_index=f"new_{datetime.datetime.now().timestamp()}")
                    
                db_core.log_interaction(
                    username=st.session_state.username,
                    expert_mode=selected_expert,
                    session_id=st.session_state.current_session,
                    query=prompt,
                    response=ai_reply
                )
                
            except KeyError:
                st.error("🔑 发生错误：未能从系统配置(Secrets)中找到 API_KEY，请检查配置！")
            except Exception as e:
                st.error(f"❌ 系统发生异常: {e}")
                
        if was_renamed:
            st.rerun()
