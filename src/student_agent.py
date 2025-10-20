from datetime import datetime
from uuid import uuid4
from uagents import Agent, Context, Protocol
from uagents.setup import fund_agent_if_low
from uagents_core.contrib.protocols.chat import (
   ChatAcknowledgement,
   ChatMessage,
   EndSessionContent,
   StartSessionContent,
   TextContent,
   chat_protocol_spec,
)

AGENT_MAILBOX_KEY = "student_agent_mailbox"

agent = Agent(
    name="student_agent",
    port=8000,
    seed="student_agent_seed_phrase",
    endpoint=["http://127.0.0.1:8000/submit"],
    mailbox=AGENT_MAILBOX_KEY,
)

fund_agent_if_low(agent.wallet.address())

chat_proto = Protocol(spec=chat_protocol_spec)

try:
    with open("tutor_address.txt", "r") as f:
        TUTOR_ADDRESS = f.read().strip()
except FileNotFoundError:
    TUTOR_ADDRESS = None

def create_text_chat(text: str, end_session: bool = False) -> ChatMessage:
    content = [TextContent(type="text", text=text)]
    if end_session:
        content.append(EndSessionContent())
    return ChatMessage(
        timestamp=datetime.utcnow(),
        msg_id=uuid4(),
        content=content,
    )

@agent.on_event("startup")
async def start_chat(ctx: Context):
    if not TUTOR_ADDRESS:
        ctx.logger.error("Tutor address not found. Please run tutor_agent.py first.")
        return
        
    ctx.logger.info(f"Initiating new session with Tutor at {TUTOR_ADDRESS}")
    ctx.storage.set("conversation_turn", 0)

    initial_message = create_text_chat("I'm ready for today's lesson! Can we start with Math?")
    initial_message.content.insert(0, StartSessionContent()) 
    
    await ctx.send(TUTOR_ADDRESS, initial_message)
    ctx.logger.info(f"Sent initial message: 'I'm ready for today's lesson! Can we start with Math?'")

@chat_proto.on_message(ChatMessage)
async def handle_message(ctx: Context, sender: str, msg: ChatMessage):
    # 1. Send acknowledgement immediately
    await ctx.send(sender, ChatAcknowledgement(timestamp=datetime.utcnow(), acknowledged_msg_id=msg.msg_id))

    for item in msg.content:
        if isinstance(item, TextContent):
            ctx.logger.info(f"Text message from {sender}: {item.text}")

            # FIX: Handle version-specific KeyValueStore.get() bug
            stored_value = ctx.storage.get("conversation_turn")
            conversation_turn = stored_value if stored_value is not None else 0

            replies = [
                "Okay, I'm ready for the quiz.",
                "I think the answer is 42.",
                "That was a good lesson. I feel like I'm getting better at Math. I would say my level is advanced now.",
                "Thank you for the lesson!"
            ]

            if conversation_turn < len(replies):
                reply_text = replies[conversation_turn]
                ctx.logger.info(f"Student is replying: {reply_text}")
                await ctx.send(sender, create_text_chat(reply_text))
                ctx.storage.set("conversation_turn", conversation_turn + 1)
            else:
                ctx.logger.info("End of conversation.")

@chat_proto.on_message(ChatAcknowledgement)
def handle_acknowledgement(
    ctx: Context, sender: str, msg: ChatAcknowledgement
):
    ctx.logger.info(
        f"Received acknowledgement from {sender} for message {msg.acknowledged_msg_id}"
    )

agent.include(chat_proto, publish_manifest=True)

if __name__ == "__main__":
    if TUTOR_ADDRESS:
        agent.run()
    else:
        print("\nERROR: Tutor Agent address is missing. Please run tutor_agent.py first to create 'tutor_address.txt'.\n")


