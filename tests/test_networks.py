"""Networks and ready-made tokens of version 1.3: Avalanche and the USDT and USDC variants (spec 13.4, 13.5)."""
from __future__ import annotations

import os

import pytest
from eth_utils import is_checksum_address

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app import settings as settings_file  # noqa: E402
from app.networks import NETWORKS  # noqa: E402
from app.settings import Settings  # noqa: E402
from app.ui.settings_panel import SettingsPanel  # noqa: E402
from app.ui.theme import apply_theme  # noqa: E402

# The Token list of every network, in order: the native coin, the USDT family, the USDC family, other tokens
TOKENS = {
    "ethereum": ["USDT", "USDC"],
    "arbitrum": ["USDT0", "USDC", "USDC.e"],
    "robinhood": ["USDG"],
    "optimism": ["USDT", "USDT0", "USDC", "USDC.e"],
    "bsc": ["USDT", "USDC"],
    "base": ["USDT", "USDC", "USDbC"],
    "avalanche": ["USDT", "USDT.e", "USDC", "USDC.e"],
}
BRIDGED = {"USDC.e": "USDC", "USDbC": "USDC", "USDT.e": "USDT"}


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    apply_theme(application, "dark")
    return application


def test_avalanche_is_the_seventh_network():
    assert list(NETWORKS)[-1] == "avalanche" and len(NETWORKS) == 7
    avalanche = NETWORKS["avalanche"]
    assert (avalanche.title, avalanche.chain_id, avalanche.symbol) == ("Avalanche", 43114, "AVAX")
    assert avalanche.eip1559 and not avalanche.l1_fee
    assert avalanche.default_rpc == "https://avalanche-c-chain-rpc.publicnode.com"  # spec 13.7
    assert avalanche.tx_url("0xabc") == "https://snowtrace.io/tx/0xabc"
    assert (avalanche.color, avalanche.light_color) == ("#E0459B", "#B8287A")


def test_every_network_has_exactly_its_tokens_in_order():
    assert {key: [preset.label for preset in network.tokens] for key, network in NETWORKS.items()} == TOKENS


def test_token_addresses_are_checksummed_and_unique_per_network():
    for network in NETWORKS.values():
        addresses = [preset.address for preset in network.tokens]
        assert all(is_checksum_address(address) for address in addresses), network.key
        assert len(set(addresses)) == len(addresses) and len({p.key for p in network.tokens}) == len(addresses)
        assert all(preset.decimals == (18 if network.key == "bsc" else 6) for preset in network.tokens)


def test_only_old_bridged_versions_warn():
    found = {preset.label: preset.bridged_of for network in NETWORKS.values() for preset in network.tokens
             if preset.bridged_of}
    assert found == BRIDGED


def test_arbitrum_usdt_is_usdt0_under_the_old_key():
    preset = NETWORKS["arbitrum"].preset("usdt")
    assert preset.label == "USDT0" and preset.address == "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9"
    assert NETWORKS["arbitrum"].preset("usdt0") is None


def test_optimism_usdt_and_usdt0_are_different_tokens():
    optimism = NETWORKS["optimism"]
    assert optimism.preset("usdt").address != optimism.preset("usdt0").address


def test_settings_with_usdt_from_older_versions_open_with_usdt0_in_arbitrum(app, tmp_path):
    path = tmp_path / "settings.txt"
    path.write_text("[main]\nnetwork = arbitrum\ntoken = usdt\n", encoding="utf-8")
    loaded, warnings = settings_file.load(path)
    assert warnings == [] and loaded.token == "usdt"
    panel = SettingsPanel()
    panel.set_settings(loaded)
    assert panel.token.currentText() == "USDT0" and panel.token_address.text() == NETWORKS["arbitrum"].tokens[0].address


@pytest.mark.parametrize("network, token", [("optimism", "usdt0"), ("arbitrum", "usdc.e"), ("base", "usdbc"),
                                            ("avalanche", "usdt.e"), ("avalanche", "usdc")])
def test_new_token_keys_are_saved_and_read(tmp_path, network, token):
    path = tmp_path / "settings.txt"
    original = Settings(network=network, token=token)
    settings_file.save(path, original)
    loaded, warnings = settings_file.load(path)
    assert warnings == [] and loaded == original and not loaded.custom_token


def test_ready_made_token_of_another_network_is_an_error():
    errors = [str(error) for error in settings_file.validate(Settings(network="ethereum", token="usdc.e"))]
    assert errors == ["Token: USDC.e is not among the ready-made tokens of Ethereum"]
    assert settings_file.validate(Settings(network="base", token="usdt0"))  # USDT0 only in Optimism


def test_token_list_in_the_panel(app):
    panel = SettingsPanel()
    for key, labels in TOKENS.items():
        panel.network.setCurrentIndex(panel.network.findData(key))
        texts = [panel.token.itemText(i) for i in range(panel.token.count())]
        assert texts == [f"{NETWORKS[key].symbol} (native)", *labels, "Custom ERC-20"]


def test_avalanche_rpc_field_is_seventh(app):
    panel = SettingsPanel()
    assert list(panel.rpc)[-1] == "avalanche" and len(panel.rpc) == 7
    assert panel.rpc["avalanche"].text() == "https://avalanche-c-chain-rpc.publicnode.com"


def test_saved_avalanche_rpc_is_kept_and_a_new_file_gets_publicnode(tmp_path):
    """The default changed in 1.3.1, but an address already in settings.txt stays (spec 13.7)."""
    path = tmp_path / "settings.txt"
    path.write_text("[main]\nnetwork = avalanche\n[rpc]\navalanche = https://api.avax.network/ext/bc/C/rpc\n",
                    encoding="utf-8")
    loaded, warnings = settings_file.load(path)
    assert warnings == [] and loaded.rpc["avalanche"] == "https://api.avax.network/ext/bc/C/rpc"
    fresh, _ = settings_file.load(tmp_path / "new.txt")
    assert fresh.rpc["avalanche"] == "https://avalanche-c-chain-rpc.publicnode.com"
