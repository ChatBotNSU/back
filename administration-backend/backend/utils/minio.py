import json
import io
from minio import Minio
from config import get_config

config = get_config()

client = Minio(
        f"{config.minio.host}:{config.minio.port}",
        config.minio.access_key,
        config.minio.secret_key
    )
    
bucket_name = config.minio.bucket_name

def save_json_to_minio(
    data: dict,
    bot_name: str,
    user_id: int
) -> str:
    if not client.bucket_exists(bucket_name):
        client.make_bucket(bucket_name)

    object_key = f"json/{bot_name}_{user_id}.json"
    
    json_str = json.dumps(data, ensure_ascii=False)
    data_bytes = json_str.encode('utf-8')
    data_stream = io.BytesIO(data_bytes)
    
    client.put_object(
        bucket_name=bucket_name,
        object_name=object_key,
        data=data_stream,
        length=len(data_bytes),
        content_type='application/json'
    )
    
    return object_key

def get_json_from_minio(object_key: str) -> dict:    
    response = client.get_object(bucket_name, object_key)
    data = response.read().decode('utf-8')
    response.close()
    response.release_conn()
    
    return json.loads(data)

def update_json_in_minio(object_key: str, data: dict) -> str:
    json_str = json.dumps(data, ensure_ascii=False)
    data_bytes = json_str.encode('utf-8')
    data_stream = io.BytesIO(data_bytes)
    
    client.put_object(
        bucket_name=bucket_name,
        object_name=object_key,
        data=data_stream,
        length=len(data_bytes),
        content_type='application/json'
    )
    
    return object_key

def delete_json_from_minio(object_key: str) -> bool:
    try:
        client.remove_object(bucket_name, object_key)
        return True
    except Exception as e:
        print(f"Ошибка при удалении объекта {object_key}: {e}")
        return False