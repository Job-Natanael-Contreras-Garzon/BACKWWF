import asyncio
import asyncpg

async def check_schema():
    conn = await asyncpg.connect("postgresql://avnadmin:AVNS_zOJVLKeGTsRv-AwnrlP@pg-df37a89-contrerasjob123-fc4e.l.aivencloud.com:18981/defaultdb?sslmode=require")
    
    rows = await conn.fetch("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'users';
    """)
    
    print("Columnas en la tabla 'users':")
    for row in rows:
        print(f"- {row['column_name']}: {row['data_type']}")
        
    await conn.close()

asyncio.run(check_schema())
