from nonebot import get_driver, on_command, get_bot
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message, MessageSegment
from nonebot.params import CommandArg
from nonebot.plugin import PluginMetadata
from nonebot.log import logger
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Dict, Optional, Tuple
import aiohttp
import asyncio

# 获取配置中的昵称
driver = get_driver()
nickname = list(driver.config.nickname)[0] if driver.config.nickname else "生日提醒"

# 插件元数据
__plugin_meta__ = PluginMetadata(
    name="birthday",
    description="生日提醒插件",
    usage=f"""添加生日: /添加生日 [QQ号] [月] [日] 或 @群友 添加生日 [月] [日]
修改生日: /修改生日 [QQ号] [月] [日] 或 @群友 修改生日 [月] [日]
查看列表: /生日列表
删除记录: /删除生日 [QQ号] 或 @群友 删除生日""",
    extra={"version": "1.2.0"},
)

# 全局配置
TZ = timezone(timedelta(hours=8))  # 强制东八区
DATA_PATH = Path("data/birthday")
DATA_PATH.mkdir(parents=True, exist_ok=True)

# 日期验证
def is_valid_date(month: int, day: int) -> bool:
    """验证日期是否合法（基于东八区）"""
    if month < 1 or month > 12:
        return False
    month_days = {
        1: 31, 2: 29, 3: 31, 4: 30, 5: 31, 6: 30,
        7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31
    }
    return 1 <= day <= month_days.get(month, 31)

# 头像缓存系统
class AvatarCache:
    _cache: Dict[int, Tuple[bytes, float]] = {}
    CACHE_TIME = 3600  # 1小时缓存
    CDN_URLS = [
        "https://q.qlogo.cn/headimg_dl?dst_uin={}&spec=640",
        "https://thirdqq.qlogo.cn/headimg_dl?dst_uin={}&spec=640",
        "https://q1.qlogo.cn/g?b=qq&nk={}&s=640"
    ]

    @classmethod
    async def get_avatar(cls, user_id: int) -> Optional[bytes]:
        """获取头像（带三重CDN和缓存）"""
        # 检查缓存
        if user_id in cls._cache:
            data, timestamp = cls._cache[user_id]
            if datetime.now(TZ).timestamp() - timestamp < cls.CACHE_TIME:
                logger.debug(f"使用缓存头像: {user_id}")
                return data

        # 三重CDN尝试
        async with aiohttp.ClientSession(
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=aiohttp.ClientTimeout(total=10)
        ) as session:
            for url_template in cls.CDN_URLS:
                try:
                    url = url_template.format(user_id)
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            data = await resp.read()
                            if len(data) > 1024:  # 有效图片验证
                                cls._cache[user_id] = (data, datetime.now(TZ).timestamp())
                                logger.info(f"下载头像成功: {user_id}")
                                return data
                except Exception as e:
                    logger.warning(f"头像下载失败 [{url}]: {e}")

        logger.error(f"所有CDN尝试失败: {user_id}")
        return None

# 数据存储
def get_group_data(group_id: int) -> Path:
    return DATA_PATH / f"group_{group_id}.json"

def load_birthdays(group_id: int) -> Dict[str, str]:
    try:
        with open(get_group_data(group_id), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"加载生日数据失败: {e}")
        return {}

def save_birthdays(group_id: int, data: Dict[str, str]):
    try:
        with open(get_group_data(group_id), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存生日数据失败: {e}")

# 核心功能
async def get_member_nickname(group_id: int, user_id: int) -> str:
    """获取群成员昵称（带错误处理）"""
    try:
        bot = get_bot()
        info = await bot.get_group_member_info(
            group_id=group_id,
            user_id=user_id,
            no_cache=True
        )
        return info.get("card") or info.get("nickname") or str(user_id)
    except Exception as e:
        logger.warning(f"获取昵称失败: {e}")
        return str(user_id)

async def parse_at_qq(event: GroupMessageEvent) -> Optional[int]:
    """从@消息中解析QQ号"""
    for seg in event.message:
        if seg.type == "at":
            return int(seg.data["qq"])
    return None

async def parse_date_args(args: Message) -> Optional[Tuple[int, int]]:
    """解析日期参数"""
    arg_text = args.extract_plain_text().strip()
    parts = arg_text.split()
    if len(parts) >= 2:
        try:
            month = int(parts[0])
            day = int(parts[1])
            if is_valid_date(month, day):
                return month, day
        except ValueError:
            pass
    return None

async def send_birthday_notice(group_id: int, user_id: int, date_str: str):
    """发送生日祝福（带缓存优化）"""
    for attempt in range(3):
        try:
            nickname = await get_member_nickname(group_id, user_id)
            avatar_data = await AvatarCache.get_avatar(user_id)
            
            # 构建消息
            msg = Message()
            msg.append(MessageSegment.at(user_id))
            msg.append(MessageSegment.text(f" （{user_id}）生日快乐！🎉\n"))
            
            if avatar_data:
                try:
                    msg.append(MessageSegment.image(avatar_data))
                except Exception as e:
                    logger.error(f"构建图片消息失败: {e}")
                    msg.append(MessageSegment.text("\n[头像加载失败]"))
            else:
                msg.append(MessageSegment.text("\n[无法加载头像]"))
            
            msg.append(MessageSegment.text(f"\n今天是你的生日({date_str})，祝你天天开心！"))
            
            await get_bot().send_group_msg(
                group_id=group_id,
                message=msg
            )
            
            # 发送成功消息到群聊和日志
            success_msg = f"🎂 生日祝福发送成功: {nickname}({user_id})"
            await get_bot().send_group_msg(group_id=group_id, message=success_msg)
            logger.success(f"生日祝福发送成功: 群{group_id} -> {user_id}")
            return True
            
        except Exception as e:
            error_msg = f"⚠️ 生日祝福发送失败(尝试{attempt+1}/3): {str(e)}"
            logger.error(f"发送失败(尝试{attempt+1}/3): {e}")
            await asyncio.sleep(2)
    
    # 最终失败消息
    final_error = f"❌ 生日祝福发送彻底失败: {nickname}({user_id})"
    await get_bot().send_group_msg(group_id=group_id, message=final_error)
    logger.critical(f"消息发送彻底失败: 群{group_id} -> {user_id}")
    return False

async def build_avatar_message(user_id: int, text: str) -> Message:
    """构建带头像的消息"""
    avatar_data = await AvatarCache.get_avatar(user_id)
    msg = Message()
    
    if avatar_data:
        try:
            msg.append(MessageSegment.image(avatar_data))
        except Exception as e:
            logger.error(f"构建图片消息失败: {e}")
            msg.append(MessageSegment.text("[头像加载失败]\n"))
    else:
        msg.append(MessageSegment.text("[无法加载头像]\n"))
    
    msg.append(MessageSegment.text(text))
    return msg

# 定时任务
async def birthday_scheduler():
    """定时检查生日任务"""
    while True:
        now = datetime.now(TZ)
        next_run = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        await asyncio.sleep((next_run - now).total_seconds())
        
        # 双重时间验证
        if datetime.now(TZ).hour != 0:
            continue
            
        today = datetime.now(TZ).strftime("%m-%d")
        logger.info(f"开始每日生日检查: {today}")
        
        for file in DATA_PATH.glob("group_*.json"):
            try:
                group_id = int(file.stem.split("_")[1])
                birthdays = load_birthdays(group_id)
                for uid, date in birthdays.items():
                    if date == today:
                        await send_birthday_notice(
                            group_id=group_id,
                            user_id=int(uid),
                            date_str=date
                        )
            except Exception as e:
                logger.error(f"定时任务异常: {e}")

# 命令处理
add_cmd = on_command("添加生日", aliases={"设置生日"}, priority=10)
mod_cmd = on_command("修改生日", priority=10)
list_cmd = on_command("生日列表", priority=10)
del_cmd = on_command("删除生日", priority=10)

@add_cmd.handle()
async def handle_add(event: GroupMessageEvent, args: Message = CommandArg()):
    # 尝试从@消息获取QQ号
    at_qq = await parse_at_qq(event)
    
    if at_qq:
        # @群友: /添加生日 @群友 月 日
        date_args = await parse_date_args(args)
        if not date_args:
            await add_cmd.finish("日期格式不正确，请使用：月 日（例如：5 20）")
        
        month, day = date_args
        qq = str(at_qq)
    else:
        # 默认: /添加生日 QQ号 月 日
        args = args.extract_plain_text().strip().split()
        if len(args) != 3:
            await add_cmd.finish("格式: /添加生日 QQ号 月 日 或 @群友 添加生日 月 日\n例: /添加生日 123456 5 20 或 @群友 添加生日 5 20")

        qq, month, day = args[0], int(args[1]), int(args[2])
        if not is_valid_date(month, day):
            await add_cmd.finish(f"无效日期: {month}月{day}日不存在")

    date_str = f"{month:02d}-{day:02d}"
    is_today = date_str == datetime.now(TZ).strftime("%m-%d")
    
    data = load_birthdays(event.group_id)
    if qq in data:
        nickname = await get_member_nickname(event.group_id, int(qq))
        msg = await build_avatar_message(int(qq), f"⚠️ {nickname}({qq}) 已有记录: {data[qq]}")
        await add_cmd.finish(msg)

    data[qq] = date_str
    save_birthdays(event.group_id, data)
    
    nickname = await get_member_nickname(event.group_id, int(qq))
    msg = await build_avatar_message(int(qq), f"✅ 已记录 {nickname}({qq}) 的生日: {date_str}")
    await add_cmd.send(msg)
    
    if is_today:
        await asyncio.sleep(1)
        await send_birthday_notice(event.group_id, int(qq), date_str)

@mod_cmd.handle()
async def handle_mod(event: GroupMessageEvent, args: Message = CommandArg()):
    # 尝试从@消息获取QQ号
    at_qq = await parse_at_qq(event)
    
    if at_qq:
        # @群友: /修改生日 @群友 月 日
        date_args = await parse_date_args(args)
        if not date_args:
            await mod_cmd.finish("日期格式不正确，请使用：月 日（例如：5 20）")
        
        month, day = date_args
        qq = str(at_qq)
    else:
        # 默认: /修改生日 QQ号 月 日
        args = args.extract_plain_text().strip().split()
        if len(args) != 3:
            await mod_cmd.finish("格式: /修改生日 QQ号 月 日 或 @群友 修改生日 月 日\n例: /修改生日 123456 5 20 或 @群友 修改生日 5 20")

        qq, month, day = args[0], int(args[1]), int(args[2])
        if not is_valid_date(month, day):
            await mod_cmd.finish(f"无效日期: {month}月{day}日不存在")

    date_str = f"{month:02d}-{day:02d}"
    is_today = date_str == datetime.now(TZ).strftime("%m-%d")
    
    data = load_birthdays(event.group_id)
    if qq not in data:
        nickname = await get_member_nickname(event.group_id, int(qq))
        msg = await build_avatar_message(int(qq), f"⚠️ {nickname}({qq}) 没有生日记录，请先添加")
        await mod_cmd.finish(msg)

    old_date = data[qq]
    data[qq] = date_str
    save_birthdays(event.group_id, data)
    
    nickname = await get_member_nickname(event.group_id, int(qq))
    # 修改后的消息格式
    msg = await build_avatar_message(
        int(qq),
        f"✅ 已修改 {nickname}({qq}) 的生日:\n"
        f"📅 {old_date}(old) → {date_str}(new)"
    )
    await mod_cmd.send(msg)
    
    if is_today:
        await asyncio.sleep(1)
        await send_birthday_notice(event.group_id, int(qq), date_str)


@del_cmd.handle()
async def handle_del(event: GroupMessageEvent, args: Message = CommandArg()):
    # 尝试从@消息获取QQ号
    at_qq = await parse_at_qq(event)
    
    if at_qq:
        # @群友: /删除生日 @群友
        qq = str(at_qq)
    else:
        # 默认: /删除生日 QQ号
        qq = args.extract_plain_text().strip()
        if not qq.isdigit():
            await del_cmd.finish("请输入正确的QQ号")

    data = load_birthdays(event.group_id)
    if qq not in data:
        msg = await build_avatar_message(int(qq), f"未找到QQ号 {qq} 的生日记录")
        await del_cmd.finish(msg)

    nickname = await get_member_nickname(event.group_id, int(qq))
    del data[qq]
    save_birthdays(event.group_id, data)
    msg = await build_avatar_message(int(qq), f"✅ 已删除 {nickname}({qq}) 的生日记录")
    await del_cmd.send(msg)

@list_cmd.handle()
async def handle_list(event: GroupMessageEvent):
    data = load_birthdays(event.group_id)
    
    if not data:
        await list_cmd.finish(f"当前群聊({event.group_id})没有记录任何生日信息")

    # 按日期排序
    sorted_birthdays = sorted(data.items(), key=lambda x: x[1])
    total_records = len(sorted_birthdays)
    
    try:
        bot = get_bot()
        # 分段处理，每100条一个合并转发
        chunks = [sorted_birthdays[i:i+100] for i in range(0, len(sorted_birthdays), 100)]
        total_pages = len(chunks)
        
        for chunk_index, chunk in enumerate(chunks):
            forward_msgs = []
            
            # 构建更详细的标题消息
            title_content = Message(
                f"🎂 本群({event.group_id})生日列表\n"
                f"📊 共 {total_records} 条记录\n"
                f"📑 第 {chunk_index+1}/{total_pages} 页（每页最多100条记录）"
            )
            
            title_msg = {
                "type": "node",
                "data": {
                    "name": nickname,  # 使用配置的昵称
                    "uin": bot.self_id,
                    "content": title_content
                }
            }
            forward_msgs.append(title_msg)
            
            # 添加每条生日记录
            for qq, date in chunk:
                try:
                    member_nickname = await get_member_nickname(event.group_id, int(qq))
                    content = Message(f"📅 {date}\n🎂 {member_nickname}({qq})")
                    
                    user_msg = {
                        "type": "node",
                        "data": {
                            "name": member_nickname,
                            "uin": qq,
                            "content": content
                        }
                    }
                    forward_msgs.append(user_msg)
                except Exception as e:
                    continue
            
            # 发送合并转发
            await bot.send_group_forward_msg(
                group_id=event.group_id,
                messages=forward_msgs
            )
            
            # 如果有多段，发送间隔1秒避免刷屏
            if total_pages > 1 and chunk_index < total_pages-1:
                await asyncio.sleep(1)
                
    except Exception as e:
        logger.error(f"发送生日列表失败: {e}")
        await list_cmd.finish("发送生日列表失败，请稍后再试")




# 启动系统 
@driver.on_startup
async def startup():
    asyncio.create_task(birthday_scheduler())
    logger.success("生日插件已启动")

