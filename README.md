# 🎓 Educational AI Agent System

This project demonstrates a multi-agent educational platform built using the **Fetch.ai `uAgents` framework**. It features a modular architecture with a Student, Tutor, and Knowledge agent. A key feature is the AI Assessment agent, which leverages **Google's Gemini AI** to provide personalized learning recommendations. The system also uses the SingularityNET **`MeTTa` knowledge graph** for structured curriculum retrieval and the **Chat Protocol** for user interaction, ensuring compatibility with the ASI:One interface.

### Project Overview

| Agent Name | Role | Technology Used |
| :--- | :--- | :--- |
| **Student Agent** | **User Interface (CLI):** Handles session initiation, user input (subject/level choices, answers, AI diagnostics), and displays the Tutor's questions and feedback. | `uagents`, `Chat Protocol` |
| **Tutor Agent** | **Central Coordinator:** Manages the user's session state (history), routes queries to the Knowledge Agent, grades answers, and forwards diagnostic requests to the AI Assessment Agent. | `uAgents`, `Chat Protocol`, State Management |
| **Knowledge Agent** | **Knowledge Base:** Serves questions and answers based on specific Subject/Level queries by querying the structured `curriculum.metta` file using `MeTTa`. | `uAgents`, `MeTTa` (`hyperon`), Knowledge Graph |
| **AI Assessment Agent** | **(Optional) AI Diagnostician:** Receives user challenges from the Tutor, analyzes them, and provides a personalized subject/level recommendation. | `uAgents`, AI Integration (Google Gemini) |

### Required Submission Badges

The agents are categorized under Innovation Lab and are part of the Hackathon:

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

---


### Setup and Running Instructions

This guide assumes you have **Python 3.9+** and have initialized a virtual environment (`venv`).

**1. Clone the Repository**

```bash
git clone https://github.com/ayomideadeniran/edu-agent-platform
cd edu-agent-platform/src 
```

**2. Install Dependencies**

This project requires `uagents` for agent communication and `hyperon` for MeTTa integration:

```bash
pip install -r requirements.txt
```

**3. Agent Addresses**

The three agents communicate using pre-determined addresses, which are written to local files on startup. Please ensure the following files exist in the `src` directory with the most recently generated addresses:

  * **Tutor Agent Address:** `tutor_address.txt`
  * **Knowledge Agent Address:** `knowledge_address.txt`
  * **Student Agent Address:** `student_address.txt`

For the judges' reference, the expected addresses for the agents are:

  * **Tutor Agent:** `agent1qfz0z6wc0ep8ser24qssdf3dtkln4lyzvvutr0zwj0kv0h74w6r8yhe7kyt`
  * **Knowledge Agent:** `agent1q0n0gf3nm2mevkj6mm45cmjvm3sx23glx38sdmn4kjmw8xm4stn2q600dnq`
  * **Student Agent:** `agent1qddgfypwrksthknutu7pxxk4mkp86uma7g0lrxp8ae3wdx472qjxyxhzgp5`
  * **Knowledge Agent:**
  `agent1qtmnjcac90xddj67av0j3jumtrj8y6y69xtxslpt9e0uuszufnz3xxu0pky`

**4. Run Agents (In Order)**

Run each agent in a separate terminal window, ensuring the `venv` is activated for all sessions:

| Terminal | Command | Role |
| :--- | :--- | :--- |
| **Terminal 1** | `python knowledge_agent.py` | Starts the MeTTa knowledge base. |
| **Terminal 2** | `python ai_assessment_agent.py` | (Optional) Starts the AI diagnostician. |
| **Terminal 3** | `python tutor_agent.py` | Starts the central coordinator. |
| **Terminal 4** | `python student_agent.py` | Starts the user interface (CLI). |


**5. Interaction**

Once all three agents are running, interact with the platform via **Terminal 3** (`student_agent.py`). Follow the menu prompts to:

1.  Select a subject (Math, History, Science).
2.  Select a difficulty level (Beginner, Intermediate).
3.  Answer the question.
4.  Use the `[0] Check My History` option to view the Tutor Agent's grading and session history.

### Use of ASI Alliance Technology

| Technology | Implementation in Project |
| :--- | :--- | :--- |
| **`uAgents` Framework** | Forms the foundation of the entire architecture. Used for all inter-agent communication, agent state management, and defining clear protocols. |
| **`MeTTa` Knowledge Graph** | Integrated into the `knowledge_agent.py` to query the `curriculum.metta` file. We use a robust `(question ...)` fact structure for reliable, subject/level-based retrieval. |
| **Chat Protocol** | Implemented in the `student_agent.py` and `tutor_agent.py` to handle all user interactions, ensuring the application is compatible with the Agentverse and ASI:One interface for seamless human-agent interaction. |


## Quick demo (how to run a minimal end-to-end)

This quick demo shows the minimal steps to run the Student, Tutor and Knowledge agents and the Flask UI locally so a reviewer can verify a round-trip (send input → student ack → tutor/question → answer).

1. Open a terminal and activate the project virtual environment (from `src/`):

```bash
cd ~/Documents/Project/ASI-Agents-Track/edu-agent-platform/src
source venv/bin/activate
```

2. Start the Knowledge Agent (terminal 1):

```bash
# Terminal 1
python knowledge_agent.py
```

3. (Optional) Start the AI Assessment Agent (terminal 2) if you use the diagnostic flow:

```bash
# Terminal 2
python ai_assessment_agent.py
```

4. Start the Tutor Agent (terminal 3):

```bash
# Terminal 3
python tutor_agent.py
```

5. Start the Student Agent (terminal 4):

```bash
# Terminal 4
python student_agent.py
```

6. Start the Flask UI (separate terminal) and open the browser UI:

```bash
# Terminal 5
python src/app.py
# then open http://127.0.0.1:5000 in your browser
```

What to expect (happy path)
- The UI will accept your input and show an immediate acknowledgement ("[Student Ack] Received input: ...").
- The Student Agent terminal will display the tutor's question (the agent writes the question to its console and also stores it in a buffer exposed to the UI).
- The UI will show the tutor question (blue box) and, once you submit an answer, will show your answer (gray box) and the tutor's feedback (green for correct, red for incorrect).

Quick troubleshooting
- If the UI shows "Input cannot be empty": ensure the browser request is posting JSON and that Flask is running on port 5000. Use the browser DevTools Network tab to inspect the POST `/submit_input` payload.
- If Flask returns a 503 saying the Student Agent is not running, check that `student_agent.py` started without errors and is listening on port 8000.
- If you see `{"error":"contents do not match envelope schema"}` when posting to `/submit`, make sure the Flask app is configured to POST to `http://127.0.0.1:8000/ui` (the Student Agent exposes `/ui` and `/submit` compatibility handlers).
- If tutor responses are delayed, wait a few seconds — the UI polls for recent outputs for ~5–6s after submission. You can also re-submit or click Refresh to force another fetch.

Notes for reviewers
- The agent addresses are written to `student_address.txt`, `tutor_address.txt` and `knowledge_address.txt` on startup — include these in your review notes if needed.
- The code includes `agent.include(..., publish_manifest=True)` which prepares manifests for Agentverse publishing.


You typically do this step only once per project.

1.  **Navigate** to your project directory:
    ```bash
    cd ~/Documents/Project/ASI-Agents-Track/edu-agent-platform/src
    ```
2.  **Create the environment:** This command tells Python to create a virtual environment named `venv` inside your current directory.
    ```bash
    python -m venv venv
    ```
      * *Note: If you are on an older system, you might need to use `python3` instead of `python`.*

---

## 2. Activating the Virtual Environment

You must do this step **every time** you open a new terminal session for your project.

To activate the environment:

```bash
source venv/bin/activate
```

### How to Confirm Activation

After running the command above, your terminal prompt will change to show the name of the environment in parentheses. In your case, it will look like this:

```bash
(venv) knights@knights-VivoBook-ASUSLaptop-X420UA:~/Documents/Project/ASI-Agents-Track/edu-agent-platform/src$
```

### Why Use `venv`?

A virtual environment ensures that the Python packages you install for your project (like `uagents` and `hyperon`) are isolated from the rest of your system's Python packages. This prevents conflicts and keeps your project dependencies clean.

---

## 3. Deactivating the Virtual Environment

When you are finished working on this project in your current terminal window, you can exit the virtual environment using the command:

```bash
deactivate
```

## Environment variables and .env file

For local development you can store sensitive keys in a `.env` file at the project root (same directory that contains `src/`). The agents will load these values at startup when `python-dotenv` is installed.

Example `.env` content:

```bash
# Gemini API Key for the AI Assessment Agent
GEMINI_API_KEY="your_gemini_api_key_here"

# (Optional) Legacy name accepted by the code
GOOGLE_API_KEY="your_gemini_api_key_here"

Installation and usage tips:

- Install the loader library:

```bash
pip install python-dotenv
```

- Add `.env` to your `.gitignore` to avoid committing secrets:

```
.env
```

- The AI Assessment Agent prefers `GEMINI_API_KEY` but will fall back to `GOOGLE_API_KEY` if present. If no key is available, the agent uses a local mock fallback.


Your terminal prompt will return to its normal state, and any subsequent `pip install` commands will affect your global Python environment (which is usually what you want to avoid).