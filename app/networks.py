"""Networks and ready-made stablecoins (spec 2, 2.1, 13.4, 13.5)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TokenPreset:
    key: str  # how the token is stored in settings.txt: usdt, usdc, usdc.e…
    label: str  # the name in the interface, the log and the confirmation window
    address: str
    decimals: int
    bridged_of: str | None = None  # an old bridged version of this token: the confirmation window warns (spec 13.5)


@dataclass(frozen=True)
class Network:
    key: str
    title: str
    chain_id: int
    symbol: str  # the gas coin
    eip1559: bool  # False — legacy transactions with gasPrice (BSC)
    l1_fee: bool  # OP Stack: an L1 fee is charged on top of L2 gas
    explorer: str
    default_rpc: str
    color: str  # the network color in the dark theme
    light_color: str  # a darker shade for the light theme: visible on white with contrast of 3:1 or more
    tokens: tuple[TokenPreset, ...]

    def tx_url(self, tx_hash: str) -> str:
        return f"{self.explorer}/tx/{tx_hash}"

    def preset(self, key: str) -> TokenPreset | None:
        return next((token for token in self.tokens if token.key == key), None)


_NETWORKS = (
    Network(
        key="ethereum",
        title="Ethereum",
        chain_id=1,
        symbol="ETH",
        eip1559=True,
        l1_fee=False,
        explorer="https://etherscan.io",
        default_rpc="https://ethereum-rpc.publicnode.com",
        color="#8C9EF7",
        light_color="#5B6EE0",
        tokens=(
            TokenPreset("usdt", "USDT", "0xdAC17F958D2ee523a2206206994597C13D831ec7", 6),
            TokenPreset("usdc", "USDC", "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", 6),
        ),
    ),
    Network(
        key="arbitrum",
        title="Arbitrum",
        chain_id=42161,
        symbol="ETH",
        eip1559=True,
        l1_fee=False,
        explorer="https://arbiscan.io",
        default_rpc="https://arb1.arbitrum.io/rpc",
        color="#3CB2F5",
        light_color="#1384C6",
        tokens=(
            # USDT0 at the address of the old USDT, the contract symbol is USD₮0. The key stays "usdt", so settings
            # saved before version 1.3 keep working (spec 13.5)
            TokenPreset("usdt", "USDT0", "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9", 6),
            TokenPreset("usdc", "USDC", "0xaf88d065e77c8cC2239327C5EDb3A432268e5831", 6),
            TokenPreset("usdc.e", "USDC.e", "0xFF970A61A04b1cA14834A43f5dE4533eBDDB5CC8", 6, bridged_of="USDC"),
        ),
    ),
    Network(
        key="robinhood",
        title="Robinhood",
        chain_id=4663,
        symbol="ETH",
        eip1559=True,
        l1_fee=False,
        explorer="https://robinhoodchain.blockscout.com",
        default_rpc="https://rpc.mainnet.chain.robinhood.com",
        color="#CCFF00",
        light_color="#6B8A00",
        tokens=(
            # The network has many fake USDG tokens — only this one is real (spec 2.1)
            TokenPreset("usdg", "USDG", "0x5fc5360D0400a0Fd4f2af552ADD042D716F1d168", 6),
        ),
    ),
    Network(
        key="optimism",
        title="Optimism",
        chain_id=10,
        symbol="ETH",
        eip1559=True,
        l1_fee=True,
        explorer="https://optimistic.etherscan.io",
        default_rpc="https://mainnet.optimism.io",
        color="#FF4655",
        light_color="#E5293A",
        tokens=(
            # Two different tokens: the old bridged USDT and the new USDT0
            TokenPreset("usdt", "USDT", "0x94b008aA00579c1307B0EF2c499aD98a8ce58e58", 6),
            TokenPreset("usdt0", "USDT0", "0x01bFF41798a0BcF287b996046Ca68b395DbC1071", 6),
            TokenPreset("usdc", "USDC", "0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85", 6),
            TokenPreset("usdc.e", "USDC.e", "0x7F5c764cBc14f9669B88837ca1490cCa17c31607", 6, bridged_of="USDC"),
        ),
    ),
    Network(
        key="bsc",
        title="BSC",
        chain_id=56,
        symbol="BNB",
        eip1559=False,
        l1_fee=False,
        explorer="https://bscscan.com",
        default_rpc="https://bsc-dataseed.bnbchain.org",
        color="#F3BA2F",
        light_color="#B07F00",
        tokens=(
            TokenPreset("usdt", "USDT", "0x55d398326f99059fF775485246999027B3197955", 18),
            TokenPreset("usdc", "USDC", "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d", 18),
        ),
    ),
    Network(
        key="base",
        title="Base",
        chain_id=8453,
        symbol="ETH",
        eip1559=True,
        l1_fee=True,
        explorer="https://basescan.org",
        default_rpc="https://mainnet.base.org",
        color="#4C84FF",
        light_color="#3370F5",
        tokens=(
            TokenPreset("usdt", "USDT", "0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2", 6),
            TokenPreset("usdc", "USDC", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", 6),
            TokenPreset("usdbc", "USDbC", "0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA", 6, bridged_of="USDC"),
        ),
    ),
    Network(
        key="avalanche",
        title="Avalanche",
        chain_id=43114,
        symbol="AVAX",
        eip1559=True,
        l1_fee=False,
        explorer="https://snowtrace.io",
        # Not the Ava Labs public RPC (api.avax.network): its Cloudflare blocks the computer for minutes after
        # the balance requests of a few dozen wallets (spec 13.7)
        default_rpc="https://avalanche-c-chain-rpc.publicnode.com",
        # Crimson: the brand red of Avalanche is too close to the red of Optimism (spec 13.4)
        color="#E0459B",
        light_color="#B8287A",
        tokens=(
            TokenPreset("usdt", "USDT", "0x9702230A8Ea53601f5cD2dc00fDBc13d4dF4A8c7", 6),  # the contract symbol is USDt
            TokenPreset("usdt.e", "USDT.e", "0xc7198437980c041c805A1EDcbA50c1Ce5db95118", 6, bridged_of="USDT"),
            TokenPreset("usdc", "USDC", "0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E", 6),
            TokenPreset("usdc.e", "USDC.e", "0xA7D7079b0FEaD91F3e65f86E8915Cb59c1a4C664", 6, bridged_of="USDC"),
        ),
    ),
)

NETWORKS: dict[str, Network] = {network.key: network for network in _NETWORKS}


def preset_label(key: str) -> str:
    """The name of a ready-made token by its settings key, as the first network that has it calls it."""
    return next((preset.label for network in _NETWORKS for preset in network.tokens if preset.key == key),
                key.upper())
