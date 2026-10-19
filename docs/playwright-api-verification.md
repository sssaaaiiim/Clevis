# Playwright API verification

Installed and pinned version: **1.64.0**.

The driver uses the installed async Python API. Signatures and bundled documentation were checked in `playwright/async_api/_generated.py`; the async manager is in `_context_manager.py`. Event names and callback types were checked against the generated `on` overloads. No deprecated `page.accessibility` API is used.

Official references: [BrowserType](https://playwright.dev/python/docs/api/class-browsertype), [Browser](https://playwright.dev/python/docs/api/class-browser), [BrowserContext](https://playwright.dev/python/docs/api/class-browsercontext), [Page](https://playwright.dev/python/docs/api/class-page), [Locator](https://playwright.dev/python/docs/api/class-locator), [Keyboard](https://playwright.dev/python/docs/api/class-keyboard), [Dialog](https://playwright.dev/python/docs/api/class-dialog).

| Installed async API | Verified signature / property |
|---|---|
| `PlaywrightContextManager.start` | `(self) -> playwright.async_api._generated.Playwright` |
| `PlaywrightContextManager.__aexit__` | `(self, *args: Any) -> None` |
| `Playwright.stop` | `(self) -> None` |
| `Playwright.chromium` | `property` |
| `BrowserType.launch` | `(self, *, args: Sequence[str] / None = None, artifacts_dir: str / pathlib.Path / None = None, channel: str / None = None, chromium_sandbox: bool / None = None, downloads_path: str / pathlib.Path / None = None, env: Dict[str, str / float / bool] / None = None, executable_path: str / pathlib.Path / None = None, firefox_user_prefs: Dict[str, str / float / bool] / None = None, handle_sighup: bool / None = None, handle_sigint: bool / None = None, handle_sigterm: bool / None = None, headless: bool / None = None, ignore_default_args: bool / Sequence[str] / None = None, proxy: playwright._impl._api_structures.ProxySettings / None = None, slow_mo: float / None = None, timeout: float / datetime.timedelta / None = None, traces_dir: str / pathlib.Path / None = None) -> 'Browser'` |
| `Browser.new_context` | `(self, *, accept_downloads: bool / None = None, base_url: str / None = None, bypass_csp: bool / None = None, client_certificates: Sequence[playwright._impl._api_structures.ClientCertificate] / None = None, color_scheme: Literal['dark', 'light', 'no-preference', 'null'] / None = None, contrast: Literal['more', 'no-preference', 'null'] / None = None, default_browser_type: str / None = None, device_scale_factor: float / None = None, extra_http_headers: Dict[str, str] / None = None, forced_colors: Literal['active', 'none', 'null'] / None = None, geolocation: playwright._impl._api_structures.Geolocation / None = None, has_touch: bool / None = None, http_credentials: playwright._impl._api_structures.HttpCredentials / Sequence[playwright._impl._api_structures.HttpCredentials] / None = None, ignore_https_errors: bool / None = None, is_mobile: bool / None = None, java_script_enabled: bool / None = None, locale: str / None = None, no_viewport: bool / None = None, offline: bool / None = None, permissions: Sequence[str] / None = None, proxy: playwright._impl._api_structures.ProxySettings / None = None, record_har_content: Literal['attach', 'embed', 'omit'] / None = None, record_har_mode: Literal['full', 'minimal'] / None = None, record_har_omit_content: bool / None = None, record_har_path: str / pathlib.Path / None = None, record_har_url_filter: str / Pattern[str] / None = None, record_video_dir: str / pathlib.Path / None = None, record_video_fps: int / None = None, record_video_size: playwright._impl._api_structures.ViewportSize / None = None, reduced_motion: Literal['no-preference', 'null', 'reduce'] / None = None, screen: playwright._impl._api_structures.ViewportSize / None = None, service_workers: Literal['allow', 'block'] / None = None, storage_state: str / pathlib.Path / playwright._impl._api_structures.StorageState / None = None, strict_selectors: bool / None = None, timezone_id: str / None = None, user_agent: str / None = None, viewport: playwright._impl._api_structures.ViewportSize / None = None) -> 'BrowserContext'` |
| `Browser.close` | `(self, *, reason: str / None = None) -> None` |
| `Browser.is_connected` | `(self) -> bool` |
| `Browser.contexts` | `property` |
| `BrowserContext.grant_permissions` | `(self, permissions: Sequence[str], *, origin: str / None = None) -> None` |
| `BrowserContext.new_page` | `(self) -> 'Page'` |
| `BrowserContext.close` | `(self, *, reason: str / None = None) -> None` |
| `BrowserContext.pages` | `property` |
| `BrowserContext.browser` | `property` |
| `BrowserContext.on` | `(self, event: str, f: Callable[..., Awaitable[NoneType] / None]) -> None` |
| `BrowserContext.set_default_timeout` | `(self, timeout: float / datetime.timedelta) -> None` |
| `BrowserContext.set_default_navigation_timeout` | `(self, timeout: float / datetime.timedelta) -> None` |
| `BrowserContext.add_cookies` | `(self, cookies: Sequence[playwright._impl._api_structures.SetCookieParam]) -> None` |
| `BrowserContext.cookies` | `(self, urls: str / Sequence[str] / None = None) -> List[playwright._impl._api_structures.Cookie]` |
| `Page.goto` | `(self, url: str, *, referer: str / None = None, timeout: float / datetime.timedelta / None = None, wait_until: Literal['commit', 'domcontentloaded', 'load', 'networkidle'] / None = None) -> ForwardRef('Response') / None` |
| `Page.wait_for_load_state` | `(self, state: Literal['domcontentloaded', 'load', 'networkidle'] / None = None, *, timeout: float / datetime.timedelta / None = None) -> None` |
| `Page.evaluate` | `(self, expression: str, arg: Any / None = None) -> Any` |
| `Page.locator` | `(self, selector: str, *, has: ForwardRef('Locator') / None = None, has_not: ForwardRef('Locator') / None = None, has_not_text: str / Pattern[str] / None = None, has_text: str / Pattern[str] / None = None) -> 'Locator'` |
| `Page.is_closed` | `(self) -> bool` |
| `Page.close` | `(self, *, reason: str / None = None, run_before_unload: bool / None = None) -> None` |
| `Page.on` | `(self, event: str, f: Callable[..., Awaitable[NoneType] / None]) -> None` |
| `Page.keyboard` | `property` |
| `Page.url` | `property` |
| `Page.viewport_size` | `property` |
| `Locator.count` | `(self) -> int` |
| `Locator.evaluate` | `(self, expression: str, arg: Any / None = None, *, timeout: float / datetime.timedelta / None = None) -> Any` |
| `Locator.scroll_into_view_if_needed` | `(self, *, timeout: float / datetime.timedelta / None = None) -> None` |
| `Locator.click` | `(self, *, button: Literal['left', 'middle', 'right'] / None = None, click_count: int / None = None, delay: float / None = None, force: bool / None = None, modifiers: Sequence[Literal['Alt', 'Control', 'ControlOrMeta', 'Meta', 'Shift']] / None = None, no_wait_after: bool / None = None, position: playwright._impl._api_structures.Position / None = None, scroll: Literal['auto', 'none'] / None = None, steps: int / None = None, timeout: float / datetime.timedelta / None = None, trial: bool / None = None) -> None` |
| `Locator.focus` | `(self, *, timeout: float / datetime.timedelta / None = None) -> None` |
| `Locator.fill` | `(self, value: str, *, force: bool / None = None, no_wait_after: bool / None = None, timeout: float / datetime.timedelta / None = None) -> None` |
| `Locator.press` | `(self, key: str, *, delay: float / None = None, no_wait_after: bool / None = None, timeout: float / datetime.timedelta / None = None) -> None` |
| `Locator.press_sequentially` | `(self, text: str, *, delay: float / None = None, no_wait_after: bool / None = None, timeout: float / datetime.timedelta / None = None) -> None` |
| `Locator.select_option` | `(self, value: str / Sequence[str] / None = None, *, element: ForwardRef('ElementHandle') / Sequence[ForwardRef('ElementHandle')] / None = None, force: bool / None = None, index: int / Sequence[int] / None = None, label: str / Sequence[str] / None = None, no_wait_after: bool / None = None, timeout: float / datetime.timedelta / None = None) -> List[str]` |
| `Locator.input_value` | `(self, *, timeout: float / datetime.timedelta / None = None) -> str` |
| `Locator.is_checked` | `(self, *, timeout: float / datetime.timedelta / None = None) -> bool` |
| `Locator.inner_text` | `(self, *, timeout: float / datetime.timedelta / None = None) -> str` |
| `Keyboard.press` | `(self, key: str, *, delay: float / None = None) -> None` |
| `Dialog.type` | `property` |
| `Dialog.dismiss` | `(self) -> None` |
| `Frame.parent_frame` | `property` |
| `Frame.page` | `property` |
