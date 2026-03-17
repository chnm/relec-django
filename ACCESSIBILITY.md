# Accessibility Compliance Report

**Standard:** WCAG 2.1 Level AA
**Date:** 2026-03-04
**Method:** Static analysis of HTML templates, CSS, and JavaScript source files
**Scope:** All Django templates, static CSS/JS, admin and public-facing interfaces

> **Note:** Color contrast ratios and runtime behaviors (screen reader compatibility, focus order in dynamic contexts) cannot be fully verified through static analysis alone. Manual testing with WAVE, axe, or NVDA/VoiceOver is required to confirm compliance.

---

## Summary

**Significant accessibility risks detected.**

The project has a number of accessible patterns in place (semantic HTML structure, `lang` attribute, CSRF-protected forms, table headers) but contains critical gaps that would fail WCAG 2.1 Level AA requirements: missing skip-to-content navigation, absent focus indicators on most interactive elements, unlabeled SVG icons, and incomplete ARIA patterns.

---

## 1. Perceivable

### Language Declaration
- **PASS** — `<html lang="en">` is set in `templates/base.html`.

### Semantic HTML Structure
- **PARTIAL** — `<nav>`, `<main>`, `<footer>`, `<header>`, `<article>`, and `<section>` elements are used throughout.
- **Risk:** No `<figure>`/`<figcaption>` wrapping images that have associated captions (e.g., `templates/pages/blog_detail.html`).
- **Risk:** Heading hierarchy is broken in several admin templates — `<h3>` appears without a preceding `<h2>` (e.g., `templates/admin/index.html` line 97).

### Alt Text for Images
- **PARTIAL** — Most content images have descriptive alt text (`templates/pages/index.html`, `templates/pages/blog_list.html`).
- **Risk:** Numerous inline SVG icons across `base.html`, `census/browser.html`, and admin templates lack `aria-label` or an inner `<title>` element. This includes the hamburger menu, dropdown carets, and record status icons.
- **Recommendation:** Add `aria-label` or `aria-hidden="true"` (for decorative icons) to all SVG elements.

### Form Labels
- **CRITICAL** — The newsletter email input in `templates/pages/index.html` uses only a placeholder; no `<label>` is associated.
- **Risk:** Mobile menu and filter toggle buttons in `base.html` have no accessible label (`aria-label` missing).
- **PASS:** Most admin forms use proper Django-rendered `<label>` elements with `for` attributes (e.g., `templates/admin/census/bulk_assign.html`).

### Tables
- **PARTIAL** — Tables use `<thead>` and `<th>` elements (e.g., `templates/pages/index.html`, `templates/analytics/table.html`, `templates/admin/census/missing_county_analysis.html`).
- **Risk:** No `<th>` elements include `scope="col"` or `scope="row"` attributes, required for complex tables (WCAG 1.3.1).

### Color and Non-Text Contrast
- **Needs Verification** — Cannot be confirmed programmatically. Potential concerns:
  - Status badges in `templates/admin/index.html` use color alone to convey state (unassigned, assigned, in_progress, etc.), violating WCAG 1.4.1 (Use of Color).
  - Light background/text combinations in `static/css/custom_unfold.css` (e.g., `#eff6ff` backgrounds) need contrast checking.
  - Warning boxes in `templates/admin/census/missing_county_analysis.html` combine yellow backgrounds with orange text — likely below 4.5:1.
- **Recommendation:** Run all color pairs through [WebAIM Contrast Checker](https://webaim.org/resources/contrastchecker/). Add text labels or icons to status badges to supplement color.

### Emoji as Indicators
- **Risk:** `templates/admin/census/missing_county_analysis.html` uses emoji (📊, 🚨, ⚠️, 📍, 📝) as section labels without text alternatives.
- **Recommendation:** Wrap emoji in `<span aria-hidden="true">` and follow with visible text, or use `aria-label` on the containing element.

### Captions / Transcripts
- **N/A** — No audio or video media identified.

### Responsive Layout
- **PASS** — Tailwind responsive classes (`md:hidden`, etc.) indicate a mobile-first layout approach. No obvious responsive issues detected in static analysis.

---

## 2. Operable

### Skip-to-Content Link
- **CRITICAL** — No skip navigation link is present in any template. `static/js/app.js` contains a partial attempt that never renders a visible link.
- **Recommendation:** Add as the first element inside `<body>` in `templates/base.html`:
  ```html
  <a href="#main-content" class="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-50 focus:bg-white focus:text-blue-700 focus:p-2 focus:rounded">
    Skip to main content
  </a>
  ```
  And ensure `<main>` has `id="main-content"`.

### Keyboard Navigation
- **PARTIAL** — Standard HTML form controls and links are keyboard-accessible by default.
- **Risk:** The filter toggle in `templates/census/browser.html` handles `click` events only; keyboard activation (Enter/Space) is not explicitly tested.
- **Risk:** Mobile menu toggle in `base.html` lacks focus management — when the menu opens, focus does not move into it; when it closes, focus does not return to the trigger.

### Focus Management
- **CRITICAL** — No visible focus indicators are defined for most interactive elements. Navigation links, buttons, and anchors rely on `:hover` Tailwind classes only.
- **PASS:** Admin form inputs in `static/css/custom_unfold.css` do have a visible `:focus` ring (blue outline, `box-shadow`).
- **Recommendation:** Add a global focus rule to `static/css/custom_unfold.css` or the base stylesheet:
  ```css
  a:focus-visible, button:focus-visible, input:focus-visible, select:focus-visible, textarea:focus-visible {
    outline: 3px solid #0060b1;
    outline-offset: 2px;
  }
  ```

### No Keyboard Traps
- **Assumption:** No modal dialogs identified that would trap focus. Admin bulk-assign interface does not appear to use a focus-trapping overlay.

### Accessible Modals / Dropdowns
- **N/A / Risk** — No explicit modal dialogs found. The dropdown/mobile menu in `base.html` lacks `aria-expanded` state on its trigger and does not implement a focus trap during open state.

---

## 3. Understandable

### Language Declaration
- **PASS** — `lang="en"` on `<html>` (see Perceivable above).

### Consistent Navigation
- **PASS** — Navigation structure is consistent across page templates via `base.html` inheritance.

### Form Validation and Error Messages
- **PARTIAL** — Django renders server-side form errors, but no error templates with `aria-live` or `aria-describedby` were identified that associate error messages with specific inputs.
- **Risk:** The analytics query builder (`templates/analytics/query_builder.html`) uses a tab interface but the tab buttons lack `role="tab"`, `aria-selected`, and `aria-controls` attributes; tab panels lack `role="tabpanel"` and `aria-labelledby`. This breaks the ARIA tab pattern.
- **PASS:** CSRF-protected forms enable accessible error re-rendering through standard Django form validation.

### Required Field Indication
- **Risk:** Required fields use the HTML `required` attribute (e.g., newsletter form) but no visible textual indicator (e.g., asterisk with legend) is present for screen reader users who may not receive the browser's native required announcement in all contexts.

---

## 4. Robust

### Valid Semantic Markup
- **Assumption:** Django template inheritance and standard HTML output is structurally valid; no raw validation performed.

### ARIA Usage
- **Risk:** The tab pattern in `templates/analytics/query_builder.html` has `role="tablist"` on the `<nav>` but tab items lack `role="tab"`, `aria-selected`, and `aria-controls`. This is an incomplete and potentially misleading ARIA pattern.
- **Risk:** ARIA usage is sparse overall — not a misuse problem so much as an absence problem.
- **PASS:** `aria-expanded` is used correctly for the filter toggle in `templates/census/browser.html`.

### Screen Reader Compatibility
- **Assumption (cannot verify statically):** Standard Django-rendered HTML should be compatible with screen readers. Custom JavaScript interactions (filter toggle, cascading selects) need manual testing.

### HTMX / Dynamic Content
- **Risk:** No `aria-live` regions are defined for sections that receive dynamic content updates (query results, filter counts, census browser results). Screen reader users will not be notified of content changes.
- **Recommendation:** Add `aria-live="polite"` and `aria-atomic="true"` to result-count and filter-result sections.

### Data Visualizations
- **Risk:** Observable Plot charts in `static/viz/` generate SVG output without accessible figure wrappers, descriptive text summaries, or data table alternatives.
- **Risk:** Chart.js canvas elements in `templates/admin/index.html` have no text alternative.
- **Recommendation:** Wrap each visualization in `<figure>` with a `<figcaption>` describing the key finding, and provide a summary data table (can be visually hidden but available to screen readers).

### Progressive Enhancement
- **Partial** — The site uses server-rendered Django templates as a baseline. JavaScript enhances filtering and visualization. Core content is accessible without JS.

---

## Priority Remediation Checklist

### Critical (pre-launch blockers)
- [ ] Add skip-to-content link in `templates/base.html`
- [ ] Add global `:focus-visible` styles for all interactive elements
- [ ] Label all SVG icons with `aria-label` or `aria-hidden="true"` (decorative)
- [ ] Associate the newsletter form email input with a `<label>`
- [ ] Add text labels to color-only status badges in admin dashboard

### High
- [ ] Add `scope="col"` / `scope="row"` to all `<th>` elements
- [ ] Replace emoji-only indicators with labeled alternatives
- [ ] Implement complete ARIA tab pattern in `templates/analytics/query_builder.html`
- [ ] Add `aria-label` to mobile menu and filter toggle buttons (with open/close state)

### Medium
- [ ] Add `aria-live="polite"` to dynamic result regions
- [ ] Provide data table or text summary alternative for all charts and visualizations
- [ ] Fix heading hierarchy in admin templates
- [ ] Implement focus management for mobile menu (trap and restore focus)
- [ ] Verify color contrast for all text/background pairs with WebAIM Contrast Checker

### Ongoing
- [ ] Integrate automated accessibility scanning (axe, WAVE, or Lighthouse) into development workflow
- [ ] Manual testing with NVDA (Windows), JAWS (Windows), and VoiceOver (macOS/iOS)
- [ ] User testing with individuals who use assistive technologies

---

## Tools for Verification

- [WAVE Browser Extension](https://wave.webaim.org/extension/) — visual overlay of errors
- [axe DevTools](https://www.deque.com/axe/devtools/) — Chrome/Firefox extension
- [WebAIM Contrast Checker](https://webaim.org/resources/contrastchecker/) — color contrast
- [Lighthouse](https://developer.chrome.com/docs/lighthouse/accessibility/) — automated audit in Chrome DevTools
- [NVDA screen reader](https://www.nvaccess.org/) (Windows, free) — functional testing
- [VoiceOver](https://support.apple.com/guide/voiceover/) (macOS/iOS, built-in) — functional testing
