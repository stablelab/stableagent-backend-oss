from typing import Type, List, Dict, Any, Optional
import time
from pydantic import BaseModel, Field

from langchain_core.tools import BaseTool

import os
import time
import requests

from src.utils.logger import logger
from src.utils.tool_events import emit_tool_event


class EtherscanInput(BaseModel):
    operation: str = Field(
        ...,
        description=(
            "Supported operations (subset of Premium API):\n"
            "account_balance, account_balancemulti, account_txlist, account_txlistinternal,\n"
            "account_tokentx, account_tokennfttx, account_token1155tx, account_tokenbalance, account_minedblocks,\n"
            "contract_getabi, contract_getsourcecode, contract_getcontractcreation,\n"
            "transaction_getstatus, transaction_gettxreceiptstatus, transaction_summary,\n"
            "block_getblocknobytime, block_getblockreward, block_getblockcountdown,\n"
            "logs_getLogs,\n"
            "gas_gasoracle,\n"
            "stats_ethsupply, stats_ethsupply2, stats_ethprice,\n"
            "proxy_eth_blockNumber, proxy_eth_getBlockByNumber, proxy_eth_getTransactionByHash,\n"
            "proxy_eth_getTransactionReceipt, proxy_eth_getBalance,\n"
            "raw (advanced: call arbitrary module/action with extra_params)"
        ),
    )
    # Common params
    address: Optional[str] = Field(None, description="Single EVM address")
    addresses: List[str] = Field(default_factory=list, description="Multiple EVM addresses for balancemulti")
    txhash: Optional[str] = Field(None, description="Transaction hash")
    contract_address: Optional[str] = Field(None, description="Contract address for token balance")
    token_contract_address: Optional[str] = Field(None, description="Token contract for tokentx / nft tx")
    startblock: Optional[int] = Field(None)
    endblock: Optional[int] = Field(None)
    page: Optional[int] = Field(None)
    offset: Optional[int] = Field(None)
    sort: Optional[str] = Field(None, description="asc or desc")
    blockno: Optional[int] = Field(None)
    timestamp: Optional[int] = Field(None, description="Unix seconds")
    closest: Optional[str] = Field(None, description="before or after for block_by_time")
    fromBlock: Optional[int] = Field(None)
    toBlock: Optional[int] = Field(None)
    topic0: Optional[str] = Field(None)
    topic1: Optional[str] = Field(None)
    topic2: Optional[str] = Field(None)
    topic3: Optional[str] = Field(None)
    topic0_1_opr: Optional[str] = Field(None)
    topic1_2_opr: Optional[str] = Field(None)
    topic2_3_opr: Optional[str] = Field(None)
    tag: Optional[str] = Field(None, description="latest or hex block tag for proxy getBalance")
    boolean: Optional[str] = Field(None, description="true/false for proxy getBlockByNumber to include txs")
    blocktype: Optional[str] = Field(None, description="'blocks' or 'uncles' for minedblocks")
    # Raw (advanced)
    module_raw: Optional[str] = Field(None, description="Raw module name for operation='raw'")
    action_raw: Optional[str] = Field(None, description="Raw action name for operation='raw'")
    extra_params: Optional[Dict[str, Any]] = Field(None, description="Additional params merged for operation='raw'")
    # Network selection
    network: Optional[str] = Field(
        None,
        description=(
            "Network/domain selector: e.g., 'ethereum' (default), 'sepolia', 'optimism', 'arbitrum', 'polygon',\n"
            "'bsc', 'base', 'gnosis', 'fantom', 'avalanche'. You can also pass a chain ID like '1', '10', '42161'."
        ),
    )
    base_url: Optional[str] = Field(None, description="Override base API URL (advanced)")
    # Safety & size
    limit: int = Field(1000, description="Max rows to return when the API returns lists")


class EtherscanTool(BaseTool):
    name: str = "etherscan_tool"
    description: str = (
        "Query Etherscan Premium-compatible APIs (and Etherscan-family explorers). "
        "Requires ETHERSCAN_API_KEY in environment. Supports many operations across account/contract/tx/block/logs/gas/stats/proxy."
    )
    args_schema: Type[BaseModel] = EtherscanInput

    # -------- Base URL resolution --------
    def _resolve_base(self, network: Optional[str], override: Optional[str]) -> str:
        if override:
            return override.rstrip("/")
        env_base = os.environ.get("ETHERSCAN_BASE_URL")
        if env_base:
            return env_base.rstrip("/")
        key = (network or "ethereum").strip().lower()
        mapping = {
            # Ethereum
            "ethereum": "https://api.etherscan.io/api",
            "mainnet": "https://api.etherscan.io/api",
            "1": "https://api.etherscan.io/api",
            "sepolia": "https://api-sepolia.etherscan.io/api",
            "11155111": "https://api-sepolia.etherscan.io/api",
            # Etherscan-family
            "optimism": "https://api-optimistic.etherscan.io/api",
            "10": "https://api-optimistic.etherscan.io/api",
            "arbitrum": "https://api.arbiscan.io/api",
            "42161": "https://api.arbiscan.io/api",
            "arbitrum-nova": "https://api-nova.arbiscan.io/api",
            "42170": "https://api-nova.arbiscan.io/api",
            "polygon": "https://api.polygonscan.com/api",
            "137": "https://api.polygonscan.com/api",
            "bsc": "https://api.bscscan.com/api",
            "56": "https://api.bscscan.com/api",
            "base": "https://api.basescan.org/api",
            "8453": "https://api.basescan.org/api",
            "gnosis": "https://api.gnosisscan.io/api",
            "100": "https://api.gnosisscan.io/api",
            "fantom": "https://api.ftmscan.com/api",
            "250": "https://api.ftmscan.com/api",
            "avalanche": "https://api.snowtrace.io/api",
            "43114": "https://api.snowtrace.io/api",
        }
        return mapping.get(key, "https://api.etherscan.io/api")

    def _headers(self) -> Dict[str, str]:
        return {"Accept": "application/json"}

    def _apikey(self) -> str:
        return os.environ.get("ETHERSCAN_API_KEY", "").strip()

    def _http_get(self, base_url: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not base_url:
            return None
        # Always include API key
        p = dict(params)
        api_key = self._apikey()
        if api_key:
            p["apikey"] = api_key
        try:
            r = requests.get(base_url, params=p, headers=self._headers(), timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.error("EtherscanTool: GET failed %s params=%s error=%s", base_url, params, e, exc_info=True)
            return None

    # -------- Helpers --------
    def _as_list_rows(self, payload: Optional[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
        if not isinstance(payload, dict):
            return []
        result = payload.get("result")
        # Standardize outputs
        if isinstance(result, list):
            rows = [r for r in result if isinstance(r, dict)]
            if rows:
                return rows[: max(1, min(limit, 10000))]
            # list of scalars
            out = [{"value": r} for r in result]
            return out[: max(1, min(limit, 10000))]
        if isinstance(result, dict):
            return [result]
        if result is None:
            # Some endpoints put data at top level
            if any(k in payload for k in ("LastBlock", "SafeGasPrice", "suggestBaseFee")):
                return [payload]
            return []
        # scalar
        return [{"value": result}]

    def _params(self, **kwargs) -> Dict[str, Any]:
        return {k: v for k, v in kwargs.items() if v is not None}

    # -------- Utilities for transaction summary --------
    @staticmethod
    def _hex_to_int(value: Optional[str]) -> Optional[int]:
        if not isinstance(value, str):
            return None
        try:
            if value.startswith("0x"):
                return int(value, 16)
            return int(value)
        except Exception:
            return None

    @staticmethod
    def _wei_to_eth(wei: Optional[int]) -> Optional[float]:
        if wei is None:
            return None
        try:
            return float(wei) / 1e18
        except Exception:
            return None

    @staticmethod
    def _normalize_address(addr: Optional[str]) -> Optional[str]:
        if not isinstance(addr, str):
            return None
        a = addr.strip()
        if len(a) == 42 and a.startswith("0x"):
            return a.lower()
        return a or None

    def _parse_erc20_transfers(self, logs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        transfers: List[Dict[str, Any]] = []
        if not isinstance(logs, list):
            return transfers
        ERC20_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
        for log in logs:
            if not isinstance(log, dict):
                continue
            topics = log.get("topics") or []
            if not (isinstance(topics, list) and topics and isinstance(topics[0], str)):
                continue
            if topics[0].lower() != ERC20_TRANSFER_TOPIC:
                continue
            # Standard Transfer(address indexed from, address indexed to, uint256 value)
            contract = self._normalize_address(log.get("address"))
            from_addr = None
            to_addr = None
            if len(topics) > 1 and isinstance(topics[1], str) and len(topics[1]) >= 66:
                from_addr = self._normalize_address("0x" + topics[1][-40:])
            if len(topics) > 2 and isinstance(topics[2], str) and len(topics[2]) >= 66:
                to_addr = self._normalize_address("0x" + topics[2][-40:])
            value_hex = log.get("data") if isinstance(log.get("data"), str) else None
            value_int = self._hex_to_int(value_hex)
            transfers.append({
                "contract": contract,
                "from": from_addr,
                "to": to_addr,
                "value": value_int,
            })
        return transfers

    def _get_block_timestamp(self, base_url: str, block_number_hex: Optional[str]) -> Optional[int]:
        if not isinstance(block_number_hex, str):
            return None
        try:
            params = {"module": "proxy", "action": "eth_getBlockByNumber", "tag": block_number_hex, "boolean": "false"}
            payload = self._http_get(base_url, params)
            if not isinstance(payload, dict):
                return None
            block = payload.get("result")
            if not isinstance(block, dict):
                return None
            ts_hex = block.get("timestamp")
            ts = self._hex_to_int(ts_hex)
            return ts
        except Exception:
            return None

    # -------- Operation implementations --------
    def _perform_operation(self, base_url: str, inp: EtherscanInput) -> List[Dict[str, Any]]:
        op = (inp.operation or "").strip().lower()
        limit = max(1, min(int(inp.limit or 1000), 10000))
        p: Dict[str, Any]

        # Account module
        if op == "account_balance":
            p = self._params(module="account", action="balance", address=inp.address, tag=inp.tag or "latest")
            return self._as_list_rows(self._http_get(base_url, p), limit)
        if op == "account_balancemulti":
            addresses = ",".join([a for a in (inp.addresses or []) if isinstance(a, str) and a])
            p = self._params(module="account", action="balancemulti", address=addresses, tag=inp.tag or "latest")
            return self._as_list_rows(self._http_get(base_url, p), limit)
        if op == "account_txlist":
            p = self._params(module="account", action="txlist", address=inp.address, startblock=inp.startblock, endblock=inp.endblock, page=inp.page, offset=inp.offset, sort=inp.sort)
            return self._as_list_rows(self._http_get(base_url, p), limit)
        if op == "account_txlistinternal":
            # Support either address or txhash filtering per Etherscan spec
            if inp.txhash:
                p = self._params(module="account", action="txlistinternal", txhash=inp.txhash, page=inp.page, offset=inp.offset, sort=inp.sort)
            else:
                p = self._params(module="account", action="txlistinternal", address=inp.address, startblock=inp.startblock, endblock=inp.endblock, page=inp.page, offset=inp.offset, sort=inp.sort)
            return self._as_list_rows(self._http_get(base_url, p), limit)
        if op == "account_tokentx":
            p = self._params(module="account", action="tokentx", address=inp.address, contractaddress=inp.token_contract_address, startblock=inp.startblock, endblock=inp.endblock, page=inp.page, offset=inp.offset, sort=inp.sort)
            return self._as_list_rows(self._http_get(base_url, p), limit)
        if op == "account_tokennfttx":
            p = self._params(module="account", action="tokennfttx", address=inp.address, contractaddress=inp.token_contract_address, startblock=inp.startblock, endblock=inp.endblock, page=inp.page, offset=inp.offset, sort=inp.sort)
            return self._as_list_rows(self._http_get(base_url, p), limit)
        if op == "account_token1155tx":
            p = self._params(module="account", action="token1155tx", address=inp.address, contractaddress=inp.token_contract_address, startblock=inp.startblock, endblock=inp.endblock, page=inp.page, offset=inp.offset, sort=inp.sort)
            return self._as_list_rows(self._http_get(base_url, p), limit)
        if op == "account_tokenbalance":
            p = self._params(module="account", action="tokenbalance", contractaddress=inp.contract_address, address=inp.address, tag=inp.tag or "latest")
            payload = self._http_get(base_url, p)
            rows = self._as_list_rows(payload, limit)
            if rows and isinstance(rows[0].get("value"), str):
                return [{"address": inp.address, "contract_address": inp.contract_address, "tag": inp.tag or "latest", "balance": rows[0]["value"]}]
            return rows
        if op == "account_minedblocks":
            p = self._params(module="account", action="getminedblocks", address=inp.address, blocktype=inp.blocktype or "blocks", page=inp.page, offset=inp.offset)
            return self._as_list_rows(self._http_get(base_url, p), limit)

        # Contract module
        if op == "contract_getabi":
            p = self._params(module="contract", action="getabi", address=inp.address)
            return self._as_list_rows(self._http_get(base_url, p), limit)
        if op == "contract_getsourcecode":
            p = self._params(module="contract", action="getsourcecode", address=inp.address)
            return self._as_list_rows(self._http_get(base_url, p), limit)
        if op == "contract_getcontractcreation":
            p = self._params(module="contract", action="getcontractcreation", contractaddresses=inp.contract_address or inp.address)
            return self._as_list_rows(self._http_get(base_url, p), limit)

        # Transaction module
        if op == "transaction_getstatus":
            p = self._params(module="transaction", action="getstatus", txhash=inp.txhash)
            return self._as_list_rows(self._http_get(base_url, p), limit)
        if op == "transaction_gettxreceiptstatus":
            p = self._params(module="transaction", action="gettxreceiptstatus", txhash=inp.txhash)
            return self._as_list_rows(self._http_get(base_url, p), limit)
        if op == "transaction_summary":
            if not inp.txhash:
                logger.warning("EtherscanTool: transaction_summary requires txhash")
                return []
            tx_payload = self._http_get(base_url, {"module": "proxy", "action": "eth_getTransactionByHash", "txhash": inp.txhash})
            rc_payload = self._http_get(base_url, {"module": "proxy", "action": "eth_getTransactionReceipt", "txhash": inp.txhash})
            tx = tx_payload.get("result") if isinstance(tx_payload, dict) else None
            rc = rc_payload.get("result") if isinstance(rc_payload, dict) else None
            if not isinstance(tx, dict):
                return []
            # Extract basics
            block_number_hex = tx.get("blockNumber") if isinstance(tx.get("blockNumber"), str) else (rc.get("blockNumber") if isinstance(rc, dict) else None)
            block_number = self._hex_to_int(block_number_hex)
            timestamp = self._get_block_timestamp(base_url, block_number_hex)
            value_wei = self._hex_to_int(tx.get("value"))
            gas = self._hex_to_int(tx.get("gas"))
            gas_price = self._hex_to_int(tx.get("gasPrice"))
            max_fee_per_gas = self._hex_to_int(tx.get("maxFeePerGas"))
            max_priority_fee_per_gas = self._hex_to_int(tx.get("maxPriorityFeePerGas"))
            effective_gas_price = self._hex_to_int(rc.get("effectiveGasPrice")) if isinstance(rc, dict) else None
            gas_used = self._hex_to_int(rc.get("gasUsed")) if isinstance(rc, dict) else None
            fee_wei = None
            if gas_used is not None:
                pg = effective_gas_price or gas_price
                if pg is not None:
                    try:
                        fee_wei = int(gas_used) * int(pg)
                    except Exception:
                        fee_wei = None
            status_hex = rc.get("status") if isinstance(rc, dict) else None
            status_int = self._hex_to_int(status_hex)
            success = (status_int == 1) if status_int is not None else None
            input_data = tx.get("input") if isinstance(tx.get("input"), str) else ""
            method_id = (input_data[:10] if input_data.startswith("0x") and len(input_data) >= 10 else None)
            # ERC-20 transfers (best-effort)
            logs = rc.get("logs") if isinstance(rc, dict) else []
            transfers = self._parse_erc20_transfers(logs if isinstance(logs, list) else [])
            summary = {
                "txhash": tx.get("hash"),
                "from": self._normalize_address(tx.get("from")),
                "to": self._normalize_address(tx.get("to")),
                "created_contract": self._normalize_address(rc.get("contractAddress")) if isinstance(rc, dict) else None,
                "block_number": block_number,
                "block_hash": rc.get("blockHash") if isinstance(rc, dict) else tx.get("blockHash"),
                "timestamp": timestamp,
                "value_wei": value_wei,
                "value_eth": self._wei_to_eth(value_wei),
                "gas": gas,
                "gas_price": gas_price,
                "max_fee_per_gas": max_fee_per_gas,
                "max_priority_fee_per_gas": max_priority_fee_per_gas,
                "effective_gas_price": effective_gas_price,
                "gas_used": gas_used,
                "fee_wei": fee_wei,
                "fee_eth": self._wei_to_eth(fee_wei if isinstance(fee_wei, int) else None),
                "nonce": self._hex_to_int(tx.get("nonce")),
                "transaction_index": self._hex_to_int(tx.get("transactionIndex")),
                "type": self._hex_to_int(tx.get("type")),
                "status": status_int,
                "success": success,
                "method_id": method_id,
                "logs_count": len(logs or []),
                "erc20_transfers": transfers,
            }
            return [summary]

        # Block module
        if op == "block_getblocknobytime":
            p = self._params(module="block", action="getblocknobytime", timestamp=inp.timestamp, closest=inp.closest)
            return self._as_list_rows(self._http_get(base_url, p), limit)
        if op == "block_getblockreward":
            p = self._params(module="block", action="getblockreward", blockno=inp.blockno)
            return self._as_list_rows(self._http_get(base_url, p), limit)
        if op == "block_getblockcountdown":
            p = self._params(module="block", action="getblockcountdown", blockno=inp.blockno)
            return self._as_list_rows(self._http_get(base_url, p), limit)

        # Logs module
        if op == "logs_getlogs":
            p = self._params(
                module="logs",
                action="getLogs",
                fromBlock=inp.fromBlock,
                toBlock=inp.toBlock,
                address=inp.address,
                topic0=inp.topic0,
                topic1=inp.topic1,
                topic2=inp.topic2,
                topic3=inp.topic3,
                topic0_1_opr=inp.topic0_1_opr,
                topic1_2_opr=inp.topic1_2_opr,
                topic2_3_opr=inp.topic2_3_opr,
            )
            return self._as_list_rows(self._http_get(base_url, p), limit)

        # Gas tracker
        if op == "gas_gasoracle":
            p = self._params(module="gastracker", action="gasoracle")
            return self._as_list_rows(self._http_get(base_url, p), limit)

        # Stats module
        if op == "stats_ethsupply":
            p = self._params(module="stats", action="ethsupply")
            return self._as_list_rows(self._http_get(base_url, p), limit)
        if op == "stats_ethsupply2":
            p = self._params(module="stats", action="ethsupply2")
            return self._as_list_rows(self._http_get(base_url, p), limit)
        if op == "stats_ethprice":
            p = self._params(module="stats", action="ethprice")
            return self._as_list_rows(self._http_get(base_url, p), limit)

        # Proxy (Ethereum JSON-RPC via explorer)
        if op == "proxy_eth_blocknumber":
            p = self._params(module="proxy", action="eth_blockNumber")
            return self._as_list_rows(self._http_get(base_url, p), limit)
        if op == "proxy_eth_getblockbynumber":
            p = self._params(module="proxy", action="eth_getBlockByNumber", tag=inp.tag or "latest", boolean=(inp.boolean or "true"))
            return self._as_list_rows(self._http_get(base_url, p), limit)
        if op == "proxy_eth_gettransactionbyhash":
            p = self._params(module="proxy", action="eth_getTransactionByHash", txhash=inp.txhash)
            return self._as_list_rows(self._http_get(base_url, p), limit)
        if op == "proxy_eth_gettransactionreceipt":
            p = self._params(module="proxy", action="eth_getTransactionReceipt", txhash=inp.txhash)
            return self._as_list_rows(self._http_get(base_url, p), limit)
        if op == "proxy_eth_getbalance":
            p = self._params(module="proxy", action="eth_getBalance", address=inp.address, tag=inp.tag or "latest")
            return self._as_list_rows(self._http_get(base_url, p), limit)

        # Raw (advanced)
        if op == "raw":
            if not inp.module_raw or not inp.action_raw:
                logger.warning("EtherscanTool: raw operation requires module_raw and action_raw")
                return []
            p = {"module": inp.module_raw, "action": inp.action_raw}
            if isinstance(inp.extra_params, dict):
                for k, v in inp.extra_params.items():
                    if v is not None:
                        p[str(k)] = v
            return self._as_list_rows(self._http_get(base_url, p), limit)

        logger.warning("EtherscanTool: unsupported operation '%s'", op)
        return []

    # -------- Entry points --------
    def _run(
        self,
        operation: str,
        address: Optional[str] = None,
        addresses: List[str] = [],
        txhash: Optional[str] = None,
        contract_address: Optional[str] = None,
        token_contract_address: Optional[str] = None,
        startblock: Optional[int] = None,
        endblock: Optional[int] = None,
        page: Optional[int] = None,
        offset: Optional[int] = None,
        sort: Optional[str] = None,
        blockno: Optional[int] = None,
        timestamp: Optional[int] = None,
        closest: Optional[str] = None,
        fromBlock: Optional[int] = None,
        toBlock: Optional[int] = None,
        topic0: Optional[str] = None,
        topic1: Optional[str] = None,
        topic2: Optional[str] = None,
        topic3: Optional[str] = None,
        topic0_1_opr: Optional[str] = None,
        topic1_2_opr: Optional[str] = None,
        topic2_3_opr: Optional[str] = None,
        tag: Optional[str] = None,
        boolean: Optional[str] = None,
        blocktype: Optional[str] = None,
        network: Optional[str] = None,
        base_url: Optional[str] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        try:
            start_ts = time.time()
            base = self._resolve_base(network, base_url)
            try:
                emit_tool_event("etherscan.input", {
                    "operation": operation,
                    "address": address,
                    "addresses": addresses[:5],
                    "txhash": txhash,
                    "contract_address": contract_address,
                    "network": network,
                })
            except Exception:
                pass
            inp = EtherscanInput(
                operation=operation,
                address=address,
                addresses=addresses,
                txhash=txhash,
                contract_address=contract_address,
                token_contract_address=token_contract_address,
                startblock=startblock,
                endblock=endblock,
                page=page,
                offset=offset,
                sort=sort,
                blockno=blockno,
                timestamp=timestamp,
                closest=closest,
                fromBlock=fromBlock,
                toBlock=toBlock,
                topic0=topic0,
                topic1=topic1,
                topic2=topic2,
                topic3=topic3,
                topic0_1_opr=topic0_1_opr,
                topic1_2_opr=topic1_2_opr,
                topic2_3_opr=topic2_3_opr,
                tag=tag,
                boolean=boolean,
                blocktype=blocktype,
                network=network,
                base_url=base_url,
                limit=limit,
            )
            rows = self._perform_operation(base, inp)
            try:
                emit_tool_event("etherscan.output", {"count": len(rows or []), "sample": rows[:3]})
                emit_tool_event("tool.end", {"tool": self.name, "status": "ok", "duration_ms": int((time.time() - start_ts) * 1000), "result": {"count": len(rows or [])}})
            except Exception:
                pass
            return rows
        except Exception as e:
            logger.error("EtherscanTool: unexpected error: %s", e, exc_info=True)
            try:
                emit_tool_event("etherscan.error", {"message": str(e), "operation": operation})
                emit_tool_event("tool.end", {"tool": getattr(self, 'name', 'etherscan_tool'), "status": "error", "error": str(e)})
            except Exception:
                pass
            return []

    async def _arun(self, **kwargs) -> List[Dict[str, Any]]:
        return self._run(**kwargs)


