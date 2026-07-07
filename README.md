# FB Velo × CI — Streamlit dashboard

A Streamlit version of the FB Velo × CI dashboard. For every pitcher in the selected date window, it compares:

- **Last `ytd_fb_velo` inside the window** from the `FB Velo` tab.
- **Average raw Concentric Impulse inside the same window** from the `Jump Data` tab.

It automatically excludes pitchers whose last selected-window `ytd_fb_velo` is **below 85 mph**. It does not include a CSV download function.

## Run it locally

The app will work locally with your existing file at:

```text
~/Desktop/service_account.json
```

In Terminal:

```bash
cd ~/Downloads/fb_velo_ci_streamlit
python3 -m pip install -r requirements.txt
python3 -m streamlit run app.py
```

It opens at `http://localhost:8501`.

## Deploy to Streamlit Community Cloud

1. Create a **private GitHub repository**, such as `fb-velo-ci-streamlit`.
2. Upload the contents of this folder to that repo. Do **not** upload your `service_account.json` or a real `.streamlit/secrets.toml`.
3. In Streamlit Community Cloud, click **Create app** and choose:
   - Repository: your repo
   - Branch: `main`
   - Main file path: `app.py`
4. Before deploying, open **Advanced settings → Secrets** and paste the contents of a filled-out `secrets.toml`.
5. Deploy.

The `requirements.txt` belongs in the repo root, and Streamlit installs it during deployment. Use the **Secrets** area for credentials rather than committing them to GitHub.

## Creating the Streamlit secrets block

Open your existing `service_account.json` and copy its values into `.streamlit/secrets.toml.example`. Save the real version as:

```text
.streamlit/secrets.toml
```

For `private_key`, preserve the `\n` escapes from the JSON file. Do not paste the key into GitHub, Slack, or a public document.

## Public versus private

A public Streamlit app does not expose the service-account key, but every visitor to the app can see whatever player-level results the app renders. Because this dashboard reads internal baseball data, start with a private deployment or an access-controlled organization-hosted app unless leadership explicitly approves public access.

## Current behavior

- Shared date window for both tabs.
- Current-team filter based on the latest team in `Jump Data`.
- Minimum FB-record and CI-jump controls.
- CI-to-velo fitted lookup plus observed CI-band chart.
- No CSV auto-download or download button.
