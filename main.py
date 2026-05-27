import os
import base64
import asyncio

import aiohttp

from astrbot.api.star import Context, Star
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult, MessageChain
from astrbot.api import logger
import astrbot.api.message_components as Comp
from astrbot.api import AstrBotConfig


# 分辨率映射
SIZE_MAP = {
    "portrait": "1024x1536",
    "landscape": "1536x1024",
}

# 固定 prompt 模板 —— 自拍模式
SELFIE_PROMPT_TEMPLATE = """根据角色三视图生成一张二次元角色自拍照。角色保持明显二次元绘画风格，保留原角色五官、发型、发色、服装、配饰和身体比例，不要写实化角色。

画面是角色{scene_desc}。背景使用真实世界环境，真实手机自拍视角，半身构图，角色靠近镜头，轻微广角透视，表情自然放松，像随手自拍。真实背景与二次元角色自然融合，光照方向一致，角色边缘干净，不要变成3D，不要真人化，不要改变角色设计，高清，生活感，真实背景，anime character in real photo background.

服装要求：{outfit_desc}"""

# 固定 prompt 模板 —— 合影/入镜模式
PHOTO_TOGETHER_PROMPT_TEMPLATE = """根据角色三视图和用户提供的照片，生成一张图片。角色保持明显二次元绘画风格，保留原角色五官、发型、发色、配饰和身体比例，不要写实化角色。照片中如有真人，保持原样不变。

画面：{scene_desc}。{composition_desc}。真实手机自拍视角，半身构图，角色靠近镜头，轻微广角透视，表情自然放松，像合拍。真实背景与二次元角色自然融合，光照方向一致，角色边缘干净，不要变成3D，不要真人化，不要改变角色设计，如有真人不要改变真人外貌，高清，生活感，真实背景，anime character in real photo background.

服装要求：{outfit_desc}"""


class CharMixerPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.config = config or {}

    async def initialize(self):
        logger.info("CharMixer plugin initialized.")
        logger.info(f"CharMixer config: char_reference_path={self.config.get('char_reference_path', '未设置')}")

    def _get_config(self):
        return {
            "openai_api_key": self.config.get("openai_api_key", ""),
            "openai_base_url": str(self.config.get("openai_base_url", "")).rstrip("/") or "https://api.openai.com/v1",
            "image_model": self.config.get("image_model", "gpt-image-2"),
            "image_quality": self.config.get("image_quality", "high"),
            "char_reference_path": self.config.get("char_reference_path", ""),
        }

    def _load_char_reference(self) -> bytes | None:
        """加载本地三视图文件"""
        cfg = self._get_config()
        path = cfg["char_reference_path"]
        if not path:
            logger.error("CharMixer: 三视图路径未配置")
            return None
        if not os.path.isfile(path):
            logger.error(f"CharMixer: 三视图文件不存在: {path}")
            return None
        with open(path, "rb") as f:
            return f.read()

    async def _call_image_edit(self, images: list[bytes], prompt: str, orientation: str) -> bytes | None:
        """调用 /v1/images/edits，多图 multipart 发送，返回生成图片 bytes"""
        cfg = self._get_config()
        api_key = cfg["openai_api_key"]
        base_url = cfg["openai_base_url"]

        if not api_key:
            logger.error("CharMixer: OpenAI API Key 未配置")
            return None

        size = SIZE_MAP.get(orientation, "1024x1536")
        url = f"{base_url}/images/edits"

        form = aiohttp.FormData()
        form.add_field("model", cfg["image_model"])
        form.add_field("prompt", prompt)
        form.add_field("size", size)
        form.add_field("quality", cfg["image_quality"])
        form.add_field("response_format", "b64_json")
        form.add_field("n", "1")

        for i, img_bytes in enumerate(images):
            form.add_field(
                "image[]",
                img_bytes,
                filename=f"image_{i}.png",
                content_type="image/png",
            )

        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, data=form, headers=headers,
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("data") and data["data"][0].get("b64_json"):
                            return base64.b64decode(data["data"][0]["b64_json"])
                    else:
                        error_text = await resp.text()
                        logger.error(f"CharMixer API error {resp.status}: {error_text}")
        except Exception as e:
            import traceback
            logger.error(f"CharMixer API call failed: {e}\n{traceback.format_exc()}")

        return None

    async def _do_generate_and_send(self, umo: str, images: list[bytes], prompt: str, orientation: str):
        """执行图片生成并通过主动消息发送"""
        try:
            image_bytes = await self._call_image_edit(images, prompt, orientation)
            if image_bytes:
                chain = MessageChain(chain=[Comp.Image.fromBytes(image_bytes)])
                await self.context.send_message(umo, chain)
            else:
                chain = MessageChain(chain=[Comp.Plain("图片生成失败了，API 调用出错 😢")])
                await self.context.send_message(umo, chain)
        except Exception as e:
            logger.error(f"CharMixer generate error: {e}")
            try:
                chain = MessageChain(chain=[Comp.Plain(f"图片生成出错了：{str(e)}")])
                await self.context.send_message(umo, chain)
            except Exception:
                pass

    @filter.llm_tool(name="generate_character_selfie")
    async def generate_selfie(self, event: AstrMessageEvent,
                              scene_description: str,
                              outfit_description: str,
                              orientation: str = "portrait") -> MessageEventResult:
        """生成二次元角色的自拍照片。当用户想要角色的自拍、照片、或者角色主动想发自拍时调用。

        Args:
            scene_description(string): 场景和动作描述，例如"半夜睡意惺忪躺在床上"、"在咖啡厅喝咖啡"、"教室里上课"
            outfit_description(string): 服装描述，例如"淡粉色睡衣"、"白色校服"、"黑色卫衣"
            orientation(string): 画面方向。portrait=竖屏（站立、坐着、半身自拍），landscape=横屏（躺着、风景宽画面）
        """
        char_data = self._load_char_reference()
        if not char_data:
            yield event.plain_result("角色三视图文件未找到，无法拍照")
            return

        cfg = self._get_config()
        if not cfg["openai_api_key"]:
            yield event.plain_result("API Key 未配置，无法拍照")
            return

        prompt = SELFIE_PROMPT_TEMPLATE.format(
            scene_desc=scene_description,
            outfit_desc=outfit_description,
        )

        umo = event.unified_msg_origin
        # 启动后台任务（不阻塞 tool 返回）
        asyncio.get_event_loop().create_task(
            self._do_generate_and_send(umo, [char_data], prompt, orientation)
        )
        yield event.plain_result("正在拍照，稍后发送~")

    @filter.llm_tool(name="generate_photo_with_user")
    async def generate_photo_together(self, event: AstrMessageEvent,
                                      scene_description: str,
                                      outfit_description: str,
                                      composition_description: str = "两人并排站立，自拍视角",
                                      orientation: str = "portrait") -> MessageEventResult:
        """将角色放入用户发送的照片中。适用场景：1.用户想和角色合影 2.用户发风景或场景照想让角色出现在里面 3.用户给角色拍照。需要用户在消息中附带了照片。

        Args:
            scene_description(string): 描述画面内容，例如"角色站在樱花树下"、"角色和用户在咖啡厅合影"、"角色坐在公园长椅上"
            outfit_description(string): 角色的服装描述，例如"白色校服"、"休闲装"
            composition_description(string): 构图描述，例如"角色站在画面中央"、"两人并排自拍"、"角色从身后抱住用户"
            orientation(string): 画面方向。portrait=竖屏（站立、半身），landscape=横屏（风景、并排、躺着）
        """
        char_data = self._load_char_reference()
        if not char_data:
            yield event.plain_result("角色三视图文件未找到，无法拍照")
            return

        cfg = self._get_config()
        if not cfg["openai_api_key"]:
            yield event.plain_result("API Key 未配置，无法拍照")
            return

        user_photo = await self._extract_user_image(event)
        if not user_photo:
            yield event.plain_result("没有找到你发的照片，先发一张照片再试试？")
            return

        prompt = PHOTO_TOGETHER_PROMPT_TEMPLATE.format(
            scene_desc=scene_description,
            outfit_desc=outfit_description,
            composition_desc=composition_description,
        )

        umo = event.unified_msg_origin
        # 启动后台任务（不阻塞 tool 返回）
        asyncio.get_event_loop().create_task(
            self._do_generate_and_send(umo, [char_data, user_photo], prompt, orientation)
        )
        yield event.plain_result("正在拍照，稍后发送~")

    async def _extract_user_image(self, event: AstrMessageEvent) -> bytes | None:
        """从消息中提取用户发送的图片"""
        message_chain = event.message_obj.message
        for seg in message_chain:
            if isinstance(seg, Comp.Image):
                url = seg.url or seg.file or ""
                if url:
                    return await self._fetch_image_bytes(url)
        return None

    async def _fetch_image_bytes(self, url: str) -> bytes | None:
        """下载图片返回 bytes"""
        try:
            if url.startswith("file:///"):
                path = url[8:]
                if os.path.isfile(path):
                    with open(path, "rb") as f:
                        return f.read()
            elif os.path.isfile(url):
                with open(url, "rb") as f:
                    return f.read()

            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 200:
                        return await resp.read()
        except Exception as e:
            logger.error(f"CharMixer fetch image error: {e}")
        return None

    async def terminate(self):
        """插件卸载时调用"""
        logger.info("CharMixer plugin terminated.")
