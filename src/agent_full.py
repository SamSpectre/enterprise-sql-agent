"""
SQL Agent - Full Featured Version
- LangSmith tracing
- Conversation memory (LangGraph built-in)
- Query caching
- Human-in-the-loop
"""
import os
from dotenv import load_dotenv
load_dotenv()
from typing import Annotated, TypedDict, Literal
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
import hashlib


# =============================================================================
# LANGSMITH SETUP
# =============================================================================
# Set these BEFORE importing langchain components in production
# For now, we set them here

os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGCHAIN_PROJECT"] = "sql-agent-project1"

# You'll need to set LANGCHAIN_API_KEY in your .env or here:
os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGCHAIN_API_KEY")

try:
    from .config import OPENAI_API_KEY, OPENAI_MODEL
    from .database import get_schema_info, execute_query
except ImportError:
    from config import OPENAI_API_KEY, OPENAI_MODEL
    from database import get_schema_info, execute_query


# =============================================================================
# QUERY CACHE
# =============================================================================

class QueryCache:
    """Simple in-memory cache for SQL query results."""
    
    def __init__(self, max_size: int = 100):
        self._cache: dict[str, str] = {}
        self._max_size = max_size
        self._hits = 0
        self._misses = 0
    
    def _hash_query(self, sql: str) -> str:
        """Normalize and hash SQL for cache key."""
        normalized = " ".join(sql.lower().split())
        return hashlib.md5(normalized.encode()).hexdigest()
    
    def get(self, sql: str) -> str | None:
        """Get cached result or None."""
        key = self._hash_query(sql)
        result = self._cache.get(key)
        if result:
            self._hits += 1
            print(f"[CACHE HIT] Returning cached result")
        else:
            self._misses += 1
        return result
    
    def set(self, sql: str, result: str) -> None:
        """Cache a query result."""
        if len(self._cache) >= self._max_size:
            # Simple eviction: remove oldest (first) item
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
        
        key = self._hash_query(sql)
        self._cache[key] = result
    
    def stats(self) -> dict:
        """Return cache statistics."""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{hit_rate:.1f}%",
            "cached_queries": len(self._cache),
        }


# Global cache instance
query_cache = QueryCache()


# =============================================================================
# RISK CLASSIFICATION
# =============================================================================

def classify_query_risk(sql: str) -> tuple[str, str]:
    """Classify SQL query risk level."""
    sql_upper = sql.upper().strip()
    
    blocked_keywords = ["DROP", "DELETE", "TRUNCATE", "ALTER", "INSERT", "UPDATE", "GRANT", "REVOKE"]
    for keyword in blocked_keywords:
        if keyword in sql_upper:
            return ("blocked", f"Contains {keyword}")
    
    if "LIMIT" not in sql_upper and sql_upper.startswith("SELECT"):
        return ("review", "No LIMIT clause")
    
    if "SELECT *" in sql_upper or "SELECT  *" in sql_upper:
        return ("review", "SELECT * detected")
    
    return ("safe", "Standard SELECT")


# =============================================================================
# TOOLS
# =============================================================================

@tool
def sql_query(query: str) -> str:
    """Execute a SQL query against the NYC taxi trips database."""
    
    # Check cache first
    cached = query_cache.get(query)
    if cached:
        return cached
    
    # Execute and cache
    result = execute_query(query)
    query_cache.set(query, result)
    return result


@tool
def get_database_schema() -> str:
    """Get the database schema including table names, columns, and descriptions."""
    return get_schema_info()


tools = [get_database_schema, sql_query]
tool_map = {t.name: t for t in tools}


# =============================================================================
# STATE
# =============================================================================

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    pending_query: str | None
    pending_tool_call_id: str | None
    awaiting_approval: bool


# =============================================================================
# LLM
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

You have conversation memory - you can reference previous questions and results.
"""

llm = ChatOpenAI(
    model=OPENAI_MODEL,
    api_key=OPENAI_API_KEY,
    temperature=0
)
llm_with_tools = llm.bind_tools(tools)


# =============================================================================
# NODES
# =============================================================================

def agent_node(state: AgentState) -> dict:
    messages = state["messages"]
    
    if not any(isinstance(m, SystemMessage) for m in messages):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + messages
    
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}


def tool_node(state: AgentState) -> dict:
    last_message = state["messages"][-1]
    
    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        return {}
    
    results = []
    
    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        tool_id = tool_call["id"]
        
        if tool_name == "sql_query":
            query = tool_args.get("query", "")
            risk_level, reason = classify_query_risk(query)
            
            print(f"\n[RISK] {risk_level.upper()}: {reason}")
            print(f"[SQL]  {query}")
            
            if risk_level == "blocked":
                result = f"BLOCKED: {reason}. Query not executed."
            elif risk_level == "review":
                return {
                    "pending_query": query,
                    "pending_tool_call_id": tool_id,
                    "awaiting_approval": True,
                }
            else:
                result = tool_map[tool_name].invoke(tool_args)
        else:
            result = tool_map[tool_name].invoke(tool_args)
        
        results.append(ToolMessage(content=str(result), tool_call_id=tool_id))
    
    return {"messages": results, "awaiting_approval": False}


def human_approval_node(state: AgentState) -> dict:
    query = state["pending_query"]
    tool_id = state["pending_tool_call_id"]
    
    print(f"\n{'='*50}")
    print("HUMAN APPROVAL REQUIRED")
    print(f"{'='*50}")
    print(f"Query: {query}")
    approval = input("Approve? (y/n): ").strip().lower()
    
    if approval == "y":
        print("[APPROVED]")
        result = execute_query(query)
        query_cache.set(query, result)  # Cache approved queries too
    else:
        print("[REJECTED]")
        result = "Query rejected by user."
    
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
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return "end"


def after_tools(state: AgentState) -> Literal["human", "agent"]:
    if state.get("awaiting_approval"):
        return "human"
    return "agent"


# =============================================================================
# BUILD GRAPH WITH MEMORY
# =============================================================================

def create_agent():
    """Build agent with memory checkpointer."""
    
    graph = StateGraph(AgentState)
    
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)
    graph.add_node("human", human_approval_node)
    
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", "end": END})
    graph.add_conditional_edges("tools", after_tools, {"human": "human", "agent": "agent"})
    graph.add_edge("human", "agent")
    
    # THIS IS THE KEY: Add MemorySaver for conversation persistence
    memory = MemorySaver()
    return graph.compile(checkpointer=memory)


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 50)
    print("NYC Taxi SQL Agent (Full Featured)")
    print("- LangSmith tracing enabled")
    print("- Conversation memory ON")
    print("- Query caching ON")
    print("- Human-in-the-loop ON")
    print("Commands: 'quit', 'cache', 'clear'")
    print("=" * 50)
    
    agent = create_agent()
    
    # Thread ID is what enables memory across invocations
    config = {"configurable": {"thread_id": "session-1"}}
    
    while True:
        user_input = input("\nYou: ").strip()
        
        if not user_input:
            continue
        
        if user_input.lower() == "quit":
            print("\nCache stats:", query_cache.stats())
            print("Goodbye!")
            break
        
        if user_input.lower() == "cache":
            print("\nCache stats:", query_cache.stats())
            continue
        
        if user_input.lower() == "clear":
            # New thread = fresh conversation
            config = {"configurable": {"thread_id": f"session-{id(config)}"}}
            print("Conversation cleared. Memory reset.")
            continue
        
        print("\nAgent: ", end="", flush=True)
        
        # IMPORTANT: Pass config with thread_id for memory
        result = agent.invoke(
            {
                "messages": [HumanMessage(content=user_input)],
                "pending_query": None,
                "pending_tool_call_id": None,
                "awaiting_approval": False,
            },
            config=config,  # <-- This enables memory
        )
        
        final_message = result["messages"][-1]
        print(final_message.content)


if __name__ == "__main__":
    main()
