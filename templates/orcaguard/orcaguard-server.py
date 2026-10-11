#!/usr/bin/env python3
"""
OrcaGuard — AI Crypto Safety Assistant
Port 8186 | Powered by Lightchain AIVM

Protects non-technical crypto users from scams:
- Contract address verification
- Airdrop safety checks
- Fake DEX/site detection
- Wallet address validation
- Plain-English AI explanations
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json, os, threading, time, secrets, base64, re
from urllib.parse import urlparse, parse_qs, quote as url_quote

PORT = int(os.environ.get("PORT", 8186))

# ════════════════════════════════════════════════════════════════════════
# KNOWN VERIFIED CONTRACTS & SITES
# ════════════════════════════════════════════════════════════════════════

VERIFIED_CONTRACTS = {
    # ── Ethereum ──────────────────────────────────────────────────────────
    "0x9ca8530ca349c966fe9ef903df17a75b8a778927": {
        "name": "LCAI Token (Ethereum Mainnet ERC-20)",
        "safe": True,
        "note": "Official Lightchain AI token on Ethereum. Verified on CoinMarketCap and CoinGecko. This is ERC-20 LCAI — bridge to Lightchain Mainnet for native gas/dApps.",
        "links": [
            "https://coinmarketcap.com/currencies/lightchain-ai/",
            "https://etherscan.io/token/0x9cA8530CA349c966Fe9ef903Df17a75B8A778927",
            "https://bridge.lightchain.ai/",
        ],
    },
    # ── Lightchain official UniV2 / LCAI Swap stack (chain 9200) ─────────
    "0x1f94c0a6cf48d3075f9713a79f87fa4eedaf7021": {
        "name": "UniswapV2Router02 — Official LCAI Swap router",
        "safe": True,
        "note": "Official Lightchain UniV2-style router used by lightdex.app. Interacting via the official frontend is expected; always double-check the site is lightdex.app.",
        "links": ["https://lightdex.app/", "https://mainnet.lightscan.app/address/0x1f94c0A6Cf48D3075f9713A79f87FA4eEdAF7021"],
    },
    "0xba502917c3f7233f9100f9430f4048a224a7d8de": {
        "name": "UniswapV2Factory — Official LCAI Swap factory",
        "safe": True,
        "note": "Official pair factory for Lightchain native DEX liquidity pools.",
        "links": ["https://lightdex.app/", "https://mainnet.lightscan.app/address/0xBA502917c3F7233F9100f9430f4048a224A7D8DE"],
    },
    "0xebf97f16d843bfd9d9e6b1857b4c00d94ca7e2b2": {
        "name": "WLCAI — Wrapped native LCAI (official)",
        "safe": True,
        "note": "Wrapped native LCAI used by UniV2-style pools on Lightchain. Native LCAI itself has no ERC-20 address.",
        "links": ["https://mainnet.lightscan.app/address/0xeBf97f16d843bFD9d9E6B1857B4C00d94ca7e2B2", "https://lightdex.app/"],
    },
    # ── Community tokens (known-good, still use care) ───────────────────
    "0x93ed20e33e7c88cfa73348086ed1f2c7a2b50854": {
        "name": "KEIKO token (Filament / Lightchain)",
        "safe": True,
        "note": "Community KEIKO meme token on Filament forge (graduated). Not official protocol LCAI. Only trade via filament.exchange with this exact address.",
        "links": [
            "https://filament.exchange/",
            "https://mainnet.lightscan.app/address/0x93eD20e33e7C88CFa73348086ed1f2c7a2B50854",
        ],
    },
    "0xde55225815c8bbd702f1d94d24b116859895beb9": {
        "name": "KEIKO/WLCAI Uniswap V2 pair (Filament)",
        "safe": True,
        "note": "Liquidity pair for KEIKO on Filament. LP is burned; always verify pair + token addresses on Filament/Lightscan.",
        "links": ["https://filament.exchange/", "https://mainnet.lightscan.app/address/0xDe55225815c8BBD702F1D94D24b116859895beB9"],
    },
    # ── Common Ethereum routers (legitimate infra; site context still matters) ─
    "0x7a250d5630b4cf539739df2c5dacb4c659f2488d": {
        "name": "Uniswap V2 Router (Ethereum)",
        "safe": True,
        "note": "Canonical Uniswap V2 router on Ethereum. Safe infrastructure — only use via app.uniswap.org or trusted UIs.",
        "links": ["https://app.uniswap.org/", "https://etherscan.io/address/0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"],
    },
    "0xe592427a0aece92de3edee1f18e0157c05861564": {
        "name": "Uniswap V3 SwapRouter (Ethereum)",
        "safe": True,
        "note": "Official Uniswap V3 router. Use only through app.uniswap.org.",
        "links": ["https://app.uniswap.org/", "https://etherscan.io/address/0xE592427A0AEce92De3Edee1F18E0157C05861564"],
    },
    "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45": {
        "name": "Uniswap V3 SwapRouter02 (Ethereum)",
        "safe": True,
        "note": "Official Uniswap V3 Router02. Use only through app.uniswap.org.",
        "links": ["https://app.uniswap.org/"],
    },
    "0x3fc91a3afd70395cd496c647d5a6cc9d4b2b7fad": {
        "name": "Uniswap Universal Router (Ethereum)",
        "safe": True,
        "note": "Official Uniswap Universal Router. Use only through app.uniswap.org.",
        "links": ["https://app.uniswap.org/"],
    },
}

VERIFIED_SITES = {
    "lightchain.ai": {"name": "Lightchain AI — Official Site", "safe": True},
    "lightdex.app": {"name": "LCAI Swap — Official native DEX", "safe": True},
    "www.lightdex.app": {"name": "LCAI Swap — Official native DEX", "safe": True},
    "bridge.lightchain.ai": {"name": "Lightchain Bridge — Official", "safe": True},
    "workers.lightchain.ai": {"name": "Lightchain Worker Explorer — Official", "safe": True},
    "docs.lightchain.ai": {"name": "Lightchain Documentation — Official", "safe": True},
    "dao.lightchain.ai": {"name": "Lightchain Governance — Official", "safe": True},
    "hub.lightchain.ai": {"name": "Lightchain dApp Hub — Official", "safe": True},
    "forum.lightchain.ai": {"name": "Lightchain Forum — Official", "safe": True},
    "deploy.lightchain.ai": {"name": "Lightchain IDE — Official", "safe": True},
    "chat.lightchain.ai": {"name": "Lightchain Chat — Official", "safe": True},
    "mainnet.lightscan.app": {"name": "Lightchain Explorer — Official", "safe": True},
    "app.uniswap.org": {"name": "Uniswap — Official (ERC-20 LCAI on Ethereum)", "safe": True},
    "uniswap.org": {"name": "Uniswap — Official", "safe": True},
    "filament.exchange": {"name": "Filament — Community DEX & forge on Lightchain", "safe": True},
    "www.filament.exchange": {"name": "Filament — Community DEX & forge on Lightchain", "safe": True},
    "dex-testnet.lightchain.ai": {"name": "Lightchain DEX (Testnet only) — Official", "safe": True},
}

KNOWN_SCAM_PATTERNS = [
    r"lightchain-ai\.com",
    r"lightchain\.io",
    r"lcai-token\.",
    r"lightchainprotocol\.",
    r"lightchain-protocol\.",
    r"free.*lcai",
    r"lcai.*airdrop.*claim",
    r"lightchain.*presale",
    r"uniswap\.(io|net|app\.io|exchange)",
    r"uninswap\.",
    r"uniswvap\.",
    r"pancakeswap\.(org|net|io)",
    r"lightdex\.(com|io|net|org|win|xyz)",
    r"light-dex\.",
    r"filament\.(com|io|net|app)",
    r"bridge\.lightchain\.(com|io|net)",
]

# ════════════════════════════════════════════════════════════════════════
# SYSTEM PROMPT
# ════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """You are OrcaGuard, an AI crypto safety assistant built to protect non-technical crypto users from scams. You have deep knowledge of crypto scams, phishing attacks, honeypot contracts, and how to verify legitimate projects.

Your job is to give CLEAR, PLAIN-ENGLISH verdicts. Never use technical jargon without explaining it. Always end with a clear recommendation: SAFE, CAUTION, or DANGER.

== LIGHTCHAIN AI (LCAI) — VERIFIED FACTS ==

Official LCAI contract (Ethereum Mainnet): 0x9cA8530CA349c966Fe9ef903Df17a75B8A778927
CoinMarketCap: https://coinmarketcap.com/currencies/lightchain-ai/
CoinGecko: (search LCAI)
Official site: lightchain.ai

WHERE TO BUY / GET LCAI SAFELY:
1. Official native DEX (Lightchain Mainnet chain 9200): https://lightdex.app/ — LCAI Swap for native LCAI (gas + dApps). Bookmark only this domain.
2. ERC-20 LCAI on Ethereum: Uniswap app.uniswap.org — search by contract 0x9cA8530CA349c966Fe9ef903Df17a75B8A778927 only, never by name alone. Slippage ~1-2%.
3. Bridge ERC-20 → native: ONLY https://bridge.lightchain.ai/ — after bridging, switch wallet to Lightchain Mainnet (9200). Native LCAI has NO contract address on Lightchain.
4. CEXs (e.g. BitMart) only if they list the official contract — check CoinMarketCap markets. Withdraw network carefully.
5. Any exchange that shows the exact contract 0x9cA8530CA349c966Fe9ef903Df17a75B8A778927 for the Ethereum token.

CRITICAL DISTINCTION:
- ERC-20 LCAI (Ethereum) ≠ native LCAI (Lightchain). DApps on Lightchain need native LCAI for gas.
- Anyone offering a "contract address for native LCAI on Lightchain" is a SCAM.

WHERE LCAI IS NOT LISTED (anything claiming LCAI there is a SCAM):
- Coinbase — NOT LISTED. Any "LCAI" on Coinbase is a fake scam token.
- Any exchange not showing the official Ethereum contract address above (when claiming the ERC-20).

Official / verified sites (ONLY trust these for LCAI / Lightchain tooling):
- lightchain.ai, lightdex.app, bridge.lightchain.ai, workers.lightchain.ai
- docs.lightchain.ai, dao.lightchain.ai, forum.lightchain.ai, hub.lightchain.ai
- mainnet.lightscan.app, deploy.lightchain.ai, chat.lightchain.ai
- app.uniswap.org (ERC-20 only), filament.exchange (community DEX/forge — not the official LCAI Swap)

== COMMON CRYPTO SCAMS TO WATCH FOR ==

HONEYPOT CONTRACTS:
- You can buy but cannot sell
- Red flags: sell function is disabled, transfer has hidden conditions, owner can change rules
- Verdict: ALWAYS DANGER — never interact

AIRDROP SCAMS:
- Random tokens appear in your wallet you didn't buy
- NEVER interact with, approve, or try to sell unknown airdropped tokens
- Interacting often triggers approval for scammers to drain your wallet
- Verdict: ALWAYS DANGER — do not touch, do not approve

FAKE EXCHANGE LISTINGS:
- Scammers create tokens with the same name/ticker as real projects
- ALWAYS verify by the contract address, never by name or ticker alone
- If someone says "buy LCAI on Coinbase" — it's a scam (LCAI is not on Coinbase)

PHISHING SITES:
- Fake Uniswap: look for misspellings (uninswap, uniswap.io vs app.uniswap.org)
- Always check the URL carefully before connecting your wallet
- Bookmark official sites, never use Google search links for DeFi

WALLET DRAINER TRANSACTIONS:
- Asks you to "approve" spending unlimited tokens
- "setApprovalForAll" — gives complete control of your NFTs
- Any transaction with a very high gas fee for a simple action
- Verdict: NEVER approve what you don't understand

FAKE SUPPORT SCAMS:
- Someone DMs you on Discord/Telegram offering to help
- Real support NEVER asks for your seed phrase or private key
- Verdict: Block immediately, your seed phrase = your entire wallet

SEED PHRASE / PRIVATE KEY:
- NEVER share with anyone, ever, for any reason
- Anyone asking is always a scammer
- Not even Lightchain support, not even MetaMask support

== HOW TO VERIFY ANY CONTRACT ==
1. Go to CoinMarketCap or CoinGecko, search the project name
2. Find the official contract address on their page
3. Compare character by character with what you have
4. If they don't match exactly — it's a fake

== YOUR RESPONSE FORMAT ==
Always structure your response as:
1. VERDICT: 🟢 SAFE / 🟡 CAUTION / 🔴 DANGER
2. Plain English explanation (2-3 sentences max)
3. What to do next (specific action)

Be direct. Be clear. These are people who may lose real money."""

# ════════════════════════════════════════════════════════════════════════
# AIVM CLIENT — Lightchain v2 Decentralized Inference
# ════════════════════════════════════════════════════════════════════════

AIVM_GATEWAY  = "https://chat-api.mainnet.lightchain.ai"
AIVM_RELAY    = "wss://relay.mainnet.lightchain.ai/ws"
AIVM_RPC      = "https://rpc.mainnet.lightchain.ai"
AIVM_JOB_REG  = "0xfB15F90298e4CcD7106E76fFB5e520315cC42B0b"
AIVM_JOB_FEE  = 20_000_000_000_000_000   # 0.02 LCAI in wei
AIVM_CHAIN_ID = 9200

AIVM_ABI = [
    {
        "name": "createSession", "type": "function", "stateMutability": "payable",
        "inputs": [
            {"name": "paramsHash",     "type": "bytes32"},
            {"name": "worker",         "type": "address"},
            {"name": "encWorkerKey",   "type": "bytes"},
            {"name": "ephemeralPubKey","type": "bytes"},
            {"name": "initState",      "type": "bytes"},
            {"name": "expiry",         "type": "uint256"},
        ],
        "outputs": [{"name": "sessionId", "type": "uint256"}],
    },
    {
        "name": "submitJob", "type": "function", "stateMutability": "payable",
        "inputs": [
            {"name": "sessionId",  "type": "uint256"},
            {"name": "promptHash", "type": "bytes32"},
        ],
        "outputs": [{"name": "jobId", "type": "uint256"}],
    },
    {
        "anonymous": False, "name": "SessionCreated", "type": "event",
        "inputs": [
            {"indexed": True,  "name": "sessionId",     "type": "uint256"},
            {"indexed": True,  "name": "user",           "type": "address"},
            {"indexed": True,  "name": "paramsHash",     "type": "bytes32"},
            {"indexed": False, "name": "worker",         "type": "address"},
            {"indexed": False, "name": "encWorkerKey",   "type": "bytes"},
            {"indexed": False, "name": "ephemeralPubKey","type": "bytes"},
        ],
    },
    {
        "anonymous": False, "name": "JobSubmitted", "type": "event",
        "inputs": [
            {"indexed": True,  "name": "jobId",     "type": "uint256"},
            {"indexed": True,  "name": "sessionId", "type": "uint256"},
            {"indexed": False, "name": "worker",    "type": "address"},
        ],
    },
    {
        "anonymous": False, "name": "JobCompleted", "type": "event",
        "inputs": [
            {"indexed": True,  "name": "jobId",          "type": "uint256"},
            {"indexed": True,  "name": "worker",          "type": "address"},
            {"indexed": False, "name": "responseHash",    "type": "bytes32"},
            {"indexed": False, "name": "ciphertextHash",  "type": "bytes32"},
        ],
    },
]


def _decode_pubkey(s):
    """Accept hex (with/without 0x) or base64; return 65-byte uncompressed P-256 point."""
    if isinstance(s, (bytes, bytearray)):
        return bytes(s)
    s = s.strip()
    if s.startswith('0x') or s.startswith('0X'):
        b = bytes.fromhex(s[2:])
    elif len(s) == 130 and all(c in '0123456789abcdefABCDEF' for c in s):
        b = bytes.fromhex(s)
    else:
        b = base64.b64decode(s)
    if len(b) != 65:
        raise ValueError(f"pubkey decode: expected 65 bytes, got {len(b)}")
    return b


def _ecdh_wrap(session_key: bytes, peer_pub_bytes: bytes) -> bytes:
    """ECDH-wrap session_key for peer P-256 pubkey."""
    from cryptography.hazmat.primitives.asymmetric.ec import (
        generate_private_key, ECDH, EllipticCurvePublicNumbers, SECP256R1
    )
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.backends import default_backend

    x = int.from_bytes(peer_pub_bytes[1:33], 'big')
    y = int.from_bytes(peer_pub_bytes[33:65], 'big')
    peer_pub = EllipticCurvePublicNumbers(x, y, SECP256R1()).public_key(default_backend())

    ephem_priv = generate_private_key(SECP256R1(), default_backend())
    shared = ephem_priv.exchange(ECDH(), peer_pub)

    pub_nums = ephem_priv.public_key().public_numbers()
    ephem_pub_bytes = (b'\x04' +
                       pub_nums.x.to_bytes(32, 'big') +
                       pub_nums.y.to_bytes(32, 'big'))

    nonce  = secrets.token_bytes(12)
    ct_tag = AESGCM(shared).encrypt(nonce, session_key, None)
    return ephem_pub_bytes + nonce + ct_tag


def _aes_encrypt(key: bytes, plaintext: bytes) -> bytes:
    """AES-256-GCM encrypt. Returns nonce(12) || ct || tag(16)."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = secrets.token_bytes(12)
    return nonce + AESGCM(key).encrypt(nonce, plaintext, None)


def _aes_decrypt(key: bytes, blob: bytes) -> bytes:
    """AES-256-GCM decrypt nonce(12) || ct || tag(16)."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if len(blob) < 28:
        raise ValueError("ciphertext too short")
    return AESGCM(key).decrypt(blob[:12], blob[12:], None)


class AIVMClient:
    """Runs LLM inference through the Lightchain v2 decentralized worker network."""

    def __init__(self, private_key: str):
        import requests as _req
        from web3 import Web3
        from eth_account import Account

        self._req      = _req
        self._w3       = Web3(Web3.HTTPProvider(AIVM_RPC))
        self._account  = Account.from_key(private_key)
        self._registry = self._w3.eth.contract(
            address=Web3.to_checksum_address(AIVM_JOB_REG),
            abi=AIVM_ABI,
        )
        self._jwt     = None
        self._jwt_exp = 0
        print(f"  [AIVM] wallet: {self._account.address}")

    def _get_jwt(self) -> str:
        from eth_account.messages import encode_defunct
        if self._jwt and time.time() < self._jwt_exp - 30:
            return self._jwt
        r = self._req.get(
            f"{AIVM_GATEWAY}/api/auth/challenge",
            params={"address": self._account.address}, timeout=15,
        )
        r.raise_for_status()
        message = r.json()["message"]
        sig = self._account.sign_message(encode_defunct(text=message))
        r2 = self._req.post(
            f"{AIVM_GATEWAY}/api/auth/verify",
            json={"message": message, "signature": "0x" + sig.signature.hex()},
            timeout=15,
        )
        r2.raise_for_status()
        v = r2.json()
        self._jwt = v["token"]
        exp_str = v["expiresAt"][:19].replace("T", " ")
        self._jwt_exp = time.mktime(time.strptime(exp_str, "%Y-%m-%d %H:%M:%S"))
        return self._jwt

    def _auth_headers(self):
        return {
            "Authorization": f"Bearer {self._get_jwt()}",
            "Accept":        "application/json",
            "Content-Type":  "application/json",
        }

    def run_inference(self, prompt: str, timeout_secs: int = 360) -> str:
        import aivm_client as _aivm_sortition
        return _aivm_sortition.infer(prompt, timeout=timeout_secs)
        import websocket as _ws
        from web3 import Web3

        req = self._req
        print(f"  [AIVM] starting inference ({len(prompt)} chars)")

        # 1-2. Auth + pick model
        r = req.get(f"{AIVM_GATEWAY}/api/models", timeout=15)
        r.raise_for_status()
        models = r.json().get("models", [])
        model  = next((m for m in models if m["name"] == "llama3-8b"), models[0] if models else None)
        if not model:
            raise RuntimeError("No models available from AIVM gateway")
        model_id = model["id"]
        print(f"  [AIVM] model: {model['name']} id={model_id[:10]}...")

        # 3. Select worker
        r = req.post(
            f"{AIVM_GATEWAY}/api/sessions/select",
            json={"modelId": model_id},
            headers=self._auth_headers(), timeout=15,
        )
        r.raise_for_status()
        sel = r.json()
        print(f"  [AIVM] worker: {sel['worker']}")

        # 4-5. Session key + ECDH wrap
        session_key  = secrets.token_bytes(32)
        enc_worker   = _ecdh_wrap(session_key, _decode_pubkey(sel["workerEncryptionKey"]))
        enc_disputer = _ecdh_wrap(session_key, _decode_pubkey(sel["disputerEncryptionKey"]))

        # 6. Prepare (get dispatcher signature)
        r = req.post(
            f"{AIVM_GATEWAY}/api/sessions/prepare",
            json={
                "modelId":        model_id,
                "encWorkerKey":   base64.b64encode(enc_worker).decode(),
                "encDisputerKey": base64.b64encode(enc_disputer).decode(),
            },
            headers=self._auth_headers(), timeout=15,
        )
        r.raise_for_status()
        prep = r.json()

        # 7. createSession on-chain
        def _h(s): return s[2:] if isinstance(s, str) and s[:2].lower() == '0x' else s
        params_hash = bytes.fromhex(_h(model_id).zfill(64))
        sig_bytes   = bytes.fromhex(_h(prep["signature"]))
        gas_price = self._w3.eth.gas_price
        nonce_val = self._w3.eth.get_transaction_count(self._account.address)

        tx = self._registry.functions.createSession(
            params_hash,
            Web3.to_checksum_address(prep["worker"]),
            enc_worker,
            enc_disputer,
            sig_bytes,
            prep["expiry"],
        ).build_transaction({
            "from":     self._account.address,
            "nonce":    nonce_val,
            "gas":      1_000_000,
            "gasPrice": gas_price,
            "value":    0,
            "chainId":  AIVM_CHAIN_ID,
        })
        signed  = self._account.sign_transaction(tx)
        tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)
        print(f"  [AIVM] createSession tx: {tx_hash.hex()}")
        receipt1 = self._w3.eth.wait_for_transaction_receipt(tx_hash, timeout=90)
        if receipt1.status != 1:
            raise RuntimeError("createSession reverted on-chain")

        session_id = None
        for log in receipt1.logs:
            try:
                evt = self._registry.events.SessionCreated().process_log(log)
                session_id = evt["args"]["sessionId"]
                break
            except Exception:
                pass
        if session_id is None:
            raise RuntimeError("SessionCreated event not found in receipt")
        print(f"  [AIVM] sessionId: {session_id}")

        # 8. Get relay token
        relay_token = None
        deadline = time.time() + 120
        while time.time() < deadline:
            r = req.get(
                f"{AIVM_GATEWAY}/api/sessions/{session_id}/token",
                headers=self._auth_headers(), timeout=10,
            )
            if r.status_code == 200:
                d = r.json()
                if d.get("token"):
                    relay_token = d["token"]
                    break
            time.sleep(1)
        if not relay_token:
            raise RuntimeError("Relay token not ready within 120s")

        chunks   = []
        ws_ready = threading.Event()
        ws_err   = [None]

        def _on_message(ws_obj, message):
            try:
                frame = json.loads(message)
                payload = frame.get("payload")
                if not payload:
                    return
                blob = base64.b64decode(payload)
                try:
                    pt = _aes_decrypt(session_key, blob)
                    chunks.append(pt.decode("utf-8", errors="replace"))
                except Exception:
                    pass
            except Exception:
                pass

        def _on_open(ws_obj):
            ws_ready.set()

        def _on_error(ws_obj, err):
            ws_err[0] = err
            ws_ready.set()

        ws = _ws.WebSocketApp(
            f"{AIVM_RELAY}?token={url_quote(relay_token)}",
            on_message=_on_message,
            on_open=_on_open,
            on_error=_on_error,
        )
        ws_thread = threading.Thread(target=ws.run_forever, daemon=True)
        ws_thread.start()
        ws_ready.wait(timeout=15)
        if ws_err[0]:
            raise RuntimeError(f"WebSocket failed: {ws_err[0]}")
        print("  [AIVM] relay connected")

        # 9. Encrypt prompt + upload blob
        # Build full prompt with system context
        full_prompt = f"[SYSTEM]\n{SYSTEM_PROMPT}\n\n[USER]\n{prompt}"
        cipher = _aes_encrypt(session_key, full_prompt.encode("utf-8"))
        r = req.post(
            f"{AIVM_GATEWAY}/api/blobs",
            json={"data": base64.b64encode(cipher).decode()},
            headers=self._auth_headers(), timeout=15,
        )
        r.raise_for_status()
        blob_hashes = r.json().get("blobHashes", [])
        if not blob_hashes:
            raise RuntimeError("No blob hash returned from gateway")
        prompt_hash = bytes.fromhex(_h(blob_hashes[0]).zfill(64))

        # 10. submitJob (pay 0.02 LCAI)
        nonce_val2 = self._w3.eth.get_transaction_count(self._account.address)
        tx2 = self._registry.functions.submitJob(
            session_id,
            prompt_hash,
        ).build_transaction({
            "from":     self._account.address,
            "nonce":    nonce_val2,
            "gas":      500_000,
            "gasPrice": gas_price,
            "value":    AIVM_JOB_FEE,
            "chainId":  AIVM_CHAIN_ID,
        })
        signed2  = self._account.sign_transaction(tx2)
        tx_hash2 = self._w3.eth.send_raw_transaction(signed2.raw_transaction)
        print(f"  [AIVM] submitJob tx: {tx_hash2.hex()}")
        receipt2 = self._w3.eth.wait_for_transaction_receipt(tx_hash2, timeout=90)
        if receipt2.status != 1:
            raise RuntimeError("submitJob reverted — check LCAI balance")

        job_id = None
        for log in receipt2.logs:
            try:
                evt = self._registry.events.JobSubmitted().process_log(log)
                job_id = evt["args"]["jobId"]
                break
            except Exception:
                pass
        if job_id is None:
            raise RuntimeError("JobSubmitted event not found in receipt")
        print(f"  [AIVM] jobId: {job_id}")

        # 11. Poll for JobCompleted
        job_completed_topic = "0x" + Web3.keccak(
            text="JobCompleted(uint256,address,bytes32,bytes32)"
        ).hex()
        job_id_topic = "0x" + hex(job_id)[2:].zfill(64)

        done     = False
        deadline = time.time() + timeout_secs
        while time.time() < deadline and not done:
            time.sleep(5)
            if chunks:
                print(f"  [AIVM] relay data arrived ({len(chunks)} chunks), returning early")
                done = True
                break
            try:
                head = self._w3.eth.block_number
                logs = self._w3.eth.get_logs({
                    "address":   Web3.to_checksum_address(AIVM_JOB_REG),
                    "fromBlock": receipt2.blockNumber,
                    "toBlock":   head,
                    "topics":    [job_completed_topic, job_id_topic],
                })
                if logs:
                    done = True
                    print(f"  [AIVM] JobCompleted on-chain!")
            except Exception as e:
                print(f"  [AIVM] log poll error (retrying): {e}")

        time.sleep(4)  # grace period for final relay frames
        ws.close()

        result = "".join(chunks)
        if result:
            print(f"  [AIVM] inference done, {len(result)} chars")
            return result

        if not done:
            raise RuntimeError(f"Timeout after {timeout_secs}s waiting for JobCompleted")

        return result or "Sorry, the AI completed the job but returned no response. Please try again."


_aivm_client = None

def get_aivm_client():
    global _aivm_client
    pk = os.environ.get("LIGHTCHAIN_PRIVATE_KEY", "").strip()
    if not pk:
        return None
    if _aivm_client is None:
        try:
            _aivm_client = AIVMClient(pk)
        except Exception as e:
            print(f"  [AIVM] init failed: {e}")
            return None
    return _aivm_client

def run_inference(prompt: str) -> str:
    client = get_aivm_client()
    if client:
        try:
            return client.run_inference(prompt)
        except Exception as e:
            print(f"  [AIVM] failed: {e}")
            return f"AI error: {e}"
    return "AI assistant unavailable — LIGHTCHAIN_PRIVATE_KEY not set."

# ════════════════════════════════════════════════════════════════════════
# QUICK CHECK LOGIC (instant, no AIVM needed)
# ════════════════════════════════════════════════════════════════════════

def quick_contract_check(address: str) -> dict:
    """Instant check against known contracts before using AIVM."""
    addr_lower = address.lower().strip()
    if addr_lower in VERIFIED_CONTRACTS:
        c = VERIFIED_CONTRACTS[addr_lower]
        return {"verdict": "safe", "known": True, "name": c["name"], "note": c["note"], "links": c.get("links", [])}
    if not re.match(r'^0x[0-9a-f]{40}$', addr_lower):
        return {"verdict": "invalid", "known": True, "note": "This doesn't look like a valid contract address. A valid address starts with 0x followed by exactly 40 characters."}
    return {"verdict": "unknown", "known": False}

def quick_url_check(url: str) -> dict:
    """Instant check against known safe/scam sites."""
    raw = (url or "").strip()
    try:
        parsed = urlparse(raw if "://" in raw else "https://" + raw)
        domain = (parsed.netloc or "").lower()
        if domain.startswith("www."):
            domain = domain[4:]
        # Drop userinfo / port for matching
        domain = domain.split("@")[-1].split(":")[0]
    except Exception:
        domain = raw.lower().strip()

    if not domain:
        return {"verdict": "invalid", "known": True,
                "note": "That doesn't look like a full website address. Paste the full URL from your browser bar (starts with https://)."}

    if domain in VERIFIED_SITES:
        s = VERIFIED_SITES[domain]
        return {"verdict": "safe", "known": True, "name": s["name"]}

    for pattern in KNOWN_SCAM_PATTERNS:
        if re.search(pattern, raw.lower()) or re.search(pattern, domain):
            return {"verdict": "danger", "known": True,
                    "note": "This URL matches a known scam pattern. Do NOT connect your wallet to this site."}

    # Suspicious patterns — brand impersonation is the main wallet-drainer risk
    warnings = []
    if re.search(r'lightchain|lcai', domain) and domain not in VERIFIED_SITES:
        warnings.append("Looks Lightchain-related but is NOT on the official verified list")
    if re.search(r'lightdex|light-dex|lcai.?swap', domain) and domain not in VERIFIED_SITES:
        warnings.append("Looks like the official DEX but is not lightdex.app — high phishing risk")
    if re.search(r'filament', domain) and domain not in VERIFIED_SITES:
        warnings.append("Looks Filament-related but is not filament.exchange")
    if re.search(r'uniswap', domain) and "uniswap.org" not in domain:
        warnings.append("Claims to be Uniswap but is not app.uniswap.org / uniswap.org")
    if re.search(r'metamask|trustwallet|coinbase', domain) and domain not in VERIFIED_SITES:
        warnings.append("Uses a wallet brand name in the domain — common phishing pattern")
    if re.search(r'(free|claim|airdrop|bonus|reward|giveaway)', domain):
        warnings.append("Domain contains words commonly used in crypto scams")
    if re.search(r'\d{2,}', domain) and re.search(r'lightchain|uniswap|lcai|lightdex', domain):
        warnings.append("Numbers in a brand-like domain often mean a lookalike scam site")

    if warnings:
        return {"verdict": "caution", "known": True, "warnings": warnings,
                "note": "This site shows suspicious patterns. Do NOT connect your wallet without verifying further.\n\n• "
                        + "\n• ".join(warnings)}

    return {"verdict": "unknown", "known": False}

# ════════════════════════════════════════════════════════════════════════
# AI RATE LIMITER — AI_DAILY_LIMIT AIVM calls per IP per day
# ════════════════════════════════════════════════════════════════════════

# Free safety checks per IP per day (contract / URL / bot / ask share this budget)
AI_DAILY_LIMIT = 12
_ip_usage      = {}   # { ip: {"count": N, "date": "YYYY-MM-DD"} }
_ip_lock       = threading.Lock()

# Scoped CORS (open-endpoints polish 2026-08-22)
_CORS_ORIGINS = [o.strip() for o in os.environ.get(
    "CORS_ORIGINS",
    "https://your-domain.example,http://localhost:8186,http://127.0.0.1:8186"
).split(",") if o.strip()]


def _cors_for(handler) -> str:
    origin = (handler.headers.get("Origin") or "").strip()
    if origin in _CORS_ORIGINS:
        return origin
    return _CORS_ORIGINS[0] if _CORS_ORIGINS else "https://your-domain.example"

def _get_client_ip(handler) -> str:
    """Get real IP, respecting Railway's X-Forwarded-For proxy header."""
    forwarded = handler.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return handler.client_address[0]

def _check_ai_limit(ip: str) -> tuple[bool, int]:
    """Returns (allowed, remaining). Deducts 1 on success."""
    today = time.strftime("%Y-%m-%d")
    with _ip_lock:
        rec = _ip_usage.get(ip)
        if rec is None or rec["date"] != today:
            _ip_usage[ip] = {"count": 0, "date": today}
            rec = _ip_usage[ip]
        remaining = AI_DAILY_LIMIT - rec["count"]
        if remaining <= 0:
            return False, 0
        rec["count"] += 1
        return True, remaining - 1

def _peek_ai_remaining(ip: str) -> int:
    """Check remaining without deducting."""
    today = time.strftime("%Y-%m-%d")
    with _ip_lock:
        rec = _ip_usage.get(ip)
        if rec is None or rec["date"] != today:
            return AI_DAILY_LIMIT
        return max(0, AI_DAILY_LIMIT - rec["count"])

# ════════════════════════════════════════════════════════════════════════
# HTTP SERVER
# ════════════════════════════════════════════════════════════════════════

SERVER_START = time.time()
_jobs        = {}
_jobs_lock   = threading.Lock()


class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass

    def _send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", _cors_for(self))
        self.send_header("Vary", "Origin")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, msg, code=400):
        self._send_json({"error": msg}, code)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length))
        except Exception:
            return {}

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", _cors_for(self))
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Vary", "Origin")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path.rstrip("/")

        if path == "" or path == "/":
            html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
            try:
                with open(html_path, "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except FileNotFoundError:
                self._send_error("index.html not found", 404)
            return

        # Serve static assets (icon, favicon, etc.) from the same directory
        STATIC_TYPES = {
            ".png": "image/png", ".ico": "image/x-icon",
            ".svg": "image/svg+xml", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        }
        _, ext = os.path.splitext(path)
        if ext.lower() in STATIC_TYPES:
            static_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                       os.path.basename(path))
            if os.path.isfile(static_path):
                with open(static_path, "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", STATIC_TYPES[ext.lower()])
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                self.wfile.write(body)
                return
            self._send_error("Not found", 404)
            return

        if path == "/api/health":
            uptime = int(time.time() - SERVER_START)
            h, rem = divmod(uptime, 3600)
            m = rem // 60
            self._send_json({"ok": True, "uptime": uptime, "uptimeLabel": f"{h}h {m}m",
                             "aivm": bool(get_aivm_client())})
            return

        if path == "/api/job":
            qs     = parse_qs(parsed.query)
            job_id = qs.get("id", [""])[0].strip()
            with _jobs_lock:
                job = _jobs.get(job_id)
            if not job:
                self._send_error("Job not found", 404)
                return
            self._send_json(job)
            return

        self._send_error("Not found", 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path   = parsed.path.rstrip("/")

        if path == "/api/ask":
            self._handle_ask()
            return

        if path == "/api/check-contract":
            self._handle_check_contract()
            return

        if path == "/api/check-url":
            self._handle_check_url()
            return

        if path == "/api/check-bot":
            self._handle_check_bot()
            return

        if path == "/api/check-wallet":
            self._handle_check_wallet()
            return

        if path == "/api/scan-airdrops":
            self._handle_scan_airdrops()
            return

        self._send_error("Not found", 404)

    def _handle_ask(self):
        body     = self._read_body()
        question = body.get("question", "").strip()
        if not question:
            self._send_error("question is required")
            return
        if len(question) > 3000:
            self._send_error("question too long (max 3000 chars)")
            return

        ip = _get_client_ip(self)
        allowed, remaining = _check_ai_limit(ip)
        if not allowed:
            self._send_json({"ok": False, "limitReached": True,
                             "error": f"You've used all {AI_DAILY_LIMIT} free AI questions for today. Come back tomorrow!"}, 429)
            return

        import uuid
        job_id = str(uuid.uuid4())[:12]
        with _jobs_lock:
            _jobs[job_id] = {"status": "pending", "ts": time.time()}

        def _run():
            try:
                answer = run_inference(question)
                with _jobs_lock:
                    _jobs[job_id] = {"status": "done", "ts": time.time(), "answer": answer}
            except Exception as e:
                with _jobs_lock:
                    _jobs[job_id] = {"status": "error", "ts": time.time(), "error": str(e)}
            with _jobs_lock:
                if len(_jobs) > 50:
                    oldest = sorted(_jobs.items(), key=lambda x: x[1].get("ts", 0))
                    for k, _ in oldest[:-50]:
                        del _jobs[k]

        threading.Thread(target=_run, daemon=True).start()
        self._send_json({"ok": True, "jobId": job_id, "remaining": remaining})

    def _handle_check_contract(self):
        body    = self._read_body()
        address = body.get("address", "").strip()
        if not address:
            self._send_error("address is required")
            return

        quick = quick_contract_check(address)
        if quick["known"] and quick["verdict"] != "unknown":
            self._send_json({"ok": True, "quick": True, **quick})
            return

        # Unknown contract — check rate limit before using AIVM
        ip = _get_client_ip(self)
        allowed, remaining = _check_ai_limit(ip)
        if not allowed:
            self._send_json({"ok": False, "limitReached": True,
                             "error": f"You've used all {AI_DAILY_LIMIT} free AI questions for today. Come back tomorrow!"}, 429)
            return

        # Live data enrichment — Etherscan + Ethereum RPC + Lightchain RPC
        import urllib.request as _ur
        import datetime as _dt

        addr_norm = address if address.startswith("0x") else ("0x" + address)
        addr_norm = addr_norm[:42]

        ETHERSCAN_KEY = os.environ.get("ETHERSCAN_API_KEY", "")
        key_param     = f"&apikey={ETHERSCAN_KEY}" if ETHERSCAN_KEY else ""
        ETH_RPC       = os.environ.get("ETH_RPC_URL", "https://eth.llamarpc.com")
        LCAI_RPC      = "https://rpc.mainnet.lightchain.ai"
        es_link       = f"https://etherscan.io/address/{addr_norm}"
        ls_link       = f"https://mainnet.lightscan.app/address/{addr_norm}"

        results = {
            "source": None, "txlist_asc": None, "txlist_desc": None,
            "eth_code": None, "eth_tx": None, "eth_bal": None,
            "lcai_code": None, "lcai_tx": None,
        }

        def _es_source():
            try:
                url = (
                    "https://api.etherscan.io/v2/api?chainid=1"
                    f"&module=contract&action=getsourcecode&address={addr_norm}{key_param}"
                )
                req = _ur.Request(url, headers={"User-Agent": "OrcaGuard/1.0"})
                with _ur.urlopen(req, timeout=10) as r:
                    data = json.loads(r.read())
                if data.get("status") == "1":
                    results["source"] = data.get("result", [None])[0]
                else:
                    results["source"] = {}  # confirmed empty / not verified
            except Exception as e:
                print(f"  [Etherscan/source] {e}")

        def _es_txlist(sort, key):
            try:
                url = (
                    "https://api.etherscan.io/v2/api?chainid=1"
                    f"&module=account&action=txlist&address={addr_norm}"
                    f"&startblock=0&endblock=99999999&page=1&offset=8&sort={sort}{key_param}"
                )
                req = _ur.Request(url, headers={"User-Agent": "OrcaGuard/1.0"})
                with _ur.urlopen(req, timeout=10) as r:
                    data = json.loads(r.read())
                msg = data.get("message", "")
                if data.get("status") == "1":
                    results[key] = data.get("result", [])
                elif "No transactions" in msg or "No records" in msg:
                    results[key] = []
            except Exception as e:
                print(f"  [Etherscan/txlist-{sort}] {e}")

        def _rpc(rpc_url, method, params, key):
            try:
                payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
                req = _ur.Request(rpc_url, data=payload, headers={"Content-Type": "application/json"})
                with _ur.urlopen(req, timeout=8) as r:
                    results[key] = json.loads(r.read()).get("result", None)
            except Exception as e:
                print(f"  [RPC/{key}] {e}")

        threads = [
            threading.Thread(target=_es_source, daemon=True),
            threading.Thread(target=_es_txlist, args=("asc",  "txlist_asc"),  daemon=True),
            threading.Thread(target=_es_txlist, args=("desc", "txlist_desc"), daemon=True),
            threading.Thread(target=_rpc, args=(ETH_RPC,  "eth_getCode",             [addr_norm, "latest"], "eth_code"), daemon=True),
            threading.Thread(target=_rpc, args=(ETH_RPC,  "eth_getTransactionCount", [addr_norm, "latest"], "eth_tx"),   daemon=True),
            threading.Thread(target=_rpc, args=(ETH_RPC,  "eth_getBalance",          [addr_norm, "latest"], "eth_bal"),  daemon=True),
            threading.Thread(target=_rpc, args=(LCAI_RPC, "eth_getCode",             [addr_norm, "latest"], "lcai_code"), daemon=True),
            threading.Thread(target=_rpc, args=(LCAI_RPC, "eth_getTransactionCount", [addr_norm, "latest"], "lcai_tx"),   daemon=True),
        ]
        for t in threads:
            t.start()

        import uuid
        job_id = str(uuid.uuid4())[:12]
        with _jobs_lock:
            _jobs[job_id] = {"status": "pending", "ts": time.time(), "type": "contract", "address": addr_norm}

        # Return jobId immediately — enrichment + AIVM run in background
        self._send_json({
            "ok": True, "quick": False, "jobId": job_id, "remaining": remaining,
            "etherscanUrl": es_link,
            "lightscanUrl": ls_link,
        })

        _threads  = threads
        _results  = results
        _address  = addr_norm
        _es_link  = es_link
        _ls_link  = ls_link

        def _run():
            for t in _threads:
                t.join(timeout=12)

            # ── Ethereum: contract vs empty wallet (EOA) ─────────────────────
            eth_code = _results.get("eth_code")
            if eth_code is None:
                eth_type = "Ethereum code lookup: unavailable"
            elif eth_code in ("0x", "0x0", "") or len(eth_code) <= 4:
                eth_type = "Ethereum: NO contract code — this is a plain wallet address (EOA), not a token/smart contract. Do not treat it as a buyable token contract."
            else:
                eth_type = f"Ethereum: smart contract code present ({len(eth_code)//2 - 1} bytes bytecode approx)"

            eth_tx_raw = _results.get("eth_tx")
            eth_tx_n   = int(eth_tx_raw, 16) if eth_tx_raw else 0
            eth_bal_raw = _results.get("eth_bal")
            try:
                eth_bal_eth = (int(eth_bal_raw, 16) / 1e18) if eth_bal_raw else 0.0
            except Exception:
                eth_bal_eth = 0.0
            eth_act = f"Ethereum nonce/tx count: {eth_tx_n:,}; ETH balance ~{eth_bal_eth:.6f} ETH"

            # ── Etherscan verification ───────────────────────────────────────
            src           = _results.get("source")
            if src is None:
                verified_line = "Etherscan verification: data unavailable (API/network error)"
                contract_name = "Unknown"
            else:
                has_source    = bool((src or {}).get("SourceCode", ""))
                contract_name = (src or {}).get("ContractName", "").strip() or "Unknown"
                compiler      = (src or {}).get("CompilerVersion", "").strip() or "Unknown"
                is_proxy      = (src or {}).get("IsProxy", "0") == "1"
                if has_source:
                    verified_line = f"Etherscan verified: YES — Name: {contract_name}, Compiler: {compiler}"
                    if is_proxy:
                        verified_line += " — PROXY (implementation may differ; still verify carefully)"
                else:
                    verified_line = "Etherscan verified: NO — source code not published (major red flag if this is sold as a token or holds funds)"

            # ── Deployment / age ─────────────────────────────────────────────
            oldest = _results.get("txlist_asc") or []
            if oldest:
                first    = oldest[0]
                deployer = first.get("from", "Unknown")
                ts       = int(first.get("timeStamp", 0) or 0)
                if ts:
                    age_days    = int((time.time() - ts) / 86400)
                    deploy_date = _dt.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
                    age_str     = f"{age_days} days old (first seen {deploy_date} UTC)"
                else:
                    age_str = "Unknown age"
            else:
                deployer = "Not found on Ethereum mainnet tx history"
                age_str  = "No Ethereum normal transactions found (new, inactive, or not on ETH)"

            recent  = _results.get("txlist_desc") or []
            if recent:
                latest_ts  = int(recent[0].get("timeStamp", 0) or 0)
                days_since = int((time.time() - latest_ts) / 86400) if latest_ts else 0
                activity_line = f"Recent Ethereum activity: sample of {len(recent)} txs; last one ~{days_since} days ago"
            else:
                activity_line = "Recent Ethereum activity: none found in sample"

            # ── Lightchain ───────────────────────────────────────────────────
            lcai_code = _results.get("lcai_code")
            if lcai_code is None:
                lcai_line = "Lightchain: lookup unavailable"
            elif lcai_code in ("0x", "0x0", "") or len(lcai_code) <= 4:
                lcai_line = "Lightchain: no contract code at this address (not a Lightchain smart contract / token)"
            else:
                lcai_line = "Lightchain: contract code present at this address"
            lcai_tx_raw = _results.get("lcai_tx")
            lcai_tx_n   = int(lcai_tx_raw, 16) if lcai_tx_raw else 0
            if lcai_tx_n:
                lcai_line += f", ~{lcai_tx_n:,} txs (nonce)"

            # Lightscan token / verification extras (when this is a Lightchain contract)
            ls_extra = "Lightscan token metadata: unavailable"
            try:
                ls_req = _ur.Request(
                    f"https://mainnet.lightscan.app/api/v2/addresses/{_address}",
                    headers={"User-Agent": "OrcaGuard/1.0", "Accept": "application/json"},
                )
                with _ur.urlopen(ls_req, timeout=10) as lsr:
                    ls_addr = json.loads(lsr.read())
                tok = ls_addr.get("token") or {}
                if tok:
                    ls_extra = (
                        f"Lightscan token: name={tok.get('name') or '?'}, "
                        f"symbol={tok.get('symbol') or '?'}, type={tok.get('type') or '?'}, "
                        f"holders≈{tok.get('holders_count') or '?'}"
                    )
                elif ls_addr.get("is_contract"):
                    ls_extra = f"Lightscan: is_contract=true, name={ls_addr.get('name') or 'unnamed'}"
                else:
                    ls_extra = "Lightscan: no ERC-20 token metadata at this address"
                # Prefer verified source if present
                try:
                    sc_req = _ur.Request(
                        f"https://mainnet.lightscan.app/api/v2/smart-contracts/{_address}",
                        headers={"User-Agent": "OrcaGuard/1.0", "Accept": "application/json"},
                    )
                    with _ur.urlopen(sc_req, timeout=10) as scr:
                        sc = json.loads(scr.read())
                    if sc.get("source_code") or sc.get("is_verified"):
                        ls_extra += "; Lightscan source: VERIFIED / published"
                    elif sc.get("creation_status"):
                        ls_extra += f"; Lightscan creation_status={sc.get('creation_status')}"
                except Exception:
                    pass
            except Exception as e:
                print(f"  [contract/lightscan] {e}")

            chain_context = (
                f"{eth_type}\n"
                f"{eth_act}\n"
                f"{verified_line}\n"
                f"Deployer / first-from wallet: {deployer}\n"
                f"Age: {age_str}\n"
                f"{activity_line}\n"
                f"{lcai_line}\n"
                f"{ls_extra}\n"
                f"Etherscan: {_es_link}\n"
                f"Lightscan: {_ls_link}"
            )

            prompt = f"""You are OrcaGuard. A non-technical user wants to know if this address is safe to BUY, APPROVE, or INTERACT WITH as a crypto contract/token.

Address: {_address}

Live chain data (use these facts; do not invent explorer stats):
{chain_context}

Rules for your verdict:
- Prefer CAUTION or DANGER when data is missing, code is unverified, the address is brand-new, or it is only a plain wallet (EOA) being sold as a "token".
- "Etherscan verified" / Lightscan verified is helpful but NOT a guarantee of safety (scams can verify).
- If there is NO contract code on Ethereum AND NO contract code on Lightchain, explain it is not a normal token contract — DANGER or CAUTION for "buying this token".
- If code exists ONLY on Lightchain Mainnet (9200), treat it as a Lightchain token/contract — cite Lightscan facts, not Ethereum-only assumptions.
- Native LCAI on Lightchain has NO ERC-20 contract — anyone selling a "native LCAI contract" is a scam.
- Never tell the user to share seed phrases or private keys.
- Always give concrete next steps: e.g. compare contract on CoinMarketCap / Lightscan, use OrcaGuard URL check on the site they came from, start with tiny amount, check sellability, revoke approvals later.

Structure:
1. VERDICT: 🟢 SAFE / 🟡 CAUTION / 🔴 DANGER
2. Plain English (2–5 short sentences) citing the live facts above
3. What to do next (bullets)

Be direct. Protect the user from loss."""

            try:
                answer = run_inference(prompt)
                # Append explorer links so the UI can still surface them if model omits
                if _es_link not in answer:
                    answer = answer.rstrip() + f"\n\nReview on Etherscan: {_es_link}"
                with _jobs_lock:
                    _jobs[job_id] = {"status": "done", "ts": time.time(), "answer": answer, "type": "contract"}
            except Exception as e:
                with _jobs_lock:
                    _jobs[job_id] = {"status": "error", "ts": time.time(), "error": str(e)}

        threading.Thread(target=_run, daemon=True).start()

    def _handle_check_url(self):
        body = self._read_body()
        url  = body.get("url", "").strip()
        if not url:
            self._send_error("url is required")
            return

        quick = quick_url_check(url)
        if quick["known"] and quick["verdict"] != "unknown":
            self._send_json({"ok": True, "quick": True, **quick})
            return

        # Unknown URL — check rate limit before using AIVM
        ip = _get_client_ip(self)
        allowed, remaining = _check_ai_limit(ip)
        if not allowed:
            self._send_json({"ok": False, "limitReached": True,
                             "error": f"You've used all {AI_DAILY_LIMIT} free AI questions for today. Come back tomorrow!"}, 429)
            return

        # Domain summary for the model (parsed server-side)
        try:
            _p = urlparse(url if "://" in url else "https://" + url)
            _dom = (_p.netloc or "").lower()
            if _dom.startswith("www."):
                _dom = _dom[4:]
            _dom = _dom.split("@")[-1].split(":")[0]
        except Exception:
            _dom = url

        prompt = f"""You are OrcaGuard. A non-technical user wants to know if it is safe to OPEN this site and CONNECT a crypto wallet.

URL: {url}
Parsed domain: {_dom}

Official Lightchain / LCAI tooling domains include (non-exhaustive): lightchain.ai and subdomains like bridge/docs/dao/workers/hub, lightdex.app, mainnet.lightscan.app. Official Uniswap is app.uniswap.org. Filament community is filament.exchange.

Check carefully for:
- Typosquatting / lookalike domains (extra letters, numbers, wrong TLD)
- Fake Uniswap, MetaMask, bridge, airdrop, or "support" sites
- HTTP vs HTTPS, odd subdomains, or IP-looking hosts
- Anything urging seed phrase entry (always DANGER)

Rules:
- Prefer CAUTION or DANGER when unsure — connecting a wallet to a phishing site can drain everything.
- SAFE only if you are confident it is a known legitimate domain.
- Never ask for seed phrases.

Structure:
1. VERDICT: 🟢 SAFE / 🟡 CAUTION / 🔴 DANGER
2. Plain English (why)
3. What to do next (bookmark official sites; do not connect if unsure)"""

        import uuid
        job_id = str(uuid.uuid4())[:12]
        with _jobs_lock:
            _jobs[job_id] = {"status": "pending", "ts": time.time(), "type": "url", "url": url}

        def _run():
            try:
                answer = run_inference(prompt)
                with _jobs_lock:
                    _jobs[job_id] = {"status": "done", "ts": time.time(), "answer": answer, "type": "url"}
            except Exception as e:
                with _jobs_lock:
                    _jobs[job_id] = {"status": "error", "ts": time.time(), "error": str(e)}

        threading.Thread(target=_run, daemon=True).start()
        self._send_json({"ok": True, "quick": False, "jobId": job_id, "remaining": remaining})

    def _handle_check_wallet(self):
        """Free live on-chain wallet check (no AIVM quota). Format + ETH + Lightchain facts."""
        import urllib.request as _ur

        body    = self._read_body()
        address = (body.get("address") or "").strip()
        if not address:
            self._send_error("address is required")
            return
        if not re.match(r'^0x[0-9a-fA-F]{40}$', address):
            self._send_json({
                "ok": True, "verdict": "invalid",
                "note": "This is not a valid wallet address. It must start with 0x followed by exactly 40 hex characters (0-9, a-f).",
                "links": [],
            })
            return

        addr = address
        # Known contracts should not be treated as "send destination wallets"
        known = quick_contract_check(addr)
        if known.get("known") and known.get("verdict") == "safe":
            self._send_json({
                "ok": True,
                "verdict": "caution",
                "note": (
                    f"This address is a KNOWN CONTRACT, not a normal personal wallet: {known.get('name')}.\n\n"
                    f"{known.get('note', '')}\n\n"
                    "Do not send funds here unless you fully understand what the contract does "
                    "(e.g. you are interacting via its official app)."
                ),
                "links": known.get("links") or [],
                "facts": {"isKnownContract": True, "name": known.get("name")},
            })
            return

        ETH_RPC  = os.environ.get("ETH_RPC_URL", "https://eth.llamarpc.com")
        LCAI_RPC = "https://rpc.mainnet.lightchain.ai"
        results  = {}

        def _rpc(rpc_url, method, params, key):
            try:
                payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
                req = _ur.Request(rpc_url, data=payload, headers={"Content-Type": "application/json"})
                with _ur.urlopen(req, timeout=8) as r:
                    results[key] = json.loads(r.read()).get("result", None)
            except Exception as e:
                print(f"  [wallet/{key}] {e}")
                results[key] = None

        threads = [
            threading.Thread(target=_rpc, args=(ETH_RPC,  "eth_getCode",             [addr, "latest"], "eth_code"), daemon=True),
            threading.Thread(target=_rpc, args=(ETH_RPC,  "eth_getBalance",          [addr, "latest"], "eth_bal"),  daemon=True),
            threading.Thread(target=_rpc, args=(ETH_RPC,  "eth_getTransactionCount", [addr, "latest"], "eth_tx"),   daemon=True),
            threading.Thread(target=_rpc, args=(LCAI_RPC, "eth_getCode",             [addr, "latest"], "lcai_code"), daemon=True),
            threading.Thread(target=_rpc, args=(LCAI_RPC, "eth_getBalance",          [addr, "latest"], "lcai_bal"),  daemon=True),
            threading.Thread(target=_rpc, args=(LCAI_RPC, "eth_getTransactionCount", [addr, "latest"], "lcai_tx"),   daemon=True),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=9)

        def _code_kind(code):
            if code is None:
                return "unknown"
            if code in ("0x", "0x0", "") or len(code) <= 4:
                return "wallet"  # EOA
            return "contract"

        def _bal_eth(hexv):
            try:
                return int(hexv, 16) / 1e18 if hexv else 0.0
            except Exception:
                return 0.0

        def _nonce(hexv):
            try:
                return int(hexv, 16) if hexv else 0
            except Exception:
                return 0

        eth_kind  = _code_kind(results.get("eth_code"))
        lcai_kind = _code_kind(results.get("lcai_code"))
        eth_bal   = _bal_eth(results.get("eth_bal"))
        lcai_bal  = _bal_eth(results.get("lcai_bal"))
        eth_n     = _nonce(results.get("eth_tx"))
        lcai_n    = _nonce(results.get("lcai_tx"))

        lines = [
            "✅ Format: valid Ethereum-style address (0x + 40 hex).",
            f"First/last characters: {addr[:8]}…{addr[-6:]}",
            "",
            "── Ethereum Mainnet ──",
            f"Type: {'plain wallet (EOA)' if eth_kind == 'wallet' else ('smart contract' if eth_kind == 'contract' else 'lookup failed')}",
            f"Balance: ~{eth_bal:.6f} ETH",
            f"Transaction count (nonce): {eth_n:,}",
            "",
            "── Lightchain Mainnet (9200) ──",
            f"Type: {'plain wallet (EOA)' if lcai_kind == 'wallet' else ('smart contract' if lcai_kind == 'contract' else 'lookup failed')}",
            f"Balance: ~{lcai_bal:.6f} native LCAI",
            f"Transaction count (nonce): {lcai_n:,}",
            "",
            "⚠️ OrcaGuard cannot prove who owns this address.",
            "Before sending funds:",
            "1. Confirm the address with the recipient on a separate channel",
            "2. Re-check first 6 and last 6 characters after pasting (clipboard malware)",
            "3. Use the correct network (ETH vs Lightchain)",
            "4. For large amounts, send a tiny test first",
        ]

        if eth_kind == "contract" or lcai_kind == "contract":
            verdict = "caution"
            lines.insert(0, "⚠️ This address has smart-contract code on at least one chain — not a typical “send to friend” wallet.")
        elif eth_n == 0 and lcai_n == 0 and eth_bal == 0 and lcai_bal == 0:
            verdict = "caution"
            lines.insert(0, "⚠️ No activity or balance found on Ethereum or Lightchain yet — could be brand-new, unused, or wrong address. Double-check carefully.")
        else:
            verdict = "caution"  # never "safe" for send destinations

        self._send_json({
            "ok": True,
            "verdict": verdict,
            "note": "\n".join(lines),
            "links": [
                f"https://etherscan.io/address/{addr}",
                f"https://mainnet.lightscan.app/address/{addr}",
            ],
            "facts": {
                "eth":  {"kind": eth_kind,  "balance": eth_bal,  "nonce": eth_n},
                "lcai": {"kind": lcai_kind, "balance": lcai_bal, "nonce": lcai_n},
            },
        })

    def _handle_check_bot(self):
        body    = self._read_body()
        address = body.get("address", "").strip()
        if not address:
            self._send_error("address is required")
            return
        if not re.match(r'^0x[0-9a-fA-F]{40}$', address):
            self._send_error("invalid address format")
            return

        # Rate limit check
        ip = _get_client_ip(self)
        allowed, remaining = _check_ai_limit(ip)
        if not allowed:
            self._send_json({"ok": False, "limitReached": True,
                             "error": f"You've used all {AI_DAILY_LIMIT} free AI questions for today. Come back tomorrow!"}, 429)
            return

        # On-chain lookup — parallel threads to avoid sequential timeout
        import urllib.request as _ur

        def _rpc_call(rpc_url, method, params):
            try:
                payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
                req = _ur.Request(rpc_url, data=payload, headers={"Content-Type": "application/json"})
                with _ur.urlopen(req, timeout=7) as r:
                    return json.loads(r.read()).get("result", None)
            except Exception:
                return None

        ETH_RPC  = "https://eth.llamarpc.com"
        LCAI_RPC = "https://rpc.mainnet.lightchain.ai"

        # Known DEX router contracts — Ethereum + Lightchain
        DEX_ROUTERS = {
            "0x7a250d5630b4cf539739df2c5dacb4c659f2488d": "Uniswap V2 Router (ETH)",
            "0xe592427a0aece92de3edee1f18e0157c05861564": "Uniswap V3 Router (ETH)",
            "0x3fc91a3afd70395cd496c647d5a6cc9d4b2b7fad": "Uniswap Universal Router (ETH)",
            "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45": "Uniswap V3 Router 2 (ETH)",
            "0x1111111254eeb25477b68fb85ed929f73a960582": "1inch V5 (ETH)",
            "0x1111111254fb6c44bac0bed2854e76f90643097d": "1inch V4 (ETH)",
            "0xdef1c0ded9bec7f1a1670819833240f027b25eff": "0x Exchange Proxy (ETH)",
            "0xd9e1ce17f2641f24ae83637ab66a2cca9c378b9f": "SushiSwap Router (ETH)",
            # ERC-4337 Account Abstraction EntryPoints — bots use these to submit automated UserOperations
            "0x0000000071727de22e5e9d8baf0edac6f37da032": "ERC-4337 EntryPoint v0.7 (AA Bot)",
            "0x5ff137d4b0fdcd49dcd4dc17ae2aa8f821b42f34": "ERC-4337 EntryPoint v0.6 (AA Bot)",
            # Lightchain Mainnet (9200)
            "0x1f94c0a6cf48d3075f9713a79f87fa4eedaf7021": "LCAI Swap / UniV2 Router (Lightchain)",
            "0xba502917c3f7233f9100f9430f4048a224a7d8de": "LCAI Swap Factory (Lightchain)",
        }

        results = {
            "eth_code": None, "eth_tx": None,
            "lcai_code": None, "lcai_tx": None,
            "txlist": None, "tokentx": None,
            "lc_txlist": None, "lc_tokentx": None,
        }

        def _fetch(key, rpc, method, params):
            results[key] = _rpc_call(rpc, method, params)

        ETHERSCAN_KEY = os.environ.get("ETHERSCAN_API_KEY", "")
        key_param = f"&apikey={ETHERSCAN_KEY}" if ETHERSCAN_KEY else ""

        def _etherscan_fetch(action, key):
            """Fetch txlist or tokentx from Etherscan into results[key]."""
            try:
                url = (
                    "https://api.etherscan.io/v2/api"
                    "?chainid=1"
                    f"&module=account&action={action}"
                    f"&address={address}"
                    "&startblock=0&endblock=99999999"
                    f"&page=1&offset=50&sort=desc{key_param}"
                )
                req = _ur.Request(url, headers={"User-Agent": "OrcaGuard/1.0"})
                with _ur.urlopen(req, timeout=10) as r:
                    data = json.loads(r.read())
                msg = data.get("message", "")
                if data.get("status") == "1":
                    results[key] = data.get("result", [])
                elif "No transactions" in msg or "No records" in msg:
                    results[key] = []   # confirmed empty, not an error
                else:
                    print(f"  [Etherscan/{action}] status={data.get('status')} msg={msg}")
                    results[key] = None
            except Exception as e:
                print(f"  [Etherscan/{action}] exception: {e}")
                results[key] = None

        def _lightscan_activity():
            """Recent Lightchain txs + token transfers via Lightscan (Blockscout)."""
            try:
                base = "https://mainnet.lightscan.app/api/v2"
                # Normal txs
                req = _ur.Request(
                    f"{base}/addresses/{address}/transactions",
                    headers={"User-Agent": "OrcaGuard/1.0", "Accept": "application/json"},
                )
                with _ur.urlopen(req, timeout=12) as r:
                    d = json.loads(r.read())
                items = d.get("items") or []
                # Normalize to Etherscan-like {to: ...} for DEX hit counting
                results["lc_txlist"] = [
                    {"to": ((it.get("to") or {}).get("hash") or it.get("to") or "")}
                    for it in items[:50]
                ]
            except Exception as e:
                print(f"  [bot/lc_tx] {e}")
                results["lc_txlist"] = None
            try:
                base = "https://mainnet.lightscan.app/api/v2"
                req = _ur.Request(
                    f"{base}/addresses/{address}/token-transfers?type=ERC-20",
                    headers={"User-Agent": "OrcaGuard/1.0", "Accept": "application/json"},
                )
                with _ur.urlopen(req, timeout=12) as r:
                    d = json.loads(r.read())
                items = d.get("items") or []
                norm = []
                for it in items[:50]:
                    tok = it.get("token") or {}
                    norm.append({
                        "tokenSymbol": tok.get("symbol") or "?",
                        "to": ((it.get("to") or {}).get("hash") or ""),
                        "from": ((it.get("from") or {}).get("hash") or ""),
                        "contractAddress": tok.get("address_hash") or tok.get("address") or "",
                    })
                results["lc_tokentx"] = norm
            except Exception as e:
                print(f"  [bot/lc_tok] {e}")
                results["lc_tokentx"] = None

        # Start all threads in parallel — RPC + Etherscan + Lightscan
        rpc_threads = [
            threading.Thread(target=_fetch, args=("eth_code",  ETH_RPC,  "eth_getCode",             [address, "latest"]), daemon=True),
            threading.Thread(target=_fetch, args=("eth_tx",    ETH_RPC,  "eth_getTransactionCount", [address, "latest"]), daemon=True),
            threading.Thread(target=_fetch, args=("lcai_code", LCAI_RPC, "eth_getCode",             [address, "latest"]), daemon=True),
            threading.Thread(target=_fetch, args=("lcai_tx",   LCAI_RPC, "eth_getTransactionCount", [address, "latest"]), daemon=True),
        ]
        es_txlist  = threading.Thread(target=_etherscan_fetch, args=("txlist",  "txlist"),  daemon=True)
        es_tokentx = threading.Thread(target=_etherscan_fetch, args=("tokentx", "tokentx"), daemon=True)
        ls_act     = threading.Thread(target=_lightscan_activity, daemon=True)

        for t in rpc_threads: t.start()
        es_txlist.start()
        es_tokentx.start()
        ls_act.start()
        # Wait only for fast RPC calls before responding to user
        for t in rpc_threads: t.join(timeout=8)

        eth_contract  = bool(results["eth_code"]  and len(results["eth_code"])  > 4)
        eth_tx        = int(results["eth_tx"],  16) if results["eth_tx"]  else 0
        lcai_contract = bool(results["lcai_code"] and len(results["lcai_code"]) > 4)
        lcai_tx       = int(results["lcai_tx"], 16) if results["lcai_tx"] else 0

        import uuid
        job_id = str(uuid.uuid4())[:12]
        with _jobs_lock:
            _jobs[job_id] = {"status": "pending", "ts": time.time(), "type": "bot", "address": address}

        # Send jobId immediately — explorers + AIVM run fully in background
        self._send_json({
            "ok": True, "jobId": job_id,
            "etherscanUrl": f"https://etherscan.io/address/{address}",
            "lightscanUrl": f"https://mainnet.lightscan.app/address/{address}",
            "remaining":    remaining,
        })

        # Capture locals for background thread
        _es_txlist  = es_txlist
        _es_tokentx = es_tokentx
        _ls_act     = ls_act
        _results    = results
        _eth_tx     = eth_tx
        _lcai_tx    = lcai_tx
        _eth_c      = eth_contract
        _lcai_c     = lcai_contract
        _DEX        = DEX_ROUTERS

        def _run():
            # Wait for explorer fetches
            _es_txlist.join(timeout=12)
            _es_tokentx.join(timeout=12)
            _ls_act.join(timeout=14)

            txlist  = _results.get("txlist")  or []
            tokentx = _results.get("tokentx") or []
            lc_txlist  = _results.get("lc_txlist") or []
            lc_tokentx = _results.get("lc_tokentx") or []

            # DEX router hits — ETH + Lightchain
            dex_hits = {}
            for tx in list(txlist) + list(lc_txlist):
                to = (tx.get("to") or "").lower()
                if to in _DEX:
                    name = _DEX[to]
                    dex_hits[name] = dex_hits.get(name, 0) + 1

            def _token_summary(rows, label):
                token_summary = {}
                for tx in rows:
                    symbol   = tx.get("tokenSymbol", "?")
                    is_in    = (tx.get("to", "").lower() == address.lower())
                    contract = (tx.get("contractAddress") or "").lower()
                    if not contract:
                        continue
                    if contract not in token_summary:
                        token_summary[contract] = {"symbol": symbol, "in": 0, "out": 0}
                    if is_in:
                        token_summary[contract]["in"] += 1
                    else:
                        token_summary[contract]["out"] += 1
                if token_summary:
                    top = sorted(token_summary.items(), key=lambda x: x[1]["in"] + x[1]["out"], reverse=True)[:5]
                    return f"{label}: " + ", ".join(
                        f"{v['symbol']} ({v['in']} in / {v['out']} out)" for _, v in top)
                return None

            if dex_hits:
                dex_line = "DEX/router calls (ETH+Lightchain samples): " + ", ".join(
                    f"{v}x {k}" for k, v in dex_hits.items())
            elif _results.get("txlist") is not None or _results.get("lc_txlist") is not None:
                dex_line = "Sampled recent txs on ETH/Lightchain: no known DEX router calls detected"
            else:
                dex_line = "DEX activity data unavailable"

            eth_tok_line = _token_summary(tokentx, "Ethereum ERC-20 activity (sample)")
            lc_tok_line  = _token_summary(lc_tokentx, "Lightchain ERC-20 activity (sample)")
            if not eth_tok_line:
                eth_tok_line = (
                    "Ethereum ERC-20: none in sample"
                    if _results.get("tokentx") is not None
                    else "Ethereum ERC-20 data unavailable"
                )
            if not lc_tok_line:
                lc_tok_line = (
                    "Lightchain ERC-20: none in sample"
                    if _results.get("lc_tokentx") is not None
                    else "Lightchain ERC-20 data unavailable"
                )

            chain_s = (
                f"Ethereum: {'Smart contract' if _eth_c else 'Regular wallet'}, "
                f"{_eth_tx:,} outbound transactions (nonce)\n"
                f"Lightchain Mainnet (9200): {'Smart contract' if _lcai_c else 'Regular wallet'}, "
                f"{_lcai_tx:,} outbound transactions (nonce)\n"
                f"{dex_line}\n"
                f"{eth_tok_line}\n"
                f"{lc_tok_line}"
            )

            prompt = f"""Analyze this EVM wallet on Ethereum and/or Lightchain Mainnet and determine if it is a trading bot or a human trader.

Address: {address}

On-chain data collected from Etherscan, Lightscan, and RPC nodes:
{chain_s}

RULES you must follow:
1. Zero transactions is NOT evidence of a bot. A wallet with 0 transactions is new or unused — answer UNCLEAR.
2. Base your verdict only on the data shown above. Do not invent facts.
3. If data is missing or unavailable, acknowledge it and lean toward UNCLEAR.
4. Be decisive when the evidence is strong — do not hedge if the data clearly points one way.
5. Lightchain activity (LCAI Swap router, Filament, token transfers) counts the same as Ethereum DEX activity for bot patterns.

DEFINITIVE BOT signals — if any of these are present, verdict is BOT:
- Address is a smart contract (deployed bytecode) on either chain
- 3 or more transactions in the last 50 going to ERC-4337 EntryPoint contracts — humans do NOT manually submit UserOperations repeatedly; this is always automated
- Nonce over 1000 with all activity concentrated on one or two routers

LIKELY BOT signals:
- Majority of transactions going to DEX routers (Uniswap, 1inch, SushiSwap, 0x, LCAI Swap) with no other activity
- High nonce (200+) with only swap/trade transactions

Human signals:
- Low to moderate transaction count with a mix of activity types
- Token approvals, NFTs, governance votes, transfers — not just swaps
- Activity spread across multiple protocols and token types

Verdict must be exactly one of: BOT / LIKELY BOT / UNCLEAR / LIKELY HUMAN / HUMAN

Format your response as:
VERDICT: [label]
[2-3 sentences citing the specific numbers from the data above]
What to watch for: [one practical note for someone interacting with this address]"""

            try:
                answer = run_inference(prompt)
                with _jobs_lock:
                    _jobs[job_id] = {"status": "done", "ts": time.time(), "answer": answer, "type": "bot"}
            except Exception as e:
                with _jobs_lock:
                    _jobs[job_id] = {"status": "error", "ts": time.time(), "error": str(e)}

        threading.Thread(target=_run, daemon=True).start()


    def _handle_scan_airdrops(self):
        """Scan ERC-20 tokens received/held on Ethereum + Lightchain Mainnet."""
        import urllib.request as _ur
        import urllib.parse as _up

        body    = self._read_body()
        address = body.get("address", "").strip()
        if not address:
            self._send_error("address is required")
            return
        if not re.match(r'^0x[0-9a-fA-F]{40}$', address):
            self._send_error("invalid address format")
            return

        ip = _get_client_ip(self)
        addr_l = address.lower()

        # Name/symbol patterns common on scam airdrops
        SCAM_NAME_PATTERNS = [
            r'claim', r'reward', r'airdrop', r'bonus', r'free',
            r'prize', r'win', r'gift', r'voucher', r'cashback',
            r'refund', r'compensation', r'dividend',
            r'visit.*to', r'go to', r'www\.', r'\.com', r'\.io', r'\.net',
            r'\$\d+', r'usd', r'usdt', r'earn',
        ]
        # Never flag known-good Lightchain / ETH contracts as scam airdrops
        KNOWN_OK = set(VERIFIED_CONTRACTS.keys())

        def _name_looks_suspicious(name, symbol):
            combined = (name + ' ' + symbol).lower()
            return any(re.search(p, combined) for p in SCAM_NAME_PATTERNS)

        def _add_token(bucket, seen, contract, name, symbol, chain, balance_raw=None, decimals=None):
            c = (contract or "").lower()
            if not c or not c.startswith("0x") or len(c) != 42:
                return
            key = f"{chain}:{c}"
            # Prefer entry that already has a balance if we see the token again
            existing = None
            for e in bucket:
                if f"{e.get('chain')}:{e.get('contract')}" == key:
                    existing = e
                    break
            if existing and not balance_raw:
                return
            if key in seen and not balance_raw:
                return
            seen.add(key)
            known = c in KNOWN_OK
            suspicious = (not known) and _name_looks_suspicious(name or "", symbol or "")
            bal_fmt = None
            try:
                if balance_raw is not None and str(balance_raw).isdigit():
                    dec = int(decimals) if decimals is not None and str(decimals).isdigit() else 18
                    bal_fmt = int(balance_raw) / (10 ** dec)
            except Exception:
                bal_fmt = None
            entry = {
                "contract":   c,
                "name":       name or "Unknown",
                "symbol":     symbol or "?",
                "chain":      chain,
                "suspicious": suspicious,
                "knownSafe":  known,
            }
            if bal_fmt is not None:
                entry["balance"] = bal_fmt
                entry["balanceRaw"] = str(balance_raw)
            if known and c in VERIFIED_CONTRACTS:
                entry["knownName"] = VERIFIED_CONTRACTS[c]["name"]
            if existing:
                existing.update(entry)
            else:
                bucket.append(entry)

        all_tokens = []
        seen = set()
        eth_err = None
        lc_err = None

        # ── Ethereum: tokens received (Etherscan) ─────────────────────────
        try:
            url = (
                "https://api.etherscan.io/v2/api"
                "?chainid=1"
                "&module=account&action=tokentx"
                f"&address={address}"
                "&startblock=0&endblock=99999999"
                "&sort=desc&offset=200&page=1"
            )
            req = _ur.Request(url, headers={"User-Agent": "OrcaGuard/1.0"})
            with _ur.urlopen(req, timeout=14) as r:
                data = json.loads(r.read())
            if data.get("status") == "1":
                for tx in data.get("result", []) or []:
                    to_addr = (tx.get("to") or "").lower()
                    if to_addr != addr_l:
                        continue
                    _add_token(
                        all_tokens, seen,
                        tx.get("contractAddress", ""),
                        tx.get("tokenName", ""),
                        tx.get("tokenSymbol", ""),
                        "Ethereum",
                    )
            elif "No transactions" not in str(data.get("message", "")) and data.get("status") != "0":
                eth_err = data.get("message") or "etherscan error"
        except Exception as e:
            eth_err = str(e)
            print(f"  [airdrop/eth] {e}")

        # ── Lightchain: tokens held + received (Lightscan / Blockscout) ───
        LIGHTSCAN = "https://mainnet.lightscan.app/api/v2"

        def _ls_get(path_qs):
            req = _ur.Request(
                f"{LIGHTSCAN}/{path_qs.lstrip('/')}",
                headers={"User-Agent": "OrcaGuard/1.0", "Accept": "application/json"},
            )
            with _ur.urlopen(req, timeout=14) as r:
                return json.loads(r.read())

        try:
            # Current ERC-20 balances (covers airdrops still sitting in the wallet)
            path = f"addresses/{address}/tokens?type=ERC-20"
            pages = 0
            while path and pages < 8:
                d = _ls_get(path)
                for item in d.get("items") or []:
                    tok = item.get("token") or {}
                    _add_token(
                        all_tokens, seen,
                        tok.get("address_hash") or tok.get("address") or "",
                        tok.get("name", ""),
                        tok.get("symbol", ""),
                        "Lightchain",
                        balance_raw=item.get("value"),
                        decimals=tok.get("decimals"),
                    )
                npp = d.get("next_page_params")
                if not npp:
                    break
                qs = _up.urlencode({k: v for k, v in npp.items() if v is not None})
                path = f"addresses/{address}/tokens?type=ERC-20&{qs}"
                pages += 1
                time.sleep(0.05)

            # Token transfers where this wallet is the recipient
            path = f"addresses/{address}/token-transfers?type=ERC-20"
            pages = 0
            while path and pages < 10:
                d = _ls_get(path)
                for item in d.get("items") or []:
                    to_h = ((item.get("to") or {}).get("hash") or "").lower()
                    if to_h != addr_l:
                        continue
                    tok = item.get("token") or {}
                    _add_token(
                        all_tokens, seen,
                        tok.get("address_hash") or tok.get("address") or "",
                        tok.get("name", ""),
                        tok.get("symbol", ""),
                        "Lightchain",
                    )
                npp = d.get("next_page_params")
                if not npp:
                    break
                qs = _up.urlencode({k: v for k, v in npp.items() if v is not None})
                path = f"addresses/{address}/token-transfers?type=ERC-20&{qs}"
                pages += 1
                time.sleep(0.05)
        except Exception as e:
            lc_err = str(e)
            print(f"  [airdrop/lc] {e}")

        eth_n = sum(1 for t in all_tokens if t["chain"] == "Ethereum")
        lc_n  = sum(1 for t in all_tokens if t["chain"] == "Lightchain")
        known_n = sum(1 for t in all_tokens if t.get("knownSafe"))
        flagged = [t for t in all_tokens if t["suspicious"]]
        clean   = [t for t in all_tokens if not t["suspicious"]]

        def _summary_msg(flag_mode=False):
            parts = [
                f"Scanned {len(all_tokens)} unique ERC-20 token(s): "
                f"{eth_n} on Ethereum, {lc_n} on Lightchain Mainnet."
            ]
            if known_n:
                parts.append(
                    f"{known_n} match known Lightchain/community contracts (e.g. KEIKO, WLCAI, official routers) — not treated as scam airdrops."
                )
            if eth_err and not eth_n:
                parts.append(f"Ethereum scan issue: {eth_err}.")
            if lc_err and not lc_n:
                parts.append(f"Lightchain scan issue: {lc_err}.")
            if not all_tokens:
                parts.append(
                    "No ERC-20 tokens found on either chain for this address "
                    "(native LCAI is not an ERC-20 and will not appear here)."
                )
            elif not flagged:
                parts.append(
                    "None match common airdrop-scam name patterns. "
                    "Still: never approve or visit links from random tokens you did not buy."
                )
            elif flag_mode:
                parts.append(f"Flagged {len(flagged)} by name pattern for closer review.")
            return " ".join(parts)

        # Clean / nothing suspicious → no AIVM cost
        if not flagged:
            self._send_json({
                "ok": True,
                "flagged": [],
                "clean": len(clean),
                "total": len(all_tokens),
                "ethCount": eth_n,
                "lightchainCount": lc_n,
                "knownSafeCount": known_n,
                "tokens": all_tokens[:40],
                "aiUsed": False,
                "message": _summary_msg(False),
            })
            return

        allowed, remaining = _check_ai_limit(ip)
        if not allowed:
            self._send_json({
                "ok": True,
                "flagged": flagged[:10],
                "clean": len(clean),
                "total": len(all_tokens),
                "ethCount": eth_n,
                "lightchainCount": lc_n,
                "aiUsed": False,
                "limitReached": True,
                "message": (
                    f"Found {len(flagged)} suspicious token(s) by name. "
                    f"AI daily limit reached — showing name-based flags only. "
                    + _summary_msg(True)
                ),
            })
            return

        to_analyze = flagged[:8]
        token_list = "\n".join(
            f"- [{t['chain']}] {t['name']} ({t['symbol']}) — {t['contract']}"
            for t in to_analyze
        )
        prompt = f"""A crypto wallet received these ERC-20 tokens (possible airdrops) on Ethereum and/or Lightchain Mainnet.
Analyze each and say whether it is likely a SCAM AIRDROP or POSSIBLY LEGITIMATE.

Wallet: {address}
Tokens:
{token_list}

Known-good Lightchain community tokens (do NOT call these scams if listed: KEIKO, WLCAI, official LCAI Swap / Filament infra) are already filtered out when possible.

For each token:
TOKEN: [chain] [name/symbol]
VERDICT: SCAM AIRDROP or POSSIBLY LEGITIMATE
REASON: [1 sentence]

SUMMARY: [2-3 sentences — danger level + warn not to visit websites in token names or approve unknown contracts]"""

        import uuid
        job_id = str(uuid.uuid4())[:12]
        with _jobs_lock:
            _jobs[job_id] = {
                "status": "pending", "ts": time.time(),
                "type": "airdrop_scan",
                "flagged": flagged, "clean": len(clean), "total": len(all_tokens),
                "ethCount": eth_n, "lightchainCount": lc_n,
            }

        def _run():
            try:
                answer = run_inference(prompt)
                with _jobs_lock:
                    _jobs[job_id] = {
                        "status": "done", "ts": time.time(),
                        "answer": answer,
                        "type": "airdrop_scan",
                        "flagged": flagged[:10],
                        "clean": len(clean),
                        "total": len(all_tokens),
                        "ethCount": eth_n,
                        "lightchainCount": lc_n,
                        "message": _summary_msg(True),
                    }
            except Exception as e:
                with _jobs_lock:
                    _jobs[job_id] = {"status": "error", "ts": time.time(), "error": str(e)}

        threading.Thread(target=_run, daemon=True).start()
        self._send_json({
            "ok": True,
            "jobId": job_id,
            "flaggedCount": len(flagged),
            "total": len(all_tokens),
            "ethCount": eth_n,
            "lightchainCount": lc_n,
            "remaining": remaining,
        })


# ════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import socketserver
    print(f"OrcaGuard backend starting on port {PORT}...")

    class ThreadedHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
        daemon_threads = True

    server = ThreadedHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"  Ready: http://0.0.0.0:{PORT}")

    def _init_aivm():
        aivm = get_aivm_client()
        if aivm:
            print(f"  AI: Lightchain AIVM (wallet {aivm._account.address})")
        else:
            print("  AI: UNAVAILABLE — set LIGHTCHAIN_PRIVATE_KEY to enable")
    threading.Thread(target=_init_aivm, daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
