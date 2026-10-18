# Nashtaee Cafe Shop Bot

A Telegram bot for **Nashtaee (ناشتایی)**, a cafe that serves breakfast and lunch to office workers. Customers browse the menu, fill a cart and place orders for pickup or delivery. A single admin approves each order, tracks it until it is ready, and manages the menu, all inside Telegram.

The bot's interface is in Persian (Farsi), with Persian digits and prices in toman.

## Features

### For customers
- **Menu browsing** by category (🍳 breakfast, 🍝 lunch), with prices and availability.
- **Cart**: quick quantity buttons or a custom quantity (up to 99), view or clear the cart at any time.
- **Checkout** with in-store pickup or delivery. Name, company and phone are asked once and remembered. Past delivery addresses are offered again.
- **Iranian phone validation**: accepts `+98…`, `0098…`, `9…` and Persian/Arabic digits, or a shared Telegram contact, and normalizes to `09xxxxxxxxx`.
- **Prep-time estimate**: once an order is confirmed, the customer gets an estimated ready time that includes every order already in the kitchen queue.
- **Profile** (`/profile`) to view and edit saved details.
- **Referral program** (`/referral`): after their first purchase, a customer gets a personal invite link. Invited users get a discount on their first order, and the inviter earns reward discounts on later orders.
- **Survey** (`/poll`): a multi-section questionnaire, with option buttons and an optional free-text answer. Each user can answer each poll once.
- **Support** (`/support`) shows the support contact.

### For the admin
- **Order approval**: every new order is sent to the admin chat with Confirm and Cancel buttons. The customer is notified of the decision.
- **Open orders**: list confirmed orders, then mark them finished or cancel them (with a confirmation step).
- **Admin panel** (`/admin`): add, edit, delete and enable or disable products. Editable fields are price, batch size and batch prep time. A product that appears in orders can't be deleted.
- **Database backups**: a copy of the SQLite database is sent to the admin chat every day at 23:55 (server time), and on demand with `/backup`.
- **Log reporting**: warnings and errors are posted to a Telegram report channel, in addition to console and rotating file logs.

## Tech stack

| Concern | Library |
|---|---|
| Telegram bot | [python-telegram-bot](https://python-telegram-bot.org/) 22 (with job queue) |
| ORM / database | [SQLModel](https://sqlmodel.tiangolo.com/) on SQLAlchemy 2, SQLite by default |
| Configuration | [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) loading `.env` |
| Logging | `logging` + `colorlog`, rotating files, Telegram handler |
| Proxy support | `socksio` (SOCKS5 proxy for Telegram API access) |
| Linting | `ruff` |

## Project structure

```
NashtaeeCafeShop/
├── start_telegram_bot.py      # Entry point: builds the logger, creates tables, runs the bot
├── requirements.txt
├── Settings/
│   ├── config.py              # Settings loaded from .env (pydantic-settings)
│   ├── custom_logger.py       # Console, file and Telegram log handlers
│   └── timing.py              # UTC "now" helper
├── Models/                    # Plain dataclasses: the domain model
│   ├── customer.py
│   ├── menu.py                # Product, ProductCategory, Item (prep-time calculation)
│   ├── order.py               # Order, OrderState, Discount
│   ├── referral.py            # ReferralPlan: discount and reward rules
│   └── poll.py                # Poll template and the current survey (POLL)
├── Database/
│   ├── tables.py              # SQLModel tables mapping to and from the models
│   ├── database.py            # Engine, table creation, automatic column migration
│   ├── repository.py          # All queries used by the bot
│   ├── seed.py                # Seeds the initial menu
│   ├── backup.py              # SQLite online backup
│   └── __main__.py            # `python -m Database`: create tables
├── TelegramBot/
│   ├── bot.py                 # Application setup, conversations, commands, daily job
│   ├── handlers.py            # Customer flows: menu, cart, checkout, profile, poll, referral
│   ├── keyboards.py           # Customer inline keyboards and callback data
│   ├── utils.py               # Persian digits, price/time formatting, phone normalization
│   └── PanelAdmin/
│       ├── handlers.py        # Admin panel, open orders, backups
│       └── keyboards.py
├── Records/                   # SQLite database (created at runtime, git-ignored)
└── Logs/                      # Log files (created at runtime, git-ignored)
```

## Getting started

### Prerequisites
- Python 3.10 or newer (developed on Python 3.15)
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- The admin's numeric Telegram chat ID (for example from [@userinfobot](https://t.me/userinfobot))
- A Telegram channel for log reports, with the bot added as an admin

### Installation

```bash
git clone <repository-url>
cd NashtaeeCafeShop

python -m venv .nashtaee_venv
# Windows
.nashtaee_venv\Scripts\activate
# Linux / macOS
source .nashtaee_venv/bin/activate

pip install -r requirements.txt
```

### Configuration

Create a `.env` file in the project root:

```env
# Telegram
TELEGRAM_CUSTOMER_BOT_TOKEN="123456789:ABC..."
TELEGRAM_ADMIN_ID=123456789               # chat that approves orders and manages the menu
TELEGRAM_SUPPORT_ID="@nashtaee_support"   # shown by /support
TELEGRAM_REPORT_CHANNEL="@nashtaee_logs"  # receives WARNING+ logs
# TELEGRAM_PROXY="socks5://127.0.0.1:9050"  # optional

# Database (any SQLAlchemy URL; backups only work with SQLite)
DB_NAME="sqlite:///Records/Nashtaee.db"

# Referral plan (optional; amounts in toman)
REFERRAL_FIRST_BUY_DISCOUNT=10000   # off an invited user's first order
REFERRAL_REWARD_EVERY=1             # invited users needed per reward
REFERRAL_REWARD_DISCOUNT=20000      # inviter's reward per REFERRAL_REWARD_EVERY invites
REFERRAL_REWARD_ON_PURCHASE=true    # false: invites count when they join, not when they buy
```

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_CUSTOMER_BOT_TOKEN` | yes | | Bot token from BotFather |
| `TELEGRAM_ADMIN_ID` | yes | | Numeric chat ID of the admin |
| `TELEGRAM_SUPPORT_ID` | yes | | Support contact shown to customers |
| `TELEGRAM_REPORT_CHANNEL` | yes | | Channel or chat for log reports |
| `TELEGRAM_PROXY` | no | none | Proxy URL for the Telegram API, e.g. `socks5://host:port` |
| `DB_NAME` | yes | | SQLAlchemy database URL |
| `REFERRAL_FIRST_BUY_DISCOUNT` | no | `10000` | Invited user's first-order discount |
| `REFERRAL_REWARD_EVERY` | no | `1` | Invites per reward |
| `REFERRAL_REWARD_DISCOUNT` | no | `20000` | Reward amount |
| `REFERRAL_REWARD_ON_PURCHASE` | no | `true` | Count invites on purchase rather than on joining |

`.env` is git-ignored. Never commit your bot token.

### Set up the database

Tables are created automatically when the bot starts. To create them by hand and load the starter menu:

```bash
python -m Database        # create tables
python -m Database.seed   # insert the default menu (only if the products table is empty)
```

### Run the bot

```bash
python start_telegram_bot.py
```

The bot uses long polling, so no webhook or public URL is needed. On startup it sets the bot description and command menu. Admin-only commands are added to the admin's chat, which works only if the admin has already started the bot.

## Bot commands

| Command | Who | Description |
|---|---|---|
| `/start` | everyone | Start ordering (main menu) |
| `/cancel` | everyone | Cancel the current order |
| `/profile` | everyone | View and edit saved details |
| `/poll` | everyone | Take the survey |
| `/referral` | everyone | Invite link and referral status |
| `/support` | everyone | Support contact |
| `/admin` | admin | Open the admin panel |
| `/backup` | admin | Send a database backup now |

Deep links:
- `https://t.me/<bot_username>?start=ref_<CODE>` opens the bot with a customer's invite code.
- `https://t.me/<bot_username>?start=poll` opens the survey directly.

## How it works

### Order lifecycle

```
Customer confirms ──► sent to admin (awaiting approval)
                          │
              ┌───────────┴───────────┐
          Confirm                  Cancel
              │                       │
     saved as CONFIRMED          customer notified
     customer gets order
     number + ETA
              │
      ┌───────┴────────┐
   Finish            Cancel
      │                 │
   FINISHED          CANCELED
```

An order is written to the database only when the admin confirms it. Until then it lives in the bot's memory, so orders still waiting for approval are lost if the bot restarts.

### Prep-time estimate

Each product has a batch size (`prep_count`) and a batch time (`prep_minutes`). An item's prep time is `ceil(count / prep_count) × prep_minutes`. The estimate a customer sees is the total prep time of all confirmed (open) orders, including theirs. Delivery time is not included.

### Referral discounts

- A customer gets an 8-character invite code after their first purchase.
- A new user who opens the bot through that link gets `REFERRAL_FIRST_BUY_DISCOUNT` off their first order. Only the first invite link a user opens counts, and links don't work for users who have already bought.
- For every `REFERRAL_REWARD_EVERY` counted invitees, the inviter earns `REFERRAL_REWARD_DISCOUNT`. Rewards are spent automatically on later orders, and any part not used carries over.
- Discounts on one order never exceed the order total.

### Database migrations

`create_db_and_tables()` creates missing tables and also adds columns that were added to a model after the database was created. A new column must be nullable or have a `server_default`. Renamed or removed columns are not handled.

### Customizing the survey

The survey is defined in `Models/poll.py` as `POLL`. Edit its sections and questions there. Responses are stored per poll `key`, so give a new survey a new key to let everyone answer again.

## Development

```bash
ruff check .
ruff format .
```

## License

Released under the [MIT License](LICENSE). Copyright (c) 2026 Soheil Shiravy.
