import asyncio
import asyncpg

async def test():
    conn = await asyncpg.connect(
        host='127.0.0.1',
        port=5432,
        user='repuser',
        database='reputation_db',
        ssl=False
    )
    result = await conn.fetchval('SELECT 1')
    print('Connected! Result:', result)
    await conn.close()

asyncio.run(test())