# Library Service

Online management system for book borrowings, built with Django REST Framework.
It replaces paper-based tracking: the library keeps a books inventory, users
borrow and return books, and administrators get Telegram notifications.

## Features

- JWT authentication (registration, token obtain/refresh, profile)
- Books CRUD: anyone can list books, only admins can create/update/delete
- Borrowings: create, list, detail, return
- Book inventory is decreased on borrowing and restored on return
- Regular users see only their own borrowings; admins see everything
- Filtering borrowings by `is_active` and (for admins) `user_id`
- Telegram notification on each new borrowing
- Swagger / ReDoc API documentation

## Tech stack

Python, Django, Django REST Framework, SimpleJWT, drf-spectacular,
python-dotenv, requests, SQLite.

## Installation

```bash
git clone git@github.com:MykolaLozanDevelopment/library-service.git
cd library-service
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.sample .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

The API is available at http://127.0.0.1:8000/.

## Environment variables

Copy `.env.sample` to `.env` and fill it in. The `.env` file is never committed.

| Variable | Description |
|---|---|
| `SECRET_KEY` | Django secret key |
| `DEBUG` | `True` for development |
| `ALLOWED_HOSTS` | Comma-separated list of hosts |
| `TELEGRAM_BOT_TOKEN` | Token of the bot that sends notifications |
| `TELEGRAM_CHAT_ID` | Id of the chat that receives notifications |

## Telegram notifications

1. Create a bot with `@BotFather` (`/newbot`) and copy its token.
2. Create a group and add the bot to it, then send `/start` in the group.
3. Get the chat id:
   `curl "https://api.telegram.org/bot<TOKEN>/getUpdates"` and find `chat` -> `id`.
4. Put both values into `.env`. Restart the server after changing `.env`.

If Telegram is not configured or unavailable, borrowings are still created;
the notification is skipped and the error is logged.

## Authentication

1. Register: `POST /users/`
2. Get tokens: `POST /users/token/` with `email` and `password`
3. Send the access token in the **`Authorize`** header (not `Authorization`):

```
Authorize: Bearer <access_token>
```

The access token lives for 5 minutes; refresh it with `POST /users/token/refresh/`.
In Swagger UI use the **Authorize** button and enter `Bearer <access_token>`.

## API endpoints

### Users

| Method | Endpoint | Description | Access |
|---|---|---|---|
| POST | `/users/` | Register a new user | Anyone |
| POST | `/users/token/` | Get JWT tokens | Anyone |
| POST | `/users/token/refresh/` | Refresh access token | Anyone |
| GET, PUT, PATCH | `/users/me/` | View / update own profile | Authenticated |

### Books

| Method | Endpoint | Description | Access |
|---|---|---|---|
| GET | `/books/` | List books | Anyone |
| GET | `/books/<id>/` | Book details | Anyone |
| POST | `/books/` | Add a book | Admin |
| PUT, PATCH | `/books/<id>/` | Update a book (including inventory) | Admin |
| DELETE | `/books/<id>/` | Delete a book | Admin |

### Borrowings

| Method | Endpoint | Description | Access |
|---|---|---|---|
| GET | `/borrowings/` | List borrowings | Authenticated |
| GET | `/borrowings/<id>/` | Borrowing details | Authenticated |
| POST | `/borrowings/` | Borrow a book | Authenticated |
| POST | `/borrowings/<id>/return/` | Return a book | Authenticated |

**List filters** (query parameters of `GET /borrowings/`):

- `is_active=true` - only borrowings that are not returned yet;
  `is_active=false` - only returned ones
- `user_id=<id>` - admins only: show borrowings of one user.
  Without it admins see all borrowings. Ignored for regular users,
  who always see only their own borrowings.

**Create a borrowing** - request body:

```json
{
  "book": 1,
  "expected_return_date": "2026-12-31"
}
```

The current user is attached automatically and the book inventory is
decreased by 1. The request fails with `400` if the book inventory is 0
or the expected return date is not after today.

**Return a borrowing** - `POST /borrowings/<id>/return/` has no body.
It sets the actual return date to today and increases the book inventory
by 1. A borrowing cannot be returned twice (`400`).

## API documentation

- Swagger UI: http://127.0.0.1:8000/api/doc/swagger/
- ReDoc: http://127.0.0.1:8000/api/doc/redoc/
- OpenAPI schema: http://127.0.0.1:8000/api/schema/

## Running tests

```bash
python manage.py test
```

Test coverage:

```bash
coverage run --source=. --omit=".venv/*" manage.py test
coverage report
```

Code style:

```bash
flake8 --exclude=.venv,migrations
```

## Project structure

```
library_service/   project settings, urls, API docs tests
users/             custom email-based User model, JWT endpoints
books/             Book model, CRUD API, permissions
borrowings/        Borrowing model, list/detail/create/return, filters
notifications/     Telegram helper
```
