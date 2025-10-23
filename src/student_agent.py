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

# --- AGENT SETUP ---
# Initialize the protocol
chat_proto = Protocol(spec=chat_protocol_spec)

# The custom HistoryResponse model is REMOVED to bypass ChatMessage validation.

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


# --- STATE TRACKING (Global Variables) ---
# 0: Waiting for agent response
# 1: Waiting for subject selection (Main Menu)
# 2: Waiting for question answer
# 3: Waiting for next action (after answer/feedback)
CURRENT_STATE = 0 
SUBJECT_OPTIONS = ["Math", "History", "Science"]
CURRENT_QUESTION_TEXT = ""

# FLAG TO ENSURE INPUT TASK IS STARTED ONLY ONCE (Critical Fix)
INPUT_TASK_STARTED = False 


# --- HELPER FUNCTIONS ---

def create_text_chat(text: str, content_model=TextContent) -> ChatMessage:
    """Creates a generic ChatMessage with a single content item."""
    return ChatMessage(
        timestamp=datetime.utcnow(),
        msg_id=uuid4(),
        content=[content_model(text=text)],
    )

def create_history_query(query: str) -> ChatMessage:
    """
    Creates a ChatMessage using plain TextContent, prepending a unique tag
    for the Tutor Agent to recognize it as a history request.
    """
    # Use a unique, unlikely-to-be-typed prefix (e.g., ::HISTORY_REQUEST::)
    history_request_text = f"::HISTORY_REQUEST::{query}"
    return ChatMessage(
        timestamp=datetime.utcnow(),
        msg_id=uuid4(),
        content=[TextContent(text=history_request_text)],
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
        # Note: CURRENT_QUESTION_TEXT is set by the message handler
        print(f"**Question:** {CURRENT_QUESTION_TEXT}")
        print("="*50)
        print("Enter your answer: ", end="", flush=True)
    
    elif CURRENT_STATE == 3: # Next Action
        print("What would you like to do next?")
        print("  [1] Next Question")
        print("  [0] Check My History")
        print("="*50)
        print("Enter choice (1 or 0): ", end="", flush=True)

    elif CURRENT_STATE == 0:
        print("Waiting for agent response...")


# --- ASYNCHRONOUS USER INPUT TASK ---

async def user_input_task(ctx: Context):
    """
    Handles all user input in a separate thread.
    """
    global CURRENT_STATE, SUBJECT_OPTIONS
    
    await asyncio.sleep(1) 

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
                    CURRENT_STATE = 0 
                    print(f"\n[SYSTEM] Sending request for history...")
                else:
                    try:
                        choice_index = int(text) - 1
                        if 0 <= choice_index < len(SUBJECT_OPTIONS):
                            subject = SUBJECT_OPTIONS[choice_index]
                            ctx.logger.info(f"User chose subject: {subject}")
                            # Send subject choice to Tutor
                            await ctx.send(TUTOR_AGENT_ADDRESS, create_text_chat(subject))
                            CURRENT_STATE = 0 
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
                CURRENT_STATE = 0 
                print(f"\n[SYSTEM] Sending answer...")

            elif CURRENT_STATE == 3: # Next Action
                if text == '1':
                    # Send "next question" command to Tutor
                    await ctx.send(TUTOR_AGENT_ADDRESS, create_text_chat("next question"))
                    CURRENT_STATE = 0 
                    print(f"\n[SYSTEM] Requesting next question...")
                elif text == '0':
                    await ctx.send(TUTOR_AGENT_ADDRESS, create_history_query("check my history"))
                    CURRENT_STATE = 0 
                    print(f"\n[SYSTEM] Sending request for history...")
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

async def start_input_task_safely(ctx: Context):
    """Safely starts the user input task using a global flag."""
    global INPUT_TASK_STARTED
    
    if not INPUT_TASK_STARTED:
        ctx.logger.info("Starting user input task *immediately* on agent startup...")
        asyncio.create_task(user_input_task(ctx))
        INPUT_TASK_STARTED = True

@agent.on_event("startup")
async def on_startup(ctx: Context):
    """Sends the initial session message AND immediately launches the input task."""
    await send_initial_message(ctx)
    await start_input_task_safely(ctx)


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


# --- CHAT PROTOCOL HANDLERS ---

@chat_proto.on_message(model=ChatMessage) 
async def handle_message(ctx: Context, sender: str, msg: ChatMessage):
    """Handles incoming chat messages (Questions, Feedback, History) from the Tutor Agent."""
    
    global CURRENT_STATE, CURRENT_QUESTION_TEXT
    
    # 1. Acknowledge message immediately
    await ctx.send(sender, ChatAcknowledgement(timestamp=datetime.utcnow(), acknowledged_msg_id=msg.msg_id))

    for item in msg.content:
        
        # We only need to handle TextContent and StartSessionContent
        if isinstance(item, TextContent):
            
            text = item.text
            ctx.logger.info(f"Text message from {sender}: {text}")

            # 🔥 CRITICAL FIX: Check if this TextContent is the JSON History response
            if text.startswith("::HISTORY_RESPONSE::"):
                json_data = text.replace("::HISTORY_RESPONSE::", "", 1)
                
                try:
                    history_data = json.loads(json_data)
                    
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
                            # Ensure the date is formatted nicely
                            date_part = entry.get('date', 'N/A').split('T')[0]
                            print(f"    [{date_part}] {status:<10} - Topic: {topic}")
                    else:
                        print("    No practice questions answered yet.")
                        
                    print("="*50 + "\n")
                
                except json.JSONDecodeError:
                    ctx.logger.error("Failed to decode history data from Tutor Agent.")
                    print("\n[SYSTEM] Failed to display history due to data error.")
                
                # Return to the next action menu after showing history
                CURRENT_STATE = 3 if CURRENT_QUESTION_TEXT else 1
                print_menu()
                return # Stop processing this TextContent

            # Print the Tutor's response clearly (Only if it wasn't history)
            print("\n" + "~"*50)
            print(f"[TUTOR] {text}") 
            print("~"*50)

            # CRITICAL: Identify if this is a question or feedback
            if "Question:" in text:
                # Store the question text and move to ANSWER state
                CURRENT_STATE = 2 
                # Extract the question for the prompt (simple extraction)
                question_start = text.find("Question:") + 10 
                CURRENT_QUESTION_TEXT = text[question_start:].strip()
                
            elif "That is **correct**" in text or "That is **incorrect**" in text:
                # This is feedback, move to NEXT ACTION state
                CURRENT_STATE = 3
                
            else:
                # Fallback for introductory messages, go to main menu
                CURRENT_STATE = 1 
            
            # Print the next menu/prompt
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



