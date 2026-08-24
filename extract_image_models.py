import json


def extract_image_models():
    with open('openrouter_models.json', encoding='utf-8') as f:
        data = json.load(f)

    image_models = []
    for model in data.get('data', []):
        output_modalities = model.get('architecture', {}).get('output_modalities', [])
        if 'image' in output_modalities:
            image_models.append({
                'id': model['id'],
                'name': model['name'],
                'description': model.get('description', '')[:100] + '...'
            })

    for m in image_models:
        print(f"ID: {m['id']}")
        print(f"Name: {m['name']}")
        print(f"Desc: {m['description']}")
        print("-" * 40)

if __name__ == "__main__":
    extract_image_models()
