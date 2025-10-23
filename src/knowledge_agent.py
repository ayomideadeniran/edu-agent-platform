import sys
import os
import json
import random # <-- Used for randomization
from datetime import datetime
from uuid import uuid4

# --- CRITICAL ABSOLUTE PATH FIX ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.append(project_root)

# --- UAGENTS CORE IMPORTS ---
from uagents import Agent, Context
from uagents.setup import fund_agent_if_low
from uagents_core.models import Model

# --- AGENT-SPECIFIC MODELS (Tutor Agent Communication) ---
class KnowledgeQuery(Model):
    subject: str
    level: str # e.g., 'Beginner', 'Intermediate'

class KnowledgeResponse(Model):
    subject: str
    topic: str
    question: str
    answer: str
    explanation: str

# --- CONFIGURATION (Load Curriculum from JSON) ---
CURRICULUM = {}
CURRICULUM_FILE = "curriculum.json"

try:
    with open(CURRICULUM_FILE, "r") as f:
        CURRICULUM = json.load(f)
    print(f"Knowledge Agent successfully loaded curriculum from {CURRICULUM_FILE}.")
    
except FileNotFoundError:
    print(f"FATAL: Curriculum file '{CURRICULUM_FILE}' not found. Agent cannot function.")
    sys.exit(1)
except json.JSONDecodeError:
    print(f"FATAL: Error decoding JSON from '{CURRICULUM_FILE}'. Check file format.")
    sys.exit(1)


# --- AGENT SETUP ---
agent = Agent(
    name="knowledge_agent",
    port=8002,
    seed="knowledge_agent_seed_phrase",
    endpoint=["http://127.0.0.1:8002/submit"],
)

fund_agent_if_low(agent.wallet.address())


# --- MESSAGE HANDLERS (UPDATED for Randomization) ---
@agent.on_message(model=KnowledgeQuery)
async def handle_knowledge_query(ctx: Context, sender: str, msg: KnowledgeQuery):
    """
    Handles queries from the Tutor Agent and returns a random question 
    based on the subject and level.
    """
    subject = msg.subject
    level = msg.level
    
    ctx.logger.info(f"Received query for Subject: {subject}, Level: {level}")

    # Check if the subject exists in the loaded curriculum
    if subject not in CURRICULUM:
        ctx.logger.warning(f"Subject '{subject}' not found in curriculum.")
        await ctx.send(
            sender, 
            KnowledgeResponse(
                subject=subject, 
                topic="Error", 
                question="Subject not available.", 
                answer="", 
                explanation=""
            )
        )
        return

    # --- UPDATED LOGIC TO GATHER ALL RELEVANT QUESTIONS ---
    all_relevant_questions = []
    
    # Iterate through all topics within the chosen subject
    for topic_data in CURRICULUM[subject]:
        # Check if the topic level matches the requested level
        if topic_data["level"].lower() == level.lower():
            # Extend the list with all questions from this topic
            all_relevant_questions.extend(topic_data["questions"])
    # --- END UPDATED LOGIC ---
    
    if not all_relevant_questions:
        ctx.logger.warning(f"No content found for Subject: {subject}, Level: {level}")
        await ctx.send(
            sender, 
            KnowledgeResponse(
                subject=subject, 
                topic="Error", 
                question="No questions available at this level.", 
                answer="", 
                explanation=""
            )
        )
        return

    # Randomly select a question from the gathered list
    selected_question_data = random.choice(all_relevant_questions)
    
    # Find the topic name associated with the selected question for the response model
    selected_topic_name = "Mixed Topic" 
    for topic_data in CURRICULUM[subject]:
        if selected_question_data in topic_data["questions"]:
             selected_topic_name = topic_data["topic"]
             break

    # Build the response message
    response = KnowledgeResponse(
        subject=subject,
        topic=selected_topic_name,
        question=selected_question_data["question"],
        answer=selected_question_data["answer"],
        explanation=selected_question_data["explanation"],
    )
    
    ctx.logger.info(f"Sending response for Topic: {response.topic}")
    await ctx.send(sender, response)


# --- MAIN EXECUTION ---
if __name__ == "__main__":
    # Save address for other agents
    with open("knowledge_address.txt", "w") as f:
        f.write(agent.address)
    agent.run()