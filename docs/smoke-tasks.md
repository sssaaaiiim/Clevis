# Phase 1 smoke tasks

Open the Starting URL `http://localhost:8000/test-page.html` in the existing frontend (the test page is served from the backend). Run each goal in headless mode. For the Compose browser, the backend resolves the same page at `http://backend:8000/test-page.html`.

1. **Search a page:** Search for `Travel Mug` and report the matching product and price.
2. **Fill a form:** Enter `Taylor Example` and `taylor@example.test` in the contact form, then submit it.
3. **Extract a table:** Return each product name, category, and price from the product table.
4. **Navigate two pages:** Open the second local test page, report its page-two marker, then return to the main page.
5. **Scroll and extract:** Scroll to the lower-page content and report the sentence beginning with `Scroll target`.

For each run, check that the plan appears before the first page observation, proposed/executed actions are visible in the timeline, preview frames update, and completion or a clear failure reason is reported.
