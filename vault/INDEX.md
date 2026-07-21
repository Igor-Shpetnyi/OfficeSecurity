---
title: Vault Index
updated: 2026-07-19
status: active
---

# Vault — індекс

Точка входу. Читати цей файл першим у будь-якій сесії — далі йти лише за тими посиланнями, які реально потрібні під поточну задачу. Не читати весь vault підряд.

## Структура

| Розділ | Призначення | Мутабельність |
|---|---|---|
| [architecture/](architecture/) | Як влаштована система (компоненти, потоки даних) | Оновлюється in-place при зміні архітектури |
| [decisions/](decisions/) | Чому обрано саме так (ADR-style, одне рішення — один файл) | Append-only; старе рішення не редагується, а замінюється новим файлом зі статусом `superseded` |
| [glossary/](glossary/) | Домені терміни та їх точне значення в цьому проєкті | Оновлюється in-place |
| [progress/](progress/) | Хронологічний журнал сесій розробки | Append-only, один файл на дату |
| [backlog/](backlog/) | Відкриті питання, TODO, майбутні інтеграції | Оновлюється in-place, пункти закриваються, не видаляються без сліду |
| [design/](design/) | Дизайн-система UI (кольори, компоненти, layout) | Оновлюється in-place |

## Активні файли

- [architecture/overview.md](architecture/overview.md)
- [decisions/0001-hetzner-not-local.md](decisions/0001-hetzner-not-local.md)
- [decisions/0002-hybrid-llm-not-local.md](decisions/0002-hybrid-llm-not-local.md)
- [decisions/0003-telethon-not-pyrogram.md](decisions/0003-telethon-not-pyrogram.md)
- [decisions/0004-redis-pubsub-channel-sync.md](decisions/0004-redis-pubsub-channel-sync.md)
- [decisions/0005-docker-compose-local-infra.md](decisions/0005-docker-compose-local-infra.md)
- [decisions/0006-shared-design-system-no-react.md](decisions/0006-shared-design-system-no-react.md)
- [decisions/0007-edit-dedup-by-text-diff.md](decisions/0007-edit-dedup-by-text-diff.md)
- [decisions/0008-kyiv-time-python-side-conversion.md](decisions/0008-kyiv-time-python-side-conversion.md)
- [decisions/0009-avatar-color-hue-only.md](decisions/0009-avatar-color-hue-only.md)
- [decisions/0010-sequential-updates-race-fix.md](decisions/0010-sequential-updates-race-fix.md)
- [decisions/0011-media-stub-structured-type.md](decisions/0011-media-stub-structured-type.md)
- [decisions/0012-three-layer-detection-not-regex-then-llm.md](decisions/0012-three-layer-detection-not-regex-then-llm.md) — див. також повну специфікацію [`../TZ_konveyer_analizu_zagroz.md`](../TZ_konveyer_analizu_zagroz.md)
- [glossary/threat-levels.md](glossary/threat-levels.md)
- [backlog/open-questions.md](backlog/open-questions.md)
- [design/design.md](design/design.md) — обов'язково для будь-якого UI, див. правило в [CLAUDE.md](../CLAUDE.md)

## Джерело правди

Технічне завдання проєкту: [`../TZ_bezpeka_ofisu_sumy.md`](../TZ_bezpeka_ofisu_sumy.md). Vault не дублює ТЗ — він фіксує те, чого в ТЗ немає: хід розробки, рішення що приймались під час імплементації, питання що виникли.

Доповнення до ТЗ (свідомий відхід від розділів 5/8/9/15 оригіналу, за результатами дослідження реальних даних — [ADR-0012](decisions/0012-three-layer-detection-not-regex-then-llm.md)): [`../TZ_konveyer_analizu_zagroz.md`](../TZ_konveyer_analizu_zagroz.md).
