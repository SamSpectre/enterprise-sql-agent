"""
SQL Agent with Human-in-the-Loop (HITL).
Adds query risk classification and human approval for sensitive operations.
"""

from typing import Annotated, TypedDict, Literal
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
import os
os.environ["LANGCHAIN_TRACING_V2"] = "false"

try:
    from .config import OPENAI_API_KEY, OPENAI_MODEL
    from .database import get_schema_info, execute_query
except ImportError:
    from config import OPENAI_API_KEY, OPENAI_MODEL
    from database import get_schema_info, execute_query


# =============================================================================
# RISK CLASSIFICATION
# =============================================================================

def classify_query_risk(sql: str) -> tuple[str, str]:
    """
    Classify SQL query risk level.
    
    Returns:
        (risk_level, reason)
        risk_level: "safe", "review", or "blocked"
    """
    sql_upper = sql.upper().strip()
    
    # BLOCKED - Never allow these
    blocked_keywords = ["DROP", "DELETE", "TRUNCATE", "ALTER", "INSERT", "UPDATE", "GRANT", "REVOKE"]
    for keyword in blocked_keywords:
        if keyword in sql_upper:
            return ("blocked", f"Contains {keyword} - destructive operation")
    
    # REVIEW - Needs human approval
    review_patterns = [
        ("SELECT *", "Selecting all columns - may expose sensitive data"),
        ("LIMIT", None),  # Will check if NO limit
        ("JOIN", "Complex join - verify table relationships"),
        ("UNION", "Union query - verify data combination"),
        ("HAVING", "Aggregate filter - verify business logic"),
    ]
    
    # Check for missing LIMIT (risky for large tables)
    if "LIMIT" not in sql_upper and sql_upper.startswith("SELECT"):
        return ("review", "No LIMIT clause - could return millions of rows")
    
    # Check for SELECT *
    if "SELECT *" in sql_upper or "SELECT  *" in sql_upper:
        return ("review", "SELECT * may expose unintended columns")
    
    # Check other review patterns
    for pattern, reason in review_patterns:
        if reason and pattern in sql_upper:
            return ("review", reason)
    
    # SAFE - Standard read query
    return ("safe", "Standard SELECT query")


# =============================================================================
# TOOLS
# =============================================================================

@tool
def sql_query(query: str) -> str:
    """
    Execute a SQL query against the NYC taxi trips database.
    Only SELECT queries are allowed.
    """
    return execute_query(query)


@tool
def get_database_schema() -> str:
    """
    Get the database schema including table names, columns, and descriptions.
    Call this first to understand what data is available.
    """
    return get_schema_info()


tools = [get_database_schema, sql_query]
tool_map = {t.name: t for t in tools}


# =============================================================================
# STATE - Extended with approval tracking
# =============================================================================

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    pending_query: str | None          # Query awaiting approval
    pending_tool_call_id: str | None   # Tool call ID for the pending query
    awaiting_approval: bool            # Are we waiting for human input?


# =============================================================================
# LLM SETUP
# =============================================================================

SYSTEM_PROMPT = """You are a SQL expert assistant that helps users query NYC taxi trip data.

Your workflow:
1. ALWAYS call get_database_schema first to understand the data structure
2. Generate a SQL query based on the user's question
3. Call sql_query to execute it
4. Explain the results in plain English

Rules:
- Only generate SELECT queries
- Always use LIMIT to avoid returning too many rows (default LIMIT 10)
- Use the column descriptions to understand what values mean
- Be concise in your explanations
"""

llm = ChatOpenAI(
    model=OPENAI_MODEL,
    api_key=OPENAI_API_KEY,
    temperature=0
)
llm_with_tools = llm.bind_tools(tools)


# =============================================================================
# GRAPH NODES
# =============================================================================

def agent_node(state: AgentState) -> dict:
    """Main agent node - generates responses and tool calls."""
    messages = state["messages"]
    
    if not any(isinstance(m, SystemMessage) for m in messages):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + messages
    
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}


def tool_node(state: AgentState) -> dict:
    """
    Execute tools with risk classification.
    If sql_query is called, classify risk first.
    """
    last_message = state["messages"][-1]
    
    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        return {}
    
    results = []
    
    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        tool_id = tool_call["id"]
        
        # Special handling for sql_query
        if tool_name == "sql_query":
            query = tool_args.get("query", "")
            risk_level, reason = classify_query_risk(query)
            
            print(f"\n[RISK] {risk_level.upper()}: {reason}")
            print(f"[SQL]  {query}")
            
            if risk_level == "blocked":
                result = f"BLOCKED: {reason}. Query not executed."
            
            elif risk_level == "review":
                # Return state indicating we need approval
                return {
                    "pending_query": query,
                    "pending_tool_call_id": tool_id,
                    "awaiting_approval": True,
                }
            
            else:  # safe
                result = tool_map[tool_name].invoke(tool_args)
        
        else:
            # Other tools (like get_database_schema) - just execute
            result = tool_map[tool_name].invoke(tool_args)
        
        results.append(ToolMessage(content=str(result), tool_call_id=tool_id))
    
    return {"messages": results, "awaiting_approval": False}


def human_approval_node(state: AgentState) -> dict:
    """
    Handle human approval for risky queries.
    This node is reached when awaiting_approval is True.
    """
    query = state["pending_query"]
    tool_id = state["pending_tool_call_id"]
    
    print(f"\n{'='*50}")
    print("HUMAN APPROVAL REQUIRED")
    print(f"{'='*50}")
    print(f"Query: {query}")
    approval = input("Approve this query? (y/n): ").strip().lower()
    
    if approval == "y":
        print("[APPROVED] Executing query...")
        result = execute_query(query)
    else:
        print("[REJECTED] Query blocked by user.")
        result = "Query was rejected by human reviewer."
    
    return {
        "messages": [ToolMessage(content=str(result), tool_call_id=tool_id)],
        "pending_query": None,
        "pending_tool_call_id": None,
        "awaiting_approval": False,
    }


# =============================================================================
# ROUTING
# =============================================================================

def should_continue(state: AgentState) -> Literal["tools", "end"]:
    """After agent node - go to tools or end?"""
    last_message = state["messages"][-1]
    
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return "end"


def after_tools(state: AgentState) -> Literal["human", "agent"]:
    """After tools - need human approval or back to agent?"""
    if state.get("awaiting_approval"):
        return "human"
    return "agent"


# =============================================================================
# BUILD GRAPH
# =============================================================================

def create_agent_with_hitl():
    """Build agent with human-in-the-loop."""
    
    graph = StateGraph(AgentState)
    
    # Nodes
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)
    graph.add_node("human", human_approval_node)
    
    # Edges
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", "end": END})
    graph.add_conditional_edges("tools", after_tools, {"human": "human", "agent": "agent"})
    graph.add_edge("human", "agent")  # After approval, back to agent to format response
    
    return graph.compile()


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 50)
    print("NYC Taxi SQL Agent (with Human-in-the-Loop)")
    print("Risky queries will require your approval.")
    print("Type 'quit' to exit.")
    print("=" * 50)
    
    agent = create_agent_with_hitl()
    
    while True:
        user_input = input("\nYou: ").strip()
        
        if not user_input:
            continue
        if user_input.lower() == "quit":
            print("Goodbye!")
            break
        
        print("\nAgent: ", end="", flush=True)
        
        result = agent.invoke({
            "messages": [HumanMessage(content=user_input)],
            "pending_query": None,
            "pending_tool_call_id": None,
            "awaiting_approval": False,
        })
        
        final_message = result["messages"][-1]
        print(final_message.content)


if __name__ == "__main__":
    main()
