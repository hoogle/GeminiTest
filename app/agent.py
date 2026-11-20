# ruff: noqa
# Copyright 2026 Google LLC
# Licensed under the Apache License, Version 2.0.

import datetime
from typing import List, Optional
from zoneinfo import ZoneInfo

import json
from pathlib import Path
import re
import sys

# Ensure vendor modules (a2ui-agent-sdk / a2ui-core) are accessible
VENDOR_DIR = str(Path(__file__).resolve().parent / "vendor")
if VENDOR_DIR not in sys.path:
    sys.path.insert(0, VENDOR_DIR)

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from app.a2ui_utils import a2ui_callback

from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors.agent_engine_sandbox_code_executor import (
    AgentEngineSandboxCodeExecutor,
)
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.cloud import firestore, storage
from google.genai import types

MODEL = "gemini-3.8-flash"
PROJECT_ID = "qwiklabs-gcp-03-a5f043df2e7a"
COLLECTION_NAME = "attractions"
BUCKET_NAME = "local-travel-concierge-qwiklabs-gcp-03-a5f043df2e7a"

# Load Agent Engine resource name from deployment_metadata.json if available
METADATA_PATH = Path(__file__).resolve().parent.parent / "deployment_metadata.json"
AGENT_ENGINE_RESOURCE_NAME = None
if METADATA_PATH.is_file():
    try:
        with open(METADATA_PATH, "r", encoding="utf-8") as f:
            metadata = json.load(f)
            AGENT_ENGINE_RESOURCE_NAME = metadata.get("remote_agent_runtime_id")
    except Exception:
        pass
if not AGENT_ENGINE_RESOURCE_NAME:
    AGENT_ENGINE_RESOURCE_NAME = (
        "projects/418081633286/locations/us-east1/reasoningEngines/2554305149300375552"
    )

# The Memory Bank ID is the last component of the Agent Engine resource name
MEMORY_BANK_ID = AGENT_ENGINE_RESOURCE_NAME.split("/")[-1]


async def generate_memories_callback(callback_context: CallbackContext):
    """After each turn, send the session to Memory Bank for extraction and persistence."""
    await callback_context.add_session_to_memory()
    return None


def _get_db():
    return firestore.Client(project=PROJECT_ID)


def list_attractions(city: Optional[str] = None, category: Optional[str] = None) -> List[dict]:
    """Lists or filters travel attractions from the local catalog.

    Args:
        city: Optional city or region filter (e.g., 'Kyoto', 'New Taipei City', 'Hualien').
        category: Optional category filter (e.g., 'nature', 'cultural', 'coastal').

    Returns:
        A list of attraction dictionaries matching the criteria.
    """
    db = _get_db()
    docs = db.collection(COLLECTION_NAME).stream()
    results = []
    for doc in docs:
        data = doc.to_dict()
        if city and city.lower() not in data.get("city", "").lower() and city.lower() not in data.get("country", "").lower():
            continue
        if category and category.lower() not in data.get("category", "").lower():
            continue
        results.append(data)
    return results


def get_attraction_details(attraction_id: str) -> dict:
    """Retrieves full details for a specific travel attraction or hidden gem.

    Args:
        attraction_id: The unique ID of the attraction (e.g., 'jiufen-old-street', 'taroko-gorge', 'kyoto-arashiyama-bamboo').

    Returns:
        A dictionary with attraction details, or an error message if not found.
    """
    db = _get_db()
    doc = db.collection(COLLECTION_NAME).document(attraction_id).get()
    if not doc.exists:
        return {"error": f"Attraction '{attraction_id}' not found in catalog."}
    return doc.to_dict()


def add_attraction(
    attraction_id: str,
    name: str,
    city: str,
    country: str,
    category: str,
    vibe: str,
    best_season: str,
    estimated_duration_hours: float,
    tags: List[str],
    recommended_spots: List[str],
) -> dict:
    """Adds a new attraction, hidden gem, or recommended spot to the travel catalog.

    Args:
        attraction_id: A URL-safe slug ID (e.g. 'taipei-101', 'shibuya-sky').
        name: Name of the spot.
        city: City or district location.
        country: Country (e.g. 'Taiwan', 'Japan').
        category: Category such as 'nature', 'cultural', 'foodie', 'urban'.
        vibe: Short description of the atmosphere and unique experience.
        best_season: Recommended season to visit.
        estimated_duration_hours: Recommended visiting duration in hours.
        tags: List of descriptive keyword tags.
        recommended_spots: List of highlights or sub-locations to check out.

    Returns:
        Status dictionary confirming addition.
    """
    db = _get_db()
    data = {
        "id": attraction_id,
        "name": name,
        "city": city,
        "country": country,
        "category": category,
        "vibe": vibe,
        "best_season": best_season,
        "estimated_duration_hours": estimated_duration_hours,
        "tags": tags,
        "recommended_spots": recommended_spots,
    }
    db.collection(COLLECTION_NAME).document(attraction_id).set(data)
    return {"status": "success", "message": f"Successfully added '{name}' to catalog.", "data": data}


def get_weather(query: str) -> dict:
    """Fetches real-time live weather conditions for any travel destination using the Open-Meteo public API.

    Args:
        query: Destination city or place name (e.g., 'Kyoto', 'Tokyo', 'Taipei', 'Hualien', 'New Taipei City').

    Returns:
        A dictionary with live weather data (temperature, apparent temperature, humidity, wind, and conditions).
    """
    import json
    import urllib.parse
    import urllib.request

    try:
        # Step 1: Geocoding via Open-Meteo
        encoded_query = urllib.parse.quote(query.strip())
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={encoded_query}&count=1&language=zh&format=json"
        req = urllib.request.Request(geo_url, headers={"User-Agent": "LocalTravelConcierge/1.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            geo_data = json.loads(response.read().decode())

        if not geo_data.get("results"):
            return {"error": f"找不到目的地 '{query}' 的地理座標資訊。"}

        place = geo_data["results"][0]
        name = place.get("name", query)
        country = place.get("country", "")
        lat, lon = place["latitude"], place["longitude"]

        # Step 2: Live Weather via Open-Meteo Forecast API
        weather_url = (
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            "&current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m"
            "&timezone=auto"
        )
        req_w = urllib.request.Request(weather_url, headers={"User-Agent": "LocalTravelConcierge/1.0"})
        with urllib.request.urlopen(req_w, timeout=5) as response_w:
            w_data = json.loads(response_w.read().decode())

        current = w_data.get("current", {})
        code = current.get("weather_code", 0)

        # WMO Weather interpretation codes
        condition_map = {
            0: "晴朗無雲",
            1: "大部分晴朗",
            2: "局部多雲",
            3: "陰天",
            45: "有霧",
            48: "凍霧",
            51: "細微小雨",
            61: "短暫陣雨",
            63: "中度降雨",
            65: "劇烈大雨",
            71: "降雪",
            80: "陣雨",
            95: "雷陣雨",
        }
        condition_desc = condition_map.get(code, "多雲或晴朗")

        return {
            "query": query,
            "resolved_location": f"{name}, {country}",
            "temperature_celsius": current.get("temperature_2m"),
            "apparent_temperature_celsius": current.get("apparent_temperature"),
            "humidity_percent": current.get("relative_humidity_2m"),
            "condition": condition_desc,
            "wind_speed_kmh": current.get("wind_speed_10m"),
            "precipitation_mm": current.get("precipitation"),
        }
    except Exception as e:
        return {"error": f"取得即時天氣時發生錯誤: {str(e)}"}



def get_current_time(city: str) -> str:
    """Simulates getting current local time for a travel destination.

    Args:
        city: City name.

    Returns:
        Current time string.
    """
    c = city.lower()
    if "tokyo" in c or "kyoto" in c or "japan" in c or "日本" in c or "京都" in c:
        tz = ZoneInfo("Asia/Tokyo")
    else:
        tz = ZoneInfo("Asia/Taipei")

    now = datetime.datetime.now(tz)
    return f"{city} 當前當地時間為：{now.strftime('%Y-%m-%d %H:%M:%S %Z')}"


def calculate_travel_budget(
    destination: str,
    days: int,
    travelers: int = 1,
    budget_level: str = "moderate",
    currency: str = "TWD",
) -> dict:
    """Calculates an estimated breakdown of travel budget for a destination.

    Args:
        destination: Destination city or country (e.g., 'Kyoto', 'Tokyo', 'Taiwan', 'Hualien').
        days: Number of travel days (minimum 1).
        travelers: Number of travelers (default 1).
        budget_level: Spending style - 'budget' (小資背包), 'moderate' (舒適品質), or 'luxury' (奢華享受).
        currency: Output currency ('TWD' or 'JPY', default 'TWD').

    Returns:
        A dictionary containing detailed cost breakdown (lodging, dining, transit, activities) and total estimate.
    """
    days = max(1, days)
    travelers = max(1, travelers)
    level = budget_level.lower()

    # Base cost per person per day in TWD
    rates = {
        "budget": {"stay": 1200, "food": 600, "transit": 250, "activity": 300},
        "moderate": {"stay": 2800, "food": 1400, "transit": 500, "activity": 700},
        "luxury": {"stay": 6500, "food": 3200, "transit": 1200, "activity": 1800},
    }
    tier = rates.get(level, rates["moderate"])

    # Destination multiplier
    dest_lower = destination.lower()
    dest_factor = 1.25 if any(k in dest_lower for k in ["japan", "tokyo", "kyoto", "日本", "東京", "京都"]) else 1.0

    stay_total = round(tier["stay"] * days * (travelers if travelers == 1 else (travelers * 0.75)) * dest_factor)
    food_total = round(tier["food"] * days * travelers * dest_factor)
    transit_total = round(tier["transit"] * days * travelers * dest_factor)
    activity_total = round(tier["activity"] * days * travelers * dest_factor)

    subtotal_twd = stay_total + food_total + transit_total + activity_total
    emergency_buffer_twd = round(subtotal_twd * 0.1)
    grand_total_twd = subtotal_twd + emergency_buffer_twd

    # Conversion factor if JPY requested
    jpy_rate = 4.65  # 1 TWD ~ 4.65 JPY
    multiplier = jpy_rate if currency.upper() == "JPY" else 1.0
    display_currency = "JPY" if currency.upper() == "JPY" else "TWD"

    return {
        "destination": destination,
        "days": days,
        "travelers": travelers,
        "budget_level": budget_level,
        "currency": display_currency,
        "breakdown": {
            "lodging": round(stay_total * multiplier),
            "dining": round(food_total * multiplier),
            "transit": round(transit_total * multiplier),
            "activities": round(activity_total * multiplier),
            "emergency_reserve": round(emergency_buffer_twd * multiplier),
        },
        "total_estimated": round(grand_total_twd * multiplier),
        "per_person_estimated": round((grand_total_twd * multiplier) / travelers),
    }


def geocode_address(address: str) -> dict:
    """Uses Google Maps Geocoding API to turn a street address or place name into geographic coordinates.

    Args:
        address: The address or place name to geocode (e.g., 'Taipei 101', 'Kyoto Station', '九份老街').

    Returns:
        A dictionary containing name, formatted address, and latitude/longitude coordinates.
    """
    import json
    import os
    import urllib.parse
    import urllib.request

    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return {"error": "未設定 GOOGLE_MAPS_API_KEY 環境變數。"}

    try:
        encoded_addr = urllib.parse.quote(address.strip())
        url = f"https://maps.googleapis.com/maps/api/geocode/json?address={encoded_addr}&key={api_key}"
        req = urllib.request.Request(url, headers={"User-Agent": "LocalTravelConcierge/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())

        if data.get("status") != "OK" or not data.get("results"):
            return {
                "error": f"Geocoding 查詢失敗: {data.get('status')}",
                "message": data.get("error_message", "查無此地址座標。"),
            }

        first_res = data["results"][0]
        return {
            "query": address,
            "address": first_res.get("formatted_address"),
            "location": first_res.get("geometry", {}).get("location", {}),
            "place_id": first_res.get("place_id"),
        }
    except Exception as e:
        return {"error": f"呼叫 Geocoding API 發生異常: {str(e)}"}


def find_nearby_places(latitude: float, longitude: float, place_type: str = "tourist_attraction", radius_meters: float = 1000.0, max_results: int = 5) -> dict:
    """Uses Google Maps Places API (New) searchNearby REST endpoint to find nearby places of a given type.

    Args:
        latitude: Center latitude coordinate.
        longitude: Center longitude coordinate.
        place_type: Place type to search for (e.g., 'tourist_attraction', 'restaurant', 'cafe', 'historical_landmark').
        radius_meters: Search radius in meters (default 1000m, max 50000m).
        max_results: Maximum number of results to return (default 5, max 20).

    Returns:
        A dictionary containing the list of nearby places with key fields (name, address, location).
    """
    import json
    import os
    import urllib.request

    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return {"error": "未設定 GOOGLE_MAPS_API_KEY 環境變數。"}

    try:
        url = "https://places.googleapis.com/v1/places:searchNearby"
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location",
        }
        body = {
            "includedTypes": [place_type],
            "maxResultCount": min(max(1, max_results), 20),
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": latitude, "longitude": longitude},
                    "radius": min(max(10.0, radius_meters), 50000.0),
                }
            },
        }

        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())

        results = []
        for p in data.get("places", []):
            results.append({
                "name": p.get("displayName", {}).get("text"),
                "address": p.get("formattedAddress"),
                "location": p.get("location"),
            })

        return {
            "center": {"latitude": latitude, "longitude": longitude},
            "type": place_type,
            "places_count": len(results),
            "places": results,
        }
    except Exception as e:
        return {"error": f"呼叫 Places API (New) 發生異常: {str(e)}"}


async def generate_attraction_image(
    prompt: str,
    item_id: str,
    tool_context: ToolContext,
) -> dict:
    """Generates a scenic, atmospheric postcard image for a travel destination or attraction using the gemini-3.1-flash-lite-image model.

    The generated image is:
    1. Saved as an ADK artifact via tool_context.save_artifact so it displays in the Playground's Artifacts panel.
    2. Uploaded directly as in-memory bytes to the public Google Cloud Storage bucket.

    Args:
        prompt: A descriptive prompt detailing the scene, mood, lighting, and cultural essence (e.g. 'A scenic postcard of Jiufen Old Street at dusk with glowing red lanterns and mountain mist').
        item_id: An identifier or slug for the attraction (e.g. 'jiufen-old-street', 'kyoto-arashiyama').
        tool_context: The ADK ToolContext instance injected automatically by the runtime.

    Returns:
        A dictionary with the public HTTPS URL, artifact filename, and status.
    """
    try:
        # Step 1: Generate image using gemini-3.1-flash-lite-image in global region
        client = genai.Client(location="global")
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=prompt,
        )

        image_bytes = None
        mime_type = "image/jpeg"
        if response.candidates and response.candidates[0].content:
            for part in response.candidates[0].content.parts:
                if part.inline_data and part.inline_data.data:
                    image_bytes = part.inline_data.data
                    mime_type = part.inline_data.mime_type or "image/jpeg"
                    break

        if not image_bytes:
            return {"error": "未能成功生成圖片內容。"}

        # Normalize extension
        ext = "jpg" if "jpeg" in mime_type else "png"
        clean_id = re.sub(r"[^a-zA-Z0-9_-]", "_", item_id).strip("_") or "attraction"
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{clean_id}_{timestamp}.{ext}"

        # Step 2: Save as ADK artifact via tool_context
        artifact_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        artifact_version = await tool_context.save_artifact(
            filename=filename,
            artifact=artifact_part,
        )

        # Step 3: Upload image bytes to public Cloud Storage bucket
        storage_client = storage.Client(project=PROJECT_ID)
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(f"images/{filename}")
        blob.upload_from_string(image_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/images/{filename}"

        return {
            "status": "success",
            "item_id": item_id,
            "filename": filename,
            "artifact_version": artifact_version,
            "public_url": public_url,
            "message": f"成功生成景點意象圖並儲存至 Artifacts 與 Cloud Storage: {public_url}",
        }
    except Exception as e:
        return {"error": f"生成或儲存圖片時發生錯誤: {str(e)}"}


# Configure A2UI Schema Manager with version 0.8 and Basic Catalog
schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

a2ui_instruction = schema_manager.generate_system_prompt(
    role_description="""你是一位專業且熱情的在地深度旅遊規劃顧問（Local Travel Concierge）。
你的任務是協助旅客探索並規劃真實、道地的在地旅行，挖掘私房景點與文化美食。
重要記憶守則：你必須特別注意並牢記旅客在過去或當前對話中提及的所有過敏原（如花生、海鮮、麩質、青黴素/盤尼西林、堅果等）、飲食禁忌與健康安全限制。在推薦任何餐廳、小吃、美食行程或在地體驗時，必須嚴格避開使用者的過敏原，主動提醒飲食安全。
同時，你也會記住旅客喜好的旅行節奏與習慣的交通方式，為旅客量身打造專屬行程。
你可以利用 tools 查詢已建立在 Firestore 景點目錄中的私房景點與行程資訊（`list_attractions`、`get_attraction_details`），
也能將使用者推薦的新景點寫入目錄庫（`add_attraction`），查詢當地天氣（`get_weather`）與時間（`get_current_time`），
幫旅客精算旅程預算分配（`calculate_travel_budget`），
使用 Google Maps 工具進行經緯度轉換（`geocode_address`）與周邊熱門地點搜尋（`find_nearby_places`），
使用最新生成式模型為私房景點創作氛圍明信片意象圖（`generate_attraction_image`），
並能在安全隔離的 Agent Engine Python 沙盒環境中執行計算、資料統計分析或複雜的行程演算法。
請使用繁體中文（台灣）以親切、專業、富有旅人溫度的口吻回覆使用者。""",
    workflow_description="Analyze the request and return structured UI when appropriate.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        '{"Image": {"url": {"literalString": "https://..."}}}. Never point an '
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=a2ui_instruction,
    tools=[
        PreloadMemoryTool(),
        list_attractions,
        get_attraction_details,
        add_attraction,
        get_weather,
        get_current_time,
        calculate_travel_budget,
        geocode_address,
        find_nearby_places,
        generate_attraction_image,
    ],
    code_executor=AgentEngineSandboxCodeExecutor(
        agent_engine_resource_name=AGENT_ENGINE_RESOURCE_NAME,
    ),
    after_model_callback=a2ui_callback,
    after_agent_callback=generate_memories_callback,
)


app = App(
    root_agent=root_agent,
    name="app",
)
