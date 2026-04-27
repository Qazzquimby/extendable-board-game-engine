

python scripts\generate_schema.py

cd front
json2ts -i ../scripts/schema.json -o src\types.ts
