"""讲一条随机的动物冷知识。"""
import random

RUN_SPEC = {
    "name": "random_animal_fact",
    "description": "随机讲一条简短、令人意外的动物冷知识。无需参数。",
    "args_schema": {"type": "object", "properties": {}, "required": []},
}

FACTS = [
    ("章鱼", "章鱼有三颗心脏,其中两颗在游泳时会停跳,所以它更喜欢爬行而不是游泳。"),
    ("袋熊", "袋熊是已知唯一会拉立方体粪便的动物,这要归功于它们肠道异常的弹性。"),
    ("枪虾", "枪虾的钳子合拢速度极快,产生的气泡瞬间能达到接近太阳表面的温度。"),
    ("树懒", "树懒消化非常慢,处理一片树叶有时要花上一个月。"),
    ("螳螂虾", "螳螂虾的眼睛里有十六种色觉感受器,而人类只有三种。"),
    ("水熊虫", "水熊虫能在太空真空、沸水、接近绝对零度的环境下存活。"),
    ("六角恐龙(蝾螈)", "墨西哥钝口螈不仅能长回四肢,连心脏和大脑的一部分也能再生,且不留疤痕。"),
    ("鸭嘴兽", "雄性鸭嘴兽后腿上有毒刺,是极少数有毒的哺乳动物之一。"),
    ("蜂鸟", "蜂鸟飞行时心率可超过每分钟 1200 次。"),
    ("乌贼", "乌贼是色盲,但它们能呈现动物界最绚丽的色彩变化。"),
    ("裸鼹鼠", "裸鼹鼠几乎对癌症免疫,缺氧情况下可以存活长达 18 分钟。"),
    ("鸽子", "鸽子能在镜子里认出自己,还能区分莫奈和毕加索的画作。"),
    ("海獭", "海獭睡觉时会拉着同伴的手,以免在水面上漂散开。"),
    ("乌鸦", "乌鸦能记住特定人脸数年之久,并对欺负过它的人长期怀恨在心。"),
    ("眼镜猴", "眼镜猴的每只眼睛都比它的大脑还大,是哺乳动物里眼身比例最大的。"),
]


async def run(**kwargs):
    animal, fact = random.choice(FACTS)
    return {
        "speak": fact,
        "render": f"**{animal}**: {fact}",
    }


if __name__ == "__main__":
    import asyncio
    r = asyncio.run(run())
    assert isinstance(r, dict) and "speak" in r and "render" in r
    assert isinstance(r["speak"], str) and len(r["speak"]) > 0
    assert isinstance(r["render"], str) and len(r["render"]) > 0
    print("OK")
