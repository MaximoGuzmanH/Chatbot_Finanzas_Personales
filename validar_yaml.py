import yaml

ruta_archivo = "data/nlu.yml"  # o la ruta donde está tu archivo

try:
    with open(ruta_archivo, "r", encoding="utf-8") as f:
        yaml.safe_load(f)
    print("✅ El archivo YAML es válido.")
except yaml.YAMLError as e:
    print("❌ Error de formato YAML:")
    print(e)
