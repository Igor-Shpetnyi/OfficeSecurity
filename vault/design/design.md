# Horyzont — Design System

Документ описує дизайн-систему веб-панелі на основі аналізу `Resources/design_preference.jpg`.
Усі рішення орієнтовані на точне відтворення стилю преференсу та підтримку двох тем.

---

## 1. Загальна філософія

**Стиль:** Modern Dark Dashboard — мінімалізм, висока щільність інформації, чітка ієрархія.

Ключові принципи:
- Глибина досягається **різницею фонів** (не тінями): sidebar темніший за контент, картки світліші за фон.
- Закруглені кути на всьому — від головного контейнера до бейджів.
- Мінімум декору: жодних градієнтів, жодних яскравих кольорів окрім одного акцентного.
- Контент — головний герой: багато повітря, великі заголовки, читаємі таблиці.
- Акцентна кнопка (CTA) — **інвертована**: темна тема → біла кнопка; світла тема → темна кнопка.

---

## 2. Колірна палітра

### Реалізація: CSS Custom Properties

Весь колір — через CSS-змінні. Перемикання теми = зміна класу `data-theme="dark"` / `data-theme="light"` на `<html>`.

```css
:root[data-theme="dark"] {
  /* Фони */
  --bg-root:        #161618;   /* зовнішній фон (body) */
  --bg-sidebar:     #1c1c1e;   /* сайдбар */
  --bg-content:     #222224;   /* основний контент */
  --bg-card:        #2a2a2d;   /* картки */
  --bg-card-hover:  #313135;   /* картка при hover */
  --bg-input:       #2a2a2d;   /* input, search */
  --bg-active:      #333337;   /* активний пункт меню */

  /* Межі */
  --border:         #333336;   /* межі карток, таблиць */
  --border-subtle:  #2a2a2d;   /* дуже тонкі роздільники */

  /* Текст */
  --text-primary:   #f2f2f7;   /* основний текст */
  --text-secondary: #8e8e93;   /* другорядний (підписи, мітки) */
  --text-tertiary:  #636366;   /* найслабший (placeholder, inactive) */
  --text-inverted:  #161618;   /* текст на акцентному фоні */

  /* Акцент */
  --accent:         #f2f2f7;   /* CTA-кнопка, primary action (біла) */
  --accent-hover:   #d1d1d6;

  /* Семантичні */
  --positive:       #34c759;   /* зріст, успіх */
  --negative:       #ff3b30;   /* падіння, помилка */
  --warning:        #ff9f0a;
  --badge-pro:      #0a84ff;   /* Pro badge */

  /* Тіні */
  --shadow-card:    0 1px 3px rgba(0,0,0,0.4);
  --shadow-dropdown: 0 8px 24px rgba(0,0,0,0.6);
}

:root[data-theme="light"] {
  /* Фони */
  --bg-root:        #f2f2f7;
  --bg-sidebar:     #ffffff;
  --bg-content:     #f7f7f8;
  --bg-card:        #ffffff;
  --bg-card-hover:  #f5f5f7;
  --bg-input:       #f2f2f7;
  --bg-active:      #ebebef;

  /* Межі */
  --border:         #e5e5ea;
  --border-subtle:  #f0f0f5;

  /* Текст */
  --text-primary:   #1c1c1e;
  --text-secondary: #6c6c70;
  --text-tertiary:  #aeaeb2;
  --text-inverted:  #f2f2f7;

  /* Акцент */
  --accent:         #1c1c1e;   /* CTA — тепер темна (інверсія) */
  --accent-hover:   #3a3a3c;

  /* Семантичні */
  --positive:       #34c759;
  --negative:       #ff3b30;
  --warning:        #ff9f0a;
  --badge-pro:      #0a84ff;

  /* Тіні */
  --shadow-card:    0 1px 3px rgba(0,0,0,0.08), 0 0 0 1px var(--border);
  --shadow-dropdown: 0 8px 24px rgba(0,0,0,0.12);
}
```

### Чому саме такий світлий варіант

Преференс — класичний **Apple-style dark UI**. Світла тема будується за тією ж логікою, але через систему Apple Human Interface Guidelines:
- `#f2f2f7` = системний `systemGroupedBackground` (iOS/macOS)
- Білі картки на сірому фоні — точна інверсія темних карток на темному фоні
- CTA-кнопка інвертується (чорна замість білої), бо вона завжди має найвищий контраст
- Семантичні кольори (зелений/червоний) залишаються незмінними — вони читаються в обох темах

---

## 3. Типографіка

**Шрифт:** `Inter` (Google Fonts). Якщо недоступний — `system-ui, -apple-system, sans-serif`.

```css
font-family: 'Inter', system-ui, -apple-system, sans-serif;
font-feature-settings: 'cv02', 'cv03', 'cv04', 'cv11'; /* цифри та пунктуація Inter */
```

| Роль | Розмір | Вага | Колір | Застосування |
|---|---|---|---|---|
| Page title | 28px / 1.2 lh | 700 | `--text-primary` | "Ласкаво просимо до Horyzont" |
| Section heading | 16px | 600 | `--text-primary` | Заголовки карток |
| Nav label (MENU) | 11px / 1.4 lh | 600 | `--text-tertiary` | Uppercase, letter-spacing: 0.08em |
| Nav item | 14px | 500 | `--text-secondary` → `--text-primary` (active) | Пункти меню |
| Body | 14px | 400 | `--text-primary` | Основний текст |
| Caption | 12px | 400 | `--text-secondary` | Підписи, мітки |
| Table header | 12px | 500 | `--text-secondary` | Заголовки стовпців, uppercase |
| Badge/tag | 11px | 600 | — | Відсоткові бейджі |
| Mono/number | 14px | 500 | `--text-primary` | Ціни, об'єми — `font-variant-numeric: tabular-nums` |

---

## 4. Layout та сітка

### Загальна структура

```
┌─────────────────────────────────────────────────────┐
│  Sidebar (240px fixed)  │  Main Content (flex-grow)  │
│                         │  ┌─────────────────────┐  │
│  [Avatar + Name]        │  │ Top Bar             │  │
│  ─────────────────       │  ├─────────────────────┤  │
│  MENU                   │  │                     │  │
│  • Dashboard            │  │  Content Grid       │  │
│  • Контакти (active)    │  │  (cards, tables)    │  │
│  • Групи                │  │                     │  │
│  • Повідомлення         │  └─────────────────────┘  │
│  ─────────────────       │                           │
│  СИСТЕМА                │                           │
│  • Налаштування         │                           │
│  • Вигляд               │                           │
│  ─────────────────       │                           │
│  [Bottom card]          │                           │
└─────────────────────────────────────────────────────┘
```

### Деталі layout

| Елемент | Розмір / відступ |
|---|---|
| Sidebar width | 240px |
| Content padding | 24px |
| Card gap (grid) | 16px |
| Card padding | 20px |
| Top bar height | 60px |
| Border-radius: контейнер | 16px (десктоп) |
| Border-radius: картка | 12px |
| Border-radius: кнопка primary | 8px |
| Border-radius: кнопка small | 6px |
| Border-radius: badge/pill | 999px |
| Border-radius: input/search | 8px |
| Border-radius: avatar | 50% |

### Контентна сітка

Основний контент: CSS Grid, `auto-fill` або фіксовані зони:
- Великі картки — `col-span-2`
- Права панель деталей — `col-span-1` (270-300px)
- Таблиця — `col-span-full`

---

## 5. Компоненти

### 5.1 Sidebar

```
Sidebar
├── Header (user block)
│   ├── Avatar (40px circle, з ободком --border)
│   ├── Display name (14px, 600, --text-primary)
│   ├── Handle/email (12px, --text-secondary)
│   └── Pro badge (pill, --badge-pro bg, white text, 10px 600)
│
├── Nav section (повторюється)
│   ├── Section label (11px, uppercase, --text-tertiary, padding: 16px 12px 4px)
│   └── Nav item × N
│       ├── Icon (16px, --text-secondary → --text-primary active)
│       ├── Label (14px, 500)
│       └── Active state: bg --bg-active, border-radius 8px, text --text-primary
│
├── Bottom promo card
│   ├── bg: --bg-card, border-radius 12px
│   ├── Ілюстрація або іконка
│   └── Текст + short description
│
└── Sticky bottom links (Settings, Appearance, Support)
    └── Такі ж як nav items, але без section label
```

**Hover на nav item:** `background: --bg-active`, плавний transition 150ms.
**Активний пункт:** фон `--bg-active`, текст `--text-primary`, іконка `--text-primary`.

### 5.2 Top Bar

```
Top Bar (60px height, border-bottom: 1px --border)
├── Left: breadcrumb
│   └── "Панель / Групи" (--text-secondary / "/" / --text-primary, 14px)
├── Center: flex-grow
└── Right: [Search] [Bell] [CTA Button]
    ├── Search: input, 200px, bg --bg-input, border --border, icon всередині
    ├── Bell: icon button, 36px, bg --bg-active при hover
    └── CTA: "Надіслати" — bg --accent, color --text-inverted, 36px height, 8px radius
```

### 5.3 Картки (Cards)

Базова картка:
```css
.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
  box-shadow: var(--shadow-card);
}
```

Типи карток у Horyzont:
- **Stat card** — одна метрика (кількість повідомлень, груп, контактів)
- **Group card** — назва групи, кількість учасників, остання активність, кнопки дій
- **Message log card** — таблиця надісланих повідомлень
- **Contact card** — ім'я, номер, нотатки, кнопка "Написати"
- **Detail panel** — права панель з деталями вибраного об'єкта (як у преференсі)

### 5.4 Таблиці

```
Table
├── Header row: 12px, uppercase, --text-secondary, letter-spacing 0.05em, border-bottom --border
├── Data rows: 14px, --text-primary, hover: bg --bg-card-hover
├── Row height: 52px
├── Cell padding: 0 16px
└── Last column: Action кнопки (small outlined)
```

**Фільтри над таблицею:** pill tabs — активний: bg `--bg-active`, text `--text-primary`; інші: прозорі.

### 5.5 Кнопки

| Тип | Фон | Текст | Border | Hover |
|---|---|---|---|---|
| Primary (CTA) | `--accent` | `--text-inverted` | none | `--accent-hover` |
| Secondary | transparent | `--text-primary` | `1px --border` | bg `--bg-active` |
| Danger | transparent | `--negative` | `1px --negative` | bg `rgba(--negative, 0.1)` |
| Ghost/icon | transparent | `--text-secondary` | none | bg `--bg-active` |

Висота кнопок: large — 40px, default — 36px, small — 28px.
Усі кнопки: `transition: all 150ms ease`, `border-radius` згідно таблиці в §4.

### 5.6 Бейджі та теги

```css
/* Відсоток позитивний */
.badge-positive {
  background: rgba(52, 199, 89, 0.15);
  color: #34c759;
  border-radius: 999px;
  font-size: 11px; font-weight: 600;
  padding: 2px 8px;
}
/* Відсоток негативний */
.badge-negative {
  background: rgba(255, 59, 48, 0.15);
  color: #ff3b30;
}
/* Pro */
.badge-pro {
  background: #0a84ff;
  color: #fff;
}
/* Role: admin */
.badge-admin {
  background: rgba(10, 132, 255, 0.15);
  color: #0a84ff;
}
/* Role: operator */
.badge-operator {
  background: rgba(255, 159, 10, 0.15);
  color: #ff9f0a;
}
```

### 5.7 Форми та Inputs

```css
.input {
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 14px;
  padding: 8px 12px;
  transition: border-color 150ms;
}
.input:focus {
  border-color: var(--accent);
  outline: none;
  box-shadow: 0 0 0 3px rgba(var(--accent-rgb), 0.15);
}
.input::placeholder { color: var(--text-tertiary); }
```

### 5.8 Toggle (перемикач теми)

Компонент аналогічний `Staking` toggle з преференсу:
- Track: 36px × 20px, border-radius 999px
- Thumb: 16px circle
- Темна тема active: `--accent` track, white thumb
- Використовується й для перемикання dark/light

---

## 6. Іконки

Бібліотека: **Lucide React** (`lucide-react` npm package).

Причини:
- Pixel-perfect, однаковий stroke-width
- Tree-shakeable (лише те, що використовується)
- Активно підтримується
- Стиль повністю відповідає преференсу

Стандартний розмір: `16px` в nav, `20px` в картках, `24px` в заголовках.
Колір: `currentColor` — успадковується від батьківського тексту.

---

## 7. Анімації та переходи

| Елемент | Властивість | Тривалість | Easing |
|---|---|---|---|
| Nav hover/active | background, color | 150ms | ease |
| Кнопки | background, box-shadow | 150ms | ease |
| Картки hover | transform (translateY -1px) | 200ms | ease-out |
| Тема (toggle) | всі CSS vars через transition on `:root` | 200ms | ease |
| Dropdown/modal | opacity + transform | 200ms | ease-out |
| Toast/notification | slide-in від правого краю | 300ms | ease-out |

Перемикання теми:
```css
*, *::before, *::after {
  transition: background-color 200ms ease, border-color 200ms ease, color 200ms ease;
}
```
(застосовувати лише під час перемикання, знімати після, щоб не уповільнювати інші анімації — через JS-клас `.theme-transitioning` на `<html>`).

---

## 8. Реалізація двох тем — технічна стратегія

### Підхід: CSS Custom Properties + `data-theme` атрибут

**Чому не Tailwind `dark:`?**
Tailwind `dark:` потребує перерахування класу для кожного елемента → дублювання. CSS vars → одне місце для всіх кольорів.

**Уточнення (факт реалізації):** Tailwind у проєкті **не використовується взагалі** — ні для кольорів, ні для spacing/layout. Кожна сторінка має власний `.css`-файл (наприклад `EventsPage.css`, `DictionariesPage.css`) із прямим використанням CSS-змінних (`var(--bg-card)`, `var(--border)` тощо). Це свідоме рішення: для розміру проєкту plain CSS простіший за налаштування Tailwind-пайплайну і не вимагає синхронізації двох систем кольору.

### Зберігання вибору теми

```typescript
// theme.ts
type Theme = 'dark' | 'light';

export function getTheme(): Theme {
  return (localStorage.getItem('theme') as Theme) ?? 'dark'; // дефолт — темна
}

export function setTheme(theme: Theme) {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('theme', theme);
}

// Ініціалізація (до першого рендеру React — в index.html <script>)
// Уникає "flash of wrong theme"
```

```html
<!-- index.html, перед </head> -->
<script>
  const t = localStorage.getItem('theme') || 'dark';
  document.documentElement.setAttribute('data-theme', t);
</script>
```

### React контекст

```tsx
// ThemeContext.tsx
const ThemeContext = createContext<{
  theme: Theme;
  toggle: () => void;
}>(null!);

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState<Theme>(getTheme);

  const toggle = () => {
    const next = theme === 'dark' ? 'light' : 'dark';
    setTheme(next);
    setThemeState(next);
  };

  return (
    <ThemeContext.Provider value={{ theme, toggle }}>
      {children}
    </ThemeContext.Provider>
  );
}
```

Перемикач теми (іконка Sun/Moon) реалізований у `TopBar.jsx`, не в Sidebar — на відміну від оригінальної ASCII-схеми нижче (§9), яка показує заплановане, а не фактичне розміщення.

---

## 9. Специфіка для Horyzont

Адаптація загального дизайну до функціоналу панелі:

| Секція преференсу | Аналог у Horyzont |
|---|---|
| Portfolio (main card) | Остання активність / швидка дія |
| Eth/USDT chart | Графік активності надсилань (по днях) |
| Assets table | Список контактів або груп |
| Type of tokens panel | Деталі вибраної групи (учасники, права) |
| Token detail card | Деталі вибраного повідомлення/контакту |
| Stat badges (+2% vs last week) | Статус доставки, кількість прочитань |

### Навігаційні пункти sidebar (актуальна структура)

```
МЕНЮ (усі ролі)
  🚨  Подія
  💬  Повідомлення        ← активна сторінка
  📋  Контакти

АДМІНІСТРУВАННЯ (лише admin, без секції-лейбла — окремий блок)
  👥  Групи
  🛡️  Користувачі
  📚  Словники
  ⚙️  Налаштування
```

Перемикач теми (Sun/Moon) — **не в Sidebar**, а в `TopBar.jsx` (правий край top bar). Пункти "Дашборд" і "Вигляд" з ранніх версій дизайну в проєкті відсутні — не реалізовувались.

---

## 10. Чекліст перед верстанням

- [x] Підключити `Inter` з Google Fonts або самохостинг
- [x] Встановити `lucide-react`
- [x] Створити `src/styles/theme.css` з усіма CSS vars (§2)
- [x] Додати `<script>` анти-flash в `index.html`
- [x] Реалізувати `ThemeProvider` + `useTheme` хук
- [x] Базові компоненти: `Button`, `Card`, `Badge`, `Input`, `NavItem`
- [x] Layout компоненти: `Sidebar`, `TopBar`, `PageLayout`

Усі пункти реалізовані. Пункт «Tailwind config» з раннього чернетки видалено — Tailwind у проєкті не використовується (див. §8): кожна сторінка має власний `.css`-файл на чистих CSS custom properties.
