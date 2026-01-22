from typing import Final


# Short, domain-specific guidance distilled from the global context in
# `src/config/database_context.py` relevant to ENS resolution.
ENS_KNOWLEDGE_GUIDE: Final[str] = (
    """
    Use the table dune.ens_labels for ENS ↔ address resolution. Columns:
      - address (text): EVM address
      - blockchain (text): chain namespace, e.g., 'ethereum'
      - name (text): ENS name, e.g., 'vitalik.eth'

    Join with internal.chain_ids to map chain namespaces to numeric chain IDs and canonical names:
      - internal.chain_ids.chain_id (bigint)
      - internal.chain_ids.blockchain (text)
      - internal.chain_ids.name (text)

    Guidance:
      - Normalize addresses and names to lowercase when matching.
      - For addresses, compare with LOWER(address) = LOWER('0x…').
      - Prefer exact name matches for name → address (no fuzzy matching).
      - If a blockchain filter is supplied, accept chain slug (e.g., 'ethereum'), chain ID (e.g., 1), or chain name (e.g., 'Ethereum Mainnet').
        Apply it via the join to internal.chain_ids (match on c.blockchain, c.chain_id, or c.name).
      - Return compact fields and limit results to avoid large payloads.
    """
)


def normalize_ens_name(name: str) -> str:
    """Lowercase and trim the ENS name. Returns empty string if invalid."""
    if not isinstance(name, str):
        return ""
    cleaned = name.strip().lower()
    return cleaned


def normalize_evm_address(addr: str) -> str:
    """Lowercase the address if it matches 0x-prefixed 40 hex chars; else empty string."""
    if not isinstance(addr, str):
        return ""
    a = addr.strip()
    if len(a) == 42 and a.startswith("0x") and all(c in "0123456789abcdefABCDEF" for c in a[2:]):
        return a.lower()
    return ""


