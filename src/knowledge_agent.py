from datetime import datetime
from uagents import Agent, Context
from uagents.setup import fund_agent_if_low

# --- CONFIGURATION ---
AGENT_MAILBOX_KEY = "knowledge_agent_mailbox"

agent = Agent(
    name="knowledge_agent",
    port=8002,
    seed="knowledge_agent_seed_phrase",
    endpoint=["http://127.0.0.1:8002/submit"],
    mailbox=AGENT_MAILBOX_KEY,
)

# Attempt to fund the agent (errors here are usually ignorable in this setup)
fund_agent_if_low(agent.wallet.address())

# Import the Knowledge Protocol message types (assuming they are in knowledge_protocol_messages.py)
try:
    from knowledge_protocol_messages import KnowledgeQuery, KnowledgeResponse
except ImportError:
    # Placeholder classes for demonstration if the file is missing
    print("WARNING: knowledge_protocol_messages.py not found. Using placeholder classes.")
    class KnowledgeQuery:
        def __init__(self, student_address, subject, query):
            self.student_address = student_address
            self.subject = subject
            self.query = query
    class KnowledgeResponse:
        def __init__(self, student_address, result):
            self.student_address = student_address
            self.result = result

# --- AGENT EVENT HANDLERS ---

@agent.on_message(model=KnowledgeQuery, replies=KnowledgeResponse)
async def handle_query(ctx: Context, sender: str, msg: KnowledgeQuery):
    ctx.logger.info(f"Received knowledge query from {sender} for student {msg.student_address}")

    # Use the student's address as the storage key
    student_key = msg.student_address 

    # 1. Load Data: Get all student data or initialize an empty dictionary
    # Data structure: {'students': {'student_key_1': {'Math': {...}, 'History': {...}}}}
    all_student_data = ctx.storage.get("students") or {} 
    
    # Get the specific student's record, or initialize as an empty subject dict
    student_record = all_student_data.get(student_key, {})

    # Ensure the student has an entry for the requested subject
    # We initialize the level to 'Beginner' if we haven't seen this subject before.
    if msg.subject not in student_record:
        student_record[msg.subject] = {"level": "Beginner", "history": []}
        
    subject_data = student_record[msg.subject]
    
    # 2. Process Query: Check if the query indicates a level update (e.g., from the last student message)
    query_lower = msg.query.lower()

    if "level is advanced now" in query_lower:
        subject_data["level"] = "Advanced"
        ctx.logger.info(f"Updated {msg.subject} level for {student_key} to: Advanced")
    
    # Record the query in the student's history
    subject_data["history"].append({
        "timestamp": datetime.utcnow().isoformat(), 
        "query": msg.query
    })

    # 3. Save Data: Save the updated record back to storage
    student_record[msg.subject] = subject_data       # Update subject data
    all_student_data[student_key] = student_record   # Update student record
    ctx.storage.set("students", all_student_data)    # Persist all data
    
    ctx.logger.info(f"Current {msg.subject} level for {student_key}: {subject_data['level']}")

    # 4. Send Response: Package the student's status into a KnowledgeResponse
    # This result is what the Tutor Agent will use to personalize the lesson.
    response_result = {
        "subject": msg.subject,
        "level": subject_data["level"],
        "suggested_topic": "MeTTa Integration Basics" if subject_data["level"] == "Beginner" else "Advanced Graph Traversal"
    }
    
    await ctx.send(
        sender, # Sender is the Tutor Agent
        KnowledgeResponse(
            student_address=msg.student_address,
            result=response_result # The payload containing the student's knowledge status
        )
    )

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    # Save the knowledge agent's address for the Tutor Agent to use
    with open("knowledge_address.txt", "w") as f:
        f.write(agent.address)
        
    agent.run()


