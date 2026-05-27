# astrbot_plugin_char_mixer

让你的 AstrBot 角色拥有「拍照」能力 —— 基于 gpt-image-2 的二次元角色自拍 & 合影插件。

角色可以像真人一样随手自拍、和用户合影，二次元角色自然融入真实世界背景。

## 效果

- 🤳 **角色自拍** —— 角色在真实场景中拍照，保持二次元画风不写实化
- 📸 **合影/入镜** —— 用户发一张照片，角色出现在照片里，和用户合影或融入场景
- 🎭 **姿势表情自然** —— 比心、歪头、吐舌头、wink，不是呆板站姿
- 🌆 **真实背景** —— 涩谷街头、教室走廊、海边夕阳，有地点感和时间感

## 安装

1. 下载本仓库 zip 或 clone 到 AstrBot 插件目录：
   ```
   {AstrBot数据目录}/data/plugins/astrbot_plugin_char_mixer/
   ```
2. 重启 AstrBot

## 配置

在 AstrBot 管理面板中配置插件参数：

| 参数 | 说明 | 示例 |
|------|------|------|
| `openai_api_key` | OpenAI API Key（或兼容服务的 Key） | `sk-xxx` |
| `openai_base_url` | API 地址（填到 /v1） | `https://api.openai.com/v1` |
| `image_model` | 图片模型 | `gpt-image-2` |
| `image_quality` | 图片质量 | `high` |
| `char_reference_path` | 角色三视图 PNG 的本地绝对路径 | `C:\Users\xxx\char_reference.png` |

## 工作原理

插件注册了两个 LLM Tool：

- **`generate_character_selfie`** —— 角色自拍。LLM 根据对话上下文自主决定场景、服装、姿势和横竖屏方向。
- **`generate_photo_with_user`** —— 合影/入镜。用户发送照片后，LLM 决定如何将角色放入画面。

调用流程：
1. LLM 判断当前对话适合拍照 → 调用 tool 并传入场景/服装/构图描述
2. 插件立即返回，后台异步调用 gpt-image-2 `/images/edits` 端点
3. 图片生成完成后自动发送到对话中

由于 gpt-image-2 生成耗时较长（约 2-3 分钟），插件使用 `asyncio.create_task` 后台执行，不阻塞 AstrBot 的 tool 超时机制。

## 系统提示词配置

为了让角色自然地使用拍照能力，建议在 AstrBot 的系统提示词中加入相关引导。参考 [prompt_guide.md](./prompt_guide.md)（如有需要可单独提供）。

核心原则：
- 角色不暴露任何技术细节，表现得像真人拍照
- 可以主动发自拍，不需要用户请求
- 姿势表情青春活力，背景参照真实地点

## 要求

- AstrBot v4.25+
- Python 依赖：`openai>=1.30.0`、`aiohttp>=3.8.0`
- 支持 gpt-image-2 `/images/edits` 端点的 API 服务

## 注意事项

- 三视图建议使用高清 PNG，包含角色正面/侧面/背面，白色背景
- 单次生成费用约 $0.08-0.19（取决于分辨率和质量设置）
- 生成耗时约 2-3 分钟，期间 bot 可正常对话
- 最大输出分辨率 1536px（竖屏 1024×1536，横屏 1536×1024）

## License

MIT
