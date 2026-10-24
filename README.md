# Acupuncture — Connected care portal

This package upgrades the uploaded acupuncture site while keeping its calm visual language and all 107 intake fields across 7 sections. Use fictional information only. This is a tested software demonstration, not an independently audited clinical system.

## Two ways to open

1. **Instant interactive preview:** open `Acupuncture-Interactive-Demo.html` in a current browser. Sign in or create a sample patient account. Its accounts, care notes and messages persist only in this browser profile. This is NOT a secure multi-user service. Sample credentials are public. Other devices do not share its records.
2. **Connected server edition:** install Python 3.10 or newer, then run `start.bat` (Windows) or `sh start.sh` (macOS/Linux). Open `http://127.0.0.1:8000` while it is running. Initial installation requires internet. Or manually run `python -m venv .venv`, activate it, install `requirements.txt`, and run `python app.py`.

The included MP4 is a captioned screen recording of the actual website, not an AI-generated mockup. Read `docs/USER-GUIDE.html` for the same steps.

## Sample credentials (DEMO_MODE=1 only)

Patient: `patient@example.com` / `DemoCare!2026`

Assigned doctor: `doctor01@example.com` / `DemoCare!2026` / doctor ID `ACU-DEMO-001`.

There are exactly 40 fictional doctor profiles. The remaining sample doctor emails are `doctor02@example.com` through `doctor40@example.com`, with matching IDs `ACU-DEMO-002` through `ACU-DEMO-040`. These are sample names, not real clinicians or verified licenses. Newly registered patients are assigned to the doctor with the fewest patients, then the lowest ID; the pre-seeded patient already belongs to doctor 01. Your new account will therefore usually get doctor 02. Find the assigned doctor's email and ID under Doctors. This is load balancing, NOT a clinical match.

## Workflow

- Choose Patient, create an account with email, name and a 12+ character password; a doctor is assigned automatically.
- Gender is optional. Reproductive-health fields require an optional opt-in and are never submission prerequisites. All 107 original fields are retained. Only name and the sample-data acknowledgment are required to submit.
- Save an intake draft or submit it. Mark pain on front/back body maps or use accessible coordinate controls.
- Request a future appointment. Only the assigned doctor can confirm it or mark it completed. Competing requests for the same doctor/date/time are rejected.
- Sign out and use the assigned sample doctor's email, password and ID. Only their assigned patients can be accessed.
- Read intake and publish a consultation record with assessment, doctor suggestions, optional prescription text, treatment details, follow-up, optional 21-field practitioner assessment and meridian labels.
- Published records are append-only. To correct one, add a new clearly labelled correction. Old records stay visible.
- Sign back in as the patient and use Care history to find past visits, expand prescriptions, search or print. Doctor suggestions provides saved messages; consultation-specific advice remains in Care history.
- Meridian reference includes your original image and its 14 transcribed meridian names, colors and point counts. This is educational, not a point-location or self-needling guide.
- Export the patient's account, intake, notes, messages and appointments as JSON. Change passwords under My account.

## Real doctor onboarding

Doctor registration is an application, NOT self-approval. Email and ID alone must never grant access. Applications remain pending. On the server, run:

`flask --app app:create_app approve-doctor`

A clinic administrator must independently check the claimed identity, registration, qualifications, professional scope and consent before typing APPROVE. The CLI provisions a practitioner account with a temporary password that must be transmitted securely. The practitioner should change it on first login. There is no admin approval endpoint exposed to patients. Use a fresh data directory with DEMO_MODE=0 so public sample accounts are never carried into a real environment. Approve a practitioner before patient registration; otherwise registration correctly reports no practitioner available.

## Hosting / a direct public website

The HTML preview link is a preview/download, not public hosting of the connected backend. A real public URL requires deploying this package to a Python/container-capable hosting account. No hosting account, domain or deployment credential was provided, so this delivery does not claim an externally deployed medical service.

Use the Dockerfile, or a Python host with build `pip install -r requirements.txt` and start `gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 4 wsgi:app`. Provide persistent storage for DATA_DIR. Place the application behind HTTPS, set COOKIE_SECURE=1 and keep secrets outside source control. The server-side key files are generated with restrictive permissions when not supplied by environment. Persist BOTH database and encryption keys; losing the encryption key loses encrypted records. The default Flask development server is for local use only.

## Security implemented, and limits

Server: salted password hashes, HttpOnly/SameSite session cookies, 30-minute session lifetime, CSRF token checks, role and assignment access checks on every patient endpoint, encrypted intake/notes/message payloads, database audit events, unique appointment slots, bounded payloads, login-attempt throttling, and basic security headers. SQLite data and local keys must be protected by deployment file-system permissions and encrypted storage.

Names, emails, appointment metadata and contact details/IDs on practitioner applications are not encrypted by application code. A server-side key is not a substitute for host or operator security. Clinical text is rendered as text, not executable HTML. The server uses inline styles/scripts for the single-file preview, so CSP permits inline code; a production hardening pass should split assets and use nonces/hashes.

NOT included: email verification or email delivery, automated password recovery, two-factor authentication, push notifications, real clinic calendar integration, video calls, billing, production retention/deletion tooling, automatic credential verification or any compliance certification. No account deletion action from the old preview is represented as working here; clinic data-retention and deletion handling needs policy and implementation before real use. Ask your server operator for recovery. Sessions on other devices are not revoked when a password is changed; stronger session revocation should be added for real deployment.

No automatic diagnoses, treatment plans or prescriptions are generated. Medical appropriateness, licensing and review remain a qualified clinician's responsibility. For emergencies, contact appropriate local services; the portal is not monitored for emergencies. No HIPAA/GDPR compliance claim is made. Real use requires independent security/privacy review, backups/restoration tests, operational monitoring and jurisdiction-specific clinical/legal review.

Google Fonts is the sole optional external asset. If blocked, system fonts are used. The uploaded reference image is bundled locally and embedded in the standalone HTML; no patient data is sent to font services. No AI-generated media is used.

## Testing

Install `requirements-dev.txt`; run `python -m pytest tests -q`. API tests use isolated temporary databases. A browser smoke-test recording is produced during delivery; see `docs/TEST-RESULTS.txt` for the actual outcome. Testing covers representative workflows and security boundaries, not every browser/device or all failure scenarios. No zero-bug guarantee is made.

## Source map

`app.py` Flask API + encrypted SQLite storage + doctor approval CLI; `wsgi.py` hosting entrypoint; `static/index.html` complete served application; `static/app.js` frontend source; `static/demo.js` browser-only adapter; `static/portal.css` portal styling; `static/schema.json` original intake/clinician questions; `static/meridian-reference.jpg` uploaded legend; `doctors.json` 40 fictional profiles; `tests/` automated API checks; `Dockerfile`, `.env.example`, requirements and startup scripts.
