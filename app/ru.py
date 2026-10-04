"""The Russian translation of the interface (spec 12.2): English template → Russian template.

The placeholders in both templates must match; tests/test_i18n.py checks that every text of the program is here.
"""
from __future__ import annotations

# Noun forms for plurals: (one, few, many). "wallets_gen" is the genitive case: «с 1 кошелька», «без 5 кошельков»
RU_NOUNS: dict[str, tuple[str, ...]] = {
    "wallets": ("кошелёк", "кошелька", "кошельков"),
    "wallets_gen": ("кошелька", "кошельков", "кошельков"),
    "entries": ("запись", "записи", "записей"),
}

SETTINGS_TEMPLATE = """\
# ===== ETH Sender: настройки =====
# Файл можно править в блокноте или в программе.
# Кнопка «Применить» перезаписывает его целиком.

[main]
# Сеть: ethereum | arbitrum | robinhood | optimism | bsc | base | avalanche
network = {network}
# Токен: native (ETH/BNB/AVAX) | usdt | usdc | адрес контракта ERC-20
# Ещё: usdg (robinhood) | usdt0 (optimism) | usdc.e (arbitrum, optimism, avalanche) | usdbc (base) | usdt.e (avalanche)
token = {token}
# Сумма: all (весь баланс) | percent (процент от баланса) | range (случайная сумма из диапазона)
amount_mode = {amount_mode}
percent = {percent}
range_min = {range_min}
range_max = {range_max}
# Множитель цены газа, один на все сети: от 1.0 до 5.0
gas_multiplier = {gas_multiplier}
# Пауза между кошельками, сек: случайно от delay_min до delay_max
delay_min = {delay_min}
delay_max = {delay_max}
# Порядок: sequential (как в файле) | random (случайный)
order = {order}
# Сколько ждать попадания транзакции в блок, сек: от 10 до 3600
tx_timeout = {tx_timeout}

[rpc]
{rpc}

[ui]
# Язык интерфейса: en | ru
language = {language}
# Тема: dark | light
theme = {theme}
"""

WALLETS_TEMPLATE = """\
# Кошельки для рассылки: одна строка — один кошелёк.
# Формат: имя,приватный ключ,адрес получателя
# Без имени: приватный ключ,адрес получателя (или с запятой в начале: ,приватный ключ,адрес получателя).
# У кошелька без имени вместо имени показывается сокращённый адрес отправителя.
# Форматы можно смешивать в одном файле. Ключ — 64 hex-символа, с 0x или без.
# Пустые строки и строки, начинающиеся с #, пропускаются.
#
# Примеры:
# Основной 1,0x<64 hex-символа>,0x1111111111111111111111111111111111111111
# 0x<64 hex-символа>,0x2222222222222222222222222222222222222222
"""

RU: dict[str, str] = {
    # --- files ---
    "# ===== ETH Sender: settings =====\n# The file can be edited in Notepad or in the program.\n"
    "# The Apply button rewrites it entirely.\n\n[main]\n"
    "# Network: ethereum | arbitrum | robinhood | optimism | bsc | base | avalanche\nnetwork = {network}\n"
    "# Token: native (ETH/BNB/AVAX) | usdt | usdc | ERC-20 contract address\n"
    "# Also: usdg (robinhood) | usdt0 (optimism) | usdc.e (arbitrum, optimism, avalanche) | usdbc (base) | "
    "usdt.e (avalanche)\ntoken = {token}\n"
    "# Amount: all (whole balance) | percent (percent of the balance) | range (random amount from a range)\n"
    "amount_mode = {amount_mode}\npercent = {percent}\nrange_min = {range_min}\nrange_max = {range_max}\n"
    "# Gas price multiplier, one for all networks: from 1.0 to 5.0\ngas_multiplier = {gas_multiplier}\n"
    "# Delay between wallets, sec: random from delay_min to delay_max\ndelay_min = {delay_min}\n"
    "delay_max = {delay_max}\n# Order: sequential (as in the file) | random\norder = {order}\n"
    "# How long to wait for a transaction to get into a block, sec: from 10 to 3600\ntx_timeout = {tx_timeout}\n\n"
    "[rpc]\n{rpc}\n\n[ui]\n# Interface language: en | ru\nlanguage = {language}\n# Theme: dark | light\n"
    "theme = {theme}\n": SETTINGS_TEMPLATE,
    "# Interface language: en | ru": "# Язык интерфейса: en | ru",
    "# Theme: dark | light": "# Тема: dark | light",
    "# Wallets to send from: one line per wallet.\n# Format: name,private key,recipient address\n"
    "# Without a name: private key,recipient address (or with a leading comma: ,private key,recipient address).\n"
    "# A wallet without a name is shown by the shortened sender address.\n"
    "# Formats can be mixed in one file. The key is 64 hex characters, with or without 0x.\n"
    "# Empty lines and lines starting with # are skipped.\n#\n# Examples:\n"
    "# Main 1,0x<64 hex characters>,0x1111111111111111111111111111111111111111\n"
    "# 0x<64 hex characters>,0x2222222222222222222222222222222222222222\n": WALLETS_TEMPLATE,
    "{file} not found: created a file with an example. Add wallets to it and click Apply.":
        "{file} не найден: создан файл с примером. Впишите кошельки и нажмите «Применить».",
    "{file} could not be read: {error}. Save the file in UTF-8 encoding.":
        "{file} не прочитан: {error}. Сохраните файл в кодировке UTF-8.",
    "{file} not found: created with the default settings": "{file} не найден: создан с настройками по умолчанию",
    "{file} could not be read ({error}), using the default settings":
        "{file} не прочитан ({error}), взяты настройки по умолчанию",
    "{file}: {key} = {value}: {problem}; using the default value":
        "{file}: {key} = {value}: {problem}; взято значение по умолчанию",
    "{file}, line {line}: {error}": "{file}, строка {line}: {error}",

    # --- wallets.txt and addresses ---
    "expected 2 or 3 comma-separated fields: key,address or name,key,address":
        "нужно 2 или 3 поля через запятую: ключ,адрес или имя,ключ,адрес",
    "invalid private key": "неверный приватный ключ",
    "recipient address: {problem}": "адрес получателя: {problem}",
    "the recipient is the same as the sender": "получатель совпадает с отправителем",
    "no name": "без имени",
    "expected an address like 0x followed by 40 characters 0–9, a–f": "нужен адрес вида 0x и 40 символов 0–9, a–f",
    "the address checksum does not match, check it for a typo":
        "не сходится контрольная сумма адреса, проверьте на опечатку",

    # --- settings checks ---
    "“{value}” is not a number": "«{value}» — не число",
    "“{value}” must be a whole number": "«{value}» — нужно целое число",
    "allowed: {values}": "допустимо: {values}",
    "must be {sign} {low} and ≤ {high}": "нужно {sign} {low} и ≤ {high}",
    "Network: there is no network “{value}”": "Сеть: «{value}» — такой сети нет",
    "Token: {token} is not among the ready-made tokens of {network}":
        "Токен: {token} нет среди готовых токенов сети {network}",
    "Token, contract address: {problem}": "Токен, адрес контракта: {problem}",
    "Amount: unknown mode “{value}”": "Сумма: неизвестный режим «{value}»",
    "Percent: must be more than 0 and at most 100": "Процент: нужно больше 0 и не больше 100",
    "Range: enter “from” and “to”": "Диапазон: укажите «от» и «до»",
    "Range: must be 0 < “from” ≤ “to”": "Диапазон: нужно 0 < «от» ≤ «до»",
    "Gas price multiplier: from 1.0 to 5.0": "Множитель цены газа: от 1.0 до 5.0",
    "Delay between wallets: must be 0 ≤ “from” ≤ “to”": "Пауза между кошельками: нужно 0 ≤ «от» ≤ «до»",
    "Processing order: unknown value “{value}”": "Порядок обхода: неизвестное значение «{value}»",
    "Confirmation timeout: from {low} to {high} sec": "Ожидание подтверждения: от {low} до {high} сек",
    "{network} RPC: address not set": "RPC {network}: адрес не задан",
    "{network} RPC: the address must start with http:// or https://":
        "RPC {network}: адрес должен начинаться с http:// или https://",

    # --- RPC and Apply ---
    "the RPC did not respond within {seconds} s": "RPC не ответил за {seconds} с",
    "no connection to the RPC": "нет связи с RPC",
    "the RPC limits the request rate ({detail})": "RPC ограничил частоту запросов ({detail})",
    "the RPC returned HTTP error {status}": "RPC ответил ошибкой HTTP {status}",
    "The {network} RPC does not respond: {error}": "RPC сети {network} не отвечает: {error}",
    "The {network} RPC returned chain ID {got}, expected {expected}. Check the RPC address.":
        "RPC сети {network} вернул chain ID {got}, ожидался {expected}. Проверьте адрес RPC.",
    "There is no contract at {address} in {network}. Check the token address and the selected network.":
        "По адресу {address} в сети {network} нет контракта. Проверьте адрес токена и выбранную сеть.",
    "Could not read the token {address}: {error}": "Не удалось прочитать токен {address}: {error}",
    "{network} RPC responds, chain ID {chain_id}": "RPC {network} отвечает, chain ID {chain_id}",
    "Token {token}: {address}, {decimals} decimals": "Токен {token}: {address}, {decimals} decimals",
    "Contract verified: {token}, {decimals} decimals": "Контракт проверен: {token}, {decimals} decimals",
    "Checking balances: {done} / {total}": "Опрос балансов: {done} / {total}",
    "Checking balances: {done} / {total} — RPC rate limit, waiting {seconds} s":
        "Опрос балансов: {done} / {total} — RPC ограничивает частоту, жду {seconds} с",
    "{network} RPC is rate limiting requests — slowing down":
        "RPC сети {network} ограничивает частоту запросов — опрос замедлен",
    "{prefix}: balance check failed — {error}": "{prefix}: ошибка опроса баланса — {error}",
    "Balances loaded: {count:wallets}": "Балансы загружены: {count:wallets}",
    "Balances loaded: {count:wallets}; failed for {failed} — “Retry failed” polls them again":
        "Балансы загружены: {count:wallets}; не удалось у {failed} — «Повторить ошибки» опросит их заново",
    "Retry: loaded the balances of {count:wallets}": "Повтор опроса: загружены балансы {count:wallets_gen}",
    "Retry: loaded the balances of {count:wallets}, failed again: {numbers}":
        "Повтор опроса: загружены балансы {count:wallets_gen}, снова ошибка: {numbers}",
    "Settings saved to {file}": "Настройки сохранены в {file}",
    "Could not save the language and theme to {file}: {error}": "Не удалось сохранить язык и тему в {file}: {error}",
    "Could not write {file}: {error}": "Не удалось записать {file}: {error}",
    "Unexpected error: {error}": "Непредвиденная ошибка: {error}",

    # --- sending ---
    "RPC not responding": "RPC не отвечает",
    "Retry in {seconds} s": "Повтор через {seconds} с",
    "Sending…": "Отправка…",
    "Waiting for confirmation": "Ожидание подтверждения",
    "Queued": "В очереди",
    "skipped: {detail}": "пропущен: {detail}",
    "Skipped: {reason}": "Пропущен: {reason}",
    "Error: {reason}": "Ошибка: {reason}",
    "Not confirmed": "Не подтверждена",
    "Needs review": "Требует проверки",
    "Success: {amount}": "Успешно: {amount}",
    "Sent {amount}, block {block}": "Отправлено {amount}, блок {block}",
    "Not processed (stopped)": "Не обработан (стоп)",
    "{reason}; retry in {seconds} s (attempt {attempt}/{total})":
        "{reason}; повтор через {seconds} с (попытка {attempt}/{total})",
    "{reason} (attempt {attempt}/{total})": "{reason} (попытка {attempt}/{total})",
    "The transaction was sent but did not get into a block in {count} attempts. It may still go through — check it "
    "by the link.": "Транзакция отправлена, но за {count} попытки не попала в блок. Она ещё может исполниться, "
                    "проверьте по ссылке.",
    "not confirmed in {count} attempts, tx {tx} may still go through later":
        "не подтверждена за {count} попытки, tx {tx} может пройти позже",
    "error after {count} attempts: {reason}": "ошибка после {count} попыток: {reason}",
    "resending the same transaction {tx} (attempt {attempt}/{total})":
        "повторная отправка той же транзакции {tx} (попытка {attempt}/{total})",
    "not enough funds for a replacement with a higher gas price, waiting for the sent transaction":
        "на замену с более высокой ценой газа не хватает средств, ждём отправленную транзакцию",
    "not mined": "не попала в блок",
    "did not get into a block in {seconds} s": "за {seconds} с не попала в блок",
    "pending transaction": "есть зависшая tx",
    "The wallet already has an unconfirmed transaction (nonce {nonce}). Wait for it or cancel it and start again.":
        "С кошелька уже есть неподтверждённая транзакция (nonce {nonce}). Дождитесь её или отмените и запустите "
        "снова.",
    "zero balance": "баланс 0",
    "The wallet has 0 {token}": "На кошельке 0 {token}",
    "low {symbol} for gas": "мало {symbol} на газ",
    "Not enough {symbol} for gas: have {have}, need ~{need}": "Не хватает {symbol} на газ: есть {have}, нужно ~{need}",
    "{amount} {token} after gas": "{amount} {token} за вычетом газа",
    "below the minimum": "ниже минимума",
    "Balance {have} is below the range minimum {minimum} {token}":
        "Баланс {have} меньше минимума диапазона {minimum} {token}",
    "Nothing to send: 0 {token}": "К отправке 0 {token}",
    "transfer reverted": "перевод отклонён",
    "Gas estimation showed the transfer will be rejected: {error}":
        "Оценка газа показала, что перевод будет отклонён: {error}",
    "replacement with the same nonce": "замена с тем же nonce",
    "sending": "отправка",
    "{action} {amount} {token} → {to}, gas {gwei} gwei, attempt {attempt}/{total}":
        "{action} {amount} {token} → {to}, газ {gwei} gwei, попытка {attempt}/{total}",
    "tx {tx} sent": "tx {tx} отправлена",
    "the node answered “{error}”; the transaction may already be in the network — waiting for its receipt":
        "узел ответил «{error}»; возможно, транзакция уже в сети — ждём её квитанцию",
    "the nonce is already taken, checking the transaction sent earlier":
        "nonce уже занят, проверяем отправленную ранее транзакцию",
    "not enough funds for a replacement, waiting for the sent transaction":
        "на замену не хватает средств, ждём отправленную транзакцию",
    "insufficient funds": "мало средств",
    "insufficient funds ({error})": "недостаточно средств ({error})",
    "The node rejected the transaction: insufficient funds ({error})":
        "Узел отклонил транзакцию: недостаточно средств ({error})",
    "the RPC returned a different transaction hash: {hash}": "RPC вернул другой хеш транзакции: {hash}",
    "transaction failed": "tx не прошла",
    "tx {tx} got into block {block} but failed (status 0)": "tx {tx} попала в блок {block}, но не прошла (status 0)",
    "The transaction went through, but the Transfer event to the recipient was not found":
        "Транзакция исполнена, но событие Transfer на получателя не найдено",
    "The transaction went through, but the Transfer event has {moved} {token} instead of {amount}":
        "Транзакция исполнена, но в событии Transfer {moved} {token} вместо {amount}",
    "{detail}; block {block}, tx {tx}. Needs review": "{detail}; блок {block}, tx {tx}. Требует проверки",
    "success, block {block}, tx {tx}": "успешно, блок {block}, tx {tx}",
    "nonce already used": "nonce занят",
    "nonce already used ({error}), taking a new one": "nonce уже использован ({error}), возьмём новый",
    "gas price too low": "низкая цена газа",
    "the node rejected the gas price as too low ({error}), raising it by 15%":
        "узел отклонил из-за низкой цены газа ({error}), поднимем на 15%",
    "call reverted": "вызов отклонён",
    "the contract rejects the call ({error})": "контракт отклоняет вызов ({error})",
    "rejected by the node": "отказ узла",
    "the node rejected: {error}": "узел отклонил: {error}",
    "RPC error: {error}": "ошибка RPC: {error}",
    "unexpected error": "сбой программы",
    "random order": "порядок случайный",
    "file order": "порядок как в файле",
    "Sending started: {network}, {token}, {count:wallets}, {order}":
        "Рассылка запущена: {network}, {token}, {count:wallets}, {order}",
    "Processed {done} of {total}": "Обработано {done} из {total}",
    "Processed {done} of {total}, now {wallet}": "Обработано {done} из {total}, сейчас {wallet}",
    "Processed {done} of {total}, delay {seconds} s": "Обработано {done} из {total}, пауза {seconds} с",
    "Delay {seconds} s": "Пауза {seconds} с",
    "Sending was stopped with the Stop button": "Рассылка остановлена кнопкой «Стоп»",
    "Sending stopped, not processed: {count:wallets}": "Рассылка остановлена, не обработано: {count:wallets}",
    "Done: {ok} succeeded, {check} need review, {unconfirmed} not confirmed, {error} failed, {skipped} skipped":
        "Готово: успешно {ok}, требует проверки {check}, не подтверждено {unconfirmed}, ошибок {error}, "
        "пропущено {skipped}",
    "Done: {ok} succeeded, {check} need review, {unconfirmed} not confirmed, {error} failed, {skipped} skipped, "
    "{stopped} not processed":
        "Готово: успешно {ok}, требует проверки {check}, не подтверждено {unconfirmed}, ошибок {error}, "
        "пропущено {skipped}, не обработано {stopped}",
    "Sending was interrupted by an unexpected error: {error}": "Рассылка прервана из-за непредвиденной ошибки: {error}",
    "Stop pressed: sending will stop after the current wallet":
        "Нажата «Стоп»: рассылка остановится после текущего кошелька",
    "Stopping after the current wallet…": "Остановка после текущего кошелька…",

    # --- the settings panel ---
    "version {version}": "версия {version}",
    "Switch to light theme": "Светлая тема",
    "Switch to dark theme": "Тёмная тема",
    "Network and token": "Сеть и токен",
    "Network": "Сеть",
    "Token": "Токен",
    "{symbol} (native)": "{symbol} (нативная)",
    "Custom ERC-20": "Другой ERC-20",
    "Contract address, 0x…": "Адрес контракта, 0x…",
    "Amount": "Сумма",
    "Full balance": "Весь баланс",
    "Percent": "Процент",
    "Range": "Диапазон",
    "% of balance": "% от баланса",
    "from": "от",
    "to": "до",
    "sec": "сек",
    "Each wallet sends all its {symbol} except the amount for gas.":
        "С каждого кошелька уходит весь {symbol}, кроме суммы на газ.",
    "Each wallet sends its entire token balance.": "С каждого кошелька уходит весь баланс токена.",
    "Each wallet sends its entire {token} balance.": "С каждого кошелька уходит весь баланс {token}.",
    "Gas and delays": "Газ и паузы",
    "Gas price multiplier": "Множитель цены газа",
    "Delay between wallets": "Пауза между кошельками",
    "Processing order": "Порядок обхода",
    "File order": "Как в файле",
    "Random": "Случайный",
    "Confirmation timeout": "Ожидание подтверждения",
    "RPC endpoints": "RPC сетей",
    "not set": "не задан",
    "Apply": "Применить",
    "token": "токена",
    "Click Apply to check the RPC and load the balances.": "Нажмите «Применить», чтобы проверить RPC и загрузить балансы.",
    "Settings changed. Click Apply to save them, check the RPC and refresh balances.":
        "Настройки изменены. Нажмите «Применить», чтобы сохранить их, проверить RPC и обновить балансы.",
    "Settings were not applied. Fix the error and click Apply again.":
        "Настройки не применены. Исправьте ошибку и нажмите «Применить» ещё раз.",

    # --- the main window and the table ---
    "Wallets": "Кошельки",
    "{count:entries} in wallets.txt": "{count:entries} в wallets.txt",
    "{count:entries} in wallets.txt, {invalid} with an error": "{count:entries} в wallets.txt, {invalid} с ошибкой",
    "native coin": "нативная монета",
    "address not set": "адрес не задан",
    "#": "№",
    "Name": "Имя",
    "Sender": "Отправитель",
    "Recipient": "Получатель",
    "{token} balance": "Баланс {token}",
    "Status": "Статус",
    "Attempts": "Попытки",
    "Transaction": "Транзакция",
    "Line error: {error}": "Ошибка в строке: {error}",
    "Attempts: {count} of {total} (1 attempt and up to 3 retries)":
        "Попыток: {count} из {total} (1 попытка и до 3 повторов)",
    "error": "ошибка",
    "Copy address": "Копировать адрес",
    "Copied": "Скопировано",
    "Retry balance check": "Повторить опрос",
    "Total": "Итого",
    "Total: {count:wallets}": "Итого: {count:wallets}",
    "{count:wallets} excluded: balance check failed": "без {count:wallets_gen}: ошибка опроса",
    "Balances were not loaded for wallets {numbers}. The reasons are in the log.":
        "Не загрузились балансы кошельков {numbers}. Причины — в логе.",
    "No wallets yet. Add them to the wallets.txt file next to the program, one per line: name,private key,recipient "
    "address — or without a name: private key,recipient address. Then click Apply.":
        "Кошельков пока нет. Впишите их в файл wallets.txt рядом с программой, по одному в строке: имя,приватный "
        "ключ,адрес получателя — или без имени: приватный ключ,адрес получателя. Затем нажмите «Применить».",
    "Select all": "Выбрать все",
    "Deselect all": "Снять все",
    "{checked} of {total} selected": "Отмечено {checked} из {total}",
    "Retry failed ({count})": "Повторить ошибки ({count})",
    "Start": "Старт",
    "Stop": "Стоп",
    "Log": "Лог",

    # --- the confirmation window and messages ---
    "Confirm sending": "Подтверждение рассылки",
    "Send {token} from {count:wallets}?": "Отправить {token} с {count:wallets_gen}?",
    "Check the details. Sent transactions cannot be reversed.":
        "Проверьте параметры. Отправленные транзакции отменить нельзя.",
    "the network's native coin": "нативная монета сети",
    "count\x04Wallets": "Кошельков",
    "Balances": "На балансах",
    "{token} and {native}": "{token} и {native}",
    "Gas": "Газ",
    "price multiplier {value}": "множитель цены {value}",
    "Delay": "Пауза",
    "Order": "Порядок",
    "{token} is a bridged version of {base}. Make sure the recipient addresses accept exactly this one: exchanges "
    "often credit only native {base}.":
        "{token} — мостовая версия {base}. Убедитесь, что адреса получателей принимают именно её: биржи часто "
        "зачисляют только родной {base}.",
    "Cancel": "Отмена",
    "Start sending": "Начать рассылку",
    "whole {token} balance": "весь баланс {token}",
    "whole {token} balance, except the amount for gas": "весь баланс {token}, кроме суммы на газ",
    "{percent}% of the {token} balance": "{percent}% от баланса {token}",
    "random from {low} to {high} {token}": "случайная от {low} до {high} {token}",
    "from {low} to {high} sec": "от {low} до {high} сек",
    "Check the settings": "Проверьте настройки",
    "Settings were not saved": "Настройки не сохранены",
    "Settings were not applied": "Настройки не применены",
    "Sending in progress": "Идёт рассылка",
    "Close the program? The current transaction may remain unconfirmed.":
        "Закрыть программу? Текущая транзакция может остаться неподтверждённой.",
    "Close": "Закрыть",
    "Continue sending": "Продолжить рассылку",
    "OK": "Понятно",
}
