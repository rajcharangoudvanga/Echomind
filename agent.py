from dotenv import load_dotenv
import os
from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions
from livekit.plugins import noise_cancellation
from livekit.plugins import google

from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION
from tool import get_weather, news_report, search_web, send_email, apply_linkedin_jobs

load_dotenv()


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=AGENT_INSTRUCTION,
            llm=google.beta.realtime.RealtimeModel(
                voice="Aoede",
                temperature=0.8,
                api_key=os.getenv("GOOGLE_API_KEY"),
            ),
            tools=[
                get_weather,
                search_web,
                send_email,
                apply_linkedin_jobs,
                news_report
            ],
        )

async def entrypoint(ctx: agents.JobContext):
    print("🔌 Connecting to LiveKit...")
    await ctx.connect()

    session = AgentSession()  # ✅ No 'agent' here

    print("🚀 Starting agent session...")
    await session.start(
        room=ctx.room,
        agent=Assistant(),  # ✅ This is the correct place
        room_input_options=RoomInputOptions(
            video_enabled=True,
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    print("💬 Generating reply from instructions...")
    await session.generate_reply(
        instructions=SESSION_INSTRUCTION,
    )



if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
