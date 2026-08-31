import datetime
from datetime import timezone, timedelta
import csv
import io
import streamlit as st
from supabase import create_client, Client

# 🌟 懒加载模式初始化 Supabase 客户端，配合 Streamlit 缓存提升速度
@st.cache_resource
def get_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

def log_interaction(username, expert_mode, session_id, query, response):
    """【云端正式版】安静地记录对话到 Supabase"""
    try:
        supabase = get_supabase()
        bj_tz = timezone(timedelta(hours=8))
        timestamp = datetime.datetime.now(bj_tz).strftime("%Y年%m月%d日 %H:%M:%S")
        
        # 写入通用聊天表
        supabase.table("chat_logs").insert({
            "timestamp": timestamp,
            "username": username,
            "expert_mode": expert_mode,
            "session_id": session_id,
            "student_query": query,
            "ai_response": response
        }).execute()
        
        # 如果是测验专家，额外双写一份到测验表
        if "测验" in expert_mode:
            supabase.table("quiz_logs").insert({
                "timestamp": timestamp,
                "username": username,
                "student_answer": query,
                "ai_feedback": response
            }).execute()
            
    except Exception as e:
        print(f"⚠️ 写入云数据库失败: {e}")

def rename_session_in_db(username, expert_mode, old_title, new_title):
    """【云端版】重命名数据库中的对话标题"""
    try:
        supabase = get_supabase()
        supabase.table("chat_logs").update({"session_id": new_title}).eq("username", username).eq("expert_mode", expert_mode).eq("session_id", old_title).execute()
    except Exception as e:
        print(f"⚠️ 更新对话标题失败: {e}")

def load_user_history(username):
    """【云端版】每次用户登录时，从 Supabase 读取记忆"""
    history = {
        "🔍 深度答疑专家 (讲解/解惑)": {},
        "📝 测验与解析专家 (出题/批改)": {},
        "📊 仿真绘图专家 (波形/频谱)": {}
    }
    
    try:
        supabase = get_supabase()
        # 按照 id 顺序拉取该用户的所有聊天记录
        response = supabase.table("chat_logs").select("*").eq("username", username).order("id").execute()
        rows = response.data
        
        for row in rows:
            expert_mode = row.get("expert_mode")
            session_id = row.get("session_id")
            if not session_id:
                session_id = "默认对话"
                
            query = row.get("student_query", "")
            response_text = row.get("ai_response", "")
            timestamp_full = row.get("timestamp", "")
            
            # 格式化时间戳显示
            time_str = timestamp_full.rsplit(":", 1)[0] if ":" in timestamp_full else timestamp_full
                
            if expert_mode in history:
                if session_id not in history[expert_mode]:
                    history[expert_mode][session_id] = []
                
                history[expert_mode][session_id].append({"role": "user", "content": query, "time": time_str})
                history[expert_mode][session_id].append({"role": "assistant", "content": response_text, "time": time_str})
                
    except Exception as e:
        st.error(f"❌ 数据库历史读取被系统拦截！详细报错原因：{e}")
        print(f"⚠️ 读取云数据库历史失败: {e}")
        
    # 保底补全
    for mode in history:
        if not history[mode]:
            history[mode]["默认对话"] = []
            
    return history

def get_all_records_as_csv():
    """【云端版】将云端历史记录打包成防乱码的 CSV 字节流"""
    try:
        supabase = get_supabase()
        # 拉取全部记录
        response = supabase.table("chat_logs").select("*").order("id").execute()
        rows = response.data
        
        col_names = ["发言时间", "账号", "咨询的专家", "对话标题", "学生提问", "AI回答"]
        
        # 转换为防乱码的 Excel 兼容 CSV 格式
        output = io.StringIO()
        output.write("sep=,\n") # 强制 Excel 分列魔法
        writer = csv.writer(output)
        writer.writerow(col_names)
        
        for row in rows:
            writer.writerow([
                row.get("timestamp", ""),
                row.get("username", ""),
                row.get("expert_mode", ""),
                row.get("session_id", ""),
                row.get("student_query", ""),
                row.get("ai_response", "")
            ])
            
        return output.getvalue().encode('utf-8-sig') 
    except Exception as e:
        print(f"⚠️ 云端数据导出失败: {e}")
        return None
