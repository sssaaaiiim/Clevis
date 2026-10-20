# Local-site live smoke goals

All data and credentials are fake. Start the API on port 8000 and the local test site on port 8765.
Run these in headless mode with a configured OpenRouter key/model. Each curl returns a runId; stream
its events with `curl -N http://localhost:8000/api/runs/<runId>/events`.

## 1. search

Goal: Open http://localhost:8765/index.html, search for Mug using the search box and Search button, and report the first visible result.

Expected result: Travel Mug; $12.00

Expected maximum steps (including done): 6.

```bash
curl -sS http://localhost:8000/api/runs -H 'Content-Type: application/json' -d '{"goal": "Open http://localhost:8765/index.html, search for Mug using the search box and Search button, and report the first visible result.", "mode": "headless"}'
```

## 2. form

Goal: Open http://localhost:8765/form.html. Fill Name with Demo Visitor, Email with visitor@example.test, Project with Priority, check Newsletter, and fill Notes with Fake demo inquiry. Submit the contact form and report its confirmation text.

Expected result: Form submitted successfully.

Expected maximum steps (including done): 10.

```bash
curl -sS http://localhost:8000/api/runs -H 'Content-Type: application/json' -d '{"goal": "Open http://localhost:8765/form.html. Fill Name with Demo Visitor, Email with visitor@example.test, Project with Priority, check Newsletter, and fill Notes with Fake demo inquiry. Submit the contact form and report its confirmation text.", "mode": "headless"}'
```

## 3. table

Goal: Open http://localhost:8765/table.html and report the product with the lowest price, including its name and price.

Expected result: Notebook; 5.00

Expected maximum steps (including done): 4.

```bash
curl -sS http://localhost:8000/api/runs -H 'Content-Type: application/json' -d '{"goal": "Open http://localhost:8765/table.html and report the product with the lowest price, including its name and price.", "mode": "headless"}'
```

## 4. load-more

Goal: Start at http://localhost:8765/index.html. Follow the Long page link, click Load more, and report the text of the last item that was added.

Expected result: Loaded more fake content.

Expected maximum steps (including done): 7.

```bash
curl -sS http://localhost:8000/api/runs -H 'Content-Type: application/json' -d '{"goal": "Start at http://localhost:8765/index.html. Follow the Long page link, click Load more, and report the text of the last item that was added.", "mode": "headless"}'
```

## 5. login

Goal: Open http://localhost:8765/login.html. On this local fake demo site, log in with the demo credentials username demo-user and password demo-pass-only, explicitly provided here in the goal. Report the welcome message.

Expected result: Welcome, demo-user

Expected maximum steps (including done): 7.

```bash
curl -sS http://localhost:8000/api/runs -H 'Content-Type: application/json' -d '{"goal": "Open http://localhost:8765/login.html. On this local fake demo site, log in with the demo credentials username demo-user and password demo-pass-only, explicitly provided here in the goal. Report the welcome message.", "mode": "headless"}'
```

The automated live suite substitutes an isolated local HTTP-server port, uses the same goals, and asserts the expected result text. Expected step counts are guidance; configured budgets remain authoritative.
