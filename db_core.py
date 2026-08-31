import datetime
from datetime import timezone, timedelta
import csv
import io
import streamlit as st

# ========== 通过Streamlit Secrets读取Postgres(Supabase)连接 ==========
@st.cache_resource
def get_db_conn():
    conn = st.connection("supabase", type="sql")
    return conn

def log_interaction(username, expert_mode, session_id, query, response):
    """【云端正式版】安静地记录对话到 Supabase"""
    try:
        conn = get_db_conn()
        bj_tz = timezone(timedelta(hours=8))
        timestamp = datetime.datetime.now(bj_tz).strftime("%Y年%m月%d日 %H:%M:%S")

        with conn.session as s:
            s.execute(
                """
                INSERT INTO chat_logs (timestamp, username, expert_mode, session_id, student_query, ai_response)
                VALUES (:ts, :un, :em, :sid, :q, :resp)
                """,
                params={
                    "ts": timestamp,
                    "un": username,
                    "em": expert_mode,
                    "sid": session_id,
                    "q": query,
                    "resp": response
                }
            )

            # 如果是测验专家，额外双写一份到测验表
            if "测验" in expert_mode:
                s.execute(
                    """
                    INSERT INTO quiz_logs (timestamp, username, student_answer, ai_feedback)
                    VALUES (:ts, :un, :ans, :feed)
                    """,
                    params={
                        "ts": timestamp,
                        "un": username,
                        "ans": query,
                        "feed": response
                    }
                )
            s.commit()

    except Exception as e:
        print(f"⚠️ 写入云数据库失败: {e}")


def rename_session_in_db(username, expert_mode, old_title, new_title):
    """【云端版】重命名数据库中的对话标题"""
    try:
        conn = get_db_conn()
        with conn.session as s:
            s.execute(
                """
                UPDATE chat_logs
                SET session_id = :new_sid
                WHERE username = :un AND expert_mode = :em AND session_id = :old_sid
                """,
                params={
                    "new_sid": new_title,
                    "un": username,
                    "em": expert_mode,
                    "old_sid": old_title
                }
            )
            s.commit()
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
        conn = get_db_conn()
        rows = conn.query(
            """
            SELECT * FROM chat_logs
            WHERE username = :un
            ORDER BY id ASC
            """,
            params={"un": username}
        )

        for _, row in rows.iterrows():
            expert_mode = row.get("expert_mode")
            session_id = row.get("session_id")
            if not session_id:
                session_id = "默认对话"

            query = str(row.get("student_query", ""))
            response_text = str(row.get("ai_response", ""))
            timestamp_full = str(row.get("timestamp", ""))

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
        conn = get_db_conn()
        rows = conn.query("SELECT * FROM chat_logs ORDER BY id ASC")

        col_names = ["发言时间", "账号", "咨询的专家", "对话标题", "学生提问", "AI回答"]

        output = io.StringIO()
        output.write("sep=,\n")
        writer = csv.writer(output)
        writer.writerow(col_names)

        for _, row in rows.iterrows():
            writer.writerow([
                row.get("timestamp", ""),
                row.get("username", ""),
                row.get("expert_mode", ""),
                row.get("session_id", ""),
                row.get("student_query", ""),
                row.get("ai_response", "")
            ])

        return output.getvalue().encode('utf‑8‑sig')

    except Exception as e:
        print(f"⚠️ 云端数据导出失败: {e}")
        return None
