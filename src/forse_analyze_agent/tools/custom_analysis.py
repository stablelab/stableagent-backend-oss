# src/forse_analyze_agent/tools/custom_analysis.py

from typing import Optional
from pydantic import BaseModel, Field
from langchain_core.tools import tool

from src.utils.model_factory import create_chat_model


class CustomAnalysisInput(BaseModel):
    graph_id: str = Field(..., description="The graph ID to analyze")
    category_id: str = Field(..., description="The category ID to analyze")
    analysis_prompt: str = Field(
        ..., 
        description="User's specific analysis request. E.g., 'Find the top 3 growth periods' or 'Compare with previous month'"
    )
    graph_data: Optional[dict] = Field(default=None, description="Pre-fetched graph data (optional)")


@tool(
    name_or_callable="analyze_graph_custom",
    description="Perform custom user-specified analysis on graph data. Use when user has specific analysis requirements.",
    args_schema=CustomAnalysisInput,
)
async def analyze_graph_custom(
    graph_id: str,
    category_id: str, 
    analysis_prompt: str,
    graph_data: Optional[dict] = None,
) -> str:
    """Execute user-specified analysis on graph data."""
    
    try:
        # Fetch data if not provided
        if graph_data is None:
            try:
                from src.forse_analyze_agent.tools.step_4_graph_data_by_id_and_category_id import (
                    step_4_graph_data_by_id_and_category_id
                )
                graph_data = await step_4_graph_data_by_id_and_category_id.ainvoke({
                    "graph_id": graph_id,
                    "category_id": category_id
                })
            except Exception as e:
                from src.utils.logger import logger
                logger.error(f"Failed to fetch graph data for analysis: {e}")
                return f"Unable to fetch data for graph {graph_id} with category {category_id}. Please try again or verify the IDs are correct."
        
        # Validate graph_data is usable
        if not graph_data or (isinstance(graph_data, list) and len(graph_data) == 0):
            return f"No data available for graph {graph_id} with category {category_id}. The graph may be empty or the IDs may be incorrect."
        
        # Build analysis prompt
        analysis_system_prompt = f"""You are a data analyst for the Forse platform.
    
Given the following graph data, perform the analysis requested by the user.

USER'S ANALYSIS REQUEST:
{analysis_prompt}

GRAPH DATA:
- Position: x-axis values (typically time or categories)
- Value: y-axis values (the metric being measured)  
- Label: data series identifier
- Category: the metric category (e.g., TVL, Users)

Provide clear, actionable insights based on the user's specific request.
"""
        
        try:
            llm = create_chat_model(model_name="gemini-3-flash-preview", temperature=0.3)
            
            response = await llm.ainvoke([
                {"role": "system", "content": analysis_system_prompt},
                {"role": "user", "content": f"Data to analyze:\n{graph_data}"}
            ])
            
            return response.content
        except Exception as e:
            from src.utils.logger import logger
            logger.error(f"LLM analysis failed: {e}")
            return f"Unable to complete the analysis due to an internal error. Please try again."
            
    except Exception as e:
        from src.utils.logger import logger
        logger.error(f"Unexpected error in custom analysis: {e}")
        return f"An unexpected error occurred during analysis. Please try again."

