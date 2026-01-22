"""ENS resolver tool for Research Agent.

Wrapper around ENS resolution for address <-> name lookups.
"""
from typing import Any, Optional, Type

from pydantic import BaseModel, Field

from .base import ResearchBaseTool
from src.utils.logger import logger


class ENSResolveInput(BaseModel):
    """Input for ENS resolution."""
    name_or_address: str = Field(..., description="ENS name (e.g., 'vitalik.eth') or Ethereum address")


class ENSResolverTool(ResearchBaseTool):
    """Resolve ENS names to addresses and vice versa.
    
    Bidirectional resolution:
    - ENS name → Ethereum address
    - Ethereum address → ENS name (reverse lookup)
    """
    
    name: str = "ens_resolver"
    description: str = """Resolve ENS names to addresses and vice versa.
Input: name_or_address (ENS name like 'vitalik.eth' OR Ethereum address)
Returns: The resolved address or ENS name.
Use for: Looking up delegate addresses, resolving voter identities."""
    args_schema: Type[BaseModel] = ENSResolveInput
    
    def _run_tool(
        self,
        name_or_address: str,
        **kwargs: Any,
    ) -> str:
        """Execute ENS resolution."""
        try:
            # Try to import and use the existing ENS resolver
            from src.tools.ens_resolver_tool import ENSResolverTool as ExistingENS
            
            ens_tool = ExistingENS()
            
            # Determine if this is a name or address
            if name_or_address.endswith('.eth'):
                # Name to address resolution
                result = ens_tool._run(query=name_or_address, direction="to_address")
                if result:
                    addresses = [r.get('address', 'N/A') for r in result[:3]]
                    return f"**{name_or_address}** resolves to: {', '.join(f'`{a}`' for a in addresses)}"
                return f"No address found for ENS name: {name_or_address}"
            elif name_or_address.startswith('0x') and len(name_or_address) == 42:
                # Address to name (reverse) resolution
                result = ens_tool._run(query=name_or_address, direction="to_name")
                if result:
                    names = [r.get('name', 'N/A') for r in result[:3]]
                    return f"**{name_or_address}** reverse resolves to: {', '.join(f'`{n}`' for n in names)}"
                return f"No ENS name found for address: {name_or_address}"
            else:
                return f"Invalid input: '{name_or_address}'. Provide an ENS name (e.g., 'vitalik.eth') or Ethereum address (0x...)"
            
        except ImportError:
            logger.warning("[ENSResolverTool] ENS resolver not available")
            return f"ENS resolution not available. Input: {name_or_address}"
        except Exception as e:
            logger.error(f"[ENSResolverTool] Error: {e}")
            return f"Error resolving '{name_or_address}': {str(e)}"

