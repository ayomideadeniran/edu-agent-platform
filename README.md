# Personalized Education & Tutoring Agent

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

This project implements a multi-agent system for personalized education, built with the uAgents framework.

## Architecture

The system consists of three agents:

1.  **Student Agent (`student_agent.py`):** Simulates a student interacting with the tutoring system. It engages in a conversation with the Tutor Agent.
2.  **Tutor Agent (`tutor_agent.py`):** The main educational agent. It receives messages from the student, queries the Knowledge Agent for the student's profile, and provides a personalized response.
3.  **Knowledge Agent (`knowledge_agent.py`):** Manages the student's knowledge profile using a MeTTa knowledge graph. It stores and retrieves information about the student's learning progress.

## How to Run

To run the system, you need to start the agents in the following order:

1.  **Start the Knowledge Agent:**

    ```bash
    python src/knowledge_agent.py
    ```

2.  **Start the Tutor Agent:**

    ```bash
    python src/tutor_agent.py
    ```

3.  **Start the Student Agent:**

    ```bash
    python src/student_agent.py
    ```

## Agent Addresses

When the `knowledge_agent.py` and `tutor_agent.py` are run, they will create `knowledge_address.txt` and `tutor_address.txt` files respectively. These files contain the agents' addresses, which are used by the other agents to communicate.