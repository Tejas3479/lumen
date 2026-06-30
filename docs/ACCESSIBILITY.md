# Lumen — Accessibility

## Compliance Target

Lumen targets **WCAG 2.1 Level AA** compliance. This standard is the baseline for most government and civic technology accessibility requirements in India and internationally.

Key WCAG 2.1 AA principles applied: **Perceivable**, **Operable**, **Understandable**, **Robust** (POUR framework).

---

## Voice Input (Web Speech API)

### Implementation

The report form description field supports voice dictation using the Web Speech API:

```typescript
const recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
recognition.lang = 'en-IN';         // Indian English accent
recognition.continuous = false;      // Captures a single utterance
recognition.interimResults = true;   // Shows partial results while speaking

recognition.onresult = (event) => {
  const transcript = Array.from(event.results)
    .map(r => r[0].transcript)
    .join('');
  setDescription(transcript);
};
```

### UX Pattern

- A microphone icon button (`🎤`) appears adjacent to the description textarea.
- On tap, button pulses with a recording animation and `aria-label="Stop recording"`.
- Partial transcript shown in textarea in real-time (interim results).
- On silence or tap-to-stop, transcript finalised in field.
- Fallback: if Web Speech API is not available (`!window.SpeechRecognition`), the microphone button is hidden without error.

### Language

`lang="en-IN"` optimises recognition for Indian English accent. This is the most widely understood recognition language for the target user base. Regional language support (Hindi, Marathi, Tamil) is planned — see `FUTURE_SCOPE.md §1.2`.

---

## High Contrast Mode

### CSS Class Approach

High contrast is applied by toggling a `.high-contrast` class on `<body>`:

```css
/* Default theme */
:root {
  --color-bg: #0f172a;
  --color-text: #f1f5f9;
  --color-primary: #3b82f6;
  --color-secondary: #64748b;
}

/* High contrast override */
body.high-contrast {
  --color-bg: #000000;
  --color-text: #ffffff;
  --color-primary: #ffff00;     /* High-visibility yellow */
  --color-secondary: #ffffff;
  --color-border: #ffffff;
  --shadow: none;               /* Remove decorative shadows */
  filter: none;                 /* Remove tint filters */
}

body.high-contrast a,
body.high-contrast button {
  text-decoration: underline;   /* Links always underlined */
  outline: 2px solid #ffff00;
}
```

### Persistence

High contrast preference is stored in `localStorage.setItem('a11y.highContrast', 'true')` and applied on page load before first render to prevent a flash of normal contrast.

### Toggle Location

Accessible via the Settings panel (`/settings` route) and via the keyboard shortcut `Alt+Shift+H`.

---

## Font Size Control

Four font size levels applied via body class:

| Level | Class | Body Font Size | Use Case |
|-------|-------|---------------|----------|
| Small | `font-sm` | 14px | Dense information, power users |
| Normal (default) | — | 16px | Standard |
| Large | `font-lg` | 18px | Low vision, comfort reading |
| Extra Large | `font-xl` | 22px | Significant visual impairment |

```css
body.font-lg  { font-size: 18px; }
body.font-xl  { font-size: 22px; }
```

All spacing, padding, and line heights use `em` units relative to `font-size`, so the entire UI scales proportionally when font size changes.

Preference stored in `localStorage.setItem('a11y.fontSize', 'lg')`.

---

## Color-Blind Safety

Map markers use **three combined signals** — color + shape + category emoji — so no information is conveyed by color alone (WCAG Success Criterion 1.4.1). Each status maps to a distinct shape and color:

| Status | Color | Shape | Text Label |
|---|---|---|---|
| `reported` | Gray (#718096) | Square | "Reported" |
| `verified` | Blue (#3182CE) | Circle | "Verified" |
| `assigned` | Purple (#805AD5) | Diamond | "Assigned" |
| `in_progress` | Amber (#D69E2E) | Triangle | "In Progress" |
| `resolved` | Green (#38A169) | Star | "Resolved" |
| `disputed` | Red (#E53E3E) | Cross | "Disputed" |
| `closed` | Dark Slate (#2D3748) | Square | "Closed" |

### Center Emoji Markers
Each shape marker embeds a category emoji in its center to differentiate types of issues:
- Pothole: 🕳️
- Water Leakage: 💧
- Streetlight: 💡
- Garbage: 🗑️
- Drainage: 🌊
- Road Damage: 🚧
- Tree Hazard: 🌳
- Vandalism: ✏️
- Noise: 🔊
- Other: ⚠️

### Severity Representation
Severity levels are communicated textually using high-contrast colored background pills in the issue detail panels:
* **Low**: Green pill
* **Medium**: Amber pill
* **High**: Orange pill
* **Critical**: Red pill

Color palette is verified against Deuteranopia (red-green), Protanopia (red-green), and Tritanopia (blue-yellow) using browser devtools color simulation.

---

## Screen Reader: ARIA Roles, Live Regions, and Landmark IDs

### Landmark Regions

```html
<a href="#main-content" class="skip-to-content">Skip to main content</a>

<header role="banner" id="site-header">...</header>

<nav role="navigation" aria-label="Primary navigation" id="main-nav">...</nav>

<main role="main" id="main-content">
  <section aria-label="Community issue map" id="issue-map">...</section>
</main>

<footer role="contentinfo" id="site-footer">...</footer>
```

### ARIA Live Regions

Real-time updates are announced to screen readers via live regions:

```html
<!-- Status update announcements -->
<div aria-live="polite" aria-atomic="true" id="status-announcer" class="sr-only">
  <!-- Content injected by JS: "Issue #1234 status changed to In Progress" -->
</div>

<!-- Emergency alerts -->
<div aria-live="assertive" aria-atomic="true" id="emergency-announcer" class="sr-only">
  <!-- Content injected by JS: "Emergency: Burst water pipe at Main Street" -->
</div>

<!-- Offline sync status -->
<div aria-live="polite" id="offline-status" class="sr-only">
  <!-- "2 reports pending sync" | "Reports synced successfully" -->
</div>
```

### Dialog / Modal

```html
<div role="dialog"
     aria-modal="true"
     aria-labelledby="modal-title"
     aria-describedby="modal-description"
     id="report-issue-modal">
  <h2 id="modal-title">Report an Issue</h2>
  <p id="modal-description">Describe the infrastructure problem you've observed.</p>
  ...
  <button aria-label="Close report dialog">✕</button>
</div>
```

Focus is trapped within the modal while open and returned to the triggering FAB on close.

### Map

```html
<div role="application"
     aria-label="Community issue map"
     aria-describedby="map-description"
     id="issue-map"
     tabindex="0">
  <p id="map-description" class="sr-only">
    Interactive map showing civic issues. Use arrow keys to pan, +/- to zoom.
    Press Enter on a marker to view issue details.
  </p>
</div>
```

Each Leaflet marker has `title` and `alt` attributes set to the issue title and severity:
```
title="Pothole: Large pothole near Kalyani Nagar junction | Severity: High"
```

---

## Keyboard Navigation Paths

| Action | Keyboard Path |
|--------|---------------|
| Open report modal | `Tab` to FAB → `Enter` or `Space` |
| Navigate modal steps | `Tab` forward, `Shift+Tab` backward |
| Select category | `Tab` to category grid → arrow keys → `Enter` |
| Submit form | `Tab` to Submit → `Enter` |
| Close modal | `Escape` |
| Navigate map | `Tab` to map container → arrow keys to pan |
| Open issue from map | `Tab` to marker → `Enter` |
| Navigate issue list | `Tab` through cards |
| Open settings | `Tab` to settings icon → `Enter` |
| Toggle high contrast | `Alt+Shift+H` |

All interactive elements have visible focus indicators (minimum 3px outline, not suppressed by `outline: none`).

---

## Reduced Motion Support

For users with vestibular disorders or motion sensitivity, animations are disabled when `prefers-reduced-motion: reduce` is set:

```css
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }

  /* Map marker bounce → disabled */
  .leaflet-marker-icon.bounce {
    animation: none;
  }

  /* Loading spinner → hidden */
  .loading-spinner {
    display: none;
  }

  /* Notification slide-in → instant show */
  .notification-toast {
    animation: none;
    opacity: 1;
  }
}
```

The user can also manually disable animations in the Settings panel (stored in `localStorage`), which sets `data-reduce-motion="true"` on `<body>` and applies the same CSS class.

---

## Minimum Touch Target Size

All interactive elements meet the WCAG 2.5.5 AAA guideline (and the AA 2.5.8 minimum of 24×24px, with Lumen targeting 44×44px):

```css
/* Minimum touch targets */
button,
a,
input[type="checkbox"],
input[type="radio"],
[role="button"] {
  min-height: 44px;
  min-width: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

/* Icon-only buttons — expand tap area with padding */
.icon-button {
  padding: 10px;   /* 24px icon + 20px padding = 44px total */
}
```

The "Report Issue" FAB is 56×56px (exceeds minimum).

---

## Skip-to-Content Link

```html
<!-- First focusable element in the DOM, visible only on focus -->
<a href="#main-content"
   class="skip-to-content"
   id="skip-link">
  Skip to main content
</a>
```

```css
.skip-to-content {
  position: absolute;
  top: -100%;
  left: 0;
  z-index: 9999;
  padding: 8px 16px;
  background: #1a1a2e;
  color: #fff;
  border: 2px solid #fff;
  border-radius: 4px;
  transition: top 0.1s;
}

.skip-to-content:focus {
  top: 8px;   /* Slides into view on Tab press */
}
```

The skip link is the **first** focusable element in the HTML DOM so keyboard users reach it on the very first `Tab` keypress after page load.

---

## Testing Accessibility

Manual testing tools used:
- **NVDA** (Windows) + Chrome
- **VoiceOver** (macOS/iOS) + Safari
- **axe DevTools** browser extension (automated WCAG audit)
- Chrome DevTools **Colour vision deficiency** simulation (all four types)
- Chrome DevTools **Reduced motion** simulation

Automated E2E accessibility tests in `frontend/tests/e2e/report_flow.spec.ts`:
- Skip link presence and correct `href`
- FAB `aria-label` attribute
- Map `aria-label` attribute
- Modal `role="dialog"` attribute
- Keyboard navigation through report form without mouse
