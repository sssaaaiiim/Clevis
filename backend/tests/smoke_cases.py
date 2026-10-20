from dataclasses import dataclass


@dataclass(frozen=True)
class SmokeCase:
    name: str
    goal: str
    expected: tuple[str, ...]
    max_steps: int


SMOKE_CASES = [
    SmokeCase(
        "search",
        "Open {base}/index.html, search for Mug using the search box and Search "
        "button, and report the first visible result.",
        ("Travel Mug", "$12.00"),
        6,
    ),
    SmokeCase(
        "form",
        "Open {base}/form.html. Fill Name with Demo Visitor, Email with "
        "visitor@example.test, Project with Priority, check Newsletter, and fill Notes with "
        "Fake demo inquiry. Submit the contact form and report its confirmation text.",
        ("Form submitted successfully.",),
        10,
    ),
    SmokeCase(
        "table",
        "Open {base}/table.html and report the product with the lowest price, "
        "including its name and price.",
        ("Notebook", "5.00"),
        4,
    ),
    SmokeCase(
        "load-more",
        "Start at {base}/index.html. Follow the Long page link, click Load more, "
        "and report the text of the last item that was added.",
        ("Loaded more fake content.",),
        7,
    ),
    SmokeCase(
        "login",
        "Open {base}/login.html. On this local fake demo site, log in with the "
        "demo credentials username demo-user and password demo-pass-only, explicitly "
        "provided here in the goal. Report the welcome message.",
        ("Welcome, demo-user",),
        7,
    ),
]
