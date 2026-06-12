"""
Streamlit Demo App for SQL Agent

A web interface for demonstrating the SQL agent capabilities.
Run with: streamlit run app/main.py
"""

import streamlit as st
from pathlib import Path
import sys

# Add src to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import validate_config
from src.database import db

# Page config
st.set_page_config(
    page_title="SQL Agent Demo",
    page_icon="🔍",
    layout="wide",
)

# Title
st.title("🔍 Enterprise SQL Agent")
st.markdown("Query NYC Taxi data using natural language")

# Sidebar - Configuration status
with st.sidebar:
    st.header("Configuration Status")
    
    config_status = validate_config()
    if config_status["valid"]:
        st.success("All configurations valid")
    else:
        st.error("Configuration issues:")
        for issue in config_status["issues"]:
            st.warning(f"- {issue}")
    
    st.divider()
    
    st.header("Database Info")
    try:
        tables = db.get_table_names()
        st.info(f"Connected! Found {len(tables)} tables")
        
        if st.button("Show Schema"):
            schema = db.format_schema_for_llm()
            st.code(schema, language="markdown")
    except Exception as e:
        st.error(f"Database error: {e}")

# Main area
st.divider()

# Chat interface
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Chat input
if prompt := st.chat_input("Ask a question about taxi trips..."):
    # Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # Generate response
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                # Import agent here to avoid loading on startup
                from src.agent import build_agent_graph
                from langchain_core.messages import HumanMessage
                
                agent = build_agent_graph()
                config = {"configurable": {"thread_id": "streamlit-session"}}
                
                # Run agent
                response_text = ""
                for event in agent.stream(
                    {"messages": [HumanMessage(content=prompt)]},
                    config=config,
                    stream_mode="values",
                ):
                    messages = event.get("messages", [])
                    if messages:
                        last_msg = messages[-1]
                        if hasattr(last_msg, "content") and last_msg.content:
                            if not (hasattr(last_msg, "tool_calls") and last_msg.tool_calls):
                                response_text = last_msg.content
                
                st.markdown(response_text)
                st.session_state.messages.append({"role": "assistant", "content": response_text})
                
            except Exception as e:
                error_msg = f"Error: {e}"
                st.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})

# Footer
st.divider()
st.markdown("""
**Sample Questions:**
- What is the average fare amount?
- Show me the top 5 busiest pickup locations
- How many trips were paid by credit card vs cash?
- What's the average tip percentage for trips over $50?
""")
