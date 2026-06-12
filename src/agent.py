"""
SQL Agent using LangGraph.
Converts natural language questions to SQL queries.
"""

from typing import Annotated, TypedDict
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
import os
os.environ["LANGCHAIN_TRACING_V2"] = "false"

try:
    from .config import OPENAI_API_KEY, OPENAI_MODEL
    from .database import get_schema_info, execute_query
except ImportError:
    from config import OPENAI_API_KEY, OPENAI_MODEL
    from database import get_schema_info, execute_query


# =============================================================================
# TOOLS - Functions the LLM can call
# =============================================================================

@tool
def sql_query(query: str) -> str:
    """
    Execute a SQL query against the NYC taxi trips database.
    Only SELECT queries are allowed.
    
    Args:
        query: A valid PostgreSQL SELECT query
        
    Returns:
        Query results or error message
    """
    return execute_query(query)


@tool
def get_database_schema() -> str:
    """
    Get the database schema including table names, columns, and descriptions.
    Call this first to understand what data is available.
    
    Returns:
        Schema information for the taxi_trips table
    """
    return get_schema_info()


# List of tools the agent can use
tools = [get_database_schema, sql_query]


# =============================================================================
# STATE - What the agent remembers during conversation
# =============================================================================

class AgentState(TypedDict):
    """State passed between nodes in the graph."""
    messages: Annotated[list, add_messages]


# =============================================================================
# LLM SETUP
# =============================================================================

# System prompt - instructions for the agent
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

# Initialize the LLM with tools
llm = ChatOpenAI(
    model=OPENAI_MODEL,
    api_key=OPENAI_API_KEY,
    temperature=0  # Deterministic for SQL generation
)
llm_with_tools = llm.bind_tools(tools)


# =============================================================================
# GRAPH NODES - Steps the agent takes
# =============================================================================

def agent_node(state: AgentState) -> dict:
    """The main agent node - decides what to do next."""
    
    # Add system prompt if this is the first message
    messages = state["messages"]
    if not any(isinstance(m, SystemMessage) for m in messages):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + messages
    
    # Get LLM response
    response = llm_with_tools.invoke(messages)
    
    return {"messages": [response]}


def should_continue(state: AgentState) -> str:
    """Decide whether to continue to tools or end."""
    
    last_message = state["messages"][-1]
    
    # If the LLM wants to use a tool, continue to tool node
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    
    # Otherwise, we're done
    return "end"


# =============================================================================
# BUILD THE GRAPH
# =============================================================================

def create_agent():
    """Build and return the LangGraph agent."""
    
    # Create the graph
    graph = StateGraph(AgentState)
    
    # Add nodes
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools))
    
    # Add edges
    graph.add_edge(START, "agent")
    graph.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", "end": END}
    )
    graph.add_edge("tools", "agent")
    
    # Compile and return
    return graph.compile()


# =============================================================================
# MAIN - Interactive loop
# =============================================================================

def main():
    """Run the agent in interactive mode."""
    
    print("=" * 50)
    print("NYC Taxi Data SQL Agent")
    print("Ask questions about taxi trips in natural language.")
    print("Type 'quit' to exit.")
    print("=" * 50)
    
    agent = create_agent()
    
    while True:
        # Get user input
        user_input = input("\nYou: ").strip()
        
        if not user_input:
            continue
        
        if user_input.lower() == "quit":
            print("Goodbye!")
            break
        
        # Run the agent
        print("\nAgent: ", end="")
        
        result = agent.invoke({
            "messages": [HumanMessage(content=user_input)]
        })
        
        # Print the final response
        final_message = result["messages"][-1]
        print(final_message.content)


if __name__ == "__main__":
    main()
