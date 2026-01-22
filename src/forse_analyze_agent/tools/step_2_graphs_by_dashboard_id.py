import httpx
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from src.forse_analyze_agent.utils.validators import get_required_env
from src.utils.logger import logger

from .cgl_types import DashboardGraphs


class DashboardIdInput(BaseModel):
    dashboard_id: str = Field(
        ..., description="The ID of the dashboard to fetch graphs for"
    )


@tool(
    name_or_callable="step_2_graphs_by_dashboard_id",
    description="Fetch graphs metadata by dashboard ID",
    args_schema=DashboardIdInput,
)
async def step_2_graphs_by_dashboard_id(
    dashboard_id: str, timeout: int = 30
) -> DashboardGraphs:
    """Fetch graphs metadata by dashboard ID."""
    base_url = get_required_env("FORSE_BACKEND_URL")

    url = f"{base_url}/api/graphs/newdashboard/{dashboard_id}/graphs"
    cookies = {"jwt": get_required_env("FORSE_BACKEND_JWT")}

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            logger.debug(f"Fetching: {url}")
            response = await client.get(url, cookies=cookies)
            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching graphs: {e.response.status_code}")
            # can't raise error here otherwise chat will load forever
            return []
        except Exception as e:
            logger.error(f"Error fetching graphs: {str(e)}")
            return []
