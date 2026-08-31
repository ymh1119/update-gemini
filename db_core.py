import datetime
from datetime import timezone, timedelta
import streamlit as st
from supabase import create_client, Client

@st.cache_resource
def get_supabase() -> Client:
    # 这里会准确读取刚才 Secrets 里的 URL 和 KEY
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

def log_interaction(username, expert_mode, session_id, query, response):
    try:
        supabase = get_supabase()
        bj_tz = timezone(timedelta(hours=8))
        timestamp = datetime.datetime.now(bj_tz).strftime("%Y年%m月%d日 %H:%M:%S")
        
        supabase.table("chat_logs").insert({
            "timestamp": timestamp,
            "username": username,
            "expert_mode": expert_mode,
            "session_id": session_id,
            "student_query": query,
            "ai_response": response
        }).execute()
    except Exception as e:
        print(f"⚠️ 写入云数据库失败: {e}")

def load_user_history(username):
    history = {
        "🔍 深度答疑专家 (讲解/解惑)": {},
        "📝 测验与解析专家 (出题/批改)": {},
        "📊 仿真绘图专家 (波形/频谱)": {}
    }
    try:
        supabase = get_supabase()
        response = supabase.table("chat_logs").select("*").eq("username", username).order("id").execute()
        rows = response.data
        
        for row in rows:
            expert_mode = row.get("expert_mode")
            session_id = row.get("session_id", "默认对话")
            query = row.get("student_query", "")
            response_text = row.get("ai_response", "")
            timestamp_full = row.get("timestamp", "")
            time_str = timestamp_full.rsplit(":", 1)[0] if ":" in timestamp_full else timestamp_full
                
            if expert_mode in history:
                if session_id not in history[expert_mode]:
                    history[expert_mode][session_id] = []
                history[expert_mode][session_id].append({"role": "user", "content": query, "time": time_str})
                history[expert_mode][session_id].append({"role": "assistant", "content": response_text, "time": time_str})
    except Exception as e:
        print(f"⚠️ 读取云数据库历史失败: {e}")
        
    for mode in history:
        if not history[mode]:
            history[mode]["默认对话"] = []
            
    return history

def rename_session_in_db(username, expert_mode, old_title, new_title):
    try:
        supabase = get_supabase()
        supabase.table("chat_logs").update({"session_id": new_title}).eq("username", username).eq("expert_mode", expert_mode).eq("session_id", old_title).execute()
    except Exception as e:
        print(f"⚠️ 更新对话标题失败: {e}")
