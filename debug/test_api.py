import asyncio

import httpx

BASE = "http://127.0.0.1:8000"

async def test():
    async with httpx.AsyncClient() as c:

        # 1. Health
        r = await c.get(f"{BASE}/health")
        print(f"[health] {r.status_code} {r.json()}")

        # 2. Auth cookie
        r = await c.get(f"{BASE}/auth/notion",
                        follow_redirects=False)
        print(f"[auth] {r.status_code} body: {r.text[:200]}")
        cookies = dict(r.cookies)
        print(f"[auth] cookies: {cookies}")

        # 3. Commons programs (no auth)
        r = await c.get(f"{BASE}/commons/programs")
        print(f"[programs] {r.status_code} {r.text[:200]}")

        # 4. Commons tree
        r = await c.get(
            f"{BASE}/commons/tree",
            params={"program_code": "BSCPE",
                    "year_level": 1, "semester": 1},
            cookies=cookies
        )
        print(f"[commons/tree] {r.status_code} {r.text[:200]}")

        # 5. MCP tools list
        r = await c.get(f"{BASE}/mcp/tools")
        print(f"[mcp/tools] {r.status_code} {r.text[:200]}")

        # 6. MCP chat
        if not cookies:
            print("[mcp/chat] SKIPPED — no auth cookie")
            return

        r = await c.post(
            f"{BASE}/mcp/chat",
            json={"message": "I'm a 2nd year BS CpE student"},
            cookies=cookies,
            timeout=120.0
        )
        print(f"[mcp/chat] {r.status_code} {r.text[:300]}")

if __name__ == "__main__":
    asyncio.run(test())
