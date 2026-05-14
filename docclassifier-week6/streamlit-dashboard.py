from __future__ import annotations

import os
from collections import Counter
from datetime import datetime
from typing import Any

import httpx
import streamlit as st

# Inlined — dashboard runs standalone without the app package on sys.path
CLASSES = [
    "letter", "form", "email", "handwritten", "advertisement",
    "scientific report", "scientific publication", "specification",
    "file folder", "news article", "budget", "invoice", "presentation",
    "questionnaire", "resume", "memo",
]

APP_TITLE     = "Document Classifier Dashboard"
DEFAULT_API_URL = os.getenv("DOCCLASSIFIER_API_URL", "http://localhost:8000")

# ── Demo data ─────────────────────────────────────────────────────────────────

DEMO_USER: dict[str, Any] = {
    "id": "demo-user", "email": "demo@example.com",
    "role": "admin", "is_active": True, "created_at": "2026-05-01T08:00:00",
}

DEMO_USERS: list[dict[str, Any]] = [
    {"id": "user-001", "email": "admin@example.com",    "role": "admin",    "is_active": True,  "created_at": "2026-05-01T00:00:00"},
    {"id": "user-002", "email": "reviewer@example.com", "role": "reviewer", "is_active": True,  "created_at": "2026-05-02T00:00:00"},
    {"id": "user-003", "email": "auditor@example.com",  "role": "auditor",  "is_active": True,  "created_at": "2026-05-03T00:00:00"},
]

DEMO_BATCHES: list[dict[str, Any]] = [
    {"id": "batch-001", "status": "done",       "file_count": 14, "created_at": "2026-05-14T08:05:00"},
    {"id": "batch-002", "status": "processing", "file_count": 9,  "created_at": "2026-05-14T09:10:00"},
    {"id": "batch-003", "status": "pending",    "file_count": 7,  "created_at": "2026-05-14T09:35:00"},
    {"id": "batch-004", "status": "failed",     "file_count": 5,  "created_at": "2026-05-13T17:20:00"},
]

DEMO_PREDICTIONS: list[dict[str, Any]] = [
    {"id": "pred-001", "batch_id": "batch-001", "filename": "invoice_1042.tiff",
     "blob_key": "batches/batch-001/original/invoice_1042.tiff",
     "overlay_key": "batches/batch-001/overlay/invoice_1042.png",
     "predicted_class": "invoice",     "confidence": 0.93, "relabeled_class": None,             "created_at": "2026-05-14T08:17:00"},
    {"id": "pred-002", "batch_id": "batch-001", "filename": "resume_2201.tiff",
     "blob_key": "batches/batch-001/original/resume_2201.tiff",
     "overlay_key": "batches/batch-001/overlay/resume_2201.png",
     "predicted_class": "resume",      "confidence": 0.81, "relabeled_class": "resume",         "created_at": "2026-05-14T08:18:00"},
    {"id": "pred-003", "batch_id": "batch-002", "filename": "memo_018.tiff",
     "blob_key": "batches/batch-002/original/memo_018.tiff",
     "overlay_key": "batches/batch-002/overlay/memo_018.png",
     "predicted_class": "memo",        "confidence": 0.67, "relabeled_class": None,             "created_at": "2026-05-14T09:14:00"},
    {"id": "pred-004", "batch_id": "batch-002", "filename": "news_356.tiff",
     "blob_key": "batches/batch-002/original/news_356.tiff",
     "overlay_key": "batches/batch-002/overlay/news_356.png",
     "predicted_class": "news article", "confidence": 0.88, "relabeled_class": None,            "created_at": "2026-05-14T09:16:00"},
    {"id": "pred-005", "batch_id": "batch-004", "filename": "form_771.tiff",
     "blob_key": "batches/batch-004/original/form_771.tiff",
     "overlay_key": "batches/batch-004/overlay/form_771.png",
     "predicted_class": "form",        "confidence": 0.58, "relabeled_class": "questionnaire",  "created_at": "2026-05-13T17:24:00"},
    {"id": "pred-006", "batch_id": "batch-001", "filename": "letter_099.tiff",
     "blob_key": "batches/batch-001/original/letter_099.tiff",
     "overlay_key": "batches/batch-001/overlay/letter_099.png",
     "predicted_class": "letter",      "confidence": 0.52, "relabeled_class": None,             "created_at": "2026-05-14T08:20:00"},
]

DEMO_AUDIT: list[dict[str, Any]] = [
    {"id": "a-001", "actor_id": "user-001", "action": "user_created",      "target": "user:user-002", "details": {"email": "reviewer@example.com", "role": "reviewer"}, "timestamp": "2026-05-02T10:00:00"},
    {"id": "a-002", "actor_id": "user-001", "action": "user_created",      "target": "user:user-003", "details": {"email": "auditor@example.com",  "role": "auditor"},  "timestamp": "2026-05-03T11:00:00"},
    {"id": "a-003", "actor_id": None,       "action": "batch_created",      "target": "batch:batch-001", "details": {"file_count": 14},               "timestamp": "2026-05-14T08:05:00"},
    {"id": "a-004", "actor_id": None,       "action": "batch_state_change", "target": "batch:batch-001", "details": {"from": "pending", "to": "processing"}, "timestamp": "2026-05-14T08:10:00"},
    {"id": "a-005", "actor_id": None,       "action": "batch_state_change", "target": "batch:batch-001", "details": {"from": "processing", "to": "done"},    "timestamp": "2026-05-14T08:17:00"},
    {"id": "a-006", "actor_id": "user-002", "action": "relabel",            "target": "prediction:pred-002", "details": {"from": "letter", "to": "resume"},  "timestamp": "2026-05-14T09:00:00"},
    {"id": "a-007", "actor_id": "user-002", "action": "relabel",            "target": "prediction:pred-005", "details": {"from": "form", "to": "questionnaire"}, "timestamp": "2026-05-13T17:30:00"},
]

STATUS_LABELS = {"pending": "Waiting", "processing": "Processing", "done": "Completed", "failed": "Failed"}
ROLE_LABELS   = {"admin": "Administrator", "reviewer": "Reviewer", "auditor": "Viewer"}
STATUS_ICONS  = {"pending": "⏳", "processing": "⚙️", "done": "✅", "failed": "❌"}


# ── Custom exception ──────────────────────────────────────────────────────────

class DashboardAPIError(RuntimeError):
    pass


# ── Session state ─────────────────────────────────────────────────────────────

def init_state() -> None:
    for key, value in {
        "api_base_url":  DEFAULT_API_URL,
        "access_token":  "",
        "current_user":  None,
        "status_notice": "",
        "demo_relabels": {},
    }.items():
        st.session_state.setdefault(key, value)


# ── CSS ───────────────────────────────────────────────────────────────────────

def inject_styles() -> None:
    st.markdown("""
    <style>
    /* ── Force light mode on every element ──────────────────────────────────
       OS dark-mode bleeds through base-web dropdowns and the dataframe
       regardless of config.toml.  This single rule fixes all of them.      */
    *, *::before, *::after { color-scheme: light !important; }

    /* ── Selectbox / multiselect dropdown popup ──────────────────────────── */
    [data-baseweb="popover"],
    [data-baseweb="menu"],
    [data-baseweb="select"] {
        background-color: #ffffff !important;
        color: #1e293b !important;
    }
    [data-baseweb="popover"] *,
    [data-baseweb="menu"] * {
        background-color: #ffffff !important;
        color: #1e293b !important;
    }
    [role="option"]:hover,
    [data-baseweb="menu"] li:hover {
        background-color: #f0f2f6 !important;
    }

    /* ── Input fields ────────────────────────────────────────────────────── */
    input, textarea, [data-baseweb="input"] input {
        background-color: #ffffff !important;
        color: #1e293b !important;
        border-color: #cbd5e1 !important;
    }

    /* ── Buttons ─────────────────────────────────────────────────────────── */
    [data-testid="stFormSubmitButton"] button[kind="primaryFormSubmit"],
    [data-testid="stButton"] button[kind="primary"] {
        background-color: #0f766e !important;
        color: #ffffff !important;
        border: none !important;
    }
    [data-testid="stFormSubmitButton"] button[kind="secondaryFormSubmit"],
    [data-testid="stButton"] button[kind="secondary"] {
        background-color: #ffffff !important;
        color: #1e293b !important;
        border: 1px solid #94a3b8 !important;
    }

    /* ── Dataframe ───────────────────────────────────────────────────────── */
    [data-testid="stDataFrame"] iframe {
        color-scheme: light !important;
    }

    /* ── Layout ──────────────────────────────────────────────────────────── */
    .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }

    .hero-card {
        background: linear-gradient(135deg, rgba(15,118,110,0.12), rgba(255,255,255,0.97));
        border: 1px solid rgba(15,23,42,0.10);
        border-radius: 20px;
        padding: 1.5rem 1.75rem 1.25rem;
        box-shadow: 0 8px 32px rgba(15,23,42,0.07);
        margin-bottom: 1.25rem;
    }
    .hero-kicker {
        font-size: .75rem; text-transform: uppercase;
        letter-spacing: .1em; color: #0f766e;
        font-weight: 700; margin-bottom: .4rem;
    }
    .hero-title { font-size: 1.85rem; line-height: 1.15; margin: 0 0 .4rem; color: #0f172a; }
    .hero-copy  { font-size: 1rem; margin: 0; color: #475569; }

    .soft-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 14px;
        padding: 1rem 1.1rem .9rem;
        box-shadow: 0 4px 16px rgba(15,23,42,0.05);
        margin-bottom: .75rem;
    }
    .section-label {
        font-size: .72rem; text-transform: uppercase;
        letter-spacing: .1em; color: #64748b;
        font-weight: 700; margin-bottom: .3rem; margin-top: .5rem;
    }
    .tiny-note { font-size: .88rem; color: #64748b; }
    </style>
    """, unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def normalize_base_url(url: str) -> str:
    return url.strip().rstrip("/") or DEFAULT_API_URL

def short_ref(value: Any, length: int = 8) -> str:
    if value is None: return "-"
    t = str(value)
    return t[:length] if len(t) > length else t

def parse_datetime(value: Any) -> datetime | None:
    if value is None: return None
    if isinstance(value, datetime): return value
    text = str(value).strip()
    if not text: return None
    if text.endswith("Z"): text = text[:-1] + "+00:00"
    try: return datetime.fromisoformat(text)
    except ValueError: return None

def format_datetime(value: Any) -> str:
    dt = parse_datetime(value)
    return dt.strftime("%b %d %H:%M") if dt else "—"

def confidence_text(value: Any) -> str:
    try: return f"{float(value)*100:.0f}%"
    except (TypeError, ValueError): return "—"

def confidence_value(value: Any) -> float:
    try: return float(value)
    except (TypeError, ValueError): return 0.0

def status_label(value: Any) -> str:
    s = str(value)
    return f"{STATUS_ICONS.get(s,'')} {STATUS_LABELS.get(s, s.replace('_',' ').title())}".strip()

def role_label(value: Any) -> str:
    return ROLE_LABELS.get(str(value), str(value).title())

def review_label(prediction: dict[str, Any]) -> str:
    if prediction.get("relabeled_class"): return "✅ Corrected"
    if confidence_value(prediction.get("confidence")) < 0.7: return "⚠️ Needs review"
    return "🤖 Auto"

def extract_error_message(response: httpx.Response) -> str:
    try: payload = response.json()
    except ValueError: payload = None
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str): return detail
        if isinstance(detail, list): return "; ".join(str(i) for i in detail)
    return response.text.strip() or f"HTTP {response.status_code}"


# ── API client ────────────────────────────────────────────────────────────────

def request_json(
    method: str, base_url: str, path: str, *,
    token: str | None = None,
    params: dict | None = None,
    data:   dict | None = None,
    json:   dict | None = None,
    files:  Any  = None,
) -> Any:
    url = f"{normalize_base_url(base_url)}{path if path.startswith('/') else f'/{path}'}"
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as c:
            resp = c.request(method, url, headers=headers, params=params, data=data, json=json, files=files)
    except httpx.RequestError as exc:
        raise DashboardAPIError(f"Cannot reach {normalize_base_url(base_url)}.") from exc
    if resp.is_error:
        raise DashboardAPIError(extract_error_message(resp))
    if resp.status_code == 204 or not resp.content:
        return None
    try: return resp.json()
    except ValueError as exc:
        raise DashboardAPIError("API returned unreadable data.") from exc


# ── Auth & user management ────────────────────────────────────────────────────

def login_to_api(base_url: str, email: str, password: str) -> tuple[str, dict]:
    auth = request_json("POST", base_url, "/auth/jwt/login", data={"username": email, "password": password})
    token = (auth or {}).get("access_token")
    if not token:
        raise DashboardAPIError("Login succeeded but no token was returned.")
    user = request_json("GET", base_url, "/users/me", token=token)
    if not isinstance(user, dict):
        raise DashboardAPIError("Login succeeded but user profile could not be loaded.")
    return token, user

def invite_user(base_url: str, token: str, email: str, password: str, role: str) -> dict:
    result = request_json("POST", base_url, "/users/", token=token,
                          json={"email": email, "password": password, "role": role})
    if not isinstance(result, dict):
        raise DashboardAPIError("User created but response was unreadable.")
    return result

def change_user_role(base_url: str, token: str, user_id: str, role: str) -> dict:
    result = request_json("PATCH", base_url, f"/users/{user_id}/role", token=token, json={"role": role})
    if not isinstance(result, dict):
        raise DashboardAPIError("Role updated but response was unreadable.")
    return result


# ── Data loaders ──────────────────────────────────────────────────────────────

def load_live_dashboard(base_url: str, token: str) -> dict[str, Any]:
    user    = request_json("GET", base_url, "/users/me",           token=token) or {}
    role    = user.get("role", "")
    batches = request_json("GET", base_url, "/batches/",           token=token, params={"skip": 0, "limit": 50}) or []
    recent  = request_json("GET", base_url, "/predictions/recent", token=token, params={"limit": 50}) or []

    users = []
    if role == "admin":
        try:
            users = request_json("GET", base_url, "/users/", token=token, params={"skip": 0, "limit": 100}) or []
        except DashboardAPIError:
            pass

    audit = []
    if role in ("admin", "auditor"):
        try:
            audit = request_json("GET", base_url, "/audit/", token=token, params={"limit": 200}) or []
        except DashboardAPIError:
            pass

    return {
        "source":  "Live data",
        "user":    user,
        "batches": batches if isinstance(batches, list) else [],
        "recent":  recent  if isinstance(recent,  list) else [],
        "users":   users   if isinstance(users,   list) else [],
        "audit":   audit   if isinstance(audit,   list) else [],
    }

def load_demo_dashboard() -> dict[str, Any]:
    overrides = st.session_state.get("demo_relabels", {})
    recent = []
    for item in DEMO_PREDICTIONS:
        copy = dict(item)
        if copy.get("id") in overrides:
            copy["relabeled_class"] = overrides[copy["id"]]
        recent.append(copy)
    return {
        "source":  "Demo mode",
        "user":    dict(DEMO_USER),
        "batches": [dict(b) for b in DEMO_BATCHES],
        "recent":  recent,
        "users":   [dict(u) for u in DEMO_USERS],
        "audit":   [dict(a) for a in DEMO_AUDIT],
    }

def fetch_batch_predictions(batch_id: str, data: dict, token: str | None, base_url: str | None) -> list:
    if token and base_url:
        try:
            result = request_json("GET", base_url, f"/predictions/batch/{batch_id}", token=token)
            return result if isinstance(result, list) else []
        except DashboardAPIError:
            pass
    return [p for p in data.get("recent", []) if p.get("batch_id") == batch_id]


# ── Formatters ────────────────────────────────────────────────────────────────

def fmt_batch_option(b: dict) -> str:
    return f"{short_ref(b.get('id'))} · {status_label(b.get('status'))} · {b.get('file_count',0)} files"

def fmt_prediction_row(p: dict) -> dict:
    label = p.get("relabeled_class") or p.get("predicted_class") or "—"
    return {
        "Document":   p.get("filename", "—"),
        "Label":      label,
        "Confidence": confidence_text(p.get("confidence")),
        "Status":     review_label(p),
        "Batch":      short_ref(p.get("batch_id")),
        "When":       format_datetime(p.get("created_at")),
    }

def fmt_user_row(u: dict) -> dict:
    return {
        "Email":  u.get("email", "—"),
        "Role":   role_label(u.get("role")),
        "Active": "Yes" if u.get("is_active") else "No",
        "Joined": format_datetime(u.get("created_at")),
    }

def fmt_audit_row(a: dict) -> dict:
    actor = a.get("actor_id")
    details = a.get("details") or {}
    detail_str = ", ".join(f"{k}={v}" for k, v in details.items()) if isinstance(details, dict) else str(details)
    return {
        "Time":    format_datetime(a.get("timestamp")),
        "Action":  a.get("action", "—").replace("_", " ").title(),
        "Actor":   short_ref(actor) if actor else "System",
        "Target":  a.get("target", "—"),
        "Details": detail_str,
    }


# ── Sidebar ───────────────────────────────────────────────────────────────────

def render_sidebar() -> None:
    st.sidebar.title("Access")
    st.sidebar.text_input("API address", key="api_base_url")

    if st.session_state.access_token:
        user = st.session_state.current_user or {}
        st.sidebar.success(f"✓ {user.get('email', 'Unknown')}")
        st.sidebar.caption(f"Role: {role_label(user.get('role'))}")
        if st.sidebar.button("Log out", use_container_width=True):
            st.session_state.access_token  = ""
            st.session_state.current_user  = None
            st.session_state.status_notice = ""
            st.rerun()
        return

    with st.sidebar.form("login_form"):
        email    = st.text_input("Email address")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Sign in", use_container_width=True):
            if not email.strip() or not password:
                st.session_state.status_notice = "Enter your email and password."
            else:
                try:
                    token, user = login_to_api(st.session_state.api_base_url, email.strip(), password)
                    st.session_state.access_token  = token
                    st.session_state.current_user  = user
                    st.session_state.status_notice = ""
                    st.rerun()
                except DashboardAPIError as exc:
                    st.session_state.status_notice = str(exc)

    if st.session_state.status_notice:
        st.sidebar.error(st.session_state.status_notice)

    st.sidebar.caption("New accounts are created by your administrator.")
    st.sidebar.info("Browse the demo without signing in.")


# ── Hero ──────────────────────────────────────────────────────────────────────

def render_hero(user: dict, source: str) -> None:
    copy = (
        "Monitor batches, review predictions, upload documents, and manage your team."
        if source == "Live data" else
        "Demo mode — sign in to see live data and use all features."
    )
    st.markdown(f"""
    <div class="hero-card">
        <div class="hero-kicker">{source}</div>
        <h1 class="hero-title">{APP_TITLE}</h1>
        <p class="hero-copy">{copy}</p>
        <p class="hero-copy" style="margin-top:.4rem">
            Signed in as <strong>{user.get('email','demo')}</strong>
            &mdash; {role_label(user.get('role','auditor'))}
        </p>
    </div>
    """, unsafe_allow_html=True)


# ── Overview tab ──────────────────────────────────────────────────────────────

def render_overview(data: dict) -> None:
    batches = data.get("batches", [])
    recent  = data.get("recent",  [])

    status_counts = Counter(str(b.get("status")) for b in batches)
    completed     = status_counts.get("done",       0)
    processing    = status_counts.get("processing", 0)
    pending       = status_counts.get("pending",    0)
    failed        = status_counts.get("failed",     0)
    needs_review  = sum(1 for p in recent if "Needs" in review_label(p))
    conf_vals     = [confidence_value(p.get("confidence")) for p in recent]
    avg_conf      = sum(conf_vals) / len(conf_vals) if conf_vals else 0.0

    # ── Metrics ───────────────────────────────────────────────────────────────
    st.markdown('<div class="section-label">At a glance</div>', unsafe_allow_html=True)
    c0, c1, c2, c3, c4, c5 = st.columns(6)
    c0.metric("Total batches", len(batches))
    c1.metric("✅ Completed",  completed)
    c2.metric("⚙️ Processing", processing)
    c3.metric("⏳ Pending",    pending)
    c4.metric("❌ Failed",     failed)
    c5.metric("⚠️ Needs review", needs_review)
    st.caption(f"Average confidence across {len(recent)} recent predictions: **{confidence_text(avg_conf)}**")

    # ── Class distribution ────────────────────────────────────────────────────
    if recent:
        class_counts = Counter(
            p.get("relabeled_class") or p.get("predicted_class")
            for p in recent
            if p.get("predicted_class")
        )
        if class_counts:
            st.markdown('<div class="section-label">Class distribution (recent)</div>', unsafe_allow_html=True)
            st.bar_chart(dict(sorted(class_counts.items(), key=lambda x: -x[1])))

    # ── Recent predictions table ──────────────────────────────────────────────
    st.markdown('<div class="section-label">Recent predictions</div>', unsafe_allow_html=True)
    if recent:
        st.dataframe([fmt_prediction_row(p) for p in recent], use_container_width=True, hide_index=True)
    else:
        st.info("No predictions yet. Upload some TIFF files to get started.")


# ── Batches tab ───────────────────────────────────────────────────────────────

def render_batches_tab(data: dict, token: str | None, base_url: str | None) -> None:
    batches = data.get("batches", [])

    # ── Status filter ─────────────────────────────────────────────────────────
    st.markdown('<div class="section-label">Filter</div>', unsafe_allow_html=True)
    col_f, col_info = st.columns([2, 3])
    with col_f:
        status_opts = ["All", "done", "processing", "pending", "failed"]
        sel_status  = st.selectbox(
            "Status", status_opts,
            format_func=lambda s: "All statuses" if s == "All" else status_label(s),
            label_visibility="collapsed",
        )
    filtered = batches if sel_status == "All" else [b for b in batches if b.get("status") == sel_status]
    with col_info:
        st.caption(f"Showing {len(filtered)} of {len(batches)} batches.")

    if not filtered:
        st.info("No batches match the selected filter.")
        return

    # ── Batch summary table ───────────────────────────────────────────────────
    st.markdown('<div class="section-label">Batches</div>', unsafe_allow_html=True)
    st.dataframe(
        [{"ID": short_ref(b.get("id")), "Status": status_label(b.get("status")),
          "Files": b.get("file_count", 0), "Created": format_datetime(b.get("created_at"))}
         for b in filtered],
        use_container_width=True, hide_index=True,
    )

    # ── Batch detail ──────────────────────────────────────────────────────────
    st.markdown('<div class="section-label">Batch detail</div>', unsafe_allow_html=True)
    lookup   = {fmt_batch_option(b): b for b in filtered}
    selected = lookup[st.selectbox("Select a batch", list(lookup.keys()), label_visibility="collapsed")]

    c0, c1, c2 = st.columns(3)
    c0.metric("Status",  status_label(selected.get("status")))
    c1.metric("Files",   selected.get("file_count", 0))
    c2.metric("Created", format_datetime(selected.get("created_at")))

    st.markdown(f"""
    <div class="soft-card">
        <div class="tiny-note">Full batch ID</div>
        <strong style="font-family:monospace">{selected.get('id')}</strong>
    </div>
    """, unsafe_allow_html=True)

    preds = fetch_batch_predictions(selected.get("id", ""), data, token, base_url)
    st.markdown('<div class="section-label">Documents in this batch</div>', unsafe_allow_html=True)
    if preds:
        st.dataframe([fmt_prediction_row(p) for p in preds], use_container_width=True, hide_index=True)

        # Confidence breakdown within batch
        batch_conf = [confidence_value(p.get("confidence")) for p in preds]
        if batch_conf:
            avg = sum(batch_conf) / len(batch_conf)
            low = sum(1 for c in batch_conf if c < 0.7)
            ca, cb = st.columns(2)
            ca.metric("Avg confidence", confidence_text(avg))
            cb.metric("Low confidence (<70%)", low)
    else:
        st.info("No predictions found for this batch yet.")


# ── Upload tab ────────────────────────────────────────────────────────────────

def render_upload_tab(token: str | None, base_url: str | None, user: dict, live_mode: bool) -> None:
    st.markdown('<div class="section-label">Upload documents</div>', unsafe_allow_html=True)

    if not live_mode or not token or not base_url:
        st.info("Sign in to upload documents for classification.")
        return

    if user.get("role") == "auditor":
        st.warning("Auditors cannot upload documents. Contact an admin or reviewer.")
        return

    st.caption("Select one or more TIFF files. They are uploaded as a single batch and classified automatically.")

    uploaded = st.file_uploader(
        "Choose TIFF files", type=["tiff", "tif"],
        accept_multiple_files=True, label_visibility="collapsed",
    )

    if uploaded:
        st.write(f"**{len(uploaded)} file(s) selected:**")
        total_kb = 0
        for f in uploaded:
            size_kb = len(f.getvalue()) / 1024
            total_kb += size_kb
            st.write(f"  • {f.name} ({size_kb:.1f} KB)")
        st.caption(f"Total: {total_kb/1024:.2f} MB")

        if st.button("Upload and classify", type="primary", use_container_width=True):
            with st.spinner("Uploading…"):
                try:
                    result = request_json(
                        "POST", base_url, "/upload/", token=token,
                        files=[("files", (f.name, f.getvalue(), "image/tiff")) for f in uploaded],
                    )
                    bid  = result.get("batch_id", "?")
                    cnt  = result.get("file_count", 0)
                    st.success(f"✅ {cnt} file(s) enqueued for classification.")
                    st.markdown(f"""
                    <div class="soft-card">
                        <div class="tiny-note">Batch ID</div>
                        <strong style="font-family:monospace">{bid}</strong>
                        <div class="tiny-note" style="margin-top:.4rem">
                            Switch to the Batches tab in a few seconds to see results.
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                except DashboardAPIError as exc:
                    st.error(f"Upload failed: {exc}")
    else:
        st.markdown("""
        <div class="soft-card">
            <div class="tiny-note">Accepted formats</div>
            <strong>.tiff / .tif</strong> &nbsp;·&nbsp; Max 100 MB per file<br>
            <div class="tiny-note" style="margin-top:.4rem">
                All files selected together form one batch.
                Results appear in the Batches tab once classification finishes.
            </div>
        </div>
        """, unsafe_allow_html=True)


# ── Review tab ────────────────────────────────────────────────────────────────

def render_review_tab(data: dict, token: str | None, base_url: str | None, user: dict, live_mode: bool) -> None:
    recent = data.get("recent", [])
    st.markdown('<div class="section-label">Review predictions</div>', unsafe_allow_html=True)

    if not recent:
        st.info("No predictions available yet.")
        return

    if user.get("role") == "auditor":
        st.info("Auditors can view predictions but cannot relabel. Sign in as reviewer or admin.")
        st.dataframe([fmt_prediction_row(p) for p in recent], use_container_width=True, hide_index=True)
        return

    # ── Filter ────────────────────────────────────────────────────────────────
    show_all = st.toggle("Show all predictions (not just low-confidence)", value=False)
    pool = recent if show_all else [p for p in recent if confidence_value(p.get("confidence")) < 0.7 and not p.get("relabeled_class")]

    if not pool:
        st.success("All predictions are high-confidence. Nothing needs review." if not show_all else "No predictions found.")
        if not show_all:
            st.dataframe([fmt_prediction_row(p) for p in recent], use_container_width=True, hide_index=True)
        return

    st.caption(f"{len(pool)} document(s) shown.")

    # ── Document picker ───────────────────────────────────────────────────────
    labels  = [f"{p.get('filename','?')} — {confidence_text(p.get('confidence'))} — {short_ref(p.get('id'))}" for p in pool]
    options = dict(zip(labels, pool))
    sel     = options[st.selectbox("Select document", labels, label_visibility="collapsed")]

    current_class = sel.get("relabeled_class") or sel.get("predicted_class") or "Unknown"
    confidence    = confidence_value(sel.get("confidence"))

    c0, c1, c2 = st.columns(3)
    c0.metric("Current label", current_class)
    c1.metric("Confidence",    confidence_text(confidence))
    c2.metric("Batch",         short_ref(sel.get("batch_id")))

    conf_color = "normal" if confidence >= 0.7 else "inverse"
    st.progress(min(max(confidence, 0.0), 1.0))
    st.caption(f"File: {sel.get('filename','—')}  ·  Uploaded {format_datetime(sel.get('created_at'))}  ·  Batch {sel.get('batch_id','—')}")

    if sel.get("relabeled_class"):
        st.info(f"Already corrected to **{sel['relabeled_class']}**.")

    reviewer_blocked = (user.get("role") == "reviewer" and confidence >= 0.7)
    if reviewer_blocked:
        st.warning("Reviewers can only relabel predictions with confidence below 70%.")

    st.markdown("#### Relabel")
    with st.form("relabel_form"):
        cur_idx = CLASSES.index(current_class) if current_class in CLASSES else 0
        new_class = st.selectbox("Correct class", CLASSES, index=cur_idx)
        label_btn = "Save correction" if (live_mode and token) else "Apply demo correction"
        submitted = st.form_submit_button(label_btn, disabled=reviewer_blocked, use_container_width=True, type="primary")

        if submitted:
            if live_mode and token and base_url:
                try:
                    request_json("PATCH", base_url, f"/predictions/{sel.get('id')}/relabel",
                                 token=token, json={"relabeled_class": new_class})
                    st.success(f"✅ Saved — document now labelled as **{new_class}**.")
                    st.rerun()
                except DashboardAPIError as exc:
                    st.error(str(exc))
            else:
                overrides = dict(st.session_state.get("demo_relabels", {}))
                overrides[sel.get("id")] = new_class
                st.session_state.demo_relabels = overrides
                st.success(f"Demo correction applied: **{new_class}**.")
                st.rerun()


# ── Users tab (admin only) ────────────────────────────────────────────────────

def render_users_tab(data: dict, token: str | None, base_url: str | None, actor: dict, live_mode: bool) -> None:
    users = data.get("users", [])
    st.markdown('<div class="section-label">Team</div>', unsafe_allow_html=True)

    if not users:
        st.info("No users found.")
        return

    # ── Summary metrics ───────────────────────────────────────────────────────
    role_counts = Counter(u.get("role") for u in users)
    c0, c1, c2, c3 = st.columns(4)
    c0.metric("Total users", len(users))
    c1.metric("Admins",      role_counts.get("admin",    0))
    c2.metric("Reviewers",   role_counts.get("reviewer", 0))
    c3.metric("Auditors",    role_counts.get("auditor",  0))

    # ── Users table ───────────────────────────────────────────────────────────
    st.markdown('<div class="section-label">All users</div>', unsafe_allow_html=True)
    st.dataframe([fmt_user_row(u) for u in users], use_container_width=True, hide_index=True)

    # ── Change role ───────────────────────────────────────────────────────────
    st.markdown("#### Change role")
    other_users = [u for u in users if u.get("id") != actor.get("id")]
    if not other_users:
        st.caption("No other users to manage.")
    elif live_mode and token and base_url:
        with st.form("change_role_form"):
            user_opts   = {f"{u.get('email')} ({role_label(u.get('role'))})": u for u in other_users}
            sel_email   = st.selectbox("User", list(user_opts.keys()))
            target_user = user_opts[sel_email]
            new_role    = st.selectbox("New role", ["admin", "reviewer", "auditor"],
                                       index=["admin","reviewer","auditor"].index(target_user.get("role","auditor")))
            if st.form_submit_button("Apply", use_container_width=True):
                if new_role == target_user.get("role"):
                    st.info("Role unchanged — select a different role.")
                else:
                    try:
                        change_user_role(base_url, token, target_user["id"], new_role)
                        st.success(f"✅ {target_user.get('email')} is now **{role_label(new_role)}**.")
                        st.rerun()
                    except DashboardAPIError as exc:
                        st.error(str(exc))
    else:
        st.info("This action requires a live admin session.")

    # ── Invite new user ───────────────────────────────────────────────────────
    st.markdown("#### Invite new user")
    if live_mode and token and base_url:
        with st.form("invite_form"):
            inv_email    = st.text_input("Email address")
            inv_password = st.text_input("Temporary password", type="password")
            inv_role     = st.selectbox("Role", ["reviewer", "auditor"])
            if st.form_submit_button("Create account", use_container_width=True, type="primary"):
                if not inv_email.strip() or not inv_password:
                    st.error("Email and password are required.")
                else:
                    try:
                        invite_user(base_url, token, inv_email.strip(), inv_password, inv_role)
                        st.success(f"✅ Account created for **{inv_email.strip()}** as {role_label(inv_role)}.")
                        st.rerun()
                    except DashboardAPIError as exc:
                        st.error(str(exc))
    else:
        st.info("Sign in as admin to invite users.")


# ── Audit tab (admin + auditor) ───────────────────────────────────────────────

def render_audit_tab(data: dict) -> None:
    audit = data.get("audit", [])
    st.markdown('<div class="section-label">Audit log</div>', unsafe_allow_html=True)

    if not audit:
        st.info("No audit log entries found.")
        return

    # ── Filters ───────────────────────────────────────────────────────────────
    actions = sorted(set(a.get("action", "") for a in audit if a.get("action")))
    col_a, col_b, col_c = st.columns([2, 2, 1])
    with col_a:
        sel_action = st.selectbox("Action", ["All"] + actions,
                                  format_func=lambda s: "All actions" if s == "All" else s.replace("_"," ").title())
    with col_b:
        search = st.text_input("Search target", placeholder="batch:…  user:…  prediction:…")
    with col_c:
        st.write("")
        st.write("")
        st.caption(f"{len(audit)} total entries")

    filtered = audit
    if sel_action != "All":
        filtered = [a for a in filtered if a.get("action") == sel_action]
    if search.strip():
        s = search.strip().lower()
        filtered = [a for a in filtered if s in str(a.get("target","")).lower()
                    or s in str(a.get("actor_id","")).lower()]

    st.caption(f"Showing {len(filtered)} entries.")

    if filtered:
        st.dataframe([fmt_audit_row(a) for a in filtered], use_container_width=True, hide_index=True)
    else:
        st.info("No entries match the current filter.")

    # ── Action breakdown chart ────────────────────────────────────────────────
    st.markdown('<div class="section-label">Action breakdown</div>', unsafe_allow_html=True)
    action_counts = Counter(a.get("action","unknown").replace("_"," ").title() for a in audit)
    st.bar_chart(dict(sorted(action_counts.items(), key=lambda x: -x[1])))


# ── Main render ───────────────────────────────────────────────────────────────

def render_app() -> None:
    init_state()
    inject_styles()
    render_sidebar()

    token    = st.session_state.access_token or None
    base_url = normalize_base_url(st.session_state.api_base_url)
    data     = load_demo_dashboard()
    live_mode = False

    if token:
        try:
            data      = load_live_dashboard(base_url, token)
            live_mode = True
        except DashboardAPIError as exc:
            st.warning(f"Live data unavailable — showing demo. ({exc})")
            data = load_demo_dashboard()
            if st.session_state.current_user:
                data["user"] = st.session_state.current_user

    user = data.get("user") or {}
    role = user.get("role", "auditor")

    render_hero(user, data.get("source", "Demo mode"))

    # ── Tab layout — role-gated ───────────────────────────────────────────────
    tab_names = ["Overview", "Batches", "Upload", "Review"]
    if role in ("admin", "auditor"):
        tab_names.append("Audit")
    if role == "admin":
        tab_names.append("Users")

    all_tabs = st.tabs(tab_names)
    tab = dict(zip(tab_names, all_tabs))

    with tab["Overview"]:
        render_overview(data)

    with tab["Batches"]:
        render_batches_tab(data, token, base_url if live_mode else None)

    with tab["Upload"]:
        render_upload_tab(token, base_url if live_mode else None, user, live_mode)

    with tab["Review"]:
        render_review_tab(data, token, base_url if live_mode else None, user, live_mode)

    if "Audit" in tab:
        with tab["Audit"]:
            render_audit_tab(data)

    if "Users" in tab:
        with tab["Users"]:
            render_users_tab(data, token, base_url if live_mode else None, user, live_mode)


def main() -> None:
    st.set_page_config(
        page_title=APP_TITLE,
        page_icon="📄",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    render_app()


if __name__ == "__main__":
    main()
