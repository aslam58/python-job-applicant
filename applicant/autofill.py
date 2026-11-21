"""Playwright-assisted application form inspection, autofill, receipt checks, and logging."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

from applicant.models import (
    canonical_url,
    load_json,
    resolve_resume_path,
    save_json,
    validate_profile,
    validate_url,
)


def norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value).casefold()).strip()


ALIASES: dict[str, list[str]] = {
    "first_name": ["first name", "given name", "given names", "given name s", "legal first name"],
    "last_name": ["last name", "family name", "surname", "legal last name"],
    "full_name": ["full name", "full legal name", "name"],
    "email": ["email", "email address"],
    "phone": ["phone", "phone number", "mobile", "mobile number"],
    "linkedin_url": ["linkedin", "linkedin url", "linkedin profile"],
    "github_url": ["github", "github url", "github profile", "github link"],
    "portfolio_url": ["portfolio", "portfolio url", "website", "personal website", "portfolio link", "website url"],
    "city": ["city", "current city", "current location"],
    "state": ["state", "state province", "province", "region"],
    "country": ["country", "country of residence"],
    "address_line_1": ["address line 1", "street address"],
    "postal_code": ["postal code", "zip postal code", "zip code", "pin code"],
    "current_company": ["current company", "current employer", "company name"],
    "current_title": ["current title", "current job title", "current role", "headline"],
    "notice_period": ["notice period", "availability", "earliest start date"],
}

ALL_ALIAS_LABELS: set[str] = {alias for aliases in ALIASES.values() for alias in aliases}

BLOCKED_TYPES: set[str] = {"password", "hidden", "submit", "button", "reset", "image", "checkbox", "radio"}

SENSITIVE = re.compile(
    r"\b(password|otp|captcha|passport|pan|aadhaar|ssn|birth|gender|religion|race|ethnic|"
    r"disability|medical|signature|consent|terms|agree|privacy|nationality|citizenship|veteran)\b"
)

KNOWN_ATS_HOSTS: tuple[str, ...] = (
    "greenhouse.io",
    "lever.co",
    "ashbyhq.com",
    "myworkdayjobs.com",
    "smartrecruiters.com",
    "workable.com",
    "bamboohr.com",
    "icims.com",
    "jobvite.com",
    "breezy.hr",
    "rippling.com",
)

VERIFICATION_TITLES: set[str] = {
    "just a moment...",
    "just a moment…",
    "attention required! | cloudflare",
    "security check",
    "access denied",
}

VERIFICATION_MARKERS: tuple[str, ...] = (
    "performing security verification",
    "verifying you are human",
    "verify you are human",
    "checking your browser before accessing",
    "please verify you are a human",
    "complete the security check",
)

FIELD_INFO = """el => {
  const by = (el.getAttribute('aria-labelledby') || '').split(/\\s+/).filter(Boolean)
    .map(id => el.ownerDocument.getElementById(id)?.textContent || '').join(' ');
  const labels = Array.from(el.labels || []).map(label => {
    const copy = label.cloneNode(true);
    copy.querySelectorAll('input, textarea, select, button').forEach(control => control.remove());
    return copy.textContent || '';
  }).join(' ');
  return {label: el.getAttribute('aria-label') || labels || by || el.placeholder || '',
    name: el.name || '', id: el.id || '', type: el.type || '', role: el.getAttribute('role') || '',
    tag: el.tagName.toLowerCase(), value: el.value || '', required: el.required || el.getAttribute('aria-required') === 'true'};
}"""


def profile_value(field: Mapping[str, Any], profile: Mapping[str, Any]) -> str | None:
    """Conservative exact matching; unknown questions remain unanswered."""
    label = norm(field.get("label", ""))
    if field.get("type", "").lower() in BLOCKED_TYPES or field.get("role") == "combobox":
        return None
    if SENSITIVE.search(label):
        return None
    explicit = {norm(k): v for k, v in profile.get("questions", {}).items()}
    if label in explicit:
        value = explicit[label]
        return None if value is None or str(value).strip() == "" else str(value)
    for key, aliases in ALIASES.items():
        if label in aliases:
            value = profile.get(key)
            if key == "full_name" and not value:
                value = " ".join(str(profile.get(k) or "").strip() for k in ("first_name", "last_name")).strip()
            return str(value) if value is not None and str(value).strip() else None
    return None


def is_resume_input(info: Mapping[str, Any]) -> bool:
    text = norm(" ".join(str(info.get(k, "")) for k in ("label", "name", "id")))
    return bool(re.search(r"\b(resume|cv)\b", text)) and not re.search(r"\b(cover|photo|picture)\b", text)


def _is_known_ats_host(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in KNOWN_ATS_HOSTS)


def _is_recognized_contact_field(info: Mapping[str, Any]) -> bool:
    label = norm(info.get("label", ""))
    if not label or info.get("type", "").lower() in BLOCKED_TYPES or info.get("role") == "combobox":
        return False
    if SENSITIVE.search(label):
        return False
    return label in ALL_ALIAS_LABELS


def _count_contact_fields(container: Any) -> int:
    matched = 0
    for locator in container.locator("input, textarea, select").all():
        try:
            if not locator.is_visible() or not locator.is_enabled():
                continue
            info = locator.evaluate(FIELD_INFO)
            if _is_recognized_contact_field(info):
                matched += 1
                if matched >= 2:
                    return matched
        except Exception:
            continue
    return matched


def form_scopes(page: Any, explicit_scope: str | None = None) -> list[Any]:
    """Identify application forms via explicit selector, resume controls, or multi-step contact fields."""
    result: list[Any] = []
    for frame in page.frames:
        if explicit_scope:
            for root in frame.locator(explicit_scope).all():
                if root.is_visible():
                    result.append(root)
            continue
        frame_matches: list[Any] = []
        for form in frame.locator("form").all():
            if not form.is_visible():
                continue
            uploads = form.locator('input[type="file"]').all()
            if any(is_resume_input(f.evaluate(FIELD_INFO)) for f in uploads):
                frame_matches.append(form)
        if frame_matches:
            result.extend(frame_matches)
            continue
        if _is_known_ats_host(frame.url):
            uploads = frame.locator('input[type="file"]').all()
            if any(is_resume_input(f.evaluate(FIELD_INFO)) for f in uploads):
                result.append(frame.locator("body"))

    if result or explicit_scope:
        return result

    # Multi-step fallback: forms without a file input on the current step (e.g. step 1 contact info).
    for frame in page.frames:
        step_matches: list[Any] = []
        for form in frame.locator("form").all():
            if not form.is_visible():
                continue
            if _count_contact_fields(form) >= 2:
                step_matches.append(form)
        if step_matches:
            result.extend(step_matches)
            continue
        if _is_known_ats_host(frame.url):
            body = frame.locator("body")
            if _count_contact_fields(body) >= 2:
                result.append(body)
    return result


def inspect_form(
    page: Any,
    profile: Mapping[str, Any],
    resume: Path | None,
    scope: str | None = None,
    *,
    form_scopes_fn: Callable[[Any, str | None], list[Any]] | None = None,
) -> dict[str, Any]:
    """Inspect a candidate form without mutating DOM state."""
    resolve_scopes = form_scopes_fn or form_scopes
    scopes = resolve_scopes(page, scope)
    if not scopes:
        return {"status": "no_form", "to_fill": [], "to_upload": 0, "manual_required": [], "select_manual": []}
    if len(scopes) > 1:
        return {"status": "multiple_forms", "to_fill": [], "to_upload": 0, "manual_required": [], "select_manual": []}

    root = scopes[0]
    to_fill: list[str] = []
    to_upload = 0
    manual_required: list[str] = []
    select_manual: list[str] = []

    for locator in root.locator("input, textarea, select").all():
        try:
            info = locator.evaluate(FIELD_INFO)
            if info["type"] == "file":
                if resume and is_resume_input(info) and not info["value"]:
                    to_upload += 1
                continue
            if not locator.is_visible() or not locator.is_enabled():
                continue
            if info["tag"] != "select" and not locator.is_editable():
                continue
            if info["value"]:
                continue
            value = profile_value(info, profile)
            if value is None:
                if info["required"] and info["type"] not in BLOCKED_TYPES:
                    manual_required.append(info["label"] or info["name"] or "[unlabelled field]")
                continue
            if info["tag"] == "select":
                options = locator.locator("option").evaluate_all("es => es.map(e => ({label: e.label, value: e.value}))")
                exact = [o for o in options if norm(o["label"]) == norm(value)]
                if len(exact) == 1:
                    to_fill.append(info["label"] or info["name"] or "[select]")
                else:
                    select_manual.append(info["label"] or info["name"] or "[select]")
            else:
                to_fill.append(info["label"] or info["name"] or "[field]")
        except Exception:
            continue
    return {
        "status": "ok",
        "to_fill": to_fill,
        "to_upload": to_upload,
        "manual_required": manual_required,
        "select_manual": select_manual,
    }


def preview_autofill(
    page: Any,
    profile: Mapping[str, Any],
    resume: Path | None,
    scope: str | None = None,
    *,
    form_scopes_fn: Callable[[Any, str | None], list[Any]] | None = None,
) -> dict[str, Any]:
    plan = inspect_form(page, profile, resume, scope, form_scopes_fn=form_scopes_fn)
    if plan["status"] == "no_form":
        print("Preview: No recognizable application form found. Use 'scope CSS_SELECTOR' to target a custom container.")
        return plan
    if plan["status"] == "multiple_forms":
        print("Preview: Multiple candidate forms are visible. Use 'scope CSS_SELECTOR' to choose one.")
        return plan
    print(f"Preview: Would fill {len(plan['to_fill'])} field(s) and attach {plan['to_upload']} resume(s).")
    for label in plan["to_fill"]:
        print(f"  + Fill: {label}")
    for label in plan["select_manual"]:
        print(f"  ~ Select manually (no exact option match): {label}")
    for label in plan["manual_required"]:
        print(f"  ! Manual answer required: {label}")
    return plan


def autofill(
    page: Any,
    profile: Mapping[str, Any],
    resume: Path | None,
    scope: str | None = None,
    *,
    form_scopes_fn: Callable[[Any, str | None], list[Any]] | None = None,
) -> dict[str, int]:
    resolve_scopes = form_scopes_fn or form_scopes
    scopes = resolve_scopes(page, scope)
    if not scopes:
        print("No recognizable resume/application form. Open the application, then retry.")
        print("For a custom site, use 'scope CSS_SELECTOR' here or restart with --scope 'CSS SELECTOR'.")
        return {"filled": 0, "uploaded": 0}
    if len(scopes) > 1:
        print("More than one candidate form is visible. Use 'scope CSS_SELECTOR' (or --scope) to choose the intended form.")
        return {"filled": 0, "uploaded": 0}
    root = scopes[0]
    filled, uploaded = 0, 0
    for locator in root.locator("input, textarea, select").all():
        try:
            info = locator.evaluate(FIELD_INFO)
            if info["type"] == "file":
                # Hidden native file inputs are normal. Never replace an existing attachment.
                if resume and is_resume_input(info) and not info["value"]:
                    locator.set_input_files(str(resume), timeout=5000)
                    uploaded += 1
                    print("Attached resume.")
                continue
            if not locator.is_visible() or not locator.is_enabled():
                continue
            if info["tag"] != "select" and not locator.is_editable():
                continue
            if info["value"]:  # Preserve manual answers, defaults and parsed information for review.
                continue
            value = profile_value(info, profile)
            if value is None:
                if info["required"] and info["type"] not in BLOCKED_TYPES:
                    print(f"Manual answer required: {info['label'] or info['name'] or '[unlabelled field]'}")
                continue
            if info["tag"] == "select":
                options = locator.locator("option").evaluate_all("es => es.map(e => ({label: e.label, value: e.value}))")
                exact = [o for o in options if norm(o["label"]) == norm(value)]
                if len(exact) == 1:
                    locator.select_option(value=exact[0]["value"])
                else:
                    print(f"Select manually: {info['label']}")
                    continue
            else:
                locator.fill(value, timeout=3000)
            filled += 1
            print(f"Filled: {info['label']}")  # Do not print the applicant's answer.
        except Exception as exc:
            # Exception strings can contain typed data or URLs; avoid logging their contents.
            print(f"A field needs manual attention ({type(exc).__name__}).")
    print(f"Filled {filled} fields; attached {uploaded} resume(s). Review all parsed fields and dates.")
    return {"filled": filled, "uploaded": uploaded}


def detect_verification(page: Any, *, timeout: int = 5000) -> bool:
    """Detect security verification / bot-check pages across all frames."""
    try:
        top_title = page.title().strip().lower()
    except Exception:
        top_title = ""
    if top_title in VERIFICATION_TITLES:
        return True
    frames = getattr(page, "frames", None) or [page]
    saw_body = False
    first_timeout: Exception | None = None
    for idx, frame in enumerate(frames):
        try:
            ftitle = frame.title().strip().lower()
            if ftitle in VERIFICATION_TITLES:
                return True
        except Exception:
            pass
        try:
            body = frame.locator("body").inner_text(timeout=timeout if idx == 0 else 1500).lower()
            saw_body = True
        except Exception as exc:
            if idx == 0:
                first_timeout = exc
            continue
        if any(marker in body for marker in VERIFICATION_MARKERS):
            return True
    if not saw_body and first_timeout is not None:
        raise first_timeout
    return False


def evidence(page: Any) -> str | None:
    """A receipt signal, not an AI judgement. Scope excludes script/template text."""
    patterns = [
        r"your application (?:has been|was) (?:successfully )?submitted",
        r"application submitted",
        r"we.ve received your application",
        r"thank you for (?:applying|submitting your (?:application|cv))",
        r"you have successfully applied",
    ]
    for frame in page.frames:
        try:
            body = frame.locator("body").inner_text(timeout=2500)
        except Exception:
            continue
        for pattern in patterns:
            match = re.search(pattern, body, re.I)
            if match:
                return match.group(0)
    return None


def log_result(
    path: str | Path,
    url: str,
    status: str,
    receipt: str | None = None,
    screenshot: str | None = None,
    *,
    company: str | None = None,
    title: str | None = None,
    applied_url: str | None = None,
) -> None:
    target = Path(path)
    rows = load_json(target) if target.exists() else []
    entry: dict[str, Any] = {
        "time": datetime.now(timezone.utc).isoformat(),
        "job_url": url,
        "status": status,
        "receipt": receipt,
        "screenshot": screenshot,
    }
    if company:
        entry["company"] = company
    if title:
        entry["title"] = title
    if applied_url and canonical_url(applied_url) != canonical_url(url):
        entry["applied_url"] = applied_url
    rows.append(entry)
    save_json(target, rows)


def load_application_statuses(log_path: str | Path) -> dict[str, str]:
    """Return canonical URL -> latest application status (preserving submitted_by_user precedence)."""
    target = Path(log_path)
    if not target.is_file():
        return {}
    try:
        rows = load_json(target)
    except (OSError, ValueError):
        return {}
    if not isinstance(rows, list):
        return {}
    statuses: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        status = row.get("status")
        if not isinstance(status, str):
            continue
        for key in ("job_url", "applied_url"):
            raw_url = row.get(key)
            if not isinstance(raw_url, str) or not raw_url:
                continue
            try:
                canon = canonical_url(raw_url)
            except ValueError:
                continue
            if statuses.get(canon) != "submitted_by_user":
                statuses[canon] = status
    return statuses


def confirm_receipt(employer: str | None, url: str) -> bool:
    print(f"Application: {employer or urlsplit(url).hostname} | {url}")
    return input("Did you personally see the employer's submission receipt for this job? Type yes or no: ").strip().lower() == "yes"


def apply(
    args: Any,
    *,
    autofill_fn: Callable[..., dict[str, int]] | None = None,
    preview_fn: Callable[..., dict[str, Any]] | None = None,
) -> None:
    import playwright.sync_api as pw_sync

    sync_playwright = pw_sync.sync_playwright
    PlaywrightTimeoutError = pw_sync.TimeoutError

    run_autofill = autofill_fn or autofill
    run_preview = preview_fn or preview_autofill

    profile_path = Path(args.profile).resolve()
    profile = validate_profile(load_json(profile_path))
    url = args.url
    employer: str | None = None
    job_title: str | None = None
    if not url:
        jobs = load_json(args.jobs)["jobs"]
        if not args.job or not 1 <= args.job <= len(jobs):
            raise ValueError("Choose --job using the 1-based number printed by search, or provide --url")
        selected = jobs[args.job - 1]
        print(f"Selected job {args.job}: {selected.get('company', '')} | {selected.get('title', '')}")
        employer = selected.get("company")
        job_title = selected.get("title")
        url = selected["url"]
    validate_url(url)

    log_path = profile_path.parent / "application-log.json"
    if log_path.exists():
        previous = load_json(log_path)
        target_canon = canonical_url(url)
        statuses = {
            r["status"]
            for r in previous
            if isinstance(r, dict)
            and (
                canonical_url(r.get("job_url", "")) == target_canon
                or (r.get("applied_url") and canonical_url(r["applied_url"]) == target_canon)
            )
        }
        if "submitted_by_user" in statuses:
            print("This URL already has a submitted entry in application-log.json. Not reopening it.")
            return
        if "submitted_signal_detected" in statuses:
            print("An earlier session detected possible receipt text. Check the employer history before applying again.")

    resume: Path | None = None
    if profile.get("resume_file"):
        resume = resolve_resume_path(str(profile["resume_file"]), profile_path.parent).resolve()
        if not resume.is_file():
            raise ValueError("The configured resume_file does not exist")

    active_scope: str | None = getattr(args, "scope", None)
    applied_url: str = url
    verification_logged: set[str] = set()

    user_dir = profile_path.parent / ".browser-profile"
    print("Opening a dedicated local browser profile. Sign in in the browser when needed.")
    print("Navigate to the application form, then return here. No buttons are submitted automatically.")
    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(str(user_dir), headless=False)
        context.set_default_timeout(5000)
        page = context.pages[0] if context.pages else context.new_page()
        try:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except PlaywrightTimeoutError:
                print("Navigation timed out. Inspect the browser, then use check, open, or skip.")
            except Exception as exc:
                print(f"Navigation failed ({type(exc).__name__}). Inspect the browser, then use open or skip.")

            while True:
                print("\nTabs:")
                pages = [p for p in context.pages if not p.is_closed()]
                if not pages:
                    print("All browser tabs were closed.")
                    log_result(
                        log_path, url, "awaiting_manual_completion",
                        company=employer, title=job_title, applied_url=applied_url,
                    )
                    break
                for i, tab in enumerate(pages, 1):
                    print(f"  {i}: {tab.title()} | {urlsplit(tab.url).hostname}")
                if active_scope:
                    print(f"Active form scope: {active_scope}")
                print("If a tab shows security verification, complete it in the browser, then use check.")
                raw_command = input(
                    "Enter: check/preview/fill/verify [tab], scope [selector|clear], open, skip, done, or quit: "
                ).strip()
                if not raw_command:
                    continue
                parts = raw_command.split(None, 1)
                action = parts[0].lower()
                rest = parts[1].strip() if len(parts) > 1 else ""

                if action in {"quit", "q"}:
                    log_result(
                        log_path, url, "awaiting_manual_completion",
                        company=employer, title=job_title, applied_url=applied_url,
                    )
                    break
                if action == "done":
                    if confirm_receipt(employer, applied_url):
                        log_result(
                            log_path, url, "submitted_by_user",
                            company=employer, title=job_title, applied_url=applied_url,
                        )
                        break
                    print("Use verify to detect a receipt, or quit to record an unfinished application.")
                    continue
                if action == "skip":
                    log_result(
                        log_path, url, "skipped_by_user",
                        company=employer, title=job_title, applied_url=applied_url,
                    )
                    print("Recorded as skipped. Run apply --job NUMBER for another job.")
                    break
                if action == "scope":
                    if not rest:
                        print(f"Current scope: {active_scope or '(automatic)'}. Use 'scope CSS_SELECTOR' or 'scope clear'.")
                    elif rest.lower() in {"clear", "none", "auto"}:
                        active_scope = None
                        print("Cleared custom form scope; back to automatic detection.")
                    else:
                        active_scope = rest
                        print(f"Updated form scope to: {active_scope}")
                    continue
                if action == "open":
                    destination = input("Paste the employer's application URL: ").strip()
                    try:
                        validate_url(destination)
                    except ValueError as exc:
                        print(f"Invalid URL: {exc}")
                        continue
                    try:
                        pages[-1].goto(destination, wait_until="domcontentloaded", timeout=30000)
                        applied_url = destination
                    except PlaywrightTimeoutError:
                        applied_url = destination
                        print("Navigation timed out. Inspect the browser before continuing.")
                    except Exception as exc:
                        print(f"Could not open URL ({type(exc).__name__}). Inspect the browser or try another URL.")
                    continue
                if action not in {"check", "preview", "fill", "verify"}:
                    print("Unknown command.")
                    continue
                try:
                    index = int(rest) - 1 if rest else len(pages) - 1
                    if not 0 <= index < len(pages):
                        raise ValueError()
                except ValueError:
                    print("Choose a tab number from the list.")
                    continue
                page = pages[index]
                try:
                    blocked = detect_verification(page, timeout=5000)
                except PlaywrightTimeoutError:
                    print("Page is still loading. Inspect it, then use check again.")
                    continue
                except Exception:
                    print("Could not inspect page yet. Try check again after it settles.")
                    continue
                if blocked:
                    check_key = canonical_url(page.url) if page.url.startswith("https://") else url
                    if check_key not in verification_logged:
                        log_result(
                            log_path, url, "needs_manual_verification",
                            company=employer, title=job_title, applied_url=applied_url,
                        )
                        verification_logged.add(check_key)
                    print("Security verification detected. Complete it in the browser, then use check.")
                    print("If it stays blocked, use open with the employer's direct application URL, or skip.")
                    continue
                if action == "check":
                    print("No recognized verification page detected. Inspect the form before using preview or fill.")
                    continue
                if action == "preview":
                    print(f"Target: {page.url}")
                    run_preview(page, profile, resume, active_scope)
                    continue
                if action == "fill":
                    # Prevent accidental entry in unrelated pages opened during sign-in.
                    print(f"Target: {page.url}")
                    if input("Fill this application using your profile/resume? [y/N] ").strip().lower() == "y":
                        run_autofill(page, profile, resume, active_scope)
                        print("Complete remaining fields and click the employer's final Submit button yourself.")
                else:
                    receipt = evidence(page)
                    if receipt:
                        print(f"Tab {index + 1}: {page.url} | Matched text: {receipt}")
                        confirm_url = page.url if page.url.startswith("https://") else applied_url
                        if not confirm_receipt(employer, confirm_url):
                            print("Application is still open for review.")
                            continue
                        folder = profile_path.parent / "receipts"
                        folder.mkdir(exist_ok=True)
                        shot = folder / (datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".png")
                        page.screenshot(path=str(shot), full_page=False)
                        log_result(
                            log_path, url, "submitted_by_user", receipt, str(shot),
                            company=employer, title=job_title, applied_url=confirm_url,
                        )
                        print(f"Receipt text detected: {receipt}. Saved screenshot and log. Check remaining employer tasks.")
                        break
                    print("No known receipt text detected. Complete any remaining steps; do not assume success.")
        finally:
            context.close()
