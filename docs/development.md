# Development and deployment

[Project overview](../README.md) · [Architecture](architecture.md) · [Catalog coverage](catalog.md)

## Local application

Use Python 3.13 and the pinned dependencies in `requirements.txt`:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1`. The compressed catalog is included and unpacks into ignored `.cache/` storage on first run. Guest matching and planning need no Firebase configuration. Images and external instruction pages still need internet access.

For frontend development, the same interface is available through the standalone server:

```bash
python -m brickfinder.web --port 8502
```

Open `http://127.0.0.1:8502`. Its HTTP endpoints and the Streamlit request bridge use the same public service and private session implementation. The deployed entry point remains `app.py`.

The [dev container](../.devcontainer/devcontainer.json) uses Python 3.13 and installs the pinned Python requirements. Its forwarded port opens the app on 8501. Node and Java are only needed for Firebase emulator tests; the application itself has no Node build step.

## Optional Firebase configuration

Guest mode remains available without configuration. To enable cloud saves in your own deployment:

1. Select a dedicated Firebase project and enable **Authentication → Email/Password**.
2. Create a Cloud Firestore `(default)` Standard database in your chosen region. The repository configuration uses `us-east1`; choose the location deliberately before creation.
3. Install development tools with `npm ci --ignore-scripts`, sign in through the Firebase CLI, then deploy the checked-in Auth configuration, Firestore Rules, and indexes to your project:

   ```bash
   npx firebase login
   npx firebase deploy --only auth,firestore --project YOUR_PROJECT_ID
   ```

4. Copy [`.streamlit/secrets.toml.example`](../.streamlit/secrets.toml.example) to the ignored `.streamlit/secrets.toml` and set:

   ```toml
   FIREBASE_PROJECT_ID = "your-project-id"
   FIREBASE_API_KEY = "your-firebase-web-api-key"
   ```

   Environment variables with the same names also work. No service-account file is needed. Never commit local secrets, tokens, or credentials.
5. Verify signup, Save, sign out, sign in, and Load. Check that a second user cannot access the first user's collections and that conflicting saves preserve the local draft.

`.firebaserc` defaults to the non-production `demo-rebuilt` project for local development. Always pass an explicit project ID for hosted configuration changes. The app reads Firebase settings from its environment/Streamlit secrets, independently of this CLI default.

Sign-in state lasts for the active server session. Account verification, password recovery, OAuth, and persistent sign-in are outside the current implementation.

## Tests

The ordinary suite and JavaScript transport checks require no hosted credentials:

```bash
python -m unittest discover -s tests -v
node --test tests/test_transport.cjs
```

The Python suite skips four integration cases unless emulator hosts are configured. To run those cases plus the actual Firestore Security Rules tests, use **Node.js 24.12+** and **Java 21+**:

```bash
npm ci --ignore-scripts
npx firebase emulators:exec --only auth,firestore --project demo-rebuilt "node --test tests/test_rules.mjs && python -m unittest tests.test_firebase_emulator -v"
```

The emulator tests use disposable accounts and a demo project, with no hosted credentials. They cover CRUD, rename/name release, Save as identities, atomic failure, revision conflicts, concurrent case-insensitive names, and guest/cross-user access denial.

The [CI workflow](../.github/workflows/tests.yml) runs the Python suite, JavaScript syntax/transport checks, and Firebase emulator suite on Python 3.13, Node 24, and Java 21.

### Local account-flow development

Start the emulators in one terminal:

```bash
npx firebase emulators:start --only auth,firestore --project demo-rebuilt
```

In a second terminal, launch Streamlit with local configuration:

```bash
FIREBASE_PROJECT_ID=demo-rebuilt \
FIREBASE_API_KEY=emulator-key \
FIREBASE_AUTH_EMULATOR_HOST=127.0.0.1:9099 \
FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 \
python -m streamlit run app.py
```

Both emulator hosts must be loopback addresses and configured together. These accounts and records are temporary emulator data.

## Benchmarks

```bash
python scripts/benchmark.py
python scripts/benchmark_planner.py
```

Both commands print JSON. To record a new measurement deliberately:

```bash
python scripts/benchmark.py --output data/demo_results.json
python scripts/benchmark_planner.py --output data/planner_results.json
```

Reports include the Python version, architecture, collection, target/mode, counts, and elapsed times. The planner report also identifies the catalog fingerprint and solution status. Keep the environment context with any performance claim. Local measurements are not hosted latency guarantees.

## Streamlit Community Cloud

The public demo is [brick-finder.streamlit.app](https://brick-finder.streamlit.app/), deployed from `main` and `app.py`. Updates to `main` update the hosted app.

For another deployment, choose this repository/fork, `main`, and `app.py` in Streamlit Community Cloud. Use Python 3.13. Guest mode needs no secrets. For cloud saves, add the two Firebase values above under **App settings → Secrets**; the ignored local file is not uploaded by Git.

After deployment, verify a fresh browser session:

- Load Example 1 and find its exact-color complete build.
- Switch to flexible colors and inspect a substitution breakdown.
- Open a complete build and generate a dismantling plan.
- If Firebase is configured, verify signup/sign-in, Save, sign out, sign in, and Load.
- Check that the technical explanation opens, the layout scrolls, and mobile controls remain usable.

Deploy the Streamlit entry point, not `frontend/index.html` as a separate static site. Runtime exceptions appear in Streamlit's app logs. Revert the relevant application/catalog commit to roll back a code change; saved collection compatibility must be considered separately when changing the data model.
