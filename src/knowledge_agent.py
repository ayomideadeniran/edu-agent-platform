import sys
import os
from uagents import Agent, Context
from uagents.setup import fund_agent_if_low
from uagents_core.models import Model

# --- CRITICAL ABSOLUTE PATH FIX ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.append(project_root)

# --- AGENT-SPECIFIC MODELS ---
class KnowledgeQuery(Model):
    subject: str
    level: str # e.g., 'Beginner', 'Intermediate'

class KnowledgeResponse(Model):
    subject: str
    topic: str
    question: str
    answer: str
    explanation: str

# --- CONFIGURATION: EXTENDED CURRICULUM ---
CURRICULUM = {
  "Math": {
    "Beginner": [
      {
        "topic": "Basic Arithmetic",
        "questions": [
          {
            "question": "What is 5 plus 3?",
            "answer": "8",
            "explanation": "Addition is the process of combining two or more numbers."
          },
          {
            "question": "What is 10 minus 4?",
            "answer": "6",
            "explanation": "Subtraction is finding the difference between two numbers."
          },
          {
            "question": "What is 2 multiplied by 5?",
            "answer": "10",
            "explanation": "Multiplication is repeated addition."
          }
        ]
      },
      {
        "topic": "Basic Geometry",
        "questions": [
          {
            "question": "How many sides does a triangle have?",
            "answer": "3",
            "explanation": "A triangle is a polygon with three edges and three vertices."
          }
        ]
      }
    ]
  },
  "History": {
    "Beginner": [
      {
        "topic": "Ancient Civilizations",
        "questions": [
          {
            "question": "Which ancient civilization built the pyramids of Giza?",
            "answer": "Egyptian",
            "explanation": "The Ancient Egyptians built the pyramids as tombs for their pharaohs."
          },
          {
            "question": "Who was the first emperor of Rome?",
            "answer": "Augustus",
            "explanation": "Augustus, originally named Octavian, was the founder of the Roman Principate."
          }
        ]
      }
    ]
  },
  "Science": {
    "Beginner": [
      {
        "topic": "The Solar System",
        "questions": [
          {
            "question": "Which planet is known as the 'Red Planet'?",
            "answer": "Mars",
            "explanation": "Mars gets its reddish appearance from iron oxide (rust) on its surface."
          }
        ]
      }
    ]
  }
}
print("Curriculum loaded successfully internally with multiple subjects and questions.")


# --- AGENT SETUP ---
agent = Agent(
    name="knowledge_agent",
    port=8002,
    seed="knowledge_agent_seed_phrase",
    endpoint=["http://127.0.0.1:8002/submit"],
)

fund_agent_if_low(agent.wallet.address())


# --- KNOWLEDGE HANDLER ---

@agent.on_message(model=KnowledgeQuery) 
async def handle_knowledge_query(ctx: Context, sender: str, msg: KnowledgeQuery):
    """Handles requests for lesson content from the Tutor Agent."""

    ctx.logger.info(
        f"KNOWLEDGE AGENT: Received query from {sender} for subject: {msg.subject} at level: {msg.level}!"
    )
    
    subject_data = CURRICULUM.get(msg.subject)
    
    if not subject_data:
        ctx.logger.error(f"Subject '{msg.subject}' not found in curriculum.")
        return

    level_data = subject_data.get(msg.level)
    if not level_data:
        ctx.logger.error(f"Level '{msg.level}' not found for subject '{msg.subject}'.")
        return

    # Use the first topic for the selected subject/level for simplicity
    topic_data = level_data[0] 
    
    # CRITICAL: Use the agent's internal storage to track the index of the last question sent.
    current_index = ctx.storage.get("question_index")
    if current_index is None:
        current_index = 0
    
    questions = topic_data["questions"]
    
    if current_index >= len(questions):
        # Wrap around to the first question if we run out
        current_index = 0 
        
    question_data = questions[current_index]

    # 1. Prepare the response model
    response_msg = KnowledgeResponse(
        subject=msg.subject,
        topic=topic_data["topic"],
        question=question_data["question"],
        answer=question_data["answer"],
        explanation=question_data["explanation"]
    )

    # 2. Update the index for the next request
    ctx.storage.set("question_index", current_index + 1)
    
    # 3. Send the response back to the Tutor Agent
    await ctx.send(sender, response_msg)
    ctx.logger.info(f"KNOWLEDGE AGENT: Sent question index {current_index} for topic: {topic_data['topic']} back to {sender}")


# --- MAIN EXECUTION ---
if __name__ == "__main__":
    with open("knowledge_address.txt", "w") as f:
        f.write(agent.address)
    agent.run()