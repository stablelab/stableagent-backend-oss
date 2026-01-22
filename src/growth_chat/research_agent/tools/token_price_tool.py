"""Token price tool for Research Agent.

Wrapper around CoinGecko price tool for DAO token prices.
"""
from typing import Any, List, Optional, Type

from pydantic import BaseModel, Field

from .base import ResearchBaseTool
from src.utils.logger import logger


class TokenPriceInput(BaseModel):
    """Input for token price lookup."""
    token_id: str = Field(..., description="CoinGecko token ID (e.g., 'bitcoin', 'ethereum', 'uniswap')")
    vs_currency: str = Field("usd", description="Currency for price (default: usd)")


class TokenPriceTool(ResearchBaseTool):
    """Get token prices from CoinGecko.
    
    Works for any cryptocurrency, not just DAO tokens.
    Common IDs: bitcoin, ethereum, uniswap, compound-governance-token, aave, etc.
    """
    
    name: str = "token_prices"
    description: str = """Get cryptocurrency prices from CoinGecko.
Input: token_id (required, CoinGecko ID like 'bitcoin', 'ethereum', 'uniswap'), vs_currency (optional, default 'usd')
Returns: Current price data.
Use for: Any crypto price lookup. Common IDs: bitcoin, ethereum, uniswap, aave, compound-governance-token."""
    args_schema: Type[BaseModel] = TokenPriceInput
    
    def _run_tool(
        self,
        token_id: str,
        vs_currency: str = "usd",
        **kwargs: Any,
    ) -> str:
        """Execute token price lookup."""
        try:
            # Import the existing CoinGecko tool
            from src.tools.coingecko_price_tool import CoinGeckoPriceTool
            
            cg_tool = CoinGeckoPriceTool()
            
            # Use "current" action for simple price lookup
            result: List[dict] = cg_tool._run(
                action="current",
                ids=[token_id],
                vs_currencies=[vs_currency],
            )
            
            logger.info(f"[TokenPriceTool] CoinGecko result for {token_id}: {result}")
            
            # Format the result
            if result and isinstance(result, list) and len(result) > 0:
                return self._format_price_result(result, token_id, vs_currency)
            
            # If no results, try search to suggest correct ID
            search_result = cg_tool._run(
                action="search",
                search_query=token_id,
                limit=5,
            )
            
            if search_result and isinstance(search_result, list) and len(search_result) > 0:
                suggestions = [f"  - {r.get('id')} ({r.get('symbol', '').upper()}: {r.get('name')})" 
                              for r in search_result[:5]]
                return f"No price data for '{token_id}'. Did you mean:\n" + "\n".join(suggestions)
            
            return f"No price data found for '{token_id}'. Try searching with a different ID."
            
        except ImportError as e:
            logger.error(f"[TokenPriceTool] Import error: {e}")
            return f"Token price lookup not available (import error)"
        except Exception as e:
            logger.error(f"[TokenPriceTool] Error: {e}")
            return f"Error fetching price for {token_id}: {str(e)}"
    
    def _format_price_result(self, result: List[dict], token_id: str, vs_currency: str) -> str:
        """Format price result for readability."""
        if not result:
            return f"No price data found for {token_id}"
        
        # Find the matching token in results
        data = None
        for r in result:
            if r.get("id") == token_id and r.get("vs_currency") == vs_currency:
                data = r
                break
        
        if not data:
            data = result[0]  # Use first result
        
        price = data.get("price", "N/A")
        
        output = [f"**{token_id.upper()} Price:**"]
        
        if isinstance(price, (int, float)):
            if price >= 1:
                output.append(f"  - Price: ${price:,.2f} {vs_currency.upper()}")
            else:
                output.append(f"  - Price: ${price:,.6f} {vs_currency.upper()}")
        else:
            output.append(f"  - Price: {price}")
        
        return "\n".join(output)

