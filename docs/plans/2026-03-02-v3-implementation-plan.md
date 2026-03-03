# MedPrep v3.0 UI Overhaul — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform MedPrep from a tab-based clinical viewer into a GNOME/Tailwind-styled diagnostic command center with sidebar nav, analytics dashboard, flowing timeline, node-graph visualizations, and health tracker integration.

**Architecture:** Flask SPA with Tailwind CSS (CDN), D3.js visualizations, Three.js body map. Sidebar replaces top tabs. Dashboard becomes analytics hub with embedded chat. All existing analysis engines (Snowball, Cascades, PGx, Trajectories, Symptom Analytics) preserved — their overlays get Tailwind styling but logic unchanged.

**Tech Stack:** Flask, Tailwind CSS (CDN), D3.js (existing), Three.js (existing), Gemini API (existing), Python 3.13

**Design doc:** `docs/plans/2026-03-02-v3-ui-overhaul-design.md`

---

## Build Order

| Phase | Tasks | Dependency |
|-------|-------|-----------|
| **A** | Tailwind setup + GNOME theme | None — foundation |
| **B** | Sidebar navigation | Phase A |
| **C** | Body Map fix | None — independent |
| **D** | Environmental own tab | Phase B (needs sidebar entry) |
| **E** | Dashboard diagnostic command center | Phase B |
| **F** | Chat embedded in Dashboard | Phase E |
| **G** | Cross-Disciplinary node graph | Phase A (Tailwind classes) |
| **H** | Timeline flowing visualization | Phase A + B |
| **I** | Health Tracker integration | Phase B + E |
| **J** | Vitals surfaced | Phase E |
| **K** | Risk score rollup | Phase E + J |

---

## Phase A: Tailwind CSS Setup + GNOME Theme

### Task A1: Add Tailwind CSS and define GNOME theme

**Files:**
- Modify: `src/ui/static/index.html` (lines 1-20, head section)
- Create: `src/ui/static/tailwind-config.js` (custom theme tokens)

**Step 1: Add Tailwind CDN to index.html head**

In `index.html`, add before the existing `<link rel="stylesheet" href="/styles.css">`:

```html
<script src="https://cdn.tailwindcss.com"></script>
<script src="/tailwind-config.js"></script>
```

**Step 2: Create Tailwind config with MedPrep tokens**

Create `src/ui/static/tailwind-config.js`:

```javascript
tailwind.config = {
    darkMode: 'class',
    theme: {
        extend: {
            colors: {
                // GNOME Adwaita-inspired dark palette
                surface: {
                    DEFAULT: '#0a0a0a',
                    secondary: '#141414',
                    card: '#171717',
                    raised: '#1f1f1f',
                },
                border: {
                    faint: '#2a2a2a',
                    muted: '#333333',
                    loud: '#404040',
                },
                // MedPrep accent colors
                heat: '#dc2626',
                amethyst: '#a07aff',
                bluetron: '#5a8ffc',
                crimson: '#f05545',
                forest: '#5cd47f',
                honey: '#f0c550',
                rose: '#e06c8a',
                teal: '#2dd4bf',
            },
            borderRadius: {
                'gnome': '16px',
                'gnome-sm': '12px',
                'gnome-lg': '24px',
            },
            fontFamily: {
                sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
            },
        },
    },
};
```

**Step 3: Add Inter font to index.html head**

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
```

**Step 4: Serve tailwind-config.js from Flask**

The existing catch-all route at `app.py` line 73 (`GET /<filename>`) already serves files from `static/`, so `tailwind-config.js` will be served automatically.

**Step 5: Verify Tailwind loads**

Run the dev server, open browser, inspect an element. Confirm Tailwind utility classes work by temporarily adding `class="bg-red-500 p-4"` to a test div.

**Step 6: Commit**

```bash
git add src/ui/static/index.html src/ui/static/tailwind-config.js
git commit -m "feat: add Tailwind CSS CDN + GNOME theme tokens"
```

---

### Task A2: Create base layout styles bridging old CSS and Tailwind

**Files:**
- Modify: `src/ui/static/styles.css` (preserve existing, add compatibility layer)

**Step 1: Add Tailwind base overrides at top of styles.css**

Add at the very top of `styles.css`, before the `:root` block:

```css
/* ── Tailwind Compatibility Layer ─────────────────── */
/* Tailwind's preflight resets some styles we need.
   These ensure smooth coexistence during migration. */
@layer base {
    body {
        @apply bg-surface text-gray-100 font-sans;
    }
}
```

Note: With CDN Tailwind, `@apply` won't work in CSS files. Instead, keep the existing `:root` variables and gradually replace class-by-class. The old CSS stays operational while new components use Tailwind classes.

**Step 2: Commit**

```bash
git add src/ui/static/styles.css
git commit -m "feat: add Tailwind compatibility notes to styles.css"
```

---

## Phase B: Sidebar Navigation

### Task B1: Replace top tab bar with sidebar HTML

**Files:**
- Modify: `src/ui/static/index.html` (lines 44-69 nav section, entire layout wrapper)

**Step 1: Replace the nav and layout structure**

Replace the existing `<nav>` block (lines 44-69) and wrap the main content. The new structure:

```html
<!-- Sidebar -->
<nav id="sidebar" class="fixed left-0 top-0 h-screen w-56 bg-surface-secondary border-r border-border-faint flex flex-col z-50 transition-all duration-200" style="display:none;">
    <!-- Brand -->
    <div class="px-4 py-5 border-b border-border-faint">
        <div class="text-lg font-semibold text-white tracking-tight">Clinical Intelligence Hub</div>
    </div>

    <!-- Nav items -->
    <div class="flex-1 overflow-y-auto py-3 space-y-1 px-2">
        <button class="sidebar-item active" data-view="dashboard">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-4 0a1 1 0 01-1-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 01-1 1"/></svg>
            <span class="sidebar-label">Dashboard</span>
        </button>
        <button class="sidebar-item" data-view="bodymap">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"/></svg>
            <span class="sidebar-label">Body Map</span>
        </button>
        <button class="sidebar-item" data-view="timeline">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M13 17h8m0 0V9m0 8l-8-8-4 4-6-6"/></svg>
            <span class="sidebar-label">Timeline</span>
        </button>
        <button class="sidebar-item" data-view="medications">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M19.5 12c0-1.232-.046-2.453-.138-3.662a4.006 4.006 0 00-3.7-3.7 48.678 48.678 0 00-7.324 0 4.006 4.006 0 00-3.7 3.7c-.017.22-.032.441-.046.662M19.5 12l3-3m-3 3l-3-3m-12 3c0 1.232.046 2.453.138 3.662a4.006 4.006 0 003.7 3.7 48.656 48.656 0 007.324 0 4.006 4.006 0 003.7-3.7c.017-.22.032-.441.046-.662M4.5 12l3 3m-3-3l-3 3"/></svg>
            <span class="sidebar-label">Medications</span>
        </button>
        <button class="sidebar-item" data-view="labs">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714a2.25 2.25 0 00.659 1.591L19 14.5M14.25 3.104c.251.023.501.05.75.082M19 14.5l-2.47 4.532a2.25 2.25 0 01-1.99 1.2H9.46a2.25 2.25 0 01-1.99-1.2L5 14.5"/></svg>
            <span class="sidebar-label">Labs</span>
        </button>
        <button class="sidebar-item" data-view="imaging">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M6.827 6.175A2.31 2.31 0 015.186 7.23c-.38.054-.757.112-1.134.175C2.999 7.58 2.25 8.507 2.25 9.574V18a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9.574c0-1.067-.75-1.994-1.802-2.169a47.865 47.865 0 00-1.134-.175 2.31 2.31 0 01-1.64-1.055l-.822-1.316a2.192 2.192 0 00-1.736-1.039 48.774 48.774 0 00-5.232 0 2.192 2.192 0 00-1.736 1.039l-.821 1.316z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M16.5 12.75a4.5 4.5 0 11-9 0 4.5 4.5 0 019 0z"/></svg>
            <span class="sidebar-label">Imaging</span>
        </button>
        <button class="sidebar-item" data-view="symptoms">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M21 8.25c0-2.485-2.099-4.5-4.688-4.5-1.935 0-3.597 1.126-4.312 2.733-.715-1.607-2.377-2.733-4.313-2.733C5.1 3.75 3 5.765 3 8.25c0 7.22 9 12 9 12s9-4.78 9-12z"/></svg>
            <span class="sidebar-label">Symptoms</span>
        </button>
        <button class="sidebar-item" data-view="environmental">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 017.843 4.582M12 3a8.997 8.997 0 00-7.843 4.582"/></svg>
            <span class="sidebar-label">Environment</span>
        </button>
        <button class="sidebar-item" data-view="tracker">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
            <span class="sidebar-label">Health Tracker</span>
        </button>
        <button class="sidebar-item" data-view="flags">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126z"/></svg>
            <span class="sidebar-label">Flags</span>
        </button>
        <button class="sidebar-item" data-view="alerts">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0"/></svg>
            <span class="sidebar-label">Alerts</span>
        </button>
        <button class="sidebar-item" data-view="report">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"/></svg>
            <span class="sidebar-label">Report</span>
        </button>
    </div>

    <!-- Collapse toggle -->
    <div class="px-2 py-3 border-t border-border-faint">
        <button id="sidebar-collapse-btn" class="sidebar-item w-full" onclick="App.toggleSidebar();">
            <svg class="w-5 h-5 transition-transform" id="sidebar-collapse-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M18.75 19.5l-7.5-7.5 7.5-7.5m-6 15L5.25 12l7.5-7.5"/></svg>
            <span class="sidebar-label">Collapse</span>
        </button>
    </div>

    <!-- Settings at bottom -->
    <div class="px-2 py-3 border-t border-border-faint">
        <button class="sidebar-item w-full" onclick="App.showSettings();">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
            <span class="sidebar-label">Settings</span>
        </button>
    </div>
</nav>

<!-- Main content area (shifts right when sidebar open) -->
<main id="main-content" class="ml-56 transition-all duration-200 min-h-screen p-6">
```

**Step 2: Add sidebar CSS to styles.css**

```css
/* ── Sidebar Navigation ───────────────────────────── */
.sidebar-item {
    display: flex;
    align-items: center;
    gap: 12px;
    width: 100%;
    padding: 10px 12px;
    border-radius: 12px;
    color: rgba(255,255,255,0.56);
    background: transparent;
    border: none;
    cursor: pointer;
    font-size: 14px;
    font-weight: 400;
    transition: all 0.15s ease;
    text-align: left;
}
.sidebar-item:hover {
    background: rgba(255,255,255,0.06);
    color: rgba(255,255,255,0.9);
}
.sidebar-item.active {
    background: rgba(220,38,38,0.12);
    color: #dc2626;
    font-weight: 500;
}
/* Collapsed sidebar */
#sidebar.collapsed {
    width: 60px;
}
#sidebar.collapsed .sidebar-label {
    display: none;
}
#sidebar.collapsed + #main-content {
    margin-left: 60px;
}
```

**Step 3: Update App.navigateTo to use sidebar items**

In `app.js`, update `init()` to bind sidebar buttons instead of nav tabs:

```javascript
// Replace tab binding (around line 90-100)
var sidebarItems = document.querySelectorAll(".sidebar-item[data-view]");
for (var i = 0; i < sidebarItems.length; i++) {
    (function(item) {
        item.addEventListener("click", function() {
            App.navigateTo(item.dataset.view);
        });
    })(sidebarItems[i]);
}
```

Update `navigateTo` (around line 154) to set active on sidebar items instead of nav tabs:

```javascript
// Update active sidebar item
var items = document.querySelectorAll(".sidebar-item[data-view]");
for (var i = 0; i < items.length; i++) {
    items[i].classList.toggle("active", items[i].dataset.view === view);
}
```

**Step 4: Add toggleSidebar method to App**

```javascript
toggleSidebar: function() {
    var sidebar = document.getElementById("sidebar");
    var icon = document.getElementById("sidebar-collapse-icon");
    sidebar.classList.toggle("collapsed");
    if (sidebar.classList.contains("collapsed")) {
        icon.style.transform = "rotate(180deg)";
    } else {
        icon.style.transform = "";
    }
},
```

**Step 5: Add new views to loaders map**

In `app.js` `navigateTo` loaders map (line 174), add:

```javascript
environmental: function() { App.loadEnvironmental(); },
tracker: function() { App.loadTracker(); },
```

**Step 6: Update sidebar show/hide with vault unlock**

The current code shows `main-nav` after unlock. Change to show `sidebar`:

```javascript
// In unlock() success handler and init():
document.getElementById("sidebar").style.display = "flex";
```

**Step 7: Move all view divs inside the new main content wrapper**

All existing `<div id="view-*" class="view">` elements must be children of `<main id="main-content">`.

**Step 8: Verify navigation works**

Run dev server, unlock vault, click each sidebar item. Confirm view switches work.

**Step 9: Commit**

```bash
git add src/ui/static/index.html src/ui/static/styles.css src/ui/static/app.js
git commit -m "feat: replace top tabs with collapsible sidebar navigation"
```

---

## Phase C: Body Map Fix

### Task C1: Make 3D model load without patient data

**Files:**
- Modify: `src/ui/static/js/bodymap3d.js` (lines 321-334, autoLoadModel)

**Step 1: Write test — verify model loads with no profile**

Create `tests/test_bodymap_loading.py`:

```python
"""Test that body map endpoints work without profile data."""
import pytest
from src.ui.app import app

@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c

def test_demographics_returns_defaults_without_profile(client):
    """Demographics endpoint should return defaults, not error."""
    resp = client.get("/api/demographics")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "biological_sex" in data
```

**Step 2: Run test to verify it passes**

Run: `cd /Users/owner/Desktop/Tech\ Tools/MedPrep && venv/bin/python -m pytest tests/test_bodymap_loading.py -v`

**Step 3: Fix autoLoadModel to be resilient**

In `bodymap3d.js`, modify `autoLoadModel` (line 321) to always load model even if demographics fetch fails:

```javascript
autoLoadModel: function() {
    var self = this;
    fetch("/api/demographics")
        .then(function(r) {
            if (!r.ok) throw new Error("No profile");
            return r.json();
        })
        .then(function(data) {
            var gender = "male";
            if (data && data.biological_sex) {
                var sex = data.biological_sex.toLowerCase();
                if (sex === "female" || sex === "f") gender = "female";
            }
            self.loadModel(gender);
        })
        .catch(function() {
            // Always load male model as default — don't block on missing data
            self.loadModel("male");
        });
},
```

Also check `loadFindings` — it should gracefully handle no data:

```javascript
loadFindings: function() {
    // If no profile, just show clean model with no pins
    var self = this;
    fetch("/api/flags")
        .then(function(r) { return r.json(); })
        .then(function(flags) {
            if (!flags || !flags.length) return;
            self.addPinsFromFlags(flags);
        })
        .catch(function() { /* No data yet — clean model is fine */ });
},
```

**Step 4: Verify — open Body Map tab without unlocking vault**

The 3D model should render a clean anatomy model with no pins or deformations.

**Step 5: Commit**

```bash
git add src/ui/static/js/bodymap3d.js tests/test_bodymap_loading.py
git commit -m "fix: 3D body map loads without patient data"
```

---

## Phase D: Environmental Own Tab

### Task D1: Create Environmental view in HTML

**Files:**
- Modify: `src/ui/static/index.html` (add new view div)
- Modify: `src/ui/static/app.js` (add loadEnvironmental method)

**Step 1: Add Environmental view HTML**

Add a new view div in `index.html` (after the existing views):

```html
<!-- ── Environmental Health Risks ─────────────────── -->
<div id="view-environmental" class="view">
    <div class="card">
        <div class="flex items-center justify-between mb-4">
            <div class="card-title">Environmental Health Risks</div>
            <div id="env-location-badge" class="text-sm text-teal"></div>
        </div>
        <div id="env-personalized" class="mb-6">
            <div class="text-sm font-medium text-heat mb-2">Personalized to Your Health Profile</div>
            <div id="env-personalized-list"></div>
        </div>
        <div id="env-regional">
            <div class="text-sm font-medium text-gray-400 mb-2">Regional Awareness</div>
            <div id="env-regional-list"></div>
        </div>
        <div id="env-empty" style="display:none;" class="text-center py-12 text-gray-500">
            Set your location in Settings to see environmental health risks for your area.
        </div>
    </div>
</div>
```

**Step 2: Add loadEnvironmental to app.js**

```javascript
loadEnvironmental: async function() {
    try {
        var data = await api("/api/environmental");
        var locBadge = $("env-location-badge");
        var personalizedList = $("env-personalized-list");
        var regionalList = $("env-regional-list");
        var emptyState = $("env-empty");

        // Clear
        while (personalizedList.firstChild) personalizedList.removeChild(personalizedList.firstChild);
        while (regionalList.firstChild) regionalList.removeChild(regionalList.firstChild);

        if (!data || !data.risks || !data.risks.length) {
            emptyState.style.display = "block";
            return;
        }
        emptyState.style.display = "none";

        if (data.location) {
            locBadge.textContent = data.location;
        }

        var risks = data.risks;
        for (var i = 0; i < risks.length; i++) {
            var risk = risks[i];
            var card = document.createElement("div");
            card.className = "bg-surface-raised rounded-gnome-sm p-4 mb-3 border-l-3";
            card.style.borderLeftColor = risk.personalized ? "var(--heat)" : "var(--border-muted)";

            var title = document.createElement("div");
            title.className = "font-medium text-white mb-1";
            title.textContent = risk.name;
            card.appendChild(title);

            var desc = document.createElement("div");
            desc.className = "text-sm text-gray-400 mb-2";
            desc.textContent = risk.description;
            card.appendChild(desc);

            if (risk.action) {
                var action = document.createElement("div");
                action.className = "text-sm text-teal";
                action.textContent = risk.action;
                card.appendChild(action);
            }

            if (risk.personalized) {
                personalizedList.appendChild(card);
            } else {
                regionalList.appendChild(card);
            }
        }
    } catch (e) {
        $("env-empty").style.display = "block";
    }
},
```

**Step 3: Verify — navigate to Environmental tab**

Confirm risks render with personalized vs regional sections.

**Step 4: Commit**

```bash
git add src/ui/static/index.html src/ui/static/app.js
git commit -m "feat: environmental health risks as dedicated nav tab"
```

---

## Phase E: Dashboard Diagnostic Command Center

### Task E1: Build dashboard HTML grid structure

**Files:**
- Modify: `src/ui/static/index.html` (replace current dashboard view)

**Step 1: Replace dashboard view with analytics grid**

Replace the existing `<div id="view-dashboard">` content with a comprehensive widget grid. This is the largest single HTML change.

Key sections:
- Top bar: AI narrative + risk score + visit prep readiness
- Grid row 1: Blood panel overview, Lab trend sparklines
- Grid row 2: Medication safety, Overdue tests, Active conditions
- Grid row 3: Symptom-med correlation, Snowball preview, Flags count
- Grid row 4: Health tracker widgets, Vitals, Cross-specialty alerts
- Grid row 5: Recent PubMed findings
- Right dock: Chat panel (collapsible)

Each widget is a `<div class="bg-surface-card rounded-gnome p-5 border border-border-faint">` card.

**Step 2: Commit skeleton**

```bash
git commit -m "feat: dashboard diagnostic command center HTML skeleton"
```

### Task E2: Build dashboard API endpoint

**Files:**
- Modify: `src/ui/app.py` (add dashboard aggregate endpoint)

**Step 1: Create aggregated dashboard endpoint**

```python
@app.route("/api/dashboard")
def get_dashboard():
    """Aggregate all data needed for the diagnostic dashboard."""
    if not _profile_data:
        return jsonify({"has_data": False})

    clinical = _profile_data.get("clinical_timeline", {})
    analysis = _profile_data.get("analysis", {})

    # Latest labs with flags
    labs = clinical.get("labs", [])
    latest_labs = _get_latest_labs(labs)

    # Labs with 3+ data points for sparklines
    lab_trends = _get_lab_trends(labs)

    # Active medications
    meds = [m for m in clinical.get("medications", []) if m.get("status") != "discontinued"]

    # Active diagnoses
    diagnoses = clinical.get("diagnoses", [])

    # Flags summary
    flags = _get_all_flags()

    # Missing negatives count
    missing = [f for f in flags if f.get("category") == "Monitoring Gap"]

    # PGx collision count
    pgx_alerts = analysis.get("drug_gene_interactions", [])

    # Cross-specialty count
    cross_spec_count = len(analysis.get("cross_disciplinary", []))

    return jsonify({
        "has_data": True,
        "latest_labs": latest_labs,
        "lab_trends": lab_trends,
        "active_medications": len(meds),
        "diagnoses_count": len(diagnoses),
        "flags_count": len(flags),
        "missing_tests": missing,
        "pgx_collisions": len(pgx_alerts),
        "cross_specialty_count": cross_spec_count,
        "visit_prep_items": _count_visit_prep_items(),
    })
```

**Step 2: Commit**

```bash
git commit -m "feat: aggregated dashboard API endpoint"
```

### Task E3: Build dashboard JavaScript rendering

**Files:**
- Modify: `src/ui/static/app.js` (rewrite loadDashboard)

Rewrite `loadDashboard()` to fetch from `/api/dashboard` and populate all widgets. Each widget uses createElement/textContent for DOM safety. D3 sparklines for lab trends.

**Step 3: Commit**

```bash
git commit -m "feat: dashboard JavaScript rendering with analytics widgets"
```

### Task E4: Add D3 sparkline component

**Files:**
- Create: `src/ui/static/js/sparklines.js`

Small reusable D3 component: `Sparkline.render(containerId, dataPoints, options)` — renders a mini SVG line chart with optional reference range band.

**Step 4: Commit**

```bash
git commit -m "feat: D3 sparkline component for dashboard trends"
```

---

## Phase F: Chat Embedded in Dashboard

### Task F1: Move chat HTML into dashboard, remove Chat tab

**Files:**
- Modify: `src/ui/static/index.html` (move chat markup into dashboard, delete view-chat)
- Modify: `src/ui/static/app.js` (update sendChat to target new container)

**Step 1: Add collapsible chat panel to dashboard**

Add inside the dashboard view, docked right:

```html
<div id="dashboard-chat" class="fixed right-0 top-0 h-screen w-80 bg-surface-card border-l border-border-faint flex flex-col z-40 transition-transform duration-200">
    <div class="p-4 border-b border-border-faint flex justify-between items-center">
        <span class="font-medium text-white">Clinical Assistant</span>
        <button onclick="App.toggleDashboardChat();" class="text-gray-400 hover:text-white">&times;</button>
    </div>
    <div class="flex-1 overflow-y-auto p-4" id="dashboard-chat-messages">
        <!-- Chat messages render here -->
    </div>
    <div class="p-4 border-t border-border-faint">
        <div class="flex gap-2">
            <input id="dashboard-chat-input" type="text" class="flex-1 bg-surface-raised border border-border-muted rounded-gnome-sm px-3 py-2 text-white text-sm" placeholder="Ask about your records..." onkeydown="if(event.key==='Enter')App.sendChat();">
            <button class="bg-heat text-white px-4 py-2 rounded-gnome-sm text-sm font-medium" onclick="App.sendChat();">Send</button>
        </div>
    </div>
</div>
```

**Step 2: Delete the old `view-chat` div from index.html**

**Step 3: Update sendChat to use new container IDs**

**Step 4: Add chat toggle button to dashboard top bar**

**Step 5: Remove "chat" from sidebar nav (already excluded in Phase B)**

**Step 6: Commit**

```bash
git commit -m "feat: embed chat panel in dashboard, remove standalone chat tab"
```

---

## Phase G: Cross-Disciplinary Node Graph

### Task G1: Create cross-disciplinary D3 force graph

**Files:**
- Create: `src/ui/static/js/crossdisc_graph.js`
- Modify: `src/ui/static/index.html` (update crossdisc view)
- Modify: `src/ui/static/app.js` (update loadCrossDisciplinary)

**Step 1: Build CrossDiscGraph module**

Follow the same pattern as `snowball.js` — D3 force-directed graph:

- Nodes = detected systemic patterns (circle, colored by specialty category)
- Node size = number of matched patient data points
- Edges = shared findings between conditions (dashed lines)
- Click node → detail panel: severity badge, matched findings, specialties, question for doctor
- Legend: specialty color mapping
- Partnership messaging at bottom

**Step 2: Update loadCrossDisciplinary to call CrossDiscGraph.render()**

Transform the API response into nodes + edges format, pass to D3.

**Step 3: Verify with demo data**

Load demo vault, navigate to Cross-Disciplinary, confirm node graph renders with clickable detail.

**Step 4: Commit**

```bash
git commit -m "feat: cross-disciplinary node graph visualization (Snowball-style)"
```

---

## Phase H: Timeline Flowing Visualization

### Task H1: Create timeline D3 module

**Files:**
- Create: `src/ui/static/js/timeline_flow.js`
- Modify: `src/ui/static/index.html` (update view-timeline)
- Modify: `src/ui/static/app.js` (update Timeline object)

**Step 1: Build TimelineFlow module**

Core D3 visualization:

```javascript
var TimelineFlow = {
    svg: null,
    zoomBehavior: null,
    currentLevel: 1,  // 1=5yr, 2=1yr, 3=monthly, 4=individual
    events: [],

    init: function(containerId) { /* Set up SVG, zoom, pan */ },
    load: async function() { /* Fetch /api/timeline, classify events, render */ },
    render: function() { /* Draw nodes, flowing curves, labels at current zoom */ },
    zoomTo: function(level) { /* Semantic zoom transition */ },
    expandDetail: function(date) { /* Show detail panel below */ },
    classifyEvent: function(event) { /* major vs minor by type */ },
    drawFlowingCurves: function(nodes) { /* Bezier paths between nodes */ },
};
```

**Step 2: Implement semantic zoom levels**

- Level 1: Group events into 5-year buckets. Show only major nodes. Large labels.
- Level 2: Group into years. Major + notable. Year labels.
- Level 3: Group into months. All events. Month labels.
- Level 4: Individual events. Full detail.

Use `d3.zoom()` with `on("zoom", ...)` to detect scale changes and transition between levels.

**Step 3: Implement flowing bezier curves**

Draw SVG paths connecting nodes with cubic bezier curves. Animate with CSS `stroke-dashoffset` for the thrivo.ai flowing effect.

```javascript
drawFlowingCurves: function(nodes) {
    // For each pair of adjacent nodes, draw a bezier curve
    var pathData = "M " + nodes[0].x + " " + nodes[0].y;
    for (var i = 1; i < nodes.length; i++) {
        var prev = nodes[i-1];
        var curr = nodes[i];
        var midX = (prev.x + curr.x) / 2;
        // Offset control points vertically for wave effect
        var offsetY = (i % 2 === 0) ? -30 : 30;
        pathData += " C " + midX + " " + (prev.y + offsetY) +
                    ", " + midX + " " + (curr.y - offsetY) +
                    ", " + curr.x + " " + curr.y;
    }
    // Render as animated SVG path
}
```

**Step 4: Implement expanding detail panel**

On node click, slide open an HTML div below the SVG showing all records from that date. Uses createElement/textContent.

**Step 5: Implement empty state**

When no events, show the flowing path with placeholder text.

**Step 6: Verify with demo data**

30 years of data → confirm 5-year blocks at default zoom, drill into individual events.

**Step 7: Commit**

```bash
git commit -m "feat: flowing interactive timeline visualization with semantic zoom"
```

---

## Phase I: Health Tracker Integration

### Task I1: Create tracker adapter base + Fitbit adapter

**Files:**
- Create: `src/trackers/__init__.py`
- Create: `src/trackers/base.py`
- Create: `src/trackers/fitbit_adapter.py`
- Create: `src/trackers/apple_health.py`
- Create: `tests/test_trackers.py`

**Step 1: Write base adapter interface**

```python
"""Base health tracker adapter."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Optional

@dataclass
class TrackerDataPoint:
    date: date
    metric: str  # "heart_rate", "steps", "sleep_duration", "spo2", etc.
    value: float
    unit: str
    source: str  # "fitbit", "apple_health", etc.

class BaseTrackerAdapter(ABC):
    @abstractmethod
    def import_data(self, source_path: str) -> list[TrackerDataPoint]:
        """Import data from file/API and return normalized data points."""
        ...

    @abstractmethod
    def supported_metrics(self) -> list[str]:
        """Return list of metrics this adapter can provide."""
        ...
```

**Step 2: Implement Fitbit adapter (JSON export)**

Parse Fitbit data export JSON files for heart rate, steps, sleep, SpO2.

**Step 3: Implement Apple Health adapter (XML export)**

Parse Apple Health export.xml for heart rate, steps, sleep, SpO2, workouts.

**Step 4: Write tests for both adapters**

**Step 5: Commit**

```bash
git commit -m "feat: health tracker adapter framework + Fitbit + Apple Health"
```

### Task I2: Create tracker API endpoints + frontend

**Files:**
- Modify: `src/ui/app.py` (add tracker endpoints)
- Create: `src/ui/static/js/tracker.js` (tracker tab visualization)
- Modify: `src/ui/static/index.html` (add tracker view)

**Step 1: Add tracker endpoints**

- `POST /api/tracker/import` — upload tracker data file
- `GET /api/tracker/data` — get all tracker data (with date range filter)
- `GET /api/tracker/summary` — latest values for dashboard widgets

**Step 2: Build tracker tab with D3 charts**

Line charts for each metric, date range picker, symptom overlay toggle.

**Step 3: Commit**

```bash
git commit -m "feat: health tracker tab with D3 visualizations"
```

---

## Phase J: Vitals Surfaced

### Task J1: Surface vitals from clinical data

**Files:**
- Modify: `src/ui/app.py` (add vitals endpoint)
- Modify: `src/ui/static/app.js` (add vitals to dashboard)

**Step 1: Add vitals endpoint**

```python
@app.route("/api/vitals")
def get_vitals():
    """Return vital signs from clinical timeline."""
    if not _profile_data:
        return jsonify([])
    vitals = _profile_data.get("clinical_timeline", {}).get("vitals", [])
    return jsonify(vitals)
```

**Step 2: Add vitals sparklines to dashboard**

Fetch `/api/vitals`, group by type (BP, HR, weight), render D3 sparklines.

**Step 3: Commit**

```bash
git commit -m "feat: vitals surfaced on dashboard with sparklines"
```

---

## Phase K: Risk Score Rollup

### Task K1: Compute aggregate risk score

**Files:**
- Create: `src/analysis/risk_score.py`
- Modify: `src/ui/app.py` (add risk score to dashboard endpoint)
- Create: `tests/test_risk_score.py`

**Step 1: Write failing test**

```python
def test_risk_score_stable_with_no_flags():
    """No flags, no trends = stable."""
    from src.analysis.risk_score import compute_risk_score
    result = compute_risk_score(flags=[], trends=[], conditions=[])
    assert result["status"] == "stable"
    assert 0 <= result["score"] <= 100
```

**Step 2: Run test — confirm fail**

**Step 3: Implement risk score calculator**

Inputs: lab trends (from trajectories), active flag count, condition severity, overdue tests, trajectory threshold crossings.

Scoring:
- Start at 50 (neutral)
- Each critical flag: -10
- Each high flag: -5
- Each overdue test: -3
- Each rising-toward-critical trend: -8
- Each improving trend: +3
- Each stable metric: +1

Output: `{score: 0-100, status: "improving"|"stable"|"needs_attention", factors: [...]}`

**Step 4: Run test — confirm pass**

**Step 5: Add to dashboard API response**

**Step 6: Render on dashboard as color-coded badge**

**Step 7: Commit**

```bash
git commit -m "feat: aggregate risk score rollup on dashboard"
```

---

## Final Phase: Integration Testing + Demo Update

### Task Z1: Full integration test

- Unlock demo vault (passphrase: "demo")
- Navigate through every sidebar item
- Verify dashboard shows all widgets with data
- Verify chat works from dashboard
- Verify timeline flows and zooms
- Verify cross-disciplinary shows node graph
- Verify environmental shows risks
- Verify body map loads without data

### Task Z2: Update MedPrep-Demo

Copy changes to MedPrep-Demo, re-run seed script, verify demo works.

### Task Z3: Update CHANGELOG.md

```markdown
## v3.0 — 2026-03-XX

### Major UI Overhaul
- Sidebar navigation replaces top tabs (collapsible, icons + labels)
- GNOME/Tailwind CSS design system
- Dashboard → Diagnostic Command Center with 12+ analytics widgets
- Chat embedded in Dashboard (removed standalone Chat tab)
- Flowing interactive Timeline with semantic zoom (D3.js)
- Cross-Disciplinary upgraded to node graph visualization
- Environmental health risks as dedicated tab
- Health Tracker integration (Fitbit + Apple Health)
- Vitals surfaced from clinical records
- Aggregate risk score rollup
- 3D Body Map loads without patient data
```
