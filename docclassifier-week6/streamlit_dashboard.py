from __future__ import annotations

import os
from collections import Counter
from datetime import datetime
from typing import Any

import httpx
import streamlit as st

from app.classifier.classes import CLASSES

APP_TITLE = "Document Classifier Dashboard"
DEFAULT_API_URL = os.getenv("DOCCLASSIFIER_API_URL", "http://localhost:8000")

DEMO_USER: dict[str, Any] = {
    "id": "demo-user",
    "email": "demo@example.com",
    "role": "reviewer",
    "is_active": True,
    "created_at": "2026-05-14T08:30:00",
}

DEMO_BATCHES: list[dict[str, Any]] = [
    {
        "id": "batch-20260514-001",
        "status": "done",
        "file_count": 14,
        "created_at": "2026-05-14T08:05:00",
    },
    {
        "id": "batch-20260514-002",
        "status": "processing",
        "file_count": 9,
        "created_at": "2026-05-14T09:10:00",
    },
    {
        "id": "batch-20260514-003",
        "status": "pending",
        "file_count": 7,
        "created_at": "2026-05-14T09:35:00",
    },
    {
        "id": "batch-20260513-004",
        "status": "failed",
        "file_count": 5,
        "created_at": "2026-05-13T17:20:00",
    },
]

DEMO_PREDICTIONS: list[dict[str, Any]] = [
    {
        "id": "pred-001",
        "batch_id": "batch-20260514-001",
        "filename": "invoice_1042.tiff",
        "blob_key": "minio://documents/batches/batch-20260514-001/original/invoice_1042.tiff",
        "overlay_key": "minio://documents/batches/batch-20260514-001/overlay/invoice_1042.png",
        "predicted_class": "invoice",
        "confidence": 0.93,
        "relabeled_class": None,
        "created_at": "2026-05-14T08:17:00",
    },
    {
        "id": "pred-002",
        "batch_id": "batch-20260514-001",
        "filename": "resume_2201.tiff",
        "blob_key": "minio://documents/batches/batch-20260514-001/original/resume_2201.tiff",
        "overlay_key": "minio://documents/batches/batch-20260514-001/overlay/resume_2201.png",
        "predicted_class": "resume",
        "confidence": 0.81,
        "relabeled_class": "resume",
        "created_at": "2026-05-14T08:18:00",
    },
    {
        "id": "pred-003",
        "batch_id": "batch-20260514-002",
        "filename": "memo_018.tiff",
        "blob_key": "minio://documents/batches/batch-20260514-002/original/memo_018.tiff",
        "overlay_key": "minio://documents/batches/batch-20260514-002/overlay/memo_018.png",
        "predicted_class": "memo",
        "confidence": 0.67,
        "relabeled_class": None,
        "created_at": "2026-05-14T09:14:00",
    },
    {
        "id": "pred-004",
        "batch_id": "batch-20260514-002",
        "filename": "news_356.tiff",
        "blob_key": "minio://documents/batches/batch-20260514-002/original/news_356.tiff",
        "overlay_key": "minio://documents/batches/batch-20260514-002/overlay/news_356.png",
        "predicted_class": "news article",
        "confidence": 0.88,
        "relabeled_class": None,
        "created_at": "2026-05-14T09:16:00",
    },
    {
        "id": "pred-005",
        "batch_id": "batch-20260513-004",
        "filename": "form_771.tiff",
        "blob_key": "minio://documents/batches/batch-20260513-004/original/form_771.tiff",
        "overlay_key": "minio://documents/batches/batch-20260513-004/overlay/form_771.png",
        "predicted_class": "form",
        "confidence": 0.58,
        "relabeled_class": "questionnaire",
        "created_at": "2026-05-13T17:24:00",
    },
]

STATUS_LABELS = {
    "pending": "Waiting",
    "processing": "Processing",
    "done": "Completed",
    "failed": "Failed",
}

ROLE_LABELS = {
    "admin": "Administrator",
    "reviewer": "Reviewer",
    "auditor": "Viewer",
}


class DashboardAPIError(RuntimeError):
    """Friendly wrapper for API errors shown in the UI."""


def init_state() -> None:
    defaults = {
        "api_base_url": DEFAULT_API_URL,
        "access_token": "",
        "current_user": None,
        "status_notice": "",
        "demo_relabels": {},
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background: linear-gradient(180deg, #f8fafc 0%, #eef2f7 100%);
            color: #0f172a;
        }
        .block-container {
            padding-top: 1.5rem;
            padding-bottom: 2rem;
        }
        .hero-card {
            background: linear-gradient(135deg, rgba(15,118,110,0.12), rgba(255,255,255,0.98));
            border: 1px solid rgba(15,23,42,0.08);
            border-radius: 20px;
            padding: 1.5rem 1.5rem 1.25rem 1.5rem;
            box-shadow: 0 18px 40px rgba(15,23,42,0.06);
            margin-bottom: 1rem;
        }
        .hero-kicker {
            font-size: 0.78rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: #0f766e;
            margin-bottom: 0.5rem;
            font-weight: 700;
        }
        .hero-title {
            font-size: 2rem;
            line-height: 1.1;
            margin: 0 0 0.5rem 0;
            color: #0f172a;
        }
        .hero-copy {
            margin: 0;
            color: #475569;
            font-size: 1rem;
        }
        .soft-card {
            background: rgba(255, 255, 255, 0.9);
            border: 1px solid rgba(15, 23, 42, 0.08);
            border-radius: 18px;
            padding: 1rem 1rem 0.85rem 1rem;
            box-shadow: 0 12px 30px rgba(15, 23, 42, 0.04);
        }
        .section-label {
            font-size: 0.78rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: #64748b;
            margin-bottom: 0.35rem;
            font-weight: 700;
        }
        .tiny-note {
            color: #64748b;
            font-size: 0.9rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def normalize_base_url(url: str) -> str:
    cleaned = url.strip().rstrip("/")
    return cleaned or DEFAULT_API_URL


def short_ref(value: Any, length: int = 8) -> str:
    if value is None:
        return "-"
    text = str(value)
    return text[:length] if len(text) > length else text


def parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def format_datetime(value: Any) -> str:
    dt = parse_datetime(value)
    if dt is None:
        return "Unknown"
    return dt.strftime("%b %d, %Y %H:%M")


def confidence_text(value: Any) -> str:
    try:
        return f"{float(value) * 100:.0f}%"
    except (TypeError, ValueError):
        return "-"


def confidence_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def status_label(value: Any) -> str:
    return STATUS_LABELS.get(str(value), str(value).replace("_", " ").title())


def role_label(value: Any) -> str:
    return ROLE_LABELS.get(str(value), str(value).title())


def prediction_label(prediction: dict[str, Any]) -> str:
    filename = prediction.get("filename", "Document")
    label = prediction.get("relabeled_class") or prediction.get("predicted_class") or "Unknown"
    return f"{filename} - {label}"


def review_label(prediction: dict[str, Any]) -> str:
    if prediction.get("relabeled_class"):
        return "Corrected"
    if confidence_value(prediction.get("confidence")) < 0.7:
        return "Needs review"
    return "Auto"


def extract_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str):
            return detail
        if isinstance(detail, list):
            return "; ".join(str(item) for item in detail)

    text = response.text.strip()
    if text:
        return text
    return f"Request failed with status {response.status_code}"


def request_json(
    method: str,
    base_url: str,
    path: str,
    *,
    token: str | None = None,
    params: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
) -> Any:
    url = f"{normalize_base_url(base_url)}{path if path.startswith('/') else f'/{path}'}"
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            response = client.request(
                method,
                url,
                headers=headers,
                params=params,
                data=data,
                json=json,
            )
    except httpx.RequestError as exc:
        raise DashboardAPIError(
            f"Could not reach the API at {normalize_base_url(base_url)}."
        ) from exc

    if response.is_error:
        raise DashboardAPIError(extract_error_message(response))

    if response.status_code == 204 or not response.content:
        return None

    try:
        return response.json()
    except ValueError as exc:
        raise DashboardAPIError("The API returned data that could not be read.") from exc


def login_to_api(base_url: str, email: str, password: str) -> tuple[str, dict[str, Any]]:
    auth_response = request_json(
        "POST",
        base_url,
        "/auth/jwt/login",
        data={"username": email, "password": password},
    )
    token = auth_response.get("access_token") if isinstance(auth_response, dict) else None
    if not token:
        raise DashboardAPIError("Login succeeded, but no access token was returned.")

    user = request_json("GET", base_url, "/users/me", token=token)
    if not isinstance(user, dict):
        raise DashboardAPIError("Login succeeded, but the user profile could not be loaded.")
    return token, user


def register_account(base_url: str, email: str, password: str) -> dict[str, Any]:
    created_user = request_json(
        "POST",
        base_url,
        "/auth/register",
        json={"email": email, "password": password},
    )
    if not isinstance(created_user, dict):
        raise DashboardAPIError("Account creation succeeded, but the response could not be read.")
    return created_user


def load_live_dashboard(base_url: str, token: str) -> dict[str, Any]:
    user = request_json("GET", base_url, "/users/me", token=token)
    batches = request_json("GET", base_url, "/batches/", token=token, params={"skip": 0, "limit": 20})
    recent = request_json(
        "GET",
        base_url,
        "/predictions/recent",
        token=token,
        params={"limit": 10},
    )
    return {
        "source": "Live data",
        "user": user if isinstance(user, dict) else {},
        "batches": batches if isinstance(batches, list) else [],
        "recent": recent if isinstance(recent, list) else [],
    }


def load_demo_dashboard() -> dict[str, Any]:
    overrides = st.session_state.get("demo_relabels", {})
    recent: list[dict[str, Any]] = []
    for item in DEMO_PREDICTIONS:
        copy = dict(item)
        if copy.get("id") in overrides:
            copy["relabeled_class"] = overrides[copy["id"]]
        recent.append(copy)
    return {
        "source": "Demo mode",
        "user": dict(DEMO_USER),
        "batches": [dict(item) for item in DEMO_BATCHES],
        "recent": recent,
    }


def batch_predictions_for_id(
    batch_id: str,
    source: dict[str, Any],
    token: str | None = None,
    base_url: str | None = None,
) -> list[dict[str, Any]]:
    if token and base_url:
        result = request_json("GET", base_url, f"/predictions/batch/{batch_id}", token=token)
        return result if isinstance(result, list) else []
    return [pred for pred in source.get("recent", []) if pred.get("batch_id") == batch_id]


def format_batch_option(batch: dict[str, Any]) -> str:
    return (
        f"{short_ref(batch.get('id'))} - {status_label(batch.get('status'))} - "
        f"{batch.get('file_count', 0)} files"
    )


def format_prediction_row(prediction: dict[str, Any]) -> dict[str, Any]:
    current_label = prediction.get("relabeled_class") or prediction.get("predicted_class") or "-"
    return {
        "Document": prediction.get("filename", "-"),
        "Prediction": current_label,
        "Confidence": confidence_text(prediction.get("confidence")),
        "Review": review_label(prediction),
        "Batch": short_ref(prediction.get("batch_id")),
        "When": format_datetime(prediction.get("created_at")),
    }


def render_sidebar() -> None:
    st.sidebar.title("Access")
    st.sidebar.caption(
        "Sign in to see live batches and predictions. If the API is not ready yet, the demo stays visible."
    )
    st.sidebar.text_input("API address", key="api_base_url")

    if st.session_state.access_token:
        user = st.session_state.current_user or {}
        st.sidebar.success(f"Signed in as {user.get('email', 'Unknown user')}")
        st.sidebar.caption(f"Role: {role_label(user.get('role'))}")
        if st.sidebar.button("Log out", use_container_width=True):
            st.session_state.access_token = ""
            st.session_state.current_user = None
            st.session_state.status_notice = ""
            st.rerun()
        return

    with st.sidebar.form("login_form"):
        email = st.text_input("Email address")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in")
        if submitted:
            try:
                token, user = login_to_api(st.session_state.api_base_url, email, password)
                st.session_state.access_token = token
                st.session_state.current_user = user
                st.session_state.status_notice = ""
                st.rerun()
            except DashboardAPIError as exc:
                st.session_state.status_notice = str(exc)

    with st.sidebar.expander("Create account", expanded=False):
        st.caption("Create a new account, then sign in right away.")
        with st.form("signup_form"):
            new_email = st.text_input("New email address")
            new_password = st.text_input("New password", type="password")
            confirm_password = st.text_input("Confirm password", type="password")
            created = st.form_submit_button("Create account")
            if created:
                if not new_email.strip() or not new_password:
                    st.session_state.status_notice = "Please enter an email address and password."
                elif new_password != confirm_password:
                    st.session_state.status_notice = "Passwords do not match."
                else:
                    try:
                        register_account(st.session_state.api_base_url, new_email, new_password)
                        token, user = login_to_api(st.session_state.api_base_url, new_email, new_password)
                        st.session_state.access_token = token
                        st.session_state.current_user = user
                        st.session_state.status_notice = ""
                        st.rerun()
                    except DashboardAPIError as exc:
                        st.session_state.status_notice = str(exc)

    if st.session_state.status_notice:
        st.sidebar.error(st.session_state.status_notice)

    st.sidebar.info("You can keep exploring the demo without signing in.")


def render_hero(user: dict[str, Any], source: str) -> None:
    email = user.get("email", "demo user")
    role = role_label(user.get("role", "auditor"))
    title = "Document Classifier Dashboard"
    if source == "Live data":
        copy = "View new batches, check predictions, and correct low-confidence results in one simple place."
    else:
        copy = "This demo shows the dashboard layout before connecting to the live service."

    st.markdown(
        f"""
        <div class="hero-card">
            <div class="hero-kicker">{source}</div>
            <h1 class="hero-title">{title}</h1>
            <p class="hero-copy">{copy}</p>
            <p class="hero-copy">Signed in as {email} - {role}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_overview(data: dict[str, Any]) -> None:
    batches = data.get("batches", [])
    recent = data.get("recent", [])

    status_counts = Counter(str(batch.get("status")) for batch in batches)
    completed = status_counts.get("done", 0)
    active = status_counts.get("pending", 0) + status_counts.get("processing", 0)
    needs_review = sum(1 for pred in recent if review_label(pred) == "Needs review")

    confidence_values = []
    for pred in recent:
        confidence_values.append(confidence_value(pred.get("confidence")))

    average_confidence = sum(confidence_values) / len(confidence_values) if confidence_values else 0.0

    st.markdown('<div class="section-label">At a glance</div>', unsafe_allow_html=True)
    metrics = st.columns(4)
    metrics[0].metric("Batches", len(batches))
    metrics[1].metric("Completed", completed)
    metrics[2].metric("Active", active)
    metrics[3].metric("Needs review", needs_review)
    st.caption(f"Average confidence across recent documents: {confidence_text(average_confidence)}")

    st.markdown('<div class="section-label">Recent documents</div>', unsafe_allow_html=True)
    if recent:
        rows = [format_prediction_row(pred) for pred in recent]
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("No predictions are available yet.")


def render_batches_tab(data: dict[str, Any], token: str | None, base_url: str | None) -> None:
    batches = data.get("batches", [])
    st.markdown('<div class="section-label">Batches</div>', unsafe_allow_html=True)
    if not batches:
        st.info("No batches are available yet.")
        return

    batch_lookup = {format_batch_option(batch): batch for batch in batches}
    selected_label = st.selectbox("Choose a batch", list(batch_lookup.keys()))
    selected_batch = batch_lookup[selected_label]

    top = st.columns(3)
    top[0].metric("Status", status_label(selected_batch.get("status")))
    top[1].metric("Files", selected_batch.get("file_count", 0))
    top[2].metric("Created", format_datetime(selected_batch.get("created_at")))

    st.markdown(
        f"""
        <div class="soft-card">
            <div class="tiny-note">Batch reference</div>
            <strong>{selected_batch.get('id')}</strong>
            <div class="tiny-note">This groups documents that arrived together.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.write("")

    try:
        batch_predictions = batch_predictions_for_id(
            selected_batch.get("id", ""),
            data,
            token=token,
            base_url=base_url,
        )
    except DashboardAPIError as exc:
        st.warning(f"Could not load documents for this batch: {exc}")
        batch_predictions = [pred for pred in data.get("recent", []) if pred.get("batch_id") == selected_batch.get("id")]

    st.markdown('<div class="section-label">Documents in this batch</div>', unsafe_allow_html=True)
    if batch_predictions:
        st.dataframe([format_prediction_row(pred) for pred in batch_predictions], use_container_width=True, hide_index=True)
    else:
        st.info("No documents were found in this batch.")


def render_review_tab(
    data: dict[str, Any],
    token: str | None,
    base_url: str | None,
    user: dict[str, Any],
    live_mode: bool,
) -> None:
    recent = data.get("recent", [])
    st.markdown('<div class="section-label">Review</div>', unsafe_allow_html=True)

    if not recent:
        st.info("There are no documents ready for review.")
        return

    if user.get("role") == "auditor":
        st.info("This account can view documents only. Sign in as a reviewer or admin to make corrections.")
        return

    option_labels = [f"{prediction_label(pred)} - {short_ref(pred.get('id'))}" for pred in recent]
    options = dict(zip(option_labels, recent))
    default_index = next((i for i, pred in enumerate(recent) if confidence_value(pred.get("confidence")) < 0.7), 0)
    selected_label = st.selectbox("Choose a document", option_labels, index=default_index)
    selected_prediction = options[selected_label]
    current_class = selected_prediction.get("relabeled_class") or selected_prediction.get("predicted_class") or "Unknown"
    confidence = confidence_value(selected_prediction.get("confidence"))

    detail_columns = st.columns(3)
    detail_columns[0].metric("Current label", current_class)
    detail_columns[1].metric("Confidence", confidence_text(confidence))
    detail_columns[2].metric("Batch", short_ref(selected_prediction.get("batch_id")))
    st.progress(min(max(confidence, 0.0), 1.0))
    st.caption(
        f"Document: {selected_prediction.get('filename', '-')} - Uploaded {format_datetime(selected_prediction.get('created_at'))}"
    )

    reviewer_restriction = user.get("role") == "reviewer" and confidence >= 0.7
    if reviewer_restriction:
        st.warning("Reviewers can only correct low-confidence documents below 70%.")

    st.markdown("#### Relabel document")
    st.caption("Choose the correct class and save the correction.")

    with st.form("relabel_form"):
        current_index = 0
        if current_class in CLASSES:
            current_index = CLASSES.index(current_class)
        corrected_class = st.selectbox("Correct class", CLASSES, index=current_index)
        submit_label = "Save correction" if live_mode and token and base_url else "Apply demo correction"
        submitted = st.form_submit_button(
            submit_label,
            disabled=reviewer_restriction,
            use_container_width=True,
        )
        if submitted:
            if live_mode and token and base_url:
                try:
                    request_json(
                        "PATCH",
                        base_url,
                        f"/predictions/{selected_prediction.get('id')}/relabel",
                        token=token,
                        json={"relabeled_class": corrected_class},
                    )
                    st.success(f"Saved. The document is now marked as {corrected_class}.")
                    st.rerun()
                except DashboardAPIError as exc:
                    st.error(exc)
            else:
                demo_overrides = dict(st.session_state.get("demo_relabels", {}))
                demo_overrides[selected_prediction.get("id")] = corrected_class
                st.session_state.demo_relabels = demo_overrides
                st.success(f"Demo correction applied: {corrected_class}.")
                st.rerun()


def render_app() -> None:
    init_state()
    inject_styles()
    render_sidebar()

    token = st.session_state.access_token or None
    base_url = normalize_base_url(st.session_state.api_base_url)
    user: dict[str, Any] = dict(DEMO_USER)
    data = load_demo_dashboard()
    live_mode = False

    if token:
        try:
            data = load_live_dashboard(base_url, token)
            user = data.get("user") or {}
            live_mode = True
        except DashboardAPIError as exc:
            st.warning(f"Live data is unavailable right now, so the demo is showing instead. {exc}")
            user = st.session_state.current_user or DEMO_USER
            data = load_demo_dashboard()
    elif st.session_state.current_user:
        user = st.session_state.current_user

    render_hero(user, data.get("source", "Demo mode"))

    st.markdown(
        """
        <div class="soft-card">
            <div class="tiny-note">How to use this page</div>
            <div>1. Sign in on the left.</div>
            <div>2. Check the latest batches and prediction results.</div>
            <div>3. Open the Review tab to correct a label when needed.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.write("")

    overview_tab, batches_tab, review_tab = st.tabs(["Overview", "Batches", "Review"])
    with overview_tab:
        render_overview(data)
    with batches_tab:
        render_batches_tab(data, token, base_url if live_mode else None)
    with review_tab:
        render_review_tab(data, token, base_url if live_mode else None, user, live_mode)


def main() -> None:
    st.set_page_config(
        page_title=APP_TITLE,
        page_icon="DOC",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    render_app()


if __name__ == "__main__":
    main()
