# routr (MVP)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) <!-- Example badge -->

A Minimum Viable Product (MVP) for a dynamic link routing application designed for marketers and influencers.

## Table of Contents

- [Project Description](#project-description)
- [Tech Stack](#tech-stack)
- [Getting Started Locally](#getting-started-locally)
- [Available Scripts](#available-scripts)
- [Project Scope](#project-scope)
- [Project Status](#project-status)
- [License](#license)

## Project Description

_routr_ addresses the challenge of static content sharing in marketing campaigns. It allows users (primarily influencers in this MVP) to generate unique links (e.g., `routr.app/your-campaign`) that redirect end-users based on predefined rules. These rules can include time constraints (start/end dates) and click limits.

The application provides a web interface for authenticated users to manage their links, define routing rules with priorities, specify target URLs or custom HTML content, and view basic click statistics (total clicks per link, clicks per target). If no rule matches, the end-user can be redirected to a user-defined default URL or a global fallback page.

## Tech Stack

- **Backend:**
  - Language: Python 3.x
  - Framework: FastAPI
  - Server: Uvicorn
  - Architecture: Monolith (Backend serves HTML)
- **Frontend:**
  - Interaction: HTMX (via CDN)
  - UI Framework: Bootstrap 5 (via CDN)
  - Date Picker: Flatpickr (via CDN)
  - Templating: Jinja2
- **Database & Auth:**
  - Platform: Supabase
  - Database: PostgreSQL
  - Auth: Supabase Auth
  - Python Client: `supabase` library
- **Infrastructure & Deployment:**
  - Containerization: Docker
  - Hosting: Self-hosted VPS
  - Deployment Management: Coolify (planned)
- **Development Tools:**
  - Package Manager: pip
  - Virtual Environment: venv
  - Linter/Formatter: Ruff (recommended), Black

## Getting Started Locally

Follow these steps to set up and run the project on your local machine for development and testing purposes.

**Prerequisites:**

- Python 3.x installed
- pip (Python package installer)
- Git (optional, for cloning)
- Docker (optional, if you plan to build/run the Docker image locally)
- Access to a Supabase project (URL and Anon Key)

**Setup:**

1.  **Clone the repository (or download the source code):**

    ```bash
    git clone https://github.com/Timmlion/10xRoutr
    cd routr-app
    ```

2.  **Create and activate a Python virtual environment:**

    ```bash
    # Create the environment (use python3 if python points to python2)
    python -m venv .venv

    # Activate the environment
    # macOS / Linux
    source .venv/bin/activate
    # Windows (Git Bash)
    # source .venv/Scripts/activate
    # Windows (CMD)
    # .\.venv\Scripts\activate.bat
    # Windows (PowerShell)
    # .\.venv\Scripts\Activate.ps1
    ```

3.  **Upgrade pip (recommended):**

    ```bash
    pip install --upgrade pip
    ```

4.  **Install Python dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

5.  **Create the environment variables file:**

    - Create a file named `.env` in the root directory of the project.
    - Add your Supabase credentials:
      ```dotenv
      SUPABASE_URL=your_supabase_url
      SUPABASE_KEY=your_supabase_anon_key
      # Add any other required environment variables here
      ```
    - Replace `your_supabase_url` and `your_supabase_anon_key` with your actual Supabase project URL and Anon key.
    - Ensure `.env` is listed in your `.gitignore` file to prevent committing secrets.

6.  **Run the application:**

    - Use the command defined in `Available Scripts` (see below), typically:
      ```bash
      uvicorn main:app --reload --host 0.0.0.0 --port 8000
      ```
    - _Note:_ Replace `main:app` with the actual path to your FastAPI application instance (e.g., `app.server:app` if your instance `app = FastAPI()` is in `app/server.py`).
    - Alternatively, use the VS Code Debugger configuration ("Python: FastAPI") if set up.

7.  **Access the application:**
    Open your web browser and navigate to `http://localhost:8000` (or `http://127.0.0.1:8000`).

## Available Scripts

- **Run Development Server:**

  ```bash
  uvicorn main:app --reload --host 0.0.0.0 --port 8000
  ```

  The `--reload` flag automatically restarts the server when code changes are detected.

- **Linting (with Ruff):**

  ```bash
  ruff check .
  ```

- **Formatting (with Ruff):**

  ```bash
  ruff format .
  ```

- **Formatting (with Black):**

  ```bash
  black .
  ```

- **VS Code Debugger:** Use the "Python: FastAPI" launch configuration in the "Run and Debug" panel (requires `launch.json` setup).

## Project Scope

**In Scope (MVP):**

- User authentication via Supabase.
- Creating unique link aliases (e.g., `routr.app/your-alias`).
- Defining redirection rules based on:
  - Time (start/end date-time).
  - Click count limit.
- Assigning unique priorities to rules within a link.
- Setting target destinations for rules:
  - External URL.
  - Custom HTML content (pasted by the user).
- Optional default redirect URL if no rules match.
- Simple redirect mechanism (HTTP redirect).
- Basic statistics: Total clicks per link, clicks per target.
- Editing existing links (rules, targets, default URL - not the alias).
- Web-based UI for management.

**Out of Scope (MVP):**

- Combining multiple condition types (e.g., Time AND Clicks) within a _single_ rule instance (complex logic achieved via multiple rules and priorities).
- Advanced rule types (geolocation, device type, etc.).
- Advanced analytics and reporting.
- User roles and permissions beyond a single user type.
- Premium features (custom domains, A/B testing).
- Integrations with third-party services.
- Advanced security measures (bot detection, rate limiting).
- Performance optimizations (caching).
- Link archival or advanced lifecycle management.
- Editing the link alias after creation.

## Project Status

**MVP - Under Development**

This is the initial Minimum Viable Product phase. Core functionalities are being built. Future iterations may include features listed as out of scope for the MVP.

## License

This project is licensed under the MIT License.
