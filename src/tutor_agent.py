import sys
import os
import json
from datetime import datetime
from uuid import uuid4

# --- CRITICAL ABSOLUTE PATH FIX ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.append(project_root)

# --- UAGENTS CORE IMPORTS ---
from uagents import Agent, Context, Protocol
from uagents.setup import fund_agent_if_low
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    StartSessionContent,
    TextContent,
    chat_protocol_spec,
)
from uagents_core.models import Model

# --- AGENT SETUP ---
chat_proto = Protocol(spec=chat_protocol_spec)

# --- AGENT-SPECIFIC MODELS (Knowledge Agent Communication) ---
class KnowledgeQuery(Model):
    subject: str
    level: str 

class KnowledgeResponse(Model):
    subject: str
    topic: str
    question: str
    answer: str
    explanation: str

# --- GLOBAL VARIABLE FOR BUG WORKAROUND ---
STUDENT_ADDRESS = None

# --- CONFIGURATION ---
KNOWLEDGE_AGENT_ADDRESS = None
try:
    with open("knowledge_address.txt", "r") as f:
        KNOWLEDGE_AGENT_ADDRESS = f.read().strip()
    if not KNOWLEDGE_AGENT_ADDRESS:
         print("Knowledge Agent address file is empty. Please run knowledge_agent.py first.")
except FileNotFoundError:
    print("Knowledge Agent address file not found. Please run knowledge_agent.py first.")


# Simplified "curriculum" to get available subjects (Loaded from JSON)
CURRICULUM = set() 
CURRICULUM_FILE = "curriculum.json" 

try:
    with open(CURRICULUM_FILE, "r") as f:
        full_curriculum_data = json.load(f)
        CURRICULUM = set(full_curriculum_data.keys())
        print(f"Tutor Agent loaded available subjects: {CURRICULUM}")
    
except FileNotFoundError:
    print(f"WARNING: Curriculum file '{CURRICULUM_FILE}' not found. Using empty subject list.")
except json.JSONDecodeError:
    print(f"WARNING: Error decoding JSON from '{CURRICULUM_FILE}'. Check file format.")


# --- AGENT SETUP ---
agent = Agent(
    name="tutor_agent",
    port=8001,
    seed="tutor_agent_seed_phrase",
    endpoint=["http://127.0.0.1:8001/submit"],
)

fund_agent_if_low(agent.wallet.address())


# --- AGENT STATE MANAGEMENT ---
def get_default_state(subject):
    # Default level is set temporarily here, but overwritten by student choice
    return { 
        "level": "Beginner", 
        "subject": subject,
        "score": 0,
        "history": [],
        "current_question": None
    }

# --- HELPER FUNCTIONS ---

def create_text_chat(text: str, content_model=TextContent) -> ChatMessage:
    """Creates a generic ChatMessage with a single content item."""
    return ChatMessage(
        timestamp=datetime.utcnow(),
        msg_id=uuid4(),
        content=[content_model(text=text)],
    )

# --- KNOWLEDGE RESPONSE HANDLER (Remains the same) ---

@agent.on_message(model=KnowledgeResponse) 
async def handle_knowledge_response(ctx: Context, sender: str, msg: KnowledgeResponse):
    """
    Handles the response from the Knowledge Agent with a question.
    """
    global STUDENT_ADDRESS
    
    if sender != KNOWLEDGE_AGENT_ADDRESS:
        ctx.logger.warning(f"Received unexpected KnowledgeResponse from {sender}. Ignoring.")
        return
    
    student_address = STUDENT_ADDRESS
    if not student_address:
        ctx.logger.error("FATAL: KnowledgeResponse received but no student session address is set.")
        return
    
    student_state = ctx.storage.get(student_address)

    if not student_state:
        ctx.logger.error(f"FATAL: Student address {student_address} is set but no state data found.")
        return
    
    student_state["current_question"] = msg.dict() # Store the question details
    ctx.storage.set(student_address, student_state)
    
    ctx.logger.info(f"Received question for {student_address}. Subject: {msg.subject}, Topic: {msg.topic}")

    # Use the level stored in the student state for the intro message
    intro_message = f"Hello, I'm ready to teach **{msg.subject}**! Based on your chosen level (**{student_state['level']}**), we'll start with the topic: **{student_state['current_question']['topic']}**."
    question_message = f"Here is your question:\n\n**Question:** {student_state['current_question']['question']}"

    full_message = f"{intro_message}\n\n{question_message}"
    
    await ctx.send(student_address, create_text_chat(full_message))
    ctx.logger.info(f"Sent lesson content to {student_address}")


# --- CHAT PROTOCOL HANDLERS ---
@chat_proto.on_message(model=ChatMessage) 
async def handle_message(ctx: Context, sender: str, msg: ChatMessage):
    """Handles incoming chat messages."""
    
    global STUDENT_ADDRESS
    
    await ctx.send(sender, ChatAcknowledgement(timestamp=datetime.utcnow(), acknowledged_msg_id=msg.msg_id))
    ctx.logger.info(f"Acknowledged message {msg.msg_id} from {sender}")
    
    student_state = ctx.storage.get(sender)
    
    for item in msg.content:
        
        # --- 1. Handle START SESSION ---
        if isinstance(item, StartSessionContent):
            ctx.logger.info(f"Session started with {sender}")
            STUDENT_ADDRESS = sender 
            ctx.storage.set(sender, get_default_state(subject=None))
            return

        # --- 2. Handle TEXT CONTENT (Initial Subject:Level, Answer/Reply, or HISTORY REQUEST) ---
        elif isinstance(item, TextContent):
            
            if not student_state:
                ctx.logger.error(f"Received TextContent from {sender} but no session state exists.")
                return

            text = item.text.strip()
            ctx.logger.info(f"Received text from {sender}: '{text}'")
            
            # HISTORY CHECK: (Remains the same)
            if text.startswith("::HISTORY_REQUEST::"):
                ctx.logger.info(f"Received HISTORY_REQUEST from {sender}.")
                
                if not student_state:
                    await ctx.send(sender, create_text_chat("I cannot find your session data. Please start a subject first."))
                    return

                history_json = json.dumps(student_state)
                history_message_text = f"::HISTORY_RESPONSE::{history_json}"
                
                await ctx.send(sender, create_text_chat(history_message_text))
                ctx.logger.info(f"Sent history response (as JSON Text) to {sender}")
                return 

            # A. First Message: Subject:Level Selection (Subject is None) <-- UPDATED LOGIC
            if student_state.get('subject') is None:
                
                # Parse the incoming Subject:Level string from student_agent (e.g., "Math:Beginner")
                if ':' in text:
                    try:
                        subject, level = text.split(':', 1)
                        subject = subject.strip()
                        level = level.strip()
                    except ValueError:
                        subject = text
                        level = "Beginner" # Fallback
                else:
                    subject = text
                    level = "Beginner" # Fallback

                
                if subject in CURRICULUM:
                    student_state['subject'] = subject
                    student_state['level'] = level # Store the student's chosen level
                    ctx.storage.set(sender, student_state)
                    
                    # CRITICAL: QUERY KNOWLEDGE AGENT with the chosen level
                    if KNOWLEDGE_AGENT_ADDRESS:
                        query_msg = KnowledgeQuery(subject=subject, level=level) 
                        await ctx.send(KNOWLEDGE_AGENT_ADDRESS, query_msg)
                        ctx.logger.info(f"Successfully sent KnowledgeQuery to {KNOWLEDGE_AGENT_ADDRESS} for subject: {subject} at level: {level}")
                    else:
                        await ctx.send(sender, create_text_chat("Error: Tutor cannot connect to the Knowledge Agent. Please check its address."))
                else:
                    await ctx.send(sender, create_text_chat(f"Sorry, I don't offer a curriculum for '{subject}'. Please choose from: {', '.join(CURRICULUM)}"))
                return
                
            # B. Subsequent Message: Answer/Reply (Subject is set)
            else:
                current_q = student_state.get('current_question')
                
                # If there is a question waiting for an answer (Remains the same)
                if current_q:
                    answer_text = current_q.get('answer', '').strip()
                    is_correct = text.lower() == answer_text.lower()
                    
                    student_state['score'] += 1 if is_correct else 0
                    student_state['history'].append({
                        'topic': current_q.get('topic'),
                        'correct': is_correct,
                        'date': datetime.utcnow().isoformat()
                    })
                    student_state['current_question'] = None 
                    ctx.storage.set(sender, student_state)
                    
                    feedback = ""
                    if is_correct:
                        feedback = f"That is **correct**! Great job. The explanation is: {current_q.get('explanation')}"
                    else:
                        feedback = f"That is **incorrect**. The correct answer was **{answer_text}**. The explanation is: {current_q.get('explanation')}"
                        
                    await ctx.send(sender, create_text_chat(f"{feedback}\n\nReady for the next question? Type 'next topic' or 'next question'."))
                    return

                # If the student asked for the next question/topic <-- UPDATED
                elif 'next' in text.lower():
                    subject = student_state['subject']
                    level = student_state['level'] # Use the stored level
                    
                    query_msg = KnowledgeQuery(subject=subject, level=level)
                    await ctx.send(KNOWLEDGE_AGENT_ADDRESS, query_msg)
                    ctx.logger.info(f"Sent request for next topic/question to {KNOWLEDGE_AGENT_ADDRESS} at level: {level}")
                else:
                    await ctx.send(sender, create_text_chat("I'm ready for your answer or if you'd like to move on, type 'next question'."))
            

    return None

@chat_proto.on_message(model=ChatAcknowledgement)
async def handle_acknowledgement(ctx: Context, sender: str, msg: ChatAcknowledgement):
    ctx.logger.info(
        f"Received acknowledgement from {sender} for message {msg.acknowledged_msg_id}"
    )
    return None

# --- MAIN EXECUTION ---
agent.include(chat_proto, publish_manifest=True)

if __name__ == "__main__":
    with open("tutor_address.txt", "w") as f:
        f.write(agent.address)
    agent.run()





