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
# Use shared models
from models import KnowledgeQuery, KnowledgeResponse


# --- AGENT SETUP ---
chat_proto = Protocol(spec=chat_protocol_spec)

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
# 1.5: Waiting for level selection
# 2: Waiting for question answer
# 3: Waiting for next action (after answer/feedback)
CURRENT_STATE = 0 
SUBJECT_OPTIONS = ["Math", "History", "Science"]
LEVEL_OPTIONS = ["Beginner", "Intermediate"] 
CURRENT_QUESTION_TEXT = ""
INPUT_TASK_STARTED = False 
TEMP_SUBJECT = None 
# FIX 1: New Global Variable for History
STUDENT_HISTORY = [] 


# --- HELPER FUNCTIONS ---

def create_text_chat(text: str, content_model=TextContent) -> ChatMessage:
    """Creates a generic ChatMessage with a single content item."""
    return ChatMessage(
        timestamp=datetime.utcnow(),
        msg_id=uuid4(),
        content=[content_model(text=text)],
    )

def create_history_query(query: str) -> ChatMessage:
    history_request_text = f"::HISTORY_REQUEST::{query}"
    return ChatMessage(
        timestamp=datetime.utcnow(),
        msg_id=uuid4(),
        content=[TextContent(text=history_request_text)],
    )

def print_menu():
    global CURRENT_STATE
    print("\n" + "="*50)
    
    if CURRENT_STATE == 1: # Subject Selection
        print("Please choose a subject by pressing the corresponding number:")
        for i, subject in enumerate(SUBJECT_OPTIONS):
            print(f"  [{i+1}] {subject}")
        print("  [0] Check My History")
        print("  [q] Quit Session") 
        print("="*50)
        print("Enter choice (1-3, 0, or q): ", end="", flush=True) 

    elif CURRENT_STATE == 1.5: # Level Selection
        print("Please choose a difficulty level:")
        for i, level in enumerate(LEVEL_OPTIONS):
            print(f"  [{i+1}] {level}")
        print("  [q] Quit Session")
        print("="*50)
        print("Enter choice (1-2 or q): ", end="", flush=True)

    elif CURRENT_STATE == 2: # Answer Input
        print(f"**Question:** {CURRENT_QUESTION_TEXT}")
        print("="*50)
        print("Enter your answer (or 'q' to quit): ", end="", flush=True)
    
    elif CURRENT_STATE == 3: # Next Action
        print("What would you like to do next?")
        print("  [1] Select New Subject/Level") # Changed for clarity 
        print("  [0] Check My History")
        print("  [q] Quit Session") 
        print("="*50)
        print("Enter choice (1, 0, or q): ", end="", flush=True)

    elif CURRENT_STATE == 0:
        print("Waiting for agent response...")


# --- ASYNCHRONOUS USER INPUT TASK ---

async def user_input_task(ctx: Context):
    global CURRENT_STATE, SUBJECT_OPTIONS, LEVEL_OPTIONS, TEMP_SUBJECT, agent
    
    await asyncio.sleep(1) 

    print("Hello! Welcome to the agent education platform.")
    CURRENT_STATE = 1 
    print_menu()
    
    while True:
        try:
            text = await asyncio.to_thread(input)
            
            if not text.strip():
                print_menu()
                continue

            text = text.strip().lower()

            # --- QUIT HANDLING ---
            if text == 'q':
                print("\n[SYSTEM] Session terminated. Shutting down student agent...")
                sys.exit(0) 
                return

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
                            TEMP_SUBJECT = SUBJECT_OPTIONS[choice_index]
                            CURRENT_STATE = 1.5
                            print_menu()
                        else:
                            print("[SYSTEM] Invalid choice. Please enter a number from the menu.")
                            print_menu()
                    except ValueError:
                        print("[SYSTEM] Invalid input. Please enter a number or 'q'.")
                        print_menu()

            elif CURRENT_STATE == 1.5: # Level Selection
                try:
                    choice_index = int(text) - 1
                    if 0 <= choice_index < len(LEVEL_OPTIONS):
                        level = LEVEL_OPTIONS[choice_index]
                        subject = TEMP_SUBJECT
                        
                        ctx.logger.info(f"User chose subject: {subject} and level: {level}")
                        
                        # FIX: Send the query as a simple text message with the format "Subject:Level"
                        message = f"{subject}:{level}"
                        await ctx.send(TUTOR_AGENT_ADDRESS, create_text_chat(message))
                        
                        CURRENT_STATE = 0 
                        TEMP_SUBJECT = None
                        print(f"\n[SYSTEM] Sending request for {subject} at {level} level...")
                    else:
                        print("[SYSTEM] Invalid choice. Please enter a number from the menu.")
                        print_menu()
                except ValueError:
                    print("[SYSTEM] Invalid input. Please enter a number or 'q'.")
                    print_menu()
                        
            elif CURRENT_STATE == 2: # Answer Input
                ctx.logger.info(f"User submitted answer: {text}")
                await ctx.send(TUTOR_AGENT_ADDRESS, create_text_chat(text))
                CURRENT_STATE = 0 
                print(f"\n[SYSTEM] Sending answer...")

            elif CURRENT_STATE == 3: # Next Action
                if text == '1':
                    # Instead of 'next question', go back to subject selection (State 1)
                    CURRENT_STATE = 1
                    print_menu()
                elif text == '0':
                    await ctx.send(TUTOR_AGENT_ADDRESS, create_history_query("check my history"))
                    CURRENT_STATE = 0 
                    print(f"\n[SYSTEM] Sending request for history...")
                else:
                    print("[SYSTEM] Invalid choice. Please enter 1, 0, or 'q'.")
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
        timestamp=datetime.utcnow(),
        msg_id=uuid4(),
        content=[StartSessionContent()],
    )
    await ctx.send(TUTOR_AGENT_ADDRESS, start_msg)


# --- CHAT PROTOCOL HANDLERS ---

@chat_proto.on_message(model=ChatMessage) 
async def handle_message(ctx: Context, sender: str, msg: ChatMessage):
    global CURRENT_STATE, CURRENT_QUESTION_TEXT, STUDENT_HISTORY
    
    await ctx.send(sender, ChatAcknowledgement(timestamp=datetime.utcnow(), acknowledged_msg_id=msg.msg_id))

    for item in msg.content:
        if isinstance(item, TextContent):
            text = item.text
            ctx.logger.info(f"Text message from {sender}: {text}")

            if text.startswith("::HISTORY_RESPONSE::"):
                # This block is for a hypothetical *Tutor-sent* history payload, 
                # which isn't happening right now. We'll leave it as is, but rely on the logic below.
                json_data = text.replace("::HISTORY_RESPONSE::", "", 1)
                try:
                    # ... (logic to handle Tutor-sent history)
                    pass 
                except json.JSONDecodeError:
                    ctx.logger.error("Failed to decode history data from Tutor Agent.")
                    print("\n[SYSTEM] Failed to display history due to data error.")
                
                CURRENT_STATE = 3 if CURRENT_QUESTION_TEXT else 1
                print_menu()
                return 

            if text.startswith("::HISTORY_UPDATE::"):
                json_data = text.replace("::HISTORY_UPDATE::", "", 1)
                try:
                    # The payload structure is '{"...json...": value}::Feedback text...'
                    parts = json_data.split("::")
                    history_json = parts[0]
                    feedback_text = parts[1].strip() if len(parts) > 1 else ""

                    history_entry = json.loads(history_json)
                    
                    # FIX 2: Save the history entry to the global list
                    STUDENT_HISTORY.append(history_entry)

                    # Print only the feedback text
                    print("\n" + "~"*50)
                    print(f"[TUTOR] {feedback_text}") 
                    print("~"*50)

                    CURRENT_STATE = 3
                    print_menu()
                    return # Exit after processing history update and displaying feedback

                except json.JSONDecodeError:
                    ctx.logger.error("Failed to decode history data from Tutor Agent.")
                    # Fallthrough to display error as simple text
                
            # FIX 3: Check for the specific history acknowledgment from the Tutor Agent
            elif text.startswith("History request acknowledged."):
                ctx.logger.info("Received history acknowledgment. Displaying local history.")
                
                print("\n" + "="*50)
                print("           TUTORING SESSION HISTORY")
                print("="*50)
                
                if STUDENT_HISTORY:
                    for i, entry in enumerate(STUDENT_HISTORY, 1):
                        status = "✅ Correct" if entry.get('is_correct') else "❌ Incorrect"
                        print(f"\n--- Entry {i}: {entry.get('topic', 'N/A')} ---")
                        print(f"Question: {entry.get('question', 'N/A')}")
                        print(f"Your Answer: {entry.get('user_answer', 'N/A')}")
                        print(f"Correct Answer: {entry.get('correct_answer', 'N/A')}")
                        print(f"Result: {status}")
                else:
                    print("No tutoring history recorded yet.")
                    
                print("="*50 + "\n")
                
                # Revert to the appropriate state and print the menu
                CURRENT_STATE = 3 if CURRENT_QUESTION_TEXT else 1
                print_menu()
                return # IMPORTANT: return to prevent falling through to the general text handler
                
            # Print the Tutor's response clearly 
            print("\n" + "~"*50)
            print(f"[TUTOR] {text}") 
            print("~"*50)

            if "Question:" in text:
                CURRENT_STATE = 2 
                question_start = text.find("Question:") + 10 
                CURRENT_QUESTION_TEXT = text[question_start:].strip()
                
            elif "That is **correct**" in text or "That is **incorrect**" in text:
                # This should be handled by the ::HISTORY_UPDATE:: block, but included for robustness
                CURRENT_STATE = 3
                
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