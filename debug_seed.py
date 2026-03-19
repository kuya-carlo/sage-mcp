import asyncio
import sys
sys.path.insert(0, '.')

from sage.services.etl.gaffa import search_and_extract_cmo

async def test():
    try:
        result = await search_and_extract_cmo(
            "BS Computer Engineering", "BSCPE"
        )
        print(f"Records found: {len(result)}")
        if result:
            print(f"First record: {result[0]}")
        else:
            print("No records returned")
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

asyncio.run(test())
