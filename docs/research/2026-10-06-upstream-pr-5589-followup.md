# PR #5589: локальное исправление и оставшиеся зависимости

Снимок GitHub проверен 6 октября 2026. Upstream head:
`777640a9f6379d4694648842f38de702b7c6ec7f`. PR открыт, не draft,
review decision — `CHANGES_REQUESTED`. Все 21 открытое обсуждение получено
через GraphQL; пагинация threads и comments завершена.

Работа находится в локальной ветке `fix/upstream-5589-recovery-20261006`,
созданной от provider `dev` `b5496d8e1df15a743fd8ca648cbe788c527ad767` (4.3.6).
Upstream и integration fork в ходе этой работы не изменялись.

## Решение о составе изменений

Пользователь явно выбрал удаление `max_quality_dynamic` из текущего провайдера.
Удалены его coordinator, prefetch, restart-intent/session cleanup, форматная
политика, runtime setting, строки интерфейса и тесты удалённого режима.
Исторические release notes и завершённые specs сохранены.
Старое значение `stream_mode` игнорируется; используется один фиксированный
PCM-формат на сессию. Повторная настройка для этого изменения не требуется.

## Карта открытых замечаний

Статусы ниже относятся к локальной ветке. Ни одно GitHub-обсуждение агент
не закрыл и ни одного ответа не публиковал.

| Discussion | Локальный результат |
| --- | --- |
| [4175659757](https://github.com/music-assistant/server/pull/5589#discussion_r4175659757) | Сейчас используется supported API `get_provider_configs(provider_domain="yandex_music")` с фильтрацией disabled. В `ya-passport-auth` подготовлена локальная ветка `fix/list-instances-skip-disabled`: общий `list_yandex_music_instances` пропускает disabled instances. После её релиза провайдер переходит на общий helper отдельным PR. |
| [4175662425](https://github.com/music-assistant/server/pull/5589#discussion_r4175662425) | Проверки `__auto__` и `publish_name` удалены как уже покрытые core migration. Очистка own-credentials при reconfigure и отказ для `__own__` сохранены. |
| [4175664304](https://github.com/music-assistant/server/pull/5589#discussion_r4175664304) | Удалён недостижимый compatibility guard вокруг базового `get_setup_value`. |
| [4175667965](https://github.com/music-assistant/server/pull/5589#discussion_r4175667965) | Динамическая `format_policy` удалена. Стабильное согласование частоты в `_snap_rate_to_player` сохранено: объявленный формат должен совпадать с потоком. |
| [4175669880](https://github.com/music-assistant/server/pull/5589#discussion_r4175669880) | Проверки диапазонов удалены вместе с dynamic mode. |
| [4175672428](https://github.com/music-assistant/server/pull/5589#discussion_r4175672428) | RADIO callback возвращает `False` для отказа от публикации; служебное исключение удалено. |
| [4175679288](https://github.com/music-assistant/server/pull/5589#discussion_r4175679288) | Проверка `__auto__` удалена: core `migrate_connected_player_plugins` уже очищает её, провайдер проверяет только пустой плеер. Own-mode guard сохранён. |
| [4175683994](https://github.com/music-assistant/server/pull/5589#discussion_r4175683994) | Из стабильного capability lookup удалён broad fallback; динамический lookup удалён полностью. |
| [4175686304](https://github.com/music-assistant/server/pull/5589#discussion_r4175686304) | Dynamic mode удалён по решению пользователя. |
| [4175687667](https://github.com/music-assistant/server/pull/5589#discussion_r4175687667) | Бесконечные ожидания teardown удалены вместе с dynamic coordinator. |
| [4175688810](https://github.com/music-assistant/server/pull/5589#discussion_r4175688810) | Внешний бесконечный retry удалён. Стабильный fetch использует один ограниченный цикл из трёх попыток. |
| [4175690255](https://github.com/music-assistant/server/pull/5589#discussion_r4175690255) | Validation-by-side-effect удалена вместе с dynamic prefetch. |
| [4175691958](https://github.com/music-assistant/server/pull/5589#discussion_r4175691958) | Ручное возбуждение `CancelledError` удалено вместе с dynamic fetch. |
| [4175693730](https://github.com/music-assistant/server/pull/5589#discussion_r4175693730) | Удалён флаг `previous`; индекс задаёт caller, generation проверяется при отправке. Отсутствие предыдущего трека остаётся штатным no-op. |
| [4175696071](https://github.com/music-assistant/server/pull/5589#discussion_r4175696071) | Удалены неподтверждённый ключ `player` и очистка `publish_name`, которую выполняет core migration. Очистка own-credentials при reconfigure сохранена. |
| [4175697325](https://github.com/music-assistant/server/pull/5589#discussion_r4175697325) | Неиспользуемое присваивание в setup retry удалено. |
| [4175698742](https://github.com/music-assistant/server/pull/5589#discussion_r4175698742) | Empty redirect теперь непосредственно `LoginFailed` в обоих connection paths; отдельный exception удалён. |
| [4175699910](https://github.com/music-assistant/server/pull/5589#discussion_r4175699910) | Отсутствующие и некорректные числовые поля исключаются из сравнения heartbeat без sentinel-значений. |
| [4175701333](https://github.com/music-assistant/server/pull/5589#discussion_r4175701333) | Cleanup и reconnect находятся в `finally`; неожиданная ошибка сохраняет traceback. Старый loop не закрывает новую socket/session. |
| [4196454536](https://github.com/music-assistant/server/pull/5589#discussion_r4196454536) | Natural completion ждёт reconnect/settle с лимитом и повторяет одну неудачную публикацию. Изменение queue/device/pause или client отменяет действие. |
| [4196454668](https://github.com/music-assistant/server/pull/5589#discussion_r4196454668) | Исправление метаданных upstream PR остаётся действием владельца. Синхронизирована 4.3.6; локальный changelog готовит 4.3.7, `VERSION` не изменён. |

## Проверка и изменения тестового контракта

Исходная воспроизводимая база после `uv sync --extra test --frozen`: 439 тестов.
Регрессии queue recovery, socket cleanup, stale-loop ownership, malformed heartbeat,
public config access и capability errors сначала наблюдались красными.

Тесты dynamic mode и удалённого compatibility guard удалены вместе с кодом.
Ожидание callback errors обновлено по требованию reviewer: ошибка продолжает
распространяться, но cleanup/reconnect обязателен. Capability `ValueError` теперь
распространяется вместо fallback. Transport doubles поддерживают отказ callback
от публикации через `False`, а setup doubles используют public async config API.
Эти изменения отражают новые контракты и не ослабляют проверки stable playback.

Проверены полный pytest, Ruff, mypy, pre-commit и Astro build. Добавлены реальные
loopback WebSocket сценарии нормального disconnect и callback fault. Репозиторные
docs checks перенесены в `tests/standalone/`, исключаемый из upstream export.
Настоящие Yandex CDN, FFmpeg и аппаратные плееры в этой работе не проверялись.

## Порядок следующей публикации

1. Владелец проверяет локальные изменения.
2. Provider PR проходит review; merge требует явного maintainer approval.
3. Maintainer устанавливает `VERSION`; pipeline выпускает и синхронизирует релиз.
4. После проверки нового upstream head и VERSION владелец обновляет заголовок
   и описание #5589 и пишет ответы в human review threads собственными словами.

Черновик описания: `upstream-pr-5589-body-v4.3.7.md`. Он предназначен для
последующего релиза 4.3.7, а не для нынешнего upstream head 4.3.6.
Старый `pr-5589-publish-v4.3.5` bundle не обновлялся и не запускался.
