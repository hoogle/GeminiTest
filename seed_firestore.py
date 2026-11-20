# Copyright 2026 Google LLC
# Seed script for Local Travel Concierge Firestore collection.

from google.cloud import firestore

PROJECT_ID = "qwiklabs-gcp-03-a5f043df2e7a"
COLLECTION_NAME = "attractions"

SEEDED_ITEMS = [
    {
        "id": "jiufen-old-street",
        "name": "九份老街 (Jiufen Old Street)",
        "city": "新北市 (New Taipei City)",
        "country": "Taiwan",
        "category": "cultural",
        "vibe": "懷舊山城、紅燈籠茶樓、芋圓小吃",
        "best_season": "秋天、初春",
        "estimated_duration_hours": 3.0,
        "tags": ["老街", "茶文化", "山海景觀", "宮崎駿神隱少女風"],
        "recommended_spots": ["阿妹茶樓", "賴阿婆芋圓", "昇平戲院"],
    },
    {
        "id": "taroko-gorge",
        "name": "太魯閣峽谷步道 (Taroko Gorge Trails)",
        "city": "花蓮縣 (Hualien)",
        "country": "Taiwan",
        "category": "nature",
        "vibe": "大理石峽谷鬼斧神工、壯麗吊橋、溪水清澈",
        "best_season": "春末、秋天",
        "estimated_duration_hours": 5.0,
        "tags": ["大自然", "健行步道", "世界級地質", "斷崖探險"],
        "recommended_spots": ["砂卡礑步道", "燕子口", "白楊步道水濂洞"],
    },
    {
        "id": "kyoto-arashiyama-bamboo",
        "name": "京都嵐山竹林之道與常寂光寺 (Arashiyama Bamboo Grove)",
        "city": "京都市 (Kyoto)",
        "country": "Japan",
        "category": "nature & cultural",
        "vibe": "清幽竹林沙沙聲、日式庭園青苔、清晨幽靜",
        "best_season": "春秋兩季 (櫻花或楓紅)",
        "estimated_duration_hours": 4.0,
        "tags": ["竹林秘境", "古寺巡禮", "散策慢活", "抹茶和果子"],
        "recommended_spots": ["天龍寺曹源池", "常寂光寺", "渡月橋"],
    },
    {
        "id": "kamakura-enoshima",
        "name": "鎌倉江之島海岸散策 (Kamakura & Enoshima)",
        "city": "神奈川縣 (Kanagawa)",
        "country": "Japan",
        "category": "coastal & cultural",
        "vibe": "復古江之電電車、湘南海岸夕陽、大佛古都",
        "best_season": "初夏、秋天",
        "estimated_duration_hours": 6.0,
        "tags": ["灌籃高手平交道", "江之電", "海景神社", "生吻仔魚丼"],
        "recommended_spots": ["鎌倉高校前", "江島神社", "高德院大佛"],
    },
]


def seed():
    print(f"Connecting to Firestore with project '{PROJECT_ID}'...")
    db = firestore.Client(project=PROJECT_ID)
    batch = db.batch()
    for item in SEEDED_ITEMS:
        doc_ref = db.collection(COLLECTION_NAME).document(item["id"])
        batch.set(doc_ref, item)
    batch.commit()
    print(f"Successfully seeded {len(SEEDED_ITEMS)} items into collection '{COLLECTION_NAME}'!")


if __name__ == "__main__":
    seed()
