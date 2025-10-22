import sys
import os
import json
from datetime import datetime
from uuid import uuid4
import asyncio

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

# --- AGENT-SPECIFIC MODELS (Must match Tutor Agent) ---
class HistoryQuery(TextContent):
    type: str = "history_query"
    query: str
    
class HistoryResponse(TextContent):
    type: str = "history_response"
    history_data: str 

# --- CONFIGURATION ---
TUTOR_AGENT_ADDRESS = None 
try:
    with open("tutor_address.txt", "r") as f:
        TUTOR_AGENT_ADDRESS = f.read().strip()
except FileNotFoundError:
    print("Tutor Agent address not found. Please run tutor_agent.py first.")

# --- AGENT SETUP ---
agent = Agent(
    name="student_agent",
    port=8000,
    seed="student_agent_seed_phrase",
    endpoint=["http://127.0.0.1:8000/submit"],
)

fund_agent_if_low(agent.wallet.address())

chat_proto = Protocol(spec=chat_protocol_spec)


# --- STATE TRACKING ---
# 0: Waiting for initial session start acknowledgement
# 1: Waiting for subject selection (Main Menu)
# 2: Waiting for question answer
# 3: Waiting for next action (after answer/feedback)
CURRENT_STATE = 0 
SUBJECT_OPTIONS = ["Math", "History", "Science"]
CURRENT_QUESTION_TEXT = ""


# --- HELPER FUNCTIONS ---

def create_text_chat(text: str, content_model=TextContent) -> ChatMessage:
    """Creates a generic ChatMessage with a single content item."""
    return ChatMessage(
        timestamp=datetime.utcnow(),
        msg_id=uuid4(),
        content=[content_model(text=text)],
    )

def print_menu():
    """Prints the appropriate menu based on the current state."""
    global CURRENT_STATE
    print("\n" + "="*50)
    
    if CURRENT_STATE == 1: # Subject Selection
        print("Please choose a subject by pressing the corresponding number:")
        for i, subject in enumerate(SUBJECT_OPTIONS):
            print(f"  [{i+1}] {subject}")
        print("  [0] Check My History")
        print("="*50)
        print("Enter choice (1-3 or 0): ", end="", flush=True)

    elif CURRENT_STATE == 2: # Answer Input
        print(f"**Question:** {CURRENT_QUESTION_TEXT}")
        print("="*50)
        print("Enter your answer: ", end="", flush=True)
    
    elif CURRENT_STATE == 3: # Next Action
        print("What would you like to do next?")
        print("  [1] Next Question")
        print("  [0] Check My History")
        print("="*50)
        print("Enter choice (1 or 0): ", end="", flush=True)

# --- ASYNCHRONOUS USER INPUT TASK ---

async def user_input_task(ctx: Context):
    """
    Handles all user input in a separate thread.
    """
    global CURRENT_STATE, SUBJECT_OPTIONS
    
    # CRITICAL FIX: Add a pause to allow the agent to fully initialize
    await asyncio.sleep(3) 

    print("Hello! Welcome to the agent education platform.")
    CURRENT_STATE = 1 # Move to main menu state
    print_menu()
    
    while True:
        try:
            # Use asyncio.to_thread to run the blocking input() function
            text = await asyncio.to_thread(input)
            
            if not text.strip():
                print_menu()
                continue

            text = text.strip()

            # --- Handle Input Based on Current State ---
            
            if CURRENT_STATE == 1: # Subject Selection/Main Menu
                if text == '0':
                    await ctx.send(TUTOR_AGENT_ADDRESS, create_history_query("check my history"))
                else:
                    try:
                        choice_index = int(text) - 1
                        if 0 <= choice_index < len(SUBJECT_OPTIONS):
                            subject = SUBJECT_OPTIONS[choice_index]
                            ctx.logger.info(f"User chose subject: {subject}")
                            # Send subject choice to Tutor
                            await ctx.send(TUTOR_AGENT_ADDRESS, create_text_chat(subject))
                            CURRENT_STATE = 0 # Wait for Tutor's question
                            print(f"\n[SYSTEM] Sending request for {subject}...")
                        else:
                            print("[SYSTEM] Invalid choice. Please enter a number from the menu.")
                            print_menu()
                    except ValueError:
                        print("[SYSTEM] Invalid input. Please enter a number.")
                        print_menu()
                        
            elif CURRENT_STATE == 2: # Answer Input
                ctx.logger.info(f"User submitted answer: {text}")
                # Send answer as plain text to Tutor
                await ctx.send(TUTOR_AGENT_ADDRESS, create_text_chat(text))
                CURRENT_STATE = 0 # Wait for Tutor's feedback/next action menu
                print(f"\n[SYSTEM] Sending answer...")

            elif CURRENT_STATE == 3: # Next Action
                if text == '1':
                    # Send "next question" command to Tutor
                    await ctx.send(TUTOR_AGENT_ADDRESS, create_text_chat("next question"))
                    CURRENT_STATE = 0 # Wait for Tutor's question
                    print(f"\n[SYSTEM] Requesting next question...")
                elif text == '0':
                    await ctx.send(TUTOR_AGENT_ADDRESS, create_history_query("check my history"))
                else:
                    print("[SYSTEM] Invalid choice. Please enter 1 or 0.")
                    print_menu()
                    
            elif CURRENT_STATE == 0:
                print("[SYSTEM] Please wait for the agent's response...")


        except EOFError:
            ctx.logger.info("Input stream closed.")
            break
        except Exception as e:
            ctx.logger.error(f"Input task error: {e}")
            await asyncio.sleep(0.5)


# --- AGENT EVENTS ---

@agent.on_event("startup")
async def on_startup(ctx: Context):
    await send_initial_message(ctx)

async def send_initial_message(ctx: Context):
    """Initiates the conversation and session."""
    if not TUTOR_AGENT_ADDRESS:
        ctx.logger.error("Tutor Agent address is not set. Cannot start session.")
        return

    ctx.logger.info(f"Initiating new session with Tutor at {TUTOR_AGENT_ADDRESS}")
    
    # Send StartSessionContent
    start_msg = ChatMessage(
        timestamp=datetime.utcnow(),
        msg_id=uuid4(),
        content=[StartSessionContent()],
    )
    await ctx.send(TUTOR_AGENT_ADDRESS, start_msg)


# In src/student_agent.py, find and modify the start_user_input function:

@agent.on_interval(period=1.0) # We use on_interval to start the task (backward compatibility)
async def start_user_input(ctx: Context):
    # Old buggy line: if not 'input_loop_started' in ctx.storage: 
    
    # CRITICAL FIX: Use .get() to safely check for the key, bypassing the iteration error
    if ctx.storage.get('input_loop_started') is None: 
        # Start the background task using an internal asyncio method
        ctx.logger.info("Starting user input task...")
        asyncio.create_task(user_input_task(ctx))
        ctx.storage.set('input_loop_started', True)


# --- CHAT PROTOCOL HANDLERS ---

@chat_proto.on_message(model=ChatMessage) 
async def handle_message(ctx: Context, sender: str, msg: ChatMessage):
    """Handles incoming chat messages from the Tutor Agent."""
    
    global CURRENT_STATE, CURRENT_QUESTION_TEXT
    
    # 1. Acknowledge message immediately
    await ctx.send(sender, ChatAcknowledgement(timestamp=datetime.utcnow(), acknowledged_msg_id=msg.msg_id))

    for item in msg.content:
        # 2. Handle standard Text Content (This is where the question arrives)
        if isinstance(item, TextContent) and not isinstance(item, HistoryResponse):
            
            text = item.text
            ctx.logger.info(f"Text message from {sender}: {text}")
            
            # CRITICAL: Identify if this is a question or feedback
            if "Question:" in text:
                # Store the question text and move to ANSWER state
                CURRENT_STATE = 2 
                # Extract the question for the prompt (simple, non-robust extraction)
                question_start = text.find("Question:") + 10 
                CURRENT_QUESTION_TEXT = text[question_start:].strip()
                
            elif "That is **correct**" in text or "That is **incorrect**" in text:
                # This is feedback, move to NEXT ACTION state
                CURRENT_STATE = 3
                
            # CRITICAL: Print the Tutor's response clearly
            print("\n" + "~"*50)
            print(f"[TUTOR] {text}") 
            print("~"*50)
            
            # Print the next menu/prompt
            print_menu()
            
        # 3. Handle specialized History Response
        elif isinstance(item, HistoryResponse):
            try:
                history_data = json.loads(item.history_data)
                
                print("\n" + "="*50)
                print(f"📊 **STUDENT PROGRESS HISTORY** 📜")
                print("="*50)
                print(f"  Current Level: {history_data.get('level', 'N/A')}")
                print(f"  Total Score:   {history_data.get('score', 'N/A')}")
                print("\n  --- Lesson History ---")
                
                if history_data.get("history"):
                    for entry in history_data["history"]:
                        status = "✅ CORRECT" if entry.get("correct") else "❌ INCORRECT"
                        topic = entry.get('topic', 'Unknown Topic')
                        date = entry.get('date', 'N/A').split('T')[0]
                        print(f"    [{date}] {status:<10} - Topic: {topic}")
                else:
                    print("    No practice questions answered yet.")
                    
                print("="*50 + "\n")
                    
            except json.JSONDecodeError:
                ctx.logger.error("Failed to decode history data from Tutor Agent.")
                print("\n[SYSTEM] Failed to display history due to data error.")
            
            # Return to the main menu after showing history
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