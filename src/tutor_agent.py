from datetime import datetime
from uuid import uuid4
from uagents import Agent, Context, Model, Protocol
from uagents.setup import fund_agent_if_low
from uagents_core.contrib.protocols.chat import (
   ChatAcknowledgement,
   ChatMessage,
   EndSessionContent,
   StartSessionContent,
   TextContent,
   chat_protocol_spec,
)

class KnowledgeQuery(Model):
    student_id: str
    topic: str

class KnowledgeUpdate(Model):
    student_id: str
    topic: str
    level: str

class KnowledgeResponse(Model):
    profile: dict

agent = Agent(
    name="tutor_agent",
    port=8001,
    seed="tutor_agent_seed_phrase",
    endpoint=["http://127.0.0.1:8001/submit"],
)

fund_agent_if_low(agent.wallet.address())

with open("tutor_address.txt", "w") as f:
    f.write(agent.address)

with open("knowledge_address.txt", "r") as f:
    KNOWLEDGE_ADDRESS = f.read().strip()

chat_proto = Protocol(spec=chat_protocol_spec)
knowledge_proto = Protocol("KnowledgeProtocol")

def create_text_chat(text: str, end_session: bool = False) -> ChatMessage:
    content = [TextContent(type="text", text=text)]
    if end_session:
        content.append(EndSessionContent())
    return ChatMessage(
        timestamp=datetime.utcnow(),
        msg_id=uuid4(),
        content=content,
    )

@chat_proto.on_message(ChatMessage)
async def handle_message(ctx: Context, sender: str, msg: ChatMessage):
    ctx.logger.info(f"Received message from {sender}")
    await ctx.send(sender, ChatAcknowledgement(timestamp=datetime.utcnow(), acknowledged_msg_id=msg.msg_id))

    for item in msg.content:
        if isinstance(item, StartSessionContent):
            ctx.logger.info(f"Session started with {sender}")

        elif isinstance(item, TextContent):
            ctx.logger.info(f"Text message from {sender}: {item.text}")
            student_id = sender
            
            # CRITICAL FIX: Use ctx.storage to store the student_id for the response handler
            ctx.storage.set("student_id", student_id)
            
            topic = "Math"
            await ctx.send(KNOWLEDGE_ADDRESS, KnowledgeQuery(student_id=student_id, topic=topic))


        elif isinstance(item, EndSessionContent):
            ctx.logger.info(f"Session ended with {sender}")
        else:
            ctx.logger.info(f"Received unexpected content type from {sender}")

@knowledge_proto.on_message(KnowledgeResponse)
async def handle_knowledge_response(ctx: Context, sender: str, msg: KnowledgeResponse):
    ctx.logger.info(f"Received knowledge response from {sender}")
    profile = msg.profile
    
    # CRITICAL FIX: Retrieve student_id from ctx.storage
    student_id = ctx.storage.get("student_id")

    if not student_id:
        ctx.logger.error("Failed to retrieve student_id from context storage.")
        return 
    
    # ... rest of the code is correct ...


    if profile['is_advanced']:
        response_text = (
            f"Hello! Your current Math level is **{profile['current_level']}** (Great work!). "
            f"Since you seem to be making excellent progress, would you like to explore **Calculus**?"
        )
    else:
        response_text = (
            f"Welcome back! I see your current Math level is **{profile['current_level']}**. "
            f"Let's focus on **Basic Algebra** to ensure you master the fundamentals."
        )
    
    response_message = create_text_chat(response_text)
    await ctx.send(student_id, response_message)

@chat_proto.on_message(ChatAcknowledgement)
async def handle_acknowledgement(ctx: Context, sender: str, msg: ChatAcknowledgement):
    ctx.logger.info(f"Received acknowledgement from {sender} for message {msg.acknowledged_msg_id}")

agent.include(chat_proto, publish_manifest=True)
agent.include(knowledge_proto)

if __name__ == "__main__":
    agent.run()