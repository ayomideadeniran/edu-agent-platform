# ... (Existing imports remain the same)
import sys
import os
import json
from datetime import datetime
# --- NEW IMPORT ---
from uuid import uuid4
import asyncio

# --- CRITICAL ABSOLUTE PATH FIX ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir)) # Corrected path traversal
if project_root not in sys.path:
    sys.path.append(project_root)

# --- UAGENTS CORE IMPORTS ---
from uagents import Agent, Context, Protocol, Model
from uagents.setup import fund_agent_if_low
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    StartSessionContent,
    TextContent,
    chat_protocol_spec,
)
# We keep the imports for type clarity, but will use prefixed strings for simplicity
from models import KnowledgeQuery, KnowledgeResponse, AssessmentRequest, AssessmentRequestContent, RecommendationContent 


# --- NEW: Pydantic Model for Flask Input Fix (The fix for the AttributeError) ---
class FlaskInput(Model):
    text: str
    
# --- END NEW MODEL ---


# --- AGENT SETUP ---
chat_proto = Protocol(spec=chat_protocol_spec)

# --- CONFIGURATION ---
TUTOR_AGENT_ADDRESS = None 
try:
    # NOTE: The address file should typically be outside the src/ folder if this agent is in src/
    with open("tutor_address.txt", "r") as f:
        TUTOR_AGENT_ADDRESS = f.read().strip()
except FileNotFoundError:
    print("Tutor Agent address not found. Please run tutor_agent.py first.")


# --- VITAL DEPLOYMENT FIX: DYNAMIC ENDPOINT ---
STUDENT_AGENT_PORT = 8000
# Get the public URL from the environment, defaulting to localhost for dev/testing
BASE_URL = os.environ.get("PUBLIC_URL", "http://127.0.0.1")
STUDENT_AGENT_ENDPOINT = f"{BASE_URL}:{STUDENT_AGENT_PORT}/submit" # Keep the /submit path!


# --- AGENT INSTANTIATION ---
agent = Agent(
    name="student_agent",
    port=STUDENT_AGENT_PORT,
    seed="student_agent_seed_phrase",
    # *** UPDATED ENDPOINT ***
    endpoint=[STUDENT_AGENT_ENDPOINT], 
)

fund_agent_if_low(agent.wallet.address())

# ... (rest of the agent logic continues below)


# --- STATE TRACKING (Global Variables) ---
# 0: Waiting for agent response
# 1: Waiting for subject selection (Main Menu)
# 1.5: Waiting for level selection
# 1.8: Waiting for challenge input (AI Assessment)
# 2: Waiting for question answer
# 3: Waiting for next action (after answer/feedback/history)
CURRENT_STATE = 0 
SUBJECT_OPTIONS = ["Math", "History", "Science", "English", "Geography", "Literature", "Physics", "Computer Science", "Art History"]
LEVEL_OPTIONS = ["Beginner", "Intermediate", "Advanced"] 
CURRENT_QUESTION_TEXT = ""
INPUT_TASK_STARTED = False 
TEMP_SUBJECT = None 
STUDENT_HISTORY = [] 

# UI output buffer (recent lines to show in web UI)
STUDENT_USER_OUTPUTS = []

def append_user_output(text: str):
    """Store a message for the web UI and also print it to the terminal."""
    try:
        STUDENT_USER_OUTPUTS.append(str(text))
        # keep last 50 messages
        if len(STUDENT_USER_OUTPUTS) > 50:
            STUDENT_USER_OUTPUTS.pop(0)
    except Exception:
        pass
    # still print to terminal for CLI users
    print(text)


# --- HELPER FUNCTIONS ---

def create_text_chat(text: str) -> ChatMessage:
    """Creates a generic ChatMessage with a single content item."""
    return ChatMessage(
        timestamp=datetime.utcnow().isoformat(),
        msg_id=uuid4(),
        content=[TextContent(text=text)],
    )

def create_history_query(query: str) -> ChatMessage:
    """Uses a special TextContent string for the Tutor to parse History requests."""
    history_request_text = f"::HISTORY_REQUEST::{query}"
    return ChatMessage(
        timestamp=datetime.utcnow().isoformat(),
        msg_id=uuid4(),
        content=[TextContent(text=history_request_text)],
    )


def print_menu():
    global CURRENT_STATE, SUBJECT_OPTIONS, LEVEL_OPTIONS
    lines = []
    lines.append('\n' + '=' * 50)

    if CURRENT_STATE == 1:  # Subject Selection/Main Menu
        lines.append('Please choose a subject or option:')
        for i, subject in enumerate(SUBJECT_OPTIONS):
            lines.append(f'  [{i+1}] {subject}')
        lines.append('  [A] AI Assessment (Diagnostic)')
        lines.append('  [0] Check My History')
        lines.append('  [q] Quit Session')
        lines.append('=' * 50)
        lines.append('Enter choice (1-9, A, 0, or q): ')

    elif CURRENT_STATE == 1.5:  # Level Selection
        lines.append('Please choose a difficulty level:')
        for i, level in enumerate(LEVEL_OPTIONS):
            lines.append(f'  [{i+1}] {level}')
        lines.append('  [q] Quit Session')
        lines.append('=' * 50)
        lines.append('Enter choice (1-3 or q): ')

    elif CURRENT_STATE == 1.8:  # Challenge Input
        lines.append('--- AI Assessment ---')
        lines.append("Please describe your learning challenges in detail (e.g., 'I struggle with word order and sequencing in math'):")
        lines.append('=' * 50)
        lines.append("Enter challenges (or 'q' to cancel): ")

    elif CURRENT_STATE == 2:  # Answer Input
        lines.append(f'**Question:** {CURRENT_QUESTION_TEXT}')
        lines.append('=' * 50)
        lines.append("Enter your answer (or 'q' to quit): ")

    elif CURRENT_STATE == 3:  # Next Action
        lines.append('What would you like to do next?')
        lines.append('  [1] Select New Subject/Level')
        lines.append('  [0] Check My History')
        lines.append('  [q] Quit Session')
        lines.append('=' * 50)
        lines.append('Enter choice (1, 0, or q): ')

    elif CURRENT_STATE == 0:
        lines.append('Waiting for agent response...')

    out = '\n'.join(lines)
    append_user_output(out)


# --- CORE INPUT PROCESSING FUNCTION (Handles both CLI and UI input) ---

async def process_user_input(ctx: Context, text: str):
    """Processes user input based on the current state and sends the message to the Tutor Agent."""
    global CURRENT_STATE, SUBJECT_OPTIONS, LEVEL_OPTIONS, TEMP_SUBJECT

    if not text.strip():
        print_menu()
        append_user_output("[SYSTEM] No input received; showing menu.")
        return

    text = text.strip() 
    text_upper = text.upper()

    # --- QUIT HANDLING ---
    if text_upper == 'Q':
        print("\n[SYSTEM] Session terminated. Shutting down student agent...")
        sys.exit(0) 
        return

    # --- Handle Input Based on Current State ---
    
    if CURRENT_STATE == 1: # Subject Selection/Main Menu
        if text_upper == '0':
            await ctx.send(TUTOR_AGENT_ADDRESS, create_history_query("check my history"))
            CURRENT_STATE = 0 
            append_user_output("[SYSTEM] Sending request for history...")
        
        elif text_upper == 'A':
            CURRENT_STATE = 1.8
            append_user_output("[SYSTEM] Enter AI Assessment input prompt.")
            print_menu()

        # Handle "Subject:Level" format for direct lesson request (e.g., Math:Beginner)
        elif ":" in text and text.count(':') == 1:
            await ctx.send(TUTOR_AGENT_ADDRESS, create_text_chat(text))
            CURRENT_STATE = 0
            append_user_output(f"[YOU] Sent direct lesson request: {text}")
            append_user_output(f"[SYSTEM] Sending direct request for {text}...")

        else:
            try:
                choice_index = int(text) - 1
                if 0 <= choice_index < len(SUBJECT_OPTIONS): 
                    TEMP_SUBJECT = SUBJECT_OPTIONS[choice_index]
                    CURRENT_STATE = 1.5
                    append_user_output(f"[YOU] Selected subject: {TEMP_SUBJECT}")
                    print_menu()
                else:
                    append_user_output("[SYSTEM] Invalid choice. Please enter a number from the menu (1-9), 'A', '0', or 'q'.")
                    print_menu()
            except ValueError:
                append_user_output("[SYSTEM] Invalid input. Please enter a number, 'A', '0', or 'q'.")
                print_menu()

    elif CURRENT_STATE == 1.5: # Level Selection
        try:
            choice_index = int(text) - 1
            if 0 <= choice_index < len(LEVEL_OPTIONS) and TEMP_SUBJECT: 
                level = LEVEL_OPTIONS[choice_index]
                subject = TEMP_SUBJECT
                
                ctx.logger.info(f"User chose subject: {subject} and level: {level}")
                message = f"{subject}:{level}"
                await ctx.send(TUTOR_AGENT_ADDRESS, create_text_chat(message))
                
                CURRENT_STATE = 0 
                TEMP_SUBJECT = None
                append_user_output(f"[YOU] Requested lesson: {subject}:{level}")
                append_user_output(f"[SYSTEM] Sending request for {subject} at {level} level...")
            else:
                append_user_output("[SYSTEM] Invalid choice or missing subject. Please retry.")
                CURRENT_STATE = 1
                print_menu()
        except ValueError:
            append_user_output("[SYSTEM] Invalid input. Please enter a number or 'q'.")
            print_menu()

    elif CURRENT_STATE == 1.8:
        challenges = text
        if not challenges.strip():
            append_user_output("[SYSTEM] Please provide some challenges.")
        else:
            ctx.logger.info(f"User submitted challenges for AI assessment: {challenges[:20]}...")
            
            assessment_text = f"::ASSESSMENT_REQUEST::{challenges}"
            await ctx.send(TUTOR_AGENT_ADDRESS, create_text_chat(assessment_text))
            
            CURRENT_STATE = 0
            append_user_output(f"[YOU] Submitted AI assessment challenges: {challenges[:80]}")
            append_user_output(f"[SYSTEM] Sending challenges for AI analysis...")

    elif CURRENT_STATE == 2:  # Answer Input
        ctx.logger.info(f"User submitted answer: {text}")
        # Echo the user's answer into the recent outputs buffer so the UI shows it
        append_user_output(f"[YOU -> ANSWER] {text}")
        await ctx.send(TUTOR_AGENT_ADDRESS, create_text_chat(text))
        CURRENT_STATE = 0 
        append_user_output(f"[SYSTEM] Sending answer...")

    elif CURRENT_STATE == 3: # Next Action
        if text == '1':
            CURRENT_STATE = 1
            print_menu()
        elif text == '0':
            await ctx.send(TUTOR_AGENT_ADDRESS, create_history_query("check my history"))
            CURRENT_STATE = 0 
            append_user_output(f"[SYSTEM] Sending request for history...")
        else:
            append_user_output("[SYSTEM] Invalid choice. Please enter 1, 0, or 'q'.")
            print_menu()
            
    elif CURRENT_STATE == 0:
        append_user_output("[SYSTEM] Please wait for the agent's response...")


# --- ASYNCHRONOUS USER INPUT TASK (Kept for CLI use) ---

async def user_input_task(ctx: Context):
    
    await asyncio.sleep(1) 

    print("Hello! Welcome to the agent education platform.")
    CURRENT_STATE = 1 
    print_menu()
    
    while True:
        try:
            text = await asyncio.to_thread(input)
            await process_user_input(ctx, text)

        except EOFError:
            ctx.logger.info("Input stream closed.")
            break
        except Exception as e:
            ctx.logger.error(f"Input task error: {e}")
            await asyncio.sleep(0.5)


# --- AGENT EVENTS ---

async def start_input_task_safely(ctx: Context):
    global INPUT_TASK_STARTED
    if not INPUT_TASK_STARTED:
        ctx.logger.info("Starting user input task *immediately* on agent startup...")
        asyncio.create_task(user_input_task(ctx)) 
        INPUT_TASK_STARTED = True

@agent.on_event("startup")
async def on_startup(ctx: Context):
    await send_initial_message(ctx)
    await start_input_task_safely(ctx)


async def send_initial_message(ctx: Context):
    """Initiates the conversation and session."""
    if not TUTOR_AGENT_ADDRESS:
        ctx.logger.error("Tutor Agent address is not set. Cannot start session.")
        return

    ctx.logger.info(f"Initiating new session with Tutor at {TUTOR_AGENT_ADDRESS}")
    start_msg = ChatMessage(
        timestamp=datetime.utcnow().isoformat(),
        msg_id=uuid4(),
        content=[StartSessionContent()],
    )
    await ctx.send(TUTOR_AGENT_ADDRESS, start_msg)


class CustomChatAcknowledgement(Model):
    acknowledged_msg_id: str
    timestamp: str
    # Optional message field to echo back text to callers (UI/clients)
    message: str | None = None


class RecentOutputs(Model):
    outputs: list


class EmptyInput(Model):
    """A permissive empty input model used for endpoints that accept an empty POST."""
    pass


# REST endpoint to return recent student terminal/UI outputs for display in the web UI
@agent.on_rest_post("/recent_outputs", EmptyInput, RecentOutputs)
async def handle_recent_outputs(ctx: Context, msg: EmptyInput) -> RecentOutputs:
    """Return the most recent student UI/terminal outputs so the Flask UI can show them.

    Accepts an optional body (ignored) to be compatible with simple POST calls.
    """
    try:
        # return last 20 outputs
        recent = STUDENT_USER_OUTPUTS[-20:]
        return RecentOutputs(outputs=recent)
    except Exception as e:
        ctx.logger.error(f"Failed to build recent outputs: {e}")
        return RecentOutputs(outputs=[])

# --- NEW: REST POST handler to receive raw input from Flask UI (Uses FlaskInput model) ---
@agent.on_rest_post("/ui", FlaskInput, CustomChatAcknowledgement)
async def handle_raw_flask_input(ctx: Context, msg: FlaskInput) -> CustomChatAcknowledgement:
    """
    REST handler for POST /ui used by the Flask front-end.
    Accepts JSON matching FlaskInput ({"text": "..."}), passes it into the
    agent's core `process_user_input` flow, and returns a CustomChatAcknowledgement.
    """
    user_input_text = msg.text
    ctx.logger.info(f"Received raw text from Flask UI (REST): {user_input_text}")

    # Run the core processing (state transitions + forwarding to Tutor)
    try:
        await process_user_input(ctx, user_input_text)
    except Exception as e:
        ctx.logger.exception(f"Error processing user input from REST: {e}")

    # Return a custom acknowledgement model including an echo message so
    # the UI can display the input immediately while processing continues.
    echo = f"Received input: {user_input_text}"
    # Also print to the student terminal for immediate visibility
    print(f"[UI->STUDENT] {echo}")
    return CustomChatAcknowledgement(
        acknowledged_msg_id=str(uuid4()),
        timestamp=datetime.utcnow().isoformat(),
        message=echo,
    )


# Backwards-compatible REST endpoint used by the Flask UI (POST /submit)
@agent.on_rest_post("/submit", FlaskInput, CustomChatAcknowledgement)
async def handle_submit_endpoint(ctx: Context, msg: FlaskInput) -> CustomChatAcknowledgement:
    """Compatibility wrapper for POST /submit expected by the Flask UI.

    This mirrors the behavior of `/ui` and ensures older clients that post to
    `/submit` receive the same acknowledgement and processing.
    """
    user_input_text = msg.text
    ctx.logger.info(f"Received /submit POST from UI: {user_input_text}")
    try:
        # Print immediately to terminal so student sees the input
        print(f"[UI->STUDENT] Received input: {user_input_text}")
        await process_user_input(ctx, user_input_text)
    except Exception as e:
        ctx.logger.exception(f"Error processing /submit input: {e}")

    return CustomChatAcknowledgement(
        acknowledged_msg_id=str(uuid4()),
        timestamp=datetime.utcnow().isoformat(),
        message=f"Received input: {user_input_text}",
    )

# --- CHAT PROTOCOL HANDLERS ---

@chat_proto.on_message(model=ChatMessage) 
async def handle_message(ctx: Context, sender: str, msg: ChatMessage):
    global CURRENT_STATE, CURRENT_QUESTION_TEXT, STUDENT_HISTORY
    
    await ctx.send(sender, ChatAcknowledgement(timestamp=datetime.utcnow(), acknowledged_msg_id=msg.msg_id))

    for item in msg.content:
        
        if isinstance(item, TextContent):
            text = item.text
            ctx.logger.info(f"Text message from {sender}: {text}")
            
            # --- Handle AI recommendation payloads sent as prefixed JSON ---
            if text.startswith("::AI_RECOMMENDATION::"):
                try:
                    payload_json = text.replace("::AI_RECOMMENDATION::", "", 1)
                    payload = json.loads(payload_json)
                    subj = payload.get('subject')
                    lvl = payload.get('level')
                    analysis = payload.get('analysis')

                    out = "\n" + "~"*50 + "\n"
                    out += "**✅ AI Recommendation Received!**\n"
                    out += f"**AI Analysis:** {analysis}\n"
                    out += f"**Suggested Lesson:** {subj}: {lvl}\n"
                    out += f"\n[TUTOR] To start this lesson, type the exact suggestion (e.g., '{subj}:{lvl}') or select a different option from the menu.\n"
                    out += "~"*50
                    append_user_output(out)

                    CURRENT_STATE = 3
                    print_menu()
                    return
                except Exception as e:
                    ctx.logger.error(f"Failed to parse AI recommendation payload: {e}")
            
            # --- Handle HISTORY PAYLOADS ---
            elif text.startswith("::HISTORY_UPDATE::"):
                json_data = text.replace("::HISTORY_UPDATE::", "", 1)
                try:
                    parts = json_data.split("::")
                    history_json = parts[0]
                    feedback_text = parts[1].strip() if len(parts) > 1 else ""

                    history_entry = json.loads(history_json)
                    STUDENT_HISTORY.append(history_entry)

                    out = "\n" + "~"*50 + "\n"
                    out += f"[TUTOR] {feedback_text}\n"
                    out += "~"*50
                    append_user_output(out)

                    CURRENT_STATE = 3
                    print_menu()
                    return 

                except json.JSONDecodeError:
                    ctx.logger.error("Failed to decode history data from Tutor Agent.")
                
            elif text.startswith("History request acknowledged."):
                ctx.logger.info("Received history acknowledgment. Displaying local history.")
                
                out = "\n" + "="*50 + "\n"
                out += "           TUTORING SESSION HISTORY\n"
                out += "="*50 + "\n"

                if STUDENT_HISTORY:
                    for i, entry in enumerate(STUDENT_HISTORY, 1):
                        status = "✅ Correct" if entry.get('is_correct') else "❌ Incorrect"
                        out += f"\n--- Entry {i} ({status}) ---\n"
                        out += f"   Topic: {entry.get('topic', 'N/A')}\n"
                        q = entry.get('question', 'N/A')
                        out += f"   Question: {q[:60]}...\n"
                        out += f"   Your Answer: {entry.get('user_answer', 'N/A')}\n"
                        out += f"   Correct Answer: {entry.get('correct_answer', 'N/A')}\n"
                else:
                    out += "\nNo tutoring history recorded yet in this session.\n"

                out += "="*50 + "\n"

                append_user_output(out)

                CURRENT_STATE = 3 if CURRENT_QUESTION_TEXT else 1
                print_menu()
                return 
                
            # --- General Text Handler (Question, Acknowledgement, Error, Welcome) ---
            append_user_output("\n" + "~"*50 + "\n" + f"[TUTOR] {text}" + "\n" + "~"*50)

            if "Question:" in text:
                CURRENT_STATE = 2 
                question_start = text.find("Question:") + 10 
                CURRENT_QUESTION_TEXT = text[question_start:].strip()
            elif "Welcome to the Agent Education Platform" in text:
                CURRENT_STATE = 1
            else:
                CURRENT_STATE = 1 
            
            print_menu()
            
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
    with open("student_address.txt", "w") as f:
        f.write(agent.address)
    
    agent.run()