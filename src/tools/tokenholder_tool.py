# tools/tokenholder_tool.py
from langchain_core.tools import tool

@tool
def get_tokenholder_preferences(address: str) -> str:
    return "Tokenholder prefers decentralization and minimal treasury drain."
