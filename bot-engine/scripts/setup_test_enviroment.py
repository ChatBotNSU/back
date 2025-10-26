#!/usr/bin/env python3
"""
Настройка тестового окружения: создание бакета и загрузка тестового сценария
"""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import json
import io
from minio import Minio
from minio.error import S3Error
import redis

def setup_minio():
    """Настройка MinIO: создание бакета и загрузка тестового сценария"""
    
    client = Minio(
        endpoint="localhost:9100",
        access_key="minioadmin",
        secret_key="minioadmin",
        secure=False
    )
    
    bucket_name = "bot-scenarios"
    
    try:
        # Создаем бакет если не существует
        if not client.bucket_exists(bucket_name):
            client.make_bucket(bucket_name)
            print(f"✅ Created bucket: {bucket_name}")
        else:
            print(f"✅ Bucket {bucket_name} already exists")
        
        # Загружаем тестовый сценарий с правильной структурой
        scenario_data = {
            "id": "simple-support-bot",
            "name": "Simple Support Bot",
            "description": "Тестовый бот поддержки",
            "startBlockId": "welcome",  # ← ОБЯЗАТЕЛЬНОЕ поле в camelCase
            "variables": {
                "user_name": "Гость"
            },
            "blocks": {
                "welcome": {
                    "id": "welcome",
                    "type": "Prompt",
                    "config": {
                        "message": "Добро пожаловать в поддержку! Как вас зовут?"
                    },
                    "nextBlocks": [  # ← camelCase
                        {
                            "sourceHandle": "default",
                            "targetBlockId": "get_name"
                        }
                    ]
                },
                "get_name": {
                    "id": "get_name",
                    "type": "Answer",
                    "config": {
                        "question": "Введите ваше имя:",
                        "variable": "user_name"
                    },
                    "nextBlocks": [  # ← camelCase
                        {
                            "sourceHandle": "success", 
                            "targetBlockId": "main_menu"
                        }
                    ]
                },
                "main_menu": {
                    "id": "main_menu",
                    "type": "Choice",
                    "config": {
                        "question": "Привет, {{user_name}}! Чем могу помочь?",
                        "options": [
                            {
                                "label": "Техническая поддержка",
                                "value": "support"
                            },
                            {
                                "label": "Информация о продуктах", 
                                "value": "products"
                            },
                            {
                                "label": "Связь с менеджером",
                                "value": "manager"
                            }
                        ]
                    },
                    "nextBlocks": [  # ← camelCase
                        {
                            "sourceHandle": "support",
                            "targetBlockId": "tech_support"
                        },
                        {
                            "sourceHandle": "products",
                            "targetBlockId": "product_info"
                        },
                        {
                            "sourceHandle": "manager",
                            "targetBlockId": "contact_manager"
                        }
                    ]
                },
                "tech_support": {
                    "id": "tech_support",
                    "type": "Prompt",
                    "config": {
                        "message": "🔧 Перенаправляю вас в техническую поддержку..."
                    },
                    "nextBlocks": [  # ← camelCase
                        {
                            "sourceHandle": "default",
                            "targetBlockId": "exit"
                        }
                    ]
                },
                "product_info": {
                    "id": "product_info",
                    "type": "Prompt", 
                    "config": {
                        "message": "📦 Информация о продуктах: ..."
                    },
                    "nextBlocks": [  # ← camelCase
                        {
                            "sourceHandle": "default", 
                            "targetBlockId": "exit"
                        }
                    ]
                },
                "contact_manager": {
                    "id": "contact_manager",
                    "type": "Prompt",
                    "config": {
                        "message": "👨‍💼 Связываю вас с менеджером..."
                    },
                    "nextBlocks": [  # ← camelCase
                        {
                            "sourceHandle": "default",
                            "targetBlockId": "exit"
                        }
                    ]
                },
                "exit": {
                    "id": "exit", 
                    "type": "Exit",
                    "config": {
                        "message": "✅ Спасибо за обращение! Хорошего дня!",
                        "clearContext": True
                    },
                    "nextBlocks": []  # ← camelCase
                }
            }
        }
        
        # Конвертируем данные в bytes и создаем BytesIO объект
        json_data = json.dumps(scenario_data, ensure_ascii=False, indent=2).encode('utf-8')
        data_stream = io.BytesIO(json_data)
        data_length = len(json_data)
        
        # Загружаем сценарий в MinIO
        client.put_object(
            bucket_name=bucket_name,
            object_name="simple-support-bot.json",
            data=data_stream,
            length=data_length,
            content_type='application/json'
        )
        
        print("✅ Test scenario uploaded to MinIO")
        
        # Проверяем что файл загружен
        objects = client.list_objects(bucket_name)
        print("📁 Files in bucket:")
        for obj in objects:
            print(f"   - {obj.object_name}")
            
        # Выводим содержимое для отладки
        print("\n📋 Scenario content preview:")
        print(json.dumps(scenario_data, ensure_ascii=False, indent=2)[:500] + "...")
            
    except S3Error as e:
        print(f"❌ MinIO error: {e}")

def test_redis():
    """Тестирование подключения к Redis"""
    try:
        r = redis.Redis(host='localhost', port=6379, decode_responses=True)
        r.ping()
        print("✅ Redis connection successful")
        
        # Создаем consumer group если не существует
        try:
            r.xgroup_create('bot-messages', 'bot-engine', '0', mkstream=True)
            print("✅ Redis consumer group created")
        except Exception as e:
            if "BUSYGROUP" in str(e):
                print("✅ Redis consumer group already exists")
            else:
                raise e
                
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")

if __name__ == "__main__":
    print("🚀 Setting up test environment...")
    setup_minio()
    test_redis()
    print("🎉 Test environment is ready!")