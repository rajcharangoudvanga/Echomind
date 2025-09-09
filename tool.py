import logging
from dotenv import load_dotenv
from livekit.agents import function_tool, RunContext
import requests
from langchain_community.tools import DuckDuckGoSearchRun
import os
import smtplib
from email.mime.multipart import MIMEMultipart  
from email.mime.text import MIMEText
import openai
import google.generativeai as genai 
from prompts import PROMPT_TEMPLATES
import playwright
from playwright.async_api import async_playwright
import time
import random
import asyncio
load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))




# get the weather for a given city
@function_tool()
async def get_weather(
    context: RunContext,  
    city: str) -> str:
    """
    Get the current weather for a given city.
    """
    try:
        response = requests.get(
            f"https://wttr.in/{city}?format=3")
        if response.status_code == 200:
            logging.info(f"Weather for {city}: {response.text.strip()}")
            return response.text.strip()   
        else:
            logging.error(f"Failed to get weather for {city}: {response.status_code}")
            return f"Could not retrieve weather for {city}."
    except Exception as e:
        logging.error(f"Error retrieving weather for {city}: {e}")
        return f"An error occurred while retrieving weather for {city}." 
    
    
#search the web
@function_tool()
async def search_web(
    context: RunContext,  # type: ignore
    query: str) -> str:
    """
    Search the web using DuckDuckGo.
    """
    try:
        results = DuckDuckGoSearchRun().run(tool_input=query)
        logging.info(f"Search results for '{query}': {results}")
        return results
    except Exception as e:
        logging.error(f"Error searching the web for '{query}': {e}")
        return f"An error occurred while searching the web for '{query}'."    
    

# send an email
@function_tool()       
async def send_email(email_text: str) -> str:
    
    """
    Sends an email. Expects structured input:
    To: recipient@example.com
    Subject: Your subject here
    Body:
    The body of the email goes here.
    """

    try:
        # Split and parse input
        lines = email_text.strip().split("\n")
        to = next((line.split("To:")[1].strip() for line in lines if line.startswith("To:")), None)
        subject = next((line.split("Subject:")[1].strip() for line in lines if line.startswith("Subject:")), None)
        
        # body_index = next((i for i, line in enumerate(lines) if line.strip() == "Body:"), None)
        # if body_index is not None:
        #     body = "\n".join(lines[body_index+1:]).strip()
        # else:
        body = generate_body(subject)  # Auto-generate body


        if not to or not subject or not body:
            return "❌ Error: Email must include 'To:', 'Subject:', and 'Body:'."

        # Credentials
        sender_email = os.getenv("GMAIL_USER")
        app_password = os.getenv("GMAIL_PASSWORD")

        if not sender_email or not app_password:
            return "❌ Missing Gmail credentials in environment variables."

        # Compose email
        msg = MIMEMultipart()
        msg["From"] = sender_email
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        # Send
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, app_password)
            server.sendmail(sender_email, to, msg.as_string())

        return f"✅ Email successfully sent to {to}."

    except Exception as e:
        return f"❌ Failed to send email: {e}"
    
# genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
def detect_intent(subject: str) -> str:
    subject_lower = subject.lower()
    if any(word in subject_lower for word in ["iron man", "avengers", "movie", "character"]):
        return "entertainment"
    elif any(word in subject_lower for word in ["leave", "vacation", "holiday", "absent"]):
        return "leave_request"
    elif any(word in subject_lower for word in ["update", "report", "project", "status"]):
        return "work_update"
    elif any(word in subject_lower for word in ["thank", "appreciation", "grateful"]):
        return "appreciation"
    elif any(word in subject_lower for word in ["inquire", "question", "query"]):
        return "general_inquiry"
    elif any(word in subject_lower for word in ["resignation", "formal", "manager", "hr"]):
        return "professional"
    else:
        return "default"

def generate_body(subject: str) -> str:
    try:
        intent = detect_intent(subject)
        prompt = PROMPT_TEMPLATES.get(intent, PROMPT_TEMPLATES["default"]).format(subject=subject)

        model = genai.GenerativeModel("gemini-1.5-flash")  
        response = model.generate_content(prompt)
        return response.text.strip()

    except Exception as e:
        return f"(Error generating body: {e})"
    
    
# apply jobs in linkedin  
async def random_wait(min_sec=1.5, max_sec=3.5):
    """Waits for a random duration to mimic human behavior."""
    await asyncio.sleep(random.uniform(min_sec, max_sec))

async def click_next_or_submit(page):
    """Safely clicks the next logical button in an application form."""
    try:
        # Check for various common button labels in order of preference
        if await page.query_selector('button:has-text("Submit application")'):
            await page.click('button:has-text("Submit application")')
            return "submit"
        elif await page.query_selector('button:has-text("Next")'):
            await page.click('button:has-text("Next")')
            return "next"
        elif await page.query_selector('button:has-text("Review")'):
            await page.click('button:has-text("Review")')
            return "next"
        elif await page.query_selector('button:has-text("Continue")'):
            await page.click('button:has-text("Continue")')
            return "next"
        else:
            return "done" # No more known steps found
    except Exception as e:
        logging.error(f"Error clicking next/submit button: {e}")
        return "error"

# --- Main Tool Function ---

@function_tool()
async def apply_linkedin_jobs(search_term: str, headless: bool = False, max_pages: int = 5) -> str:
    """
    Automates applying for jobs on LinkedIn using the "Easy Apply" feature.
    
    This function will:
    1. Open a browser and navigate to the LinkedIn login page.
    2. Enter credentials and log in, waiting patiently for the homepage to load.
    3. Navigate to the jobs section and search for the specified term.
    4. Filter for "Easy Apply" jobs.
    5. Loop through the results and apply to jobs that have not been applied to already.
    
    Args:
        search_term: The job title or keyword to search for (e.g., "Python Developer").
        headless: If True, runs the browser in the background. Defaults to False for debugging.
        max_pages: The maximum number of job result pages to process.
    """
    email = os.getenv("LINKEDIN_EMAIL")
    password = os.getenv("LINKEDIN_PASSWORD")
    resume_path = os.getenv("RESUME_PATH")
    logs = ["--- Starting LinkedIn Job Application ---"]

    if not all([email, password]):
        return "❌ Error: LINKEDIN_EMAIL and LINKEDIN_PASSWORD environment variables must be set."

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="en-US"
        )
        page = await context.new_page()

        try:
            # STEP 1: Go to the login page
            await page.goto("https://www.linkedin.com/login")
            logs.append("➡️ Navigated to login page.")
            await random_wait()

            # STEP 2: Enter credentials and submit
            await page.type('input[name="session_key"]', email, delay=random.uniform(50, 100))
            await page.type('input[name="session_password"]', password, delay=random.uniform(50, 100))
            await page.click('button[type="submit"]')
            logs.append("✅ Submitted credentials.")
            print("🔑 Credentials submitted, waiting for login...")

            # STEP 3: Wait for login to complete by looking for the main navigation bar.
            # This is the most reliable method. It waits until the homepage is fully loaded,
            # automatically handling any intermediate security checks or double-login pages.
            # await page.wait_for_selector('nav.global-nav', timeout=45000)
            # logs.append("✅ Login successful, homepage loaded.")
            # await random_wait()

            # STEP 4: Navigate to the Jobs page by clicking the icon
            await page.wait_for_selector('a[href*="/jobs/"]', timeout=10000)
            await page.click('a[href*="/jobs/"]')

            logs.append("🖱️ Clicked 'Jobs' icon.")
            print("🔍 Navigating to Jobs page...")
            await page.wait_for_load_state("networkidle")

            # STEP 5: Perform the job search
            logs.append("🔍 Looking for the job search input fields...")

            job_title_input = 'input[placeholder="Search jobs"]'
            location_input = 'input[placeholder="Search location"]'
            try:
                await page.wait_for_selector(job_title_input, timeout=15000)
                logs.append("✅ Job title input found.")

                # Clear existing job title and enter new one
                await page.fill(job_title_input, "")
                await random_wait(0.5, 1)
                await page.fill(job_title_input, search_term)
                await random_wait()

                # Optionally clear location filter for remote/global jobs
                try:
                    clear_location = page.locator('button[aria-label="Clear location filter"]')
                    if await clear_location.count() > 0:
                        await clear_location.click()
                        logs.append("📍 Cleared location filter.")
                except Exception:
                    logs.append("📍 No location filter to clear.")

                # Press enter to trigger the search
                await page.press(job_title_input, "Enter")
                logs.append(f"✅ Submitted search for '{search_term}'.")
                await random_wait(3, 5)

            except Exception as e:
                logs.append(f"❌ Failed to perform job search: {e}")
                return "\n".join(logs)

            # STEP 6: Apply the "Easy Apply" filter
            try:
                easy_apply_button = page.locator("button:has-text('Easy Apply')")
                if await easy_apply_button.count() > 0:
                    await easy_apply_button.first.click()
                    logs.append("🎯 'Easy Apply' filter applied.")
                    await random_wait()
                else:
                    logs.append("⚠️ 'Easy Apply' filter not found.")
            except Exception as e:
                logs.append(f"⚠️ Error applying 'Easy Apply' filter: {e}")


            # STEP 7: Main application loop
            applied_count = 0
            for page_num in range(1, max_pages + 1):
                logs.append(f"--- Scanning Page {page_num} ---")
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(3) # Wait for jobs to render

                job_listings = await page.locator(".jobs-search-results__list-item").all()
                if not job_listings:
                    logs.append("❌ No jobs found on this page.")
                    break

                for job in job_listings:
                    try:
                        await job.scroll_into_view_if_needed()
                        await job.click()
                        await random_wait(1, 2)

                        # Check if already applied in the right-hand pane
                        if await page.locator('span:has-text("Applied")').count() > 0:
                            logs.append("🔁 Already applied. Skipping.")
                            continue

                        # Click the "Easy Apply" button
                        await page.locator('button:has-text("Easy Apply")').first.click(timeout=5000)
                        await random_wait(2, 4)

                        # Handle resume upload if the dialog appears
                        if resume_path and await page.locator('input[type="file"]').count() > 0:
                            await page.locator('input[type="file"]').set_input_files(resume_path)
                            logs.append("📎 Resume attached.")
                            await random_wait()

                        # Step through the application form
                        while True:
                            result = await click_next_or_submit(page)
                            if result == "submit":
                                applied_count += 1
                                logs.append(f"✅ SUCCESSFULLY APPLIED! (Total: {applied_count})")
                                break
                            elif result in ["done", "error"]:
                                logs.append("ℹ️ Reached end of form or encountered an error.")
                                # Close the modal to continue
                                await page.locator('button[aria-label="Dismiss"]').click()
                                break
                            await random_wait(1, 2)
                    except Exception as e:
                        logs.append(f"❌ Error with one job, skipping: {e}")
                        # Try to close any open modal before moving on
                        if await page.locator('button[aria-label="Dismiss"]').count() > 0:
                            await page.locator('button[aria-label="Dismiss"]').click()
                        continue
                
                # Navigate to the next page
                try:
                    logs.append("📄 Moving to next page...")
                    await page.click(f'button[aria-label="Page {page_num + 1}"]')
                except Exception:
                    logs.append("✅ No more pages to process.")
                    break

        except Exception as e:
            logs.append(f"🔥 A critical error occurred: {e}")
            await page.screenshot(path="error_screenshot.png")
            logs.append("📸 Screenshot saved as error_screenshot.png")
        finally:
            await browser.close()
            logs.append("🚪 Browser closed.")

    return "\n".join(logs)


@function_tool()
async def news_report(user_query: str) -> str:
    """
    Fetches and summarizes today's news based on a specific topic mentioned in the user query.
    Returns text only; the LiveKit voice agent will handle speech synthesis.
    """
    try:
        NEWS_API_KEY = os.getenv("NEWS_API_KEY")
        GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

        if not NEWS_API_KEY:
            return "❌ NEWS_API_KEY missing. Please set it in .env"
        if not GOOGLE_API_KEY:
            return "❌ GOOGLE_API_KEY missing. Please set it in .env"

        # --- Extract topic ---
        uq = user_query.lower()
        topic = "general"
        if "news on" in uq:
            topic = uq.split("news on")[-1].strip()
        elif "news about" in uq:
            topic = uq.split("news about")[-1].strip()
        elif "today's" in uq:
            topic = uq.split("today's")[-1].strip()
        elif "latest" in uq:
            topic = uq.split("latest")[-1].strip()
        else:
            words = uq.split()
            if len(words) > 2:
                topic = " ".join(words[-3:])
            elif words:
                topic = words[-1]

        # --- Fetch news ---
        url = (
            f"https://newsapi.org/v2/everything?"
            f"q={topic}&sortBy=publishedAt&language=en&apiKey={NEWS_API_KEY}"
        )
        response = requests.get(url).json()
        articles = response.get("articles", [])
        if not articles:
            return f"❌ No recent news found for {topic}."

        news_text = " ".join(
            f"{art['title']}. {art.get('description','')}"
            for art in articles[:5]
        )

        # --- Summarize with Gemini ---
        genai.configure(api_key=GOOGLE_API_KEY)
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = (
            f"Summarize today's latest news about {topic} "
            f"in a short, clear overview:\n\n{news_text}\n\nSummary:"
        )
        g_response = model.generate_content(prompt)

        summary = getattr(g_response, "text", "").strip()
        if not summary:
            return f"⚠️ Gemini returned no summary for {topic}."

        return f"📰 Here is today's {topic} news summary:\n\n{summary}"

    except Exception as e:
        return f"❌ Failed to fetch or summarize news: {e}"

