import os
import re
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from langchain_core.runnables import RunnablePassthrough
import streamlit as st

# ==========================================
# 向量知识库单例缓存（避免重复加载 PDF）
# ==========================================
@st.cache_resource
def get_vectorstore(pdf_path, api_key):
    """读取 PDF 并提取页码信息构建 FAISS 向量库"""
    if not os.path.exists(pdf_path):
        st.warning(f"⚠️ 未找到课本文件 {pdf_path}，检索功能将降级。")
        return None
    
    loader = PyPDFLoader(pdf_path)
    docs = loader.load()
    
    # 为每一个 document 注入准确的物理页码标识
    for doc in docs:
        page_num = doc.metadata.get("page", 0) + 1  # PDF 索引从 0 开始，转换为实际页码
        doc.metadata["page_label"] = f"第 {page_num} 页"
    
    # DeepSeek 官方不提供 Embedding 接口，需要单独配置 embedding provider
    # 推荐：硅基流动 https://siliconflow.cn （免费额度足够本项目使用）
    # 在 Streamlit Secrets 中添加：
    #   EMBEDDING_API_KEY = "sk-..."          # 硅基流动 API Key
    #   EMBEDDING_BASE_URL = "https://api.siliconflow.cn/v1"
    #   EMBEDDING_MODEL = "BAAI/bge-large-zh-v1.5"   # 中文 Embedding 效果较好
    embedding_api_key = st.secrets.get("EMBEDDING_API_KEY", api_key)
    embedding_base_url = st.secrets.get("EMBEDDING_BASE_URL", "https://api.deepseek.com/v1")
    embedding_model = st.secrets.get("EMBEDDING_MODEL", "text-embedding-3-small")
    
    embeddings = OpenAIEmbeddings(
        model=embedding_model,
        api_key=embedding_api_key,
        base_url=embedding_base_url,
        # 关键：非 OpenAI 服务商（如硅基流动）必须关闭此选项，
        # 否则 LangChain 会发送 token ID 数组，对方返回 400 错误 20015
        check_embedding_ctx_length=False,
        # 避免 base64 编码兼容性问题
        encoding_format="float",
    )
    
    vectorstore = FAISS.from_documents(docs, embeddings)
    return vectorstore

# ==========================================
# 专家专属系统提示词模板库（注入检索与页码规则）
# ==========================================
EXPERT_PROMPTS = {
    "🔍 深度答疑专家 (讲解/解惑)": """你是一个资深的《信号与系统》教授。请根据提供的课本检索内容和你的知识库解答学生的疑问。

【课本检索参考内容】：
{context}

要求：
1. 语言生动形象，多用直观的物理意义解释数学公式。
2. 涉及到的数学公式必须使用标准的 LaTeX 语法输出。
3. 必须在回答中明确指出所依据的课本页码！格式示例：`📖 参考课本：第 XX 页` 或 `[见课本第 XX 页]`。
""",
    
    "📝 测验与解析专家 (出题/批改)": """你是一个严格的《信号与系统》助教。请结合课本内容进行出题或批改。

【课本检索参考内容】：
{context}

要求：
1. 如果学生要求出题，请结合检索到的课本知识点给出一道考题，并标注该考题对应的课本页码。
2. 如果学生回答了问题，请给出专业的批改，指出错误并给出正确解析，同时附上参考课本页码（如：`📖 详解参考课本：第 XX 页`）。
""",
    
    "📊 仿真绘图专家 (波形/频谱)": """你是一个专业的《信号与系统》仿真绘图专家。

【课本检索参考内容】：
{context}

你必须遵守以下规范：
1. 严禁出现任何中文字符（标题、坐标轴均用英文）。
2. 在输出代码前，用简短文字说明该信号/系统的课本出处，并标注页码（如：`📖 对应波形见课本：第 XX 页`）。
3. 必须且只能输出一段完整的 Python 代码，包裹在 ```python 和 ``` 之间。代码必须以 import numpy as np 和 import matplotlib.pyplot as plt 开头。
4. 绘图代码必须兼容 matplotlib 3.8+：严禁使用已废弃的参数（例如 plt.stem() 的 use_line_collection 参数），不要调用 plt.show()。
"""
}

def format_docs(docs):
    """将检索到的文档片段及其页码拼接为上下文文本"""
    formatted = []
    for doc in docs:
        page = doc.metadata.get("page_label", "未知页码")
        content = doc.page_content.strip()
        formatted.append(f"【课本内容 ({page})】:\n{content}")
    return "\n\n".join(formatted)

def init_rag_system(api_key, expert_mode, pdf_name):
    """初始化带课本页码检索的对话链"""
    system_prompt = EXPERT_PROMPTS.get(expert_mode, EXPERT_PROMPTS["🔍 深度答疑专家 (讲解/解惑)"])
    
    # DeepSeek 已下线 deepseek-chat / deepseek-reasoner 别名
    # 2026-07-24 后需使用 deepseek-v4-flash 或 deepseek-v4-pro
    # 可在 Streamlit Secrets 里用 CHAT_MODEL 自定义，默认用 deepseek-v4-flash
    chat_model = st.secrets.get("CHAT_MODEL", "deepseek-v4-flash")
    
    llm = ChatOpenAI(
        api_key=api_key,
        model=chat_model,
        base_url="https://api.deepseek.com/v1",
        max_tokens=2048,
        temperature=0.1
    )
    
    vectorstore = get_vectorstore(pdf_name, api_key)
    
    if vectorstore:
        retriever = vectorstore.as_retriever(search_kwargs={"k": 3})
    else:
        retriever = None

    prompt_template = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        MessagesPlaceholder(variable_name="chat_history"), 
        ("user", "{query}")
    ])
    
    # 结合 RAG 检索链
    def get_context(inputs):
        if retriever:
            docs = retriever.invoke(inputs["query"])
            return format_docs(docs)
        return "未找到相关课本上下文。"

    chain = (
        RunnablePassthrough.assign(context=get_context)
        | prompt_template
        | llm
        | StrOutputParser()
    )
    
    return chain
