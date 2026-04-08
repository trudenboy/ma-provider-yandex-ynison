"""Constants for the Yandex Ynison plugin."""

from __future__ import annotations

from typing import Final

# Ynison WebSocket endpoints
YNISON_REDIRECT_URL: Final[str] = (
    "wss://ynison.music.yandex.ru/redirector.YnisonRedirectService/GetRedirectToYnison"
)
YNISON_STATE_PATH: Final[str] = "/ynison_state.YnisonStateService/PutYnisonState"

# Origin header required by Ynison
YNISON_ORIGIN: Final[str] = "https://music.yandex.ru"

# Configuration keys
CONF_TOKEN: Final[str] = "token"
CONF_X_TOKEN: Final[str] = "x_token"
CONF_PLAYER: Final[str] = "player"
CONF_DISPLAY_NAME: Final[str] = "display_name"
CONF_ALLOW_PLAYER_SWITCH: Final[str] = "allow_player_switch"

# Actions
CONF_ACTION_AUTH_QR: Final[str] = "auth_qr"
CONF_ACTION_CLEAR_AUTH: Final[str] = "clear_auth"
CONF_REMEMBER_SESSION: Final[str] = "remember_session"

# Defaults
DEFAULT_DISPLAY_NAME: Final[str] = "Music Assistant"
DEFAULT_APP_NAME: Final[str] = "Music Assistant"
DEFAULT_APP_VERSION: Final[str] = "1.0.0"

# Device types (from Ynison protobuf DeviceType enum)
DEVICE_TYPE_SPEAKER: Final[str] = "SPEAKER"
