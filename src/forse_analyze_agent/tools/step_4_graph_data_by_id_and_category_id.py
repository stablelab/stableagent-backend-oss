import httpx
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from src.forse_analyze_agent.utils.validators import get_required_env
from src.utils.logger import logger

from .cgl_types import CategoryData


class GraphIdAndCategoryIdInput(BaseModel):
    graph_id: str = Field(..., description="The ID of the graph to fetch data for")
    category_id: str = Field(
        ..., description="The ID of the category to fetch data for"
    )


@tool(
    name_or_callable="step_4_graph_data_by_id_and_category_id",
    description="Fetch category data by graph ID and category ID",
    args_schema=GraphIdAndCategoryIdInput,
)
async def step_4_graph_data_by_id_and_category_id(
    graph_id: str, category_id: str, timeout: int = 30
) -> CategoryData:
    """Fetch category data by graph ID and category ID."""
    base_url = get_required_env("FORSE_BACKEND_URL")

    url = f"{base_url}/api/graphs/newdashboard-graphdata/{graph_id}/{category_id}"
    cookies = {"jwt": get_required_env("FORSE_BACKEND_JWT")}

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            logger.debug(f"Fetching: {url}")
            response = await client.get(url, cookies=cookies)
            response.raise_for_status()
            data = response.json()
            return data

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching category data: {e.response.status_code}")
            # can't raise error here otherwise chat will load forever
            return []
        except Exception as e:
            logger.error(f"Error fetching category data: {str(e)}")
            return []
