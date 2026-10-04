# ETH Sender

[Русская версия](README.ru.md)

A Windows desktop program that sends the native coin (ETH, BNB, AVAX) or an ERC-20 token from a set of wallets to given addresses. Supported networks: Ethereum, Arbitrum, Robinhood Chain, Optimism, BSC, Base and Avalanche.

- One network and one token per run; every wallet has its own recipient.
- The amount is the whole balance, a percent of it or a random amount from a range.
- Every transaction is checked for execution. A failed one is retried up to 3 times; a stuck one is replaced with the same nonce, so nothing is sent twice.
- Random or file order, random delays between wallets, a Stop button.
- English and Russian interface, dark and light themes.

## Requirements

- Windows 10 or 11, x64.
- Python 3.13 — only to build the program or to run it from sources. The built `ETH_Sender.exe` does not need Python.

## Getting started

Run `build.bat`. It builds `dist\ETH_Sender\ETH_Sender.exe` and creates the "ETH Sender" desktop shortcut. See [Building](#building) for details and [Development](#development) for running from sources.

## How to use

1. Start the program with the "ETH Sender" desktop shortcut. On the first start `settings.txt` and `wallets.txt` appear next to the program.
2. Put the wallets into `wallets.txt`, one per line: `name,private key,recipient address`, or without a name — `private key,recipient address`. Formats can be mixed.
3. In the window, pick the network, the token, the amount and the delays, then click Apply: the program saves the settings, checks the RPC and loads the balances. The Token list has the native coin, the network's ready-made stablecoins (USDT, USDC and their variants such as USDT0 or the bridged USDC.e; USDG in Robinhood) and a custom ERC-20 by its contract address.
4. Check the wallets, click Start and confirm. If an old bridged token is selected (USDC.e, USDbC, USDT.e), the confirmation window warns that exchanges often credit only the native USDC and USDT.

The interface is in English. The RU | EN switch at the top of the settings panel turns it Russian, the icon next to it switches between the dark and the light theme. Both choices are saved in `settings.txt` at once and do not need Apply.

Under the table the Total row sums the token and native coin balances of all wallets; the sums of the checked wallets are next to "N of M selected". If some balances fail to load (public RPCs often limit the request rate), click ↻ next to "error" or "Retry failed" — only those wallets are polled again. When the RPC limits the request rate, the program slows the polling down by itself.

Every network comes with a public RPC address. You can replace it in the settings panel, for example with your own node or a provider's address.

## Security

- Private keys are used only to sign transactions on your computer. They are not shown in the window, not written to the log and not sent anywhere: only signed transactions go to the network.
- The program connects only to the RPC addresses from the settings. Block explorer and DeBank links open in the browser only when you click them.
- The chain ID is checked before sending, so a wrong RPC address cannot send a transaction to another network.
- `wallets.txt` keeps private keys unencrypted — keep the program folder in a safe place. `settings.txt` may hold RPC addresses with API keys. Both files are listed in `.gitignore`; never commit them.

Sent transactions cannot be reversed. Try a small amount first. The program is provided as is, without any warranty — see [License](#license).

## Building

`build.bat` builds `dist\ETH_Sender\ETH_Sender.exe` and creates the desktop shortcut. The build runs in the separate clean environment `.venv-build`, packages are installed strictly from `requirements.lock`: exact versions, SHA-256 hashes, ready-made wheels only, nothing is built from sources. If even one file differs from the locked one, the build stops. `settings.txt` and `wallets.txt` in `dist\ETH_Sender` are kept when rebuilding; other files in that folder are not — PyInstaller recreates it.

Update package versions deliberately: update them in `.venv`, check them, then run `.venv\Scripts\python tools\make_lock.py`. The script rewrites `requirements.lock` and `requirements-pip.lock` and refuses to do so if the OSV database lists vulnerabilities or malicious releases for those versions.

## Development

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt pytest
.venv\Scripts\python main.py            # the program from sources
.venv\Scripts\python main.py --demo     # a window with demo data, no network access
.venv\Scripts\python -m pytest          # tests
.venv\Scripts\python tools\check_networks.py   # a read-only check of every network's RPC
.venv\Scripts\python tools\render_ui.py        # interface snapshots in both themes, into design/
```

The tests on a local blockchain (`tests/test_local_chain.py`) run if `eth-tester` and `py-evm==0.12.1b1` are installed; otherwise they are skipped. These packages are only needed for the tests and do not get into the build.

Texts of the interface are written in English in the code; the Russian translation is `app/ru.py`. `tests/test_i18n.py` checks that every text has a translation with the same placeholders.

Comments in the code mention items such as "spec 5.6". These are item numbers of the project's internal specification, which is not part of this repository.

## License

[MIT](LICENSE)
