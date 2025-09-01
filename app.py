import re
import asyncio
from textwrap import dedent
from datetime import datetime, timedelta, date
import streamlit as st
from icalendar import Calendar, Event
import os
from agno.agent import Agent
from agno.tools.mcp import MultiMCPTools
from agno.models.google import Gemini
from agno.tools.googlesearch import GoogleSearchTools

# -----------------------------
# 📅 ICS Calendar Generator
# -----------------------------
def generate_ics_content(plan_text: str, start_date: datetime = None) -> bytes:
    cal = Calendar()
    cal.add('prodid', '-//AI Travel Planner//github.com//')
    cal.add('version', '2.0')

    if start_date is None:
        start_date = datetime.today()

    day_pattern = re.compile(r'Day (\d+)[:\s]+(.*?)(?=Day \d+|$)', re.DOTALL)
    days = day_pattern.findall(plan_text)

    if not days:
        event = Event()
        event.add('summary', "Travel Itinerary")
        event.add('description', plan_text)
        event.add('dtstart', start_date.date())
        event.add('dtend', start_date.date())
        event.add("dtstamp", datetime.now())
        cal.add_component(event)
    else:
        for day_num, day_content in days:
            day_num = int(day_num)
            current_date = start_date + timedelta(days=day_num - 1)
            event = Event()
            event.add('summary', f"Day {day_num} Itinerary")
            event.add('description', day_content.strip())
            event.add('dtstart', current_date.date())
            event.add('dtend', current_date.date())
            event.add("dtstamp", datetime.now())
            cal.add_component(event)

    return cal.to_ical()

# -----------------------------
# 🚀 Travel Planner (MCP + Gemini)
# -----------------------------
async def run_mcp_travel_planner(origin: str, destination: str, num_days: int,
                                 preferences: str, budget: int,
                                 gemini_key: str, google_maps_key: str):
    os.environ["GOOGLE_MAPS_API_KEY"] = google_maps_key

    mcp_tools = MultiMCPTools(
        [
            "npx -y @openbnb/mcp-server-airbnb --ignore-robots-txt",
            "npx @gongrzhe/server-travelplanner-mcp"
        ],
        env={"GOOGLE_MAPS_API_KEY": google_maps_key},
        timeout_seconds=60,
    )

    try:
        st.info("🔌 Connecting to MCP tools...")
        await mcp_tools.connect()
        st.success("✅ MCP tools connected.")

        # Debug: list connected tools
        if hasattr(mcp_tools, "tools") and mcp_tools.tools:
            st.write("🔧 Available MCP Tools:", [t.name for t in mcp_tools.tools])
        else:
            st.warning("⚠️ No MCP tools detected after connect().")

        travel_planner = Agent(
            name="Travel Planner",
            role="Creates detailed itineraries with Gemini + MCP",
            model=Gemini(id="gemini-1.5-flash", api_key=gemini_key),
            description=dedent("""\
                You are a professional travel consultant AI.
                Use Airbnb (via MCP), Google Maps MCP, and Google Search
                to create complete itineraries without asking questions.
            """),
            instructions=[
                "Always generate a complete, day-by-day itinerary immediately.",
                "Use Google Maps MCP to calculate distances and travel times.",
                "Include accommodation, dining, costs, safety, and weather details.",
            ],
            tools=[mcp_tools, GoogleSearchTools()],
            add_datetime_to_instructions=True,
            markdown=True,
        )

        prompt = f"""
        Create a {num_days}-day travel plan:
        Origin: {origin}
        Destination: {destination}
        Budget: ${budget}
        Preferences: {preferences}

        Include:
        - Airbnb options within budget
        - Day-by-day itinerary with times/distances (via Google Maps MCP)
        - Dining, transport, weather, safety, and cultural tips
        """

        st.info("🧠 Sending request to Travel Planner agent...")
        response = await travel_planner.arun(prompt)

        if not response:
            st.error("⚠️ Agent returned no response.")
            return "⚠️ No response from planner."

        return response.content

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        st.error(f"❌ Exception occurred: {e}")
        st.text(error_details)  # show full traceback for debugging
        return f"❌ Error running planner: {e}"

    finally:
        try:
            await mcp_tools.close()
            st.success("🔒 MCP tools closed.")
        except Exception as e:
            st.warning(f"⚠️ Failed to close MCP tools: {e}")


def run_travel_planner(*args, **kwargs):
    return asyncio.run(run_mcp_travel_planner(*args, **kwargs))

# -----------------------------
# 🖼️ Streamlit UI
# -----------------------------
st.set_page_config(page_title="✈️ MCP AI Travel Planner", page_icon="✈️", layout="wide")

if 'itinerary' not in st.session_state:
    st.session_state.itinerary = None

st.title("✈️ MCP AI Travel Planner")
st.caption("Powered by Gemini + MCP (Airbnb, Google Maps, Search)")

with st.sidebar:
    gemini_api_key = st.text_input("Gemini API Key", type="password")
    google_maps_key = st.text_input("Google Maps API Key", type="password")
    api_keys_provided = bool(gemini_api_key and google_maps_key)

if api_keys_provided:
    st.header("🌍 Trip Details")
    col1, col2 = st.columns(2)
    with col1:
        origin = st.text_input("Origin City", placeholder="e.g., Addis Ababa, Ethiopia")
        destination = st.text_input("Destination", placeholder="e.g., Gondar, Ethiopia")
        num_days = st.number_input("Days", 1, 30, 7)
    with col2:
        budget = st.number_input("Budget (USD)", 100, 10000, 2000, step=100)
        start_date = st.date_input("Start Date", min_value=date.today())

    preferences = st.text_area("🎯 Preferences", height=100,
                               placeholder="e.g., romantic, family-friendly, adventure")

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("🎯 Generate Itinerary", type="primary"):
            if not origin.strip() or not destination.strip():
                st.error("Enter both origin and destination.")
            else:
                with st.spinner("🚀 Planning trip with MCP..."):
                    st.session_state.itinerary = run_travel_planner(
                        origin=origin,
                        destination=destination,
                        num_days=num_days,
                        preferences=preferences or "General tourism",
                        budget=budget,
                        gemini_key=gemini_api_key,
                        google_maps_key=google_maps_key
                    )

    with col2:
        if st.session_state.itinerary:
            ics_data = generate_ics_content(
                st.session_state.itinerary,
                datetime.combine(start_date, datetime.min.time())
            )
            st.download_button(
                label="📅 Download Calendar",
                data=ics_data,
                file_name=f"trip_{destination.lower().replace(' ', '_')}.ics",
                mime="text/calendar"
            )

    if st.session_state.itinerary:
        st.header("📋 Your Itinerary")
        st.markdown(st.session_state.itinerary)
else:
    st.info("🔑 Please enter API keys in the sidebar.")

