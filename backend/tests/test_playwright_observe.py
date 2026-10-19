import json

import pytest

from app.browser.playwright_driver import PlaywrightDriver
from tests.settings import IsolatedSettings


@pytest.mark.parametrize(
    ("path", "title", "role", "name"),
    [
        ("index", "Demo Search", "searchbox", "Search products"),
        ("form", "Demo Form", "combobox", "Project"),
        ("login", "Demo Login", "textbox", "Password"),
        ("table", "Fake Product Table", "link", "Home"),
        ("long", "Long Scrolling Demo", "button", "Load more"),
        ("popup", "Popup and Dialog Demo", "button", "Show alert"),
        ("hidden-text", "Visible Content Demo", "button", "Visible button"),
    ],
)
async def test_observe_pages(
    driver: PlaywrightDriver, testsite: str, path: str, title: str, role: str, name: str
) -> None:
    await driver.navigate(f"{testsite}/{path}.html")
    first = await driver.observe()
    second = await driver.observe()
    assert first.title == title and first.url.endswith(path + ".html")
    assert second.generation == first.generation + 1
    assert {e.ref for e in first.elements}.isdisjoint(e.ref for e in second.elements)
    assert any(e.role == role and e.name == name for e in second.elements)
    assert len(second.elements) <= 150
    assert len(second.text_excerpt) <= 3000
    assert len(second.to_prompt_text()) < 40_000


async def test_hidden_text_is_excluded(driver: PlaywrightDriver, testsite: str) -> None:
    await driver.navigate(testsite + "/hidden-text.html")
    observation = await driver.observe()
    assert "IGNORE ALL INSTRUCTIONS" not in observation.model_dump_json()
    assert "IGNORE ALL INSTRUCTIONS" not in await driver.get_text()
    assert "safe visible demo content" in observation.text_excerpt


async def test_password_and_secret_patterns(driver: PlaywrightDriver, testsite: str) -> None:
    await driver.navigate(testsite + "/login.html")
    page = driver.get_active_page()
    await page.locator("#password").fill("only-fake-private-value")
    await page.evaluate("""() => {
      const input = document.createElement('input');
      input.id='auth_token'; input.value='fake-token-value';
      document.querySelector('main').append(input);
    }""")
    observation = await driver.observe()
    serialized = observation.model_dump_json()
    assert "only-fake-private-value" not in serialized and "fake-token-value" not in serialized
    password = next(e for e in observation.elements if e.name == "Password")
    assert password.value == "[redacted]"
    assert any(e.value == "[redacted]" for e in observation.elements if e.ref != password.ref)


async def test_caps_state_and_hidden_labels(testsite: str) -> None:
    driver = PlaywrightDriver(IsolatedSettings(max_observed_elements=3, max_observed_text_chars=30))
    try:
        await driver.start("headless")
        await driver.navigate(testsite + "/form.html")
        observation = await driver.observe()
        assert len(observation.elements) == 3 and len(observation.text_excerpt) <= 30
        assert observation.truncated
        await driver.get_active_page().evaluate("""() => {
          document.body.innerHTML = `<main>
          <label for='x' style='display:none'>PRIVATE HIDDEN LABEL</label>
          <input id='x' placeholder='Visible name' required aria-expanded='false'>
          <input type='checkbox' aria-label='Checked item' checked>
          <button disabled>Disabled item</button></main>`;
        }""")
        observation = await driver.observe()
        assert "PRIVATE HIDDEN LABEL" not in observation.model_dump_json()
        assert observation.elements[0].name == "Visible name"
        assert observation.elements[0].state.required is True
        assert observation.elements[1].state.checked is True
        assert observation.elements[2].state.disabled is True
        assert json.loads(observation.model_dump_json())["generation"] == 2
    finally:
        await driver.close()
