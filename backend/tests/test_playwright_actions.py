import asyncio

import pytest
from playwright.async_api import Error as PlaywrightError

from app.browser.playwright_driver import PlaywrightDriver
from app.core.events import Action, Target
from app.interfaces.browser import Element


async def element(driver: PlaywrightDriver, name: str) -> Element:
    observation = await driver.observe()
    return next(e for e in observation.elements if e.name == name)


async def perform(
    driver: PlaywrightDriver, kind: str, name: str | None = None, value: str | None = None
) -> None:
    ref = (await element(driver, name)).ref if name else None
    action = Action.model_validate(
        {
            "action": kind,
            "target": {"ref": ref},
            "value": value,
            "rationale": "Perform the demo step.",
        }
    )
    result = await driver.act(action)
    assert result.ok, result


async def test_search_and_link(driver: PlaywrightDriver, testsite: str) -> None:
    await driver.navigate(testsite + "/index.html")
    await perform(driver, "type", "Search products", "Travel Mug")
    await perform(driver, "click", "Search")
    text = (await driver.observe()).text_excerpt
    assert "Travel Mug" in text and "Desk Lamp" not in text
    link = await element(driver, "Form")
    result = await driver.act(
        Action(action="click", target=Target(ref=link.ref), rationale="Open form.")
    )
    assert result.ok and result.navigated
    assert (await driver.observe()).title == "Demo Form"


async def test_fill_form_select_checkbox_and_submit(
    driver: PlaywrightDriver, testsite: str
) -> None:
    await driver.navigate(testsite + "/form.html")
    await perform(driver, "type", "Name", "Demo Example")
    await perform(driver, "type", "Email", "demo@example.test")
    await perform(driver, "type", "Project", "Priority")
    await perform(driver, "type", "Project", "standard")
    await perform(driver, "click", "Newsletter")
    await perform(driver, "type", "Notes", "Only fake notes.")
    await perform(driver, "click", "Submit form")
    page = driver.get_active_page()
    assert await page.locator("#name").input_value() == "Demo Example"
    assert await page.locator("#project").input_value() == "standard"
    assert await page.locator("#newsletter").is_checked()
    assert "submitted successfully" in (await driver.observe()).text_excerpt


@pytest.mark.parametrize(
    ("password", "success"), [("demo-pass-only", True), ("wrong-demo-pass", False)]
)
async def test_login_redaction(
    driver: PlaywrightDriver,
    testsite: str,
    password: str,
    success: bool,
    caplog: pytest.LogCaptureFixture,
) -> None:
    await driver.navigate(testsite + "/login.html")
    await perform(driver, "type", "Username", "demo-user")
    ref = (await element(driver, "Password")).ref
    result = await driver.act(
        Action(
            action="type",
            target=Target(ref=ref),
            value=password,
            rationale="Fill the fake password.",
        )
    )
    assert result.ok and "typed into password field" in result.summary
    assert password not in result.model_dump_json()
    assert password not in (await driver.observe()).model_dump_json()
    await perform(driver, "click", "Sign in")
    observation = await driver.observe()
    assert ("Welcome, demo-user" in observation.text_excerpt) == success
    assert password not in observation.to_prompt_text() and password not in caplog.text
    extracted = await driver.act(Action(action="extract", rationale="Read the page."))
    assert password not in extracted.summary


async def test_scroll_and_load_more(driver: PlaywrightDriver, testsite: str) -> None:
    await driver.navigate(testsite + "/long.html")
    for direction in ("down", "up", "bottom", "top"):
        result = await driver.act(
            Action(action="scroll", value=direction, rationale="Move the page.")
        )
        assert result.ok and result.summary == "Page scrolled."
    await perform(driver, "click", "Load more")
    assert "Loaded more fake content" in await driver.get_text()
    assert await driver.get_active_page().evaluate("scrollY") > 0


async def test_table_and_target_extract(driver: PlaywrightDriver, testsite: str) -> None:
    await driver.navigate(testsite + "/table.html")
    result = await driver.act(Action(action="extract", rationale="Read inventory."))
    assert result.ok and len(result.summary) <= 3000
    for name in (
        "Travel Mug",
        "Desk Lamp",
        "Notebook",
        "Pen Set",
        "Mouse Pad",
        "Water Bottle",
        "Cable Organizer",
        "Book Stand",
    ):
        assert name in result.summary
    ref = (await element(driver, "Home")).ref
    result = await driver.act(
        Action(action="extract", target=Target(ref=ref), rationale="Read link.")
    )
    assert result.ok and result.summary == "Home"


async def test_contenteditable_and_keyboard(driver: PlaywrightDriver, testsite: str) -> None:
    await driver.navigate(testsite + "/form.html")
    await driver.get_active_page().evaluate("""() => {
      const el=document.createElement('div'); el.contentEditable='true';
      el.setAttribute('aria-label','Editor'); el.textContent='Old text';
      document.querySelector('main').append(el);
    }""")
    await perform(driver, "type", "Editor", "New demo text")
    assert (
        await driver.get_active_page().locator("[contenteditable=true]").inner_text()
        == "New demo text"
    )
    await perform(driver, "type", value="Tab")
    await perform(driver, "type", "Name", "Enter")  # A targeted value is literal text, not a key.
    assert await driver.get_active_page().locator("#name").input_value() == "Enter"


async def test_stale_removed_hidden_and_unknown_refs(
    driver: PlaywrightDriver, testsite: str
) -> None:
    await driver.navigate(testsite + "/form.html")
    old = await element(driver, "Name")
    await driver.observe()
    result = await driver.act(
        Action(
            action="type",
            target=Target(ref=old.ref),
            value="not-entered",
            rationale="Try the old ref.",
        )
    )
    assert result.error_code == "STALE_REF"
    assert await driver.get_active_page().locator("#name").input_value() == ""
    current = await element(driver, "Name")
    await driver.get_active_page().locator("#name").evaluate("el => el.style.opacity='0'")
    assert (
        await driver.act(
            Action(action="click", target=Target(ref=current.ref), rationale="Try ref.")
        )
    ).error_code == "NOT_VISIBLE"
    await driver.get_active_page().locator("#name").evaluate("el => el.remove()")
    assert (
        await driver.act(
            Action(action="click", target=Target(ref=current.ref), rationale="Try ref.")
        )
    ).error_code == "NOT_FOUND"
    assert (
        await driver.act(Action(action="click", target=Target(ref="e999999"), rationale="Try ref."))
    ).error_code == "NOT_FOUND"


@pytest.mark.parametrize("url", ["file:///etc/passwd", "javascript:alert(1)", "chrome://settings"])
async def test_blocked_action(driver: PlaywrightDriver, url: str) -> None:
    result = await driver.act(
        Action(action="navigate", value=url, rationale="Try blocked navigation.")
    )
    assert not result.ok and result.error_code == "BLOCKED_URL"


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        ("click", None),
        ("type", "text"),
        ("scroll", "sideways"),
        ("wait", "nan"),
        ("wait", "not-a-number"),
        ("navigate", None),
    ],
)
async def test_invalid_actions(driver: PlaywrightDriver, kind: str, value: str | None) -> None:
    result = await driver.act(
        Action.model_validate({"action": kind, "value": value, "rationale": "Test."})
    )
    assert not result.ok and result.error_code == "INVALID_ACTION"


async def test_wait_and_cancel_closes_browser(driver: PlaywrightDriver) -> None:
    browser = driver.get_context().browser
    assert (await driver.act(Action(action="wait", value="0", rationale="Wait briefly."))).ok
    task = asyncio.create_task(driver.act(Action(action="wait", value="10", rationale="Wait.")))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert browser is not None and not browser.is_connected()
    assert not browser.contexts
    await driver.close()


async def test_timeout_and_sanitized_browser_error(
    driver: PlaywrightDriver, testsite: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    await driver.navigate(testsite + "/form.html")
    button = await element(driver, "Submit form")
    await driver.get_active_page().evaluate("""() => {
      const cover=document.createElement('div');
      cover.style='position:fixed;inset:0;z-index:9999;background:white';document.body.append(cover);
    }""")
    driver.settings.action_timeout_ms = 150
    result = await driver.act(
        Action(action="click", target=Target(ref=button.ref), rationale="Click.")
    )
    assert result.error_code == "TIMEOUT" and "Call log" not in result.summary

    def broken_page() -> None:
        raise PlaywrightError("SECRET_RAW_DIAGNOSTICS")

    monkeypatch.setattr(driver, "get_active_page", broken_page)
    result = await driver.act(Action(action="done", rationale="Finish."))
    assert result.error_code == "BROWSER_ERROR" and "SECRET_RAW_DIAGNOSTICS" not in result.summary
